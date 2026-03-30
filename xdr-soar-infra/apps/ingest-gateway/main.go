package main

import (
	"context"
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

type serverConfig struct {
	port                  string
	schemaVersion         string
	kafkaBootstrapServers string
	kafkaTopic            string
	ingestPath            string
}

type ingestEvent map[string]interface{}

type metrics struct {
	accepted uint64
	rejected uint64
}

var appMetrics metrics

func main() {
	cfg := serverConfig{
		port:                  getEnv("PORT", "8082"),
		schemaVersion:         getEnv("SCHEMA_VERSION", "1.0.0"),
		kafkaBootstrapServers: getEnv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
		kafkaTopic:            getEnv("KAFKA_TOPIC", "telemetry.raw"),
		ingestPath:            getEnv("EVENT_INGEST_PATH", "/ingest"),
	}

	writer := newKafkaWriter(cfg)
	if writer != nil {
		defer writer.Close()
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler(cfg))
	mux.HandleFunc("/metrics", metricsHandler)
	mux.HandleFunc(cfg.ingestPath, ingestHandler(cfg, writer))

	log.Printf("ingest-gateway listening on :%s", cfg.port)
	if err := http.ListenAndServe(":"+cfg.port, mux); err != nil {
		log.Fatalf("listen failed: %v", err)
	}
}

func newKafkaWriter(cfg serverConfig) *kafka.Writer {
	if strings.TrimSpace(cfg.kafkaBootstrapServers) == "" {
		return nil
	}
	brokers := splitAndTrim(cfg.kafkaBootstrapServers)
	if len(brokers) == 0 {
		return nil
	}
	return &kafka.Writer{
		Addr:                   kafka.TCP(brokers...),
		Topic:                  cfg.kafkaTopic,
		Balancer:               &kafka.LeastBytes{},
		AllowAutoTopicCreation: false,
		RequiredAcks:           kafka.RequireOne,
	}
}

func healthHandler(cfg serverConfig) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]interface{}{
			"status":         "ok",
			"service":        "ingest-gateway",
			"schema_version": cfg.schemaVersion,
			"ingest_path":    cfg.ingestPath,
			"configured_backends": map[string]interface{}{
				"kafka_bootstrap_servers": cfg.kafkaBootstrapServers,
				"kafka_topic":             cfg.kafkaTopic,
			},
			"time": time.Now().Unix(),
		})
	}
}

func metricsHandler(w http.ResponseWriter, r *http.Request) {
	body := strings.Join([]string{
		"# HELP ingest_gateway_accepted_events_total Number of accepted ingest events.",
		"# TYPE ingest_gateway_accepted_events_total counter",
		"ingest_gateway_accepted_events_total " + uintToString(atomic.LoadUint64(&appMetrics.accepted)),
		"# HELP ingest_gateway_rejected_events_total Number of rejected ingest events.",
		"# TYPE ingest_gateway_rejected_events_total counter",
		"ingest_gateway_rejected_events_total " + uintToString(atomic.LoadUint64(&appMetrics.rejected)),
		"",
	}, "\n")
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(body))
}

func ingestHandler(cfg serverConfig, writer *kafka.Writer) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}

		var payload ingestEvent
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			atomic.AddUint64(&appMetrics.rejected, 1)
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
			return
		}

		event := normalizeEvent(r, payload, cfg.schemaVersion)
		validationErrors := validateEvent(event)
		if len(validationErrors) > 0 {
			atomic.AddUint64(&appMetrics.rejected, 1)
			writeJSON(w, http.StatusBadRequest, map[string]interface{}{
				"error":    "invalid event",
				"details":  validationErrors,
				"event_id": event["event_id"],
			})
			return
		}

		routingKey := buildRoutingKey(asString(event["tenant_id"]), asString(event["device_id"]), asString(event["layer"]), asString(event["category"]))
		body, err := json.Marshal(event)
		if err != nil {
			atomic.AddUint64(&appMetrics.rejected, 1)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "marshal failed"})
			return
		}

		published := false
		if writer != nil {
			err = writer.WriteMessages(context.Background(), kafka.Message{
				Key:   []byte(routingKey),
				Value: body,
				Time:  time.Now().UTC(),
				Headers: []kafka.Header{
					{Key: "tenant_id", Value: []byte(asString(event["tenant_id"]))},
					{Key: "device_id", Value: []byte(asString(event["device_id"]))},
					{Key: "correlation_id", Value: []byte(asString(event["correlation_id"]))},
					{Key: "schema_version", Value: []byte(asString(event["schema_version"]))},
				},
			})
			if err != nil {
				log.Printf("kafka publish failed: %v", err)
			} else {
				published = true
			}
		}

		if !published {
			atomic.AddUint64(&appMetrics.rejected, 1)
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "no transport backend available"})
			return
		}

		atomic.AddUint64(&appMetrics.accepted, 1)
		writeJSON(w, http.StatusAccepted, map[string]interface{}{
			"status":      "accepted",
			"service":     "ingest-gateway",
			"event_id":    event["event_id"],
			"routing_key": routingKey,
			"received_at": event["received_at"],
			"kafka_topic": cfg.kafkaTopic,
		})
	}
}

func normalizeEvent(r *http.Request, payload ingestEvent, schemaVersion string) ingestEvent {
	event := make(ingestEvent, len(payload)+8)
	for k, v := range payload {
		event[k] = v
	}

	if blank(event["tenant_id"]) {
		event["tenant_id"] = r.Header.Get("X-Tenant-ID")
	}
	if blank(event["device_id"]) {
		event["device_id"] = r.Header.Get("X-Device-ID")
	}
	if blank(event["agent_id"]) {
		event["agent_id"] = r.Header.Get("X-Agent-ID")
	}
	if blank(event["source"]) {
		event["source"] = "ingest_gateway"
	}
	if blank(event["layer"]) {
		event["layer"] = "network"
	}
	if blank(event["category"]) {
		event["category"] = "network"
	}
	if blank(event["severity"]) {
		event["severity"] = "medium"
	}
	if _, ok := event["payload"].(map[string]interface{}); !ok {
		event["payload"] = map[string]interface{}{}
	}
	if blank(event["event_id"]) {
		event["event_id"] = time.Now().UTC().Format("20060102T150405.000000000Z07:00")
	}
	if blank(event["timestamp"]) {
		event["timestamp"] = time.Now().UTC().Format(time.RFC3339)
	}
	event["received_at"] = time.Now().UTC().Format(time.RFC3339)
	event["schema_version"] = schemaVersion
	if _, ok := event["correlation_id"]; !ok {
		event["correlation_id"] = ""
	}
	if v, ok := event["severity"].(string); ok {
		event["severity"] = strings.ToLower(v)
	}
	return event
}

func validateEvent(event ingestEvent) []string {
	var errs []string
	required := []string{"tenant_id", "device_id", "agent_id", "source", "layer", "category", "severity", "timestamp", "payload"}
	for _, field := range required {
		if blank(event[field]) {
			errs = append(errs, "missing "+field)
		}
	}
	if _, ok := event["payload"].(map[string]interface{}); !ok {
		errs = append(errs, "payload must be an object")
	}
	if severity := asString(event["severity"]); severity != "" {
		switch severity {
		case "low", "medium", "high", "critical":
		default:
			errs = append(errs, "invalid severity")
		}
	}
	if v, ok := event["risk_score"]; ok && !blank(v) {
		switch score := v.(type) {
		case float64:
			if score < 0 || score > 100 {
				errs = append(errs, "risk_score out of range")
			}
		case int:
			if score < 0 || score > 100 {
				errs = append(errs, "risk_score out of range")
			}
		default:
			errs = append(errs, "risk_score must be numeric")
		}
	}
	return errs
}

func buildRoutingKey(tenantID, deviceID, layer, category string) string {
	if tenantID == "" {
		tenantID = "*"
	}
	if deviceID == "" {
		deviceID = "*"
	}
	if layer == "" {
		layer = "*"
	}
	if category == "" {
		category = "*"
	}
	return "events." + tenantID + "." + deviceID + "." + layer + "." + category
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

func uintToString(v uint64) string {
	return strconv.FormatUint(v, 10)
}
