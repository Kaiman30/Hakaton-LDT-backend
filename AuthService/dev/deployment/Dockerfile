FROM golang:1.26.2-alpine AS builder
WORKDIR /src

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY . .
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /app/auth ./cmd/auth

FROM alpine:3
WORKDIR /app
COPY --from=builder /app/auth /app/auth

EXPOSE 8080
CMD ["/app/auth"]