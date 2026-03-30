FROM golang:1.25-alpine AS builder

WORKDIR /src

COPY go.mod /src/go.mod
RUN go mod download

COPY main.go /src/main.go

RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/mq-bridge /src/main.go

FROM alpine:3.20

RUN apk --no-cache add ca-certificates

COPY --from=builder /bin/mq-bridge /usr/local/bin/mq-bridge

EXPOSE 8093

CMD ["mq-bridge"]
