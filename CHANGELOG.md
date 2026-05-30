# Changelog

All notable changes to SmartNode will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases are created automatically when a `vX.Y.Z` tag is pushed to `main`.
The [release workflow](.github/workflows/release.yml) generates the changelog,
builds a multi-arch container image with semantic version tags, signs the image
with [cosign](https://github.com/sigstore/cosign) keyless signing, and attaches
an SBOM attestation.

---

## [Unreleased]

### Added
- `backend/__about__.py` — single source of truth for `__version__` so all
  modules and API responses reference the same value.
- `/api/health` now includes `version` field (from `__about__.__version__`).
- `/api/ready` shorthand route (alias of `/api/readyz`) — checks simulation
  thread liveness and returns HTTP 503 when not ready; response body now
  includes `simulation_thread_alive` and `version` fields.
- `.github/workflows/release.yml` — tag-triggered release pipeline: auto-
  generates changelog, creates GitHub Release, builds & pushes semantically-
  versioned container images, runs cosign keyless signing, and attaches SBOM.
- `observability/alert-rules.yml` — Alertmanager alert rules for simulation
  thread death (`SimulationThreadDead`) and elevated error rate
  (`SmartNodeHighErrorRate`).

---

## [1.1.0] - 2025-03-15

### Added
- Prometheus `/metrics` endpoint and OpenTelemetry tracing via `backend/metrics.py`.
- Grafana dashboard and provisioning configuration in `observability/`.
- Rate limiting (`backend/ratelimit.py`) with per-identity quota endpoints.
- Role-based access control (`backend/rbac.py`) with JWT authentication.
- Multi-architecture Docker image publishing via GitHub Actions.

### Changed
- Health check endpoint `/api/health` now returns simulation running state.
- Liveness (`/api/livez`) and readiness (`/api/readyz`) probes added.

---

## [1.0.0] - 2024-12-01

### Added
- Initial release of the SmartNode satellite relay simulation platform.
- Flask backend with constellation management and orbit simulation.
- Vue 3 frontend with Cesium 3D globe visualization.
- Docker Compose deployment with optional monitoring profile.

[Unreleased]: https://github.com/Tong89/smartNode/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Tong89/smartNode/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Tong89/smartNode/releases/tag/v1.0.0
