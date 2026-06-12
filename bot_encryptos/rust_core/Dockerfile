FROM rust:1.88-slim-bookworm AS builder

RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV CARGO_BUILD_JOBS=2
ENV RUSTFLAGS="-C codegen-units=4"

WORKDIR /app
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main(){}" > src/main.rs \
    && cargo build --release --jobs 2 \
    && rm -rf src

COPY src ./src
RUN touch src/main.rs && cargo build --release --jobs 2

# ---- Runtime ----
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/target/release/rust_core .

EXPOSE 8001
CMD ["./rust_core"]
