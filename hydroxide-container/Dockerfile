# Multi-stage build for hydroxide with auth patch
FROM golang:1.24-alpine AS builder

# Hydroxide version - pin to known-good commit, override with --build-arg HYDROXIDE_VERSION=master
ARG HYDROXIDE_VERSION=759f6d1

# Install build dependencies
RUN apk add --no-cache git

# Clone and build hydroxide at specified version
WORKDIR /build
RUN git clone https://github.com/emersion/hydroxide.git . && \
    git checkout ${HYDROXIDE_VERSION}

# Copy our patch file
COPY askpass-patch.go /tmp/askpass-patch.go

# Apply patch: Remove original askPass function then append our version
RUN sed -i '/^func askPass/,/^}/d' cmd/hydroxide/main.go && \
    cat /tmp/askpass-patch.go >> cmd/hydroxide/main.go && \
    grep -q '"bufio"' cmd/hydroxide/main.go || sed -i '/"fmt"/a\\t"bufio"' cmd/hydroxide/main.go

RUN go mod download
RUN go build -o hydroxide ./cmd/hydroxide

# Final stage
FROM alpine:3.18

# Install runtime dependencies
RUN apk add --no-cache ca-certificates bash

# Create non-root user
RUN addgroup -g 1000 hydroxide && \
    adduser -D -u 1000 -G hydroxide hydroxide

# Copy hydroxide binary
COPY --from=builder /build/hydroxide /usr/local/bin/hydroxide
RUN chmod +x /usr/local/bin/hydroxide

# Copy entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Create auth and bridge-password directories
RUN mkdir -p /home/hydroxide/.config/hydroxide /bridge-password && \
    chown -R hydroxide:hydroxide /home/hydroxide /bridge-password

# Switch to non-root user
USER hydroxide
WORKDIR /home/hydroxide

# Expose IMAP port
EXPOSE 1143

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["serve"]