FROM golang:1.26.8-bookworm AS builder
WORKDIR /src
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ ./
RUN CGO_ENABLED=0 go build -trimpath -o /fastread ./cmd/fastread

FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates poppler-utils curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /fastread /usr/local/bin/fastread
ENV FASTREAD_WEB_ROOT=/var/lib/fastread/web FASTREAD_DATA_ROOT=/var/lib/fastread/config
VOLUME /var/lib/fastread
ENTRYPOINT ["/usr/local/bin/fastread"]
CMD ["serve", "--listen", "0.0.0.0:8483"]
