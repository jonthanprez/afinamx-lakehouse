# ADR-002: Hybrid Storage (MinIO/S3) and Isolated Transformation Runtime

- **Status:** Accepted
- **Date:** 2026-11-18

## Context
To build an enterprise-grade Medallion Data Lakehouse (`Bronze`, `Silver`, `Gold`) with zero cloud infrastructure cost ($0 USD) during development and CI/CD, we need a local stack that mirrors production cloud behavior (AWS S3 + Snowflake + Orchestrator). Additionally, running `dbt-core` directly inside the Apache Airflow Python environment frequently triggers dependency conflicts (`pydantic`, `protobuf`, `urllib3`), and local `DuckDB` requires single-writer discipline to avoid file-lock collisions.

## Options Considered
- **Local Filesystem (`file://`) + Shared Airflow/dbt Environment:** Simplest setup, but hides S3 authentication/path issues until cloud deployment and risks breaking Airflow due to dependency collisions.
- **LocalStack:** Full AWS emulator, discarded because it consumes heavier system resources when we only require S3-compatible object storage locally.
- **MinIO + Isolated `uv` Virtual Environment in Docker (Selected):** Lightweight, production-grade S3-compatible object storage paired with an isolated `dbt` virtual environment inside the Airflow image.

## Decision
1. **S3 Parity via MinIO:** Use **MinIO** in Docker as our local S3-compatible storage layer, automatically provisioning `afinamx-bronze`, `afinamx-silver`, and `afinamx-gold` buckets via an idempotent initialization container (`minio-init`).
2. **Isolated `dbt` Runtime:** Build a custom Airflow Docker image (`docker/Dockerfile.airflow`) that installs `uv` and provisions an isolated virtual environment at `/opt/airflow/dbt_venv` containing `dbt-core` and `dbt-duckdb`. Airflow tasks invoke `/opt/airflow/dbt_venv/bin/dbt` directly via `BashOperator`.
3. **DuckDB Concurrency Control:** Because DuckDB is an in-process database allowing only a single concurrent writer, Airflow will execute `dbt build` as an atomic sequential step (or via a 1-slot Airflow Pool) when targeting `local_lake/afinamx.duckdb`.
4. **Dual-Endpoint Resolution:** Configure `AWS_ENDPOINT_URL=http://localhost:9000` in `.env` for host-level CLI execution while overriding it to `http://minio:9000` inside `docker-compose.yml` for inter-container networking.

## Consequences
- **Positive:**
  - Enforces real `s3://` URIs, credentials, and bucket policies from day one at $0 cost.
  - Decouples `dbt` and `DuckDB` upgrades from Apache Airflow core dependencies.
  - Prevents database lock errors during orchestrated local runs.
- **Negative / Trade-offs:**
  - Requires allocating at least 6 GB of RAM to Docker Desktop to run Airflow, PostgreSQL, and MinIO smoothly.
  - Slightly longer initial image build time (`docker compose build`), mitigated by `uv` caching.