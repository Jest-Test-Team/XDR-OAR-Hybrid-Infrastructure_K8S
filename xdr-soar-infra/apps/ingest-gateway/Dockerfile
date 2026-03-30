FROM golang:1.25-alpine AS builder

WORKDIR /src

COPY go.mod /src/go.mod
RUN go mod download

COPY main.go /src/main.go

RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/ingest-gateway /src/main.go

FROM alpine:3.20

RUN apk --no-cache add ca-certificates

COPY --from=builder /bin/ingest-gateway /usr/local/bin/ingest-gateway

EXPOSE 8082

CMD ["ingest-gateway"]
