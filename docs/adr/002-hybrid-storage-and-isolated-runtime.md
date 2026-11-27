# ADR-002: Hybrid Storage (MinIO/S3) and Isolated Spark + Iceberg + dbt Runtime

- **Status:** Accepted
- **Date:** 2026-11-27 (Updated from DuckDB baseline)

## Context
To build an enterprise-grade Medallion Data Lakehouse (`Bronze`, `Silver`, `Gold`) with zero cloud infrastructure cost ($0 USD) during local development and CI/CD, we need a stack that mirrors production cloud behavior (**AWS S3 + AWS Glue / PySpark + Apache Iceberg + Snowflake**). Running `dbt-core` and `pyspark` directly inside the Apache Airflow Python environment frequently triggers dependency conflicts (`pydantic`, `protobuf`, `urllib3`), and Spark requires OpenJDK 17 plus Iceberg/Hadoop-AWS JARs on its classpath.

## Options Considered
- **Local Filesystem (`file://`) + Shared Airflow Environment:** Simplest setup, but hides S3A authentication/path issues until cloud deployment and risks breaking Airflow due to dependency collisions.
- **DuckDB Local + Snowflake Cloud:** Fast and lightweight locally, but introduces SQL/engine divergence when targeting PySpark/AWS Glue for large-scale distributed Bronze-to-Silver processing.
- **Dedicated Spark Master/Worker Cluster in Docker:** Closer to a standalone cluster, but adds unnecessary RAM overhead and network/Thrift complexity alongside Airflow 3, PostgreSQL, and MinIO.
- **MinIO (`s3a://`) + Isolated `uv` Runtime (PySpark 3.5 `local[*]` + Iceberg + dbt-spark / dbt-snowflake) (Selected):** Lightweight S3-compatible object storage paired with an isolated virtual environment inside the Airflow image containing OpenJDK 17, PySpark 3.5, pre-cached Iceberg/Hadoop-AWS JARs, `dbt-spark[session]`, and `dbt-snowflake`.

## Decision
1. **S3 Parity via MinIO (`pgsty/silo`):** Use **MinIO** in Docker as our local S3-compatible storage layer, automatically provisioning `afinamx-bronze`, `afinamx-silver`, and `afinamx-gold` buckets via an idempotent initialization container (`minio-init`).
2. **Isolated Spark + dbt Runtime:** Build a custom Airflow Docker image (`docker/Dockerfile.airflow`) with **OpenJDK 17**, `uv`, and an isolated virtual environment at `/opt/airflow/dbt_venv` containing `pyspark==3.5.10`, `dbt-core==1.12.7`, `dbt-spark[session]==1.11.1`, and `dbt-snowflake==1.12.5`. Airflow tasks invoke `/opt/airflow/dbt_venv/bin/python` or `/opt/airflow/dbt_venv/bin/dbt` via `BashOperator`.
3. **Open Table Format (Apache Iceberg) & Pre-cached JARs:** Pre-download `iceberg-spark-runtime-3.5_2.12-1.8.1.jar`, `hadoop-aws-3.3.4.jar`, and `aws-java-sdk-bundle-1.12.262.jar` into `${SPARK_HOME}/jars` at image build time for deterministic, offline-capable `s3a://` + Iceberg execution.
4. **Medallion Engine Split:**
   - **Bronze → Silver:** PySpark (`local[*]` locally, **AWS Glue** in cloud) reading/writing **Apache Iceberg** tables on MinIO/S3.
   - **Silver → Gold:** `dbt-spark` (`method: session`) locally at $0 USD, and `dbt-snowflake` targeting **Snowflake** in production.
5. **Dual-Endpoint Resolution:** Configure `AWS_ENDPOINT_URL=http://localhost:9000` in `.env` for host-level CLI execution while overriding it to `http://minio:9000` inside `docker-compose.yml` for inter-container networking.

## Consequences
- **Positive:**
  - Enforces real `s3a://` URIs, Iceberg ACID semantics, and PySpark/Glue parity from day one at $0 USD local cost.
  - Decouples `pyspark` and `dbt` upgrades from Apache Airflow 3 core dependencies.
  - Pre-cached JARs eliminate Maven download latency and flakiness during DAG runs.
- **Negative / Trade-offs:**
  - Larger Airflow Docker image due to OpenJDK 17, PySpark 3.5, and Iceberg/AWS JARs.
  - Requires allocating at least 6–8 GB of RAM to Docker to run Airflow 3, PostgreSQL, MinIO, and local Spark sessions smoothly.
