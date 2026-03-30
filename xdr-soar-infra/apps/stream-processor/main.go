package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/segmentio/kafka-go"
)

type config struct {
	port                  string
	sourceTopic           string
	sinkTopic             string
	schemaVersion         string
	kafkaBootstrapServers string
	kafkaGroupID          string
}

type rawEvent map[string]interface{}

type cleanedEvent struct {
	EventID         string                 `json:"event_id"`
	Seq             int64                  `json:"seq"`
	TenantID        string                 `json:"tenant_id"`
	DeviceID        string                 `json:"device_id"`
	AgentID         string                 `json:"agent_id"`
	WatchdogID      string                 `json:"watchdog_id"`
	Source          string                 `json:"source"`
	Layer           string                 `json:"layer"`
	Category        string                 `json:"category"`
	Severity        string                 `json:"severity"`
	RiskScore       float64                `json:"risk_score"`
	Payload         map[string]interface{} `json:"payload"`
	PayloadJSON     string                 `json:"payload_json"`
	WarningMetadata interface{}            `json:"warning_metadata"`
	Timestamp       string                 `json:"timestamp"`
	CategoryHash    string                 `json:"category_hash"`
	RiskLevel       string                 `json:"risk_level"`
	CleanedAt       string                 `json:"cleaned_at"`
	SchemaVersion   string                 `json:"schema_version"`
}

type schemaQAResult struct {
	EventID         string    `json:"event_id"`
	MissingFields   []string  `json:"missing_fields"`
	MissingRate     float64   `json:"missing_rate"`
	TimeDriftSec    float64   `json:"time_drift_sec"`
	TimeDriftExceed bool      `json:"time_drift_exceed"`
	SourceOK        bool      `json:"source_ok"`
	LayerOK         bool      `json:"layer_ok"`
	QualityScore    float64   `json:"quality_score"`
	QualityTier     string    `json:"quality_tier"`
	IngestTime      time.Time `json:"ingest_time"`
}

type appMetrics struct {
	consumed   uint64
	normalized uint64
	failed     uint64
}

var metrics appMetrics

var allowedSources = map[string]bool{
	"watchdog": true, "agent": true, "sensor": true, "ingest_gateway": true,
	"yara": true, "integration": true, "manual": true,
}

var allowedLayers = map[string]bool{
	"kernel": true, "user": true, "network": true, "process": true,
	"file": true, "identity": true, "cloud": true,
}

var requiredFields = []string{
	"event_id", "tenant_id", "device_id", "agent_id", "source",
	"layer", "category", "severity", "risk_score", "timestamp", "payload",
}

func main() {
	cfg := config{
		port:                  getEnv("PORT", "8094"),
		sourceTopic:           getEnv("SOURCE_TOPIC", "telemetry.normalized"),
		sinkTopic:             getEnv("SINK_TOPIC", "telemetry.enriched"),
		schemaVersion:         getEnv("SCHEMA_VERSION", "1.0.0"),
		kafkaBootstrapServers: getEnv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
		kafkaGroupID:          getEnv("KAFKA_GROUP_ID", "stream-processor"),
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	reader, writer := newKafkaClients(cfg)
	if reader != nil && writer != nil {
		go runProcessor(ctx, reader, writer, cfg)
	} else {
		log.Printf("stream-processor started without active Kafka client configuration")
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler(cfg, reader != nil && writer != nil))
	mux.HandleFunc("/metrics", metricsHandler)
	mux.HandleFunc("/normalize", normalizeHandler(cfg))

	log.Printf("stream-processor listening on :%s", cfg.port)
	if err := http.ListenAndServe(":"+cfg.port, mux); err != nil {
		log.Fatalf("listen failed: %v", err)
	}
}

func newKafkaClients(cfg config) (*kafka.Reader, *kafka.Writer) {
	brokers := splitAndTrim(cfg.kafkaBootstrapServers)
	if len(brokers) == 0 {
		return nil, nil
	}

	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers:  brokers,
		Topic:    cfg.sourceTopic,
		GroupID:  cfg.kafkaGroupID,
		MinBytes: 1,
		MaxBytes: 10e6,
	})

	writer := &kafka.Writer{
		Addr:                   kafka.TCP(brokers...),
		Topic:                  cfg.sinkTopic,
		Balancer:               &kafka.LeastBytes{},
		AllowAutoTopicCreation: false,
		RequiredAcks:           kafka.RequireOne,
	}

	return reader, writer
}

func runProcessor(ctx context.Context, reader *kafka.Reader, writer *kafka.Writer, cfg config) {
	defer reader.Close()
	defer writer.Close()

	for {
		msg, err := reader.FetchMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			atomic.AddUint64(&metrics.failed, 1)
			log.Printf("stream-processor fetch failed: %v", err)
			time.Sleep(2 * time.Second)
			continue
		}

		atomic.AddUint64(&metrics.consumed, 1)

		var raw rawEvent
		if err := json.Unmarshal(msg.Value, &raw); err != nil {
			atomic.AddUint64(&metrics.failed, 1)
			log.Printf("stream-processor unmarshal failed: %v", err)
			_ = reader.CommitMessages(ctx, msg)
			continue
		}

		cleaned := normalizeEvent(raw, cfg.schemaVersion)
		qa := schemaQA(raw, cleaned)
		payload, err := json.Marshal(map[string]interface{}{
			"event":        cleaned,
			"schema_qa":    qa,
			"source_topic": cfg.sourceTopic,
			"sink_topic":   cfg.sinkTopic,
		})
		if err != nil {
			atomic.AddUint64(&metrics.failed, 1)
			log.Printf("stream-processor marshal failed: %v", err)
			_ = reader.CommitMessages(ctx, msg)
			continue
		}

		err = writer.WriteMessages(ctx, kafka.Message{
			Key:   []byte(cleaned.EventID),
			Value: payload,
			Time:  time.Now().UTC(),
			Headers: []kafka.Header{
				{Key: "tenant_id", Value: []byte(cleaned.TenantID)},
				{Key: "device_id", Value: []byte(cleaned.DeviceID)},
				{Key: "schema_version", Value: []byte(cleaned.SchemaVersion)},
				{Key: "risk_level", Value: []byte(cleaned.RiskLevel)},
			},
		})
		if err != nil {
			atomic.AddUint64(&metrics.failed, 1)
			log.Printf("stream-processor publish failed: %v", err)
			continue
		}

		atomic.AddUint64(&metrics.normalized, 1)
		if err := reader.CommitMessages(ctx, msg); err != nil {
			atomic.AddUint64(&metrics.failed, 1)
			log.Printf("stream-processor commit failed: %v", err)
		}
	}
}

func healthHandler(cfg config, kafkaReady bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]interface{}{
			"status":         "ok",
			"service":        "stream-processor",
			"source_topic":   cfg.sourceTopic,
			"sink_topic":     cfg.sinkTopic,
			"schema_version": cfg.schemaVersion,
			"configured_backends": map[string]interface{}{
				"kafka_bootstrap_servers": cfg.kafkaBootstrapServers,
				"kafka_group_id":          cfg.kafkaGroupID,
				"kafka_ready":             kafkaReady,
			},
			"time": time.Now().Unix(),
		})
	}
}

func metricsHandler(w http.ResponseWriter, r *http.Request) {
	body := strings.Join([]string{
		"# HELP stream_processor_consumed_events_total Number of consumed events.",
		"# TYPE stream_processor_consumed_events_total counter",
		"stream_processor_consumed_events_total " + strconv.FormatUint(atomic.LoadUint64(&metrics.consumed), 10),
		"# HELP stream_processor_normalized_events_total Number of normalized events published.",
		"# TYPE stream_processor_normalized_events_total counter",
		"stream_processor_normalized_events_total " + strconv.FormatUint(atomic.LoadUint64(&metrics.normalized), 10),
		"# HELP stream_processor_failed_events_total Number of failed processing attempts.",
		"# TYPE stream_processor_failed_events_total counter",
		"stream_processor_failed_events_total " + strconv.FormatUint(atomic.LoadUint64(&metrics.failed), 10),
		"",
	}, "\n")
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(body))
}

func normalizeHandler(cfg config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}

		var raw rawEvent
		if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
			return
		}

		cleaned := normalizeEvent(raw, cfg.schemaVersion)
		writeJSON(w, http.StatusOK, map[string]interface{}{
			"status":       "normalized",
			"source_topic": cfg.sourceTopic,
			"sink_topic":   cfg.sinkTopic,
			"event":        cleaned,
			"schema_qa":    schemaQA(raw, cleaned),
		})
	}
}

func normalizeEvent(raw rawEvent, schemaVersion string) cleanedEvent {
	eventTime := parseTime(raw["timestamp"])
	payload, _ := raw["payload"].(map[string]interface{})
	if payload == nil {
		payload = map[string]interface{}{}
	}

	cleaned := cleanedEvent{
		EventID:         asString(raw["event_id"]),
		Seq:             parseInt64(raw["seq"]),
		TenantID:        asString(raw["tenant_id"]),
		DeviceID:        asString(raw["device_id"]),
		AgentID:         asString(raw["agent_id"]),
		WatchdogID:      asString(raw["watchdog_id"]),
		Source:          asString(raw["source"]),
		Layer:           asString(raw["layer"]),
		Category:        asString(raw["category"]),
		Severity:        asString(raw["severity"]),
		RiskScore:       parseFloat64(raw["risk_score"]),
		Payload:         payload,
		PayloadJSON:     toJSONString(payload),
		WarningMetadata: raw["warning_metadata"],
		Timestamp:       eventTime.Format(time.RFC3339),
		CategoryHash:    hashCategory(asString(raw["category"]), asString(raw["layer"])),
		RiskLevel:       riskLevel(parseFloat64(raw["risk_score"])),
		CleanedAt:       time.Now().UTC().Format(time.RFC3339),
		SchemaVersion:   firstNonEmpty(asString(raw["schema_version"]), schemaVersion),
	}

	if cleaned.EventID == "" {
		cleaned.EventID = generateEventID(cleaned.TenantID, cleaned.DeviceID, eventTime)
	}

	return cleaned
}

func schemaQA(raw rawEvent, cleaned cleanedEvent) schemaQAResult {
	var missing []string
	for _, field := range requiredFields {
		if blank(raw[field]) {
			missing = append(missing, field)
		}
	}

	ingestTime := time.Now().UTC()
	eventTime := parseTime(cleaned.Timestamp)
	drift := ingestTime.Sub(eventTime)
	if drift < 0 {
		drift = -drift
	}

	score := 1.0
	score -= (float64(len(missing)) / float64(len(requiredFields))) * 0.5
	if drift > 5*time.Minute {
		score -= 0.2
	}
	if !allowedSources[cleaned.Source] {
		score -= 0.15
	}
	if !allowedLayers[cleaned.Layer] {
		score -= 0.15
	}
	if score < 0 {
		score = 0
	}

	tier := "low"
	if score >= 0.8 {
		tier = "high"
	} else if score >= 0.5 {
		tier = "medium"
	}

	return schemaQAResult{
		EventID:         cleaned.EventID,
		MissingFields:   missing,
		MissingRate:     float64(len(missing)) / float64(len(requiredFields)),
		TimeDriftSec:    drift.Seconds(),
		TimeDriftExceed: drift > 5*time.Minute,
		SourceOK:        allowedSources[cleaned.Source],
		LayerOK:         allowedLayers[cleaned.Layer],
		QualityScore:    score,
		QualityTier:     tier,
		IngestTime:      ingestTime,
	}
}

func parseTime(v interface{}) time.Time {
	switch x := v.(type) {
	case string:
		if x == "" {
			return time.Now().UTC()
		}
		if t, err := time.Parse(time.RFC3339, x); err == nil {
			return t.UTC()
		}
		if t, err := time.Parse(time.RFC3339Nano, x); err == nil {
			return t.UTC()
		}
		if ms, err := strconv.ParseInt(x, 10, 64); err == nil {
			return time.UnixMilli(ms).UTC()
		}
	case float64:
		return time.UnixMilli(int64(x)).UTC()
	case int64:
		return time.UnixMilli(x).UTC()
	}
	return time.Now().UTC()
}

func parseInt64(v interface{}) int64 {
	switch x := v.(type) {
	case int:
		return int64(x)
	case int64:
		return x
	case float64:
		return int64(x)
	case string:
		if n, err := strconv.ParseInt(x, 10, 64); err == nil {
			return n
		}
		if f, err := strconv.ParseFloat(x, 64); err == nil {
			return int64(f)
		}
	}
	return 0
}

func parseFloat64(v interface{}) float64 {
	switch x := v.(type) {
	case int:
		return float64(x)
	case int64:
		return float64(x)
	case float64:
		return x
	case string:
		if f, err := strconv.ParseFloat(x, 64); err == nil {
			return f
		}
	}
	return 0
}

func hashCategory(category, layer string) string {
	if strings.TrimSpace(category) == "" && strings.TrimSpace(layer) == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(category) + "|" + strings.TrimSpace(layer)))
	return hex.EncodeToString(sum[:8])
}

func riskLevel(score float64) string {
	if score >= 70 {
		return "high"
	}
	if score >= 40 {
		return "medium"
	}
	return "low"
}

func generateEventID(tenantID, deviceID string, t time.Time) string {
	if tenantID == "" {
		tenantID = "unknown"
	}
	if deviceID == "" {
		deviceID = "unknown"
	}
	return tenantID + ":" + deviceID + ":" + strconv.FormatInt(t.UnixMilli(), 10)
}

func writeJSON(w http.ResponseWriter, status int, payload interface{}) {
	body, err := json.Marshal(payload)
	if err != nil {
		http.Error(w, `{"error":"marshal failed"}`, http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(body)
}

func toJSONString(v interface{}) string {
	body, err := json.Marshal(v)
	if err != nil {
		return "{}"
	}
	return string(body)
}

func splitAndTrim(input string) []string {
	parts := strings.Split(input, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func getEnv(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return strings.Trim(value, `"'`)
}

func asString(v interface{}) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func firstNonEmpty(primary, fallback string) string {
	if strings.TrimSpace(primary) != "" {
		return primary
	}
	return fallback
}

func blank(v interface{}) bool {
	switch x := v.(type) {
	case nil:
		return true
	case string:
		return strings.TrimSpace(x) == ""
	default:
		return false
	}
}
