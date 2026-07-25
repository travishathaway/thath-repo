# Spec: Pixi Project Setup

## Capability

Bootstrap and manage the entire local conda channel stack via a single pixi project using `pyproject.toml` format.

## Requirements

### Project Format

- Uses `pyproject.toml` as the single project file (no `pixi.toml`)
- The Python package `auth_proxy` is defined under `[project]` and installable by pixi
- `[build-system]` uses `hatchling`
- Python `>=3.11` required

### Pixi Dependencies

All tools and Python libraries are declared under `[tool.pixi.dependencies]`:

| Dependency | Purpose |
|---|---|
| `caddy` | Reverse proxy + TLS termination |
| `mkcert` | Local CA + certificate generation |
| `rattler-build` | Build conda packages from recipes |
| `python` `>=3.11` | Runtime for Flask app |
| `flask` | Auth proxy web server |
| `authlib` | JWT validation + OAuth2 client utilities |
| `python-dotenv` | `.env` file loading |
| `requests` | HTTP relay to upstream IdP |
| `hatchling` | Python package build backend |

Channels: `conda-forge` only.
Platforms: `linux-64`, `osx-arm64`.

### Pixi Tasks

| Task | Command / Behavior |
|---|---|
| `setup-tls` | `mkdir -p certs && mkcert -install && mkcert -cert-file certs/repo.thath.local.pem -key-file certs/repo.thath.local-key.pem repo.thath.local` |
| `build-channel` | `rattler-build build recipes/greet/recipe.yaml --output-dir channel && rattler-build build recipes/timeutils/recipe.yaml --output-dir channel` |
| `serve-flask` | `flask --app auth_proxy.app run --port 5000` |
| `serve-caddy` | `caddy run --config Caddyfile` |
| `serve` | `depends-on: [serve-flask, serve-caddy]` (both start concurrently) |
| `dev` | `depends-on: [setup-tls, build-channel, serve]` |

### Gitignore

The following must be in `.gitignore`:
- `channel/` — rattler-build output
- `certs/` — mkcert-generated certificates
- `.env` — real environment variable values

### Environment Template

`.env.example` is checked in and contains all required variable names with placeholder values and comments. `.env` is gitignored.

## Constraints

- `setup-tls` is idempotent; running it again does not break an existing cert
- `pixi run dev` should be the single command to get everything running after initial hosts file setup
- The `auth_proxy` package must be importable inside the pixi environment (installed as editable or via pixi's Python environment)
