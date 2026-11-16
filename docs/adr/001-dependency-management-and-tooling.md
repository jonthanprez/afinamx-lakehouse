# ADR-001: Deterministic Dependency Management and Quality Tooling (uv + Ruff + Mypy)

- **Status:** Accepted
- **Date:** 2026-11-16

## Context
The `afinamx-lakehouse` repository requires a standardized Python development ecosystem that guarantees deterministic builds across local environments and CI/CD pipelines (GitHub Actions)[cite: 1]. We need fast feedback loops for code formatting, static type safety, and security auditing without bloating production container images with development-only tools[cite: 1].

## Options Considered
- **Poetry / pip-tools:** Mature dependency managers, but slower at resolving complex data engineering dependency trees (e.g., `dbt`, `duckdb`, `pyarrow`) compared to Rust-based tooling[cite: 1].
- **Black + Flake8 + isort:** Traditional formatting/linting stack, discarded due to configuration fragmentation across multiple files and slower execution speeds.
- **uv + Ruff + Mypy + Bandit (Selected):** Unified, high-speed toolchain written primarily in Rust with centralized configuration inside `pyproject.toml`[cite: 1].

## Decision
1. **uv:** Adopted as the universal package manager and virtual environment tool, enforcing strict deterministic builds via `uv.lock` (`--frozen` in CI) and excluding dev tools in production builds (`--no-dev`)[cite: 1].
2. **Ruff:** Selected as the single linter and code formatter, replacing Black, Flake8, and isort[cite: 1].
3. **Mypy:** Enforced for static type checking during local development and as a strict quality gate in CI/CD pipelines[cite: 1].
4. **Bandit / pip-audit:** Integrated into the `dev` dependency group for preventive Static Application Security Testing (SAST) and dependency vulnerability scanning (SCA)[cite: 1].

## Consequences
- **Positive:**
  - Sub-second dependency resolution and linting in local development and GitHub Actions[cite: 1].
  - Single source of truth in `pyproject.toml`, keeping production containers lightweight by isolating quality tools in `[dependency-groups] dev`[cite: 1].
  - Eliminates "it works on my machine" discrepancies via `uv.lock`[cite: 1].
- **Negative / Trade-offs:**
  - Developers must strictly maintain `uv.lock` synchronized via `uv sync` whenever `pyproject.toml` is modified, otherwise CI pipelines will fail[cite: 1].
  - Requires team discipline to write explicit Python type annotations to pass Mypy checks[cite: 1].