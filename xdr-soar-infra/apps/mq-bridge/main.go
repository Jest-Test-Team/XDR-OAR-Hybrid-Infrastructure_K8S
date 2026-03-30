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

type config struct {
	port                  string
	inputTopic            string
	outputTopic           string
	kafkaBootstrapServers string
	mqttBrokerHost        string
	mqttBrokerPort        string
}

type appMetrics struct {
	published uint64
	rejected  uint64
}

var metrics appMetrics

func main() {
	cfg := config{
		port:                  getEnv("PORT", "8093"),
		inputTopic:            getEnv("INPUT_TOPIC", "telemetry.raw"),
		outputTopic:           getEnv("OUTPUT_TOPIC", "telemetry.normalized"),
		kafkaBootstrapServers: getEnv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
		mqttBrokerHost:        getEnv("MQTT_BROKER_HOST", ""),
		mqttBrokerPort:        getEnv("MQTT_BROKER_PORT", ""),
	}

	writer := newKafkaWriter(cfg)
	if writer != nil {
		defer writer.Close()
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler(cfg, writer != nil))
	mux.HandleFunc("/metrics", metricsHandler)
	mux.HandleFunc("/publish", publishHandler(cfg, writer))

	log.Printf("mq-bridge listening on :%s", cfg.port)
	if err := http.ListenAndServe(":"+cfg.port, mux); err != nil {
		log.Fatalf("listen failed: %v", err)
	}
}

func newKafkaWriter(cfg config) *kafka.Writer {
	brokers := splitAndTrim(cfg.kafkaBootstrapServers)
	if len(brokers) == 0 {
		return nil
	}
	return &kafka.Writer{
		Addr:                   kafka.TCP(brokers...),
		Topic:                  cfg.outputTopic,
		Balancer:               &kafka.LeastBytes{},
		AllowAutoTopicCreation: false,
		RequiredAcks:           kafka.RequireOne,
	}
}

func healthHandler(cfg config, kafkaReady bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var mqttAddr interface{}
		if cfg.mqttBrokerHost != "" && cfg.mqttBrokerPort != "" {
			mqttAddr = cfg.mqttBrokerHost + ":" + cfg.mqttBrokerPort
		}
		writeJSON(w, http.StatusOK, map[string]interface{}{
			"status":       "ok",
			"service":      "mq-bridge",
			"input_topic":  cfg.inputTopic,
			"output_topic": cfg.outputTopic,
			"configured_backends": map[string]interface{}{
				"kafka_bootstrap_servers": cfg.kafkaBootstrapServers,
				"kafka_ready":             kafkaReady,
				"mqtt_broker":             mqttAddr,
			},
			"time": time.Now().Unix(),
		})
	}
}

func metricsHandler(w http.ResponseWriter, r *http.Request) {
	body := strings.Join([]string{
		"# HELP mq_bridge_published_messages_total Number of messages published to Kafka.",
		"# TYPE mq_bridge_published_messages_total counter",
		"mq_bridge_published_messages_total " + strconv.FormatUint(atomic.LoadUint64(&metrics.published), 10),
		"# HELP mq_bridge_rejected_messages_total Number of rejected bridge requests.",
		"# TYPE mq_bridge_rejected_messages_total counter",
		"mq_bridge_rejected_messages_total " + strconv.FormatUint(atomic.LoadUint64(&metrics.rejected), 10),
		"",
	}, "\n")
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(body))
}

func publishHandler(cfg config, writer *kafka.Writer) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}

		var message map[string]interface{}
		if err := json.NewDecoder(r.Body).Decode(&message); err != nil {
			atomic.AddUint64(&metrics.rejected, 1)
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
			return
		}

		if writer == nil {
			atomic.AddUint64(&metrics.rejected, 1)
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "no kafka backend available"})
			return
		}

		routingKey := buildRoutingKey(message)
		body, err := json.Marshal(message)
		if err != nil {
			atomic.AddUint64(&metrics.rejected, 1)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "marshal failed"})
			return
		}

		err = writer.WriteMessages(context.Background(), kafka.Message{
			Key:   []byte(routingKey),
			Value: body,
			Time:  time.Now().UTC(),
			Headers: []kafka.Header{
				{Key: "routing_key", Value: []byte(routingKey)},
				{Key: "tenant_id", Value: []byte(asString(message["tenant_id"]))},
				{Key: "device_id", Value: []byte(asString(message["device_id"]))},
			},
		})
		if err != nil {
			atomic.AddUint64(&metrics.rejected, 1)
			log.Printf("mq-bridge publish failed: %v", err)
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "publish failed"})
			return
		}

		atomic.AddUint64(&metrics.published, 1)
		writeJSON(w, http.StatusAccepted, map[string]interface{}{
			"status":       "bridged",
			"bridge_mode":  "http_to_kafka",
			"input_topic":  cfg.inputTopic,
			"output_topic": cfg.outputTopic,
			"routing_key":  routingKey,
		})
	}
}

func buildRoutingKey(message map[string]interface{}) string {
	tenant := fallback(asString(message["tenant_id"]), "*")
	device := fallback(asString(message["device_id"]), "*")
	layer := fallback(asString(message["layer"]), "*")
	category := fallback(asString(message["category"]), "*")
	return "events." + tenant + "." + device + "." + layer + "." + category
}

func fallback(primary, alt string) string {
	if strings.TrimSpace(primary) == "" {
		return alt
	}
	return primary
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

func asString(v interface{}) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
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
