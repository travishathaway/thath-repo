# Design: Local Conda Channel with OAuth2 Authentication

## System Overview

```
                      repo.thath.local:8443 (HTTPS)
                      ┌──────────────────────────────────┐
                      │             Caddy                │
                      │                                  │
  GET /channel/*  ───▶│  forward_auth http://localhost:5000/auth-check
                      │                │                 │
                      │                ▼                 │
                      │  200 → serve channel files       │
                      │  401 → return 401 + WWW-Auth     │
                      └───────────────┬──────────────────┘
                                      │ (internal HTTP)
                                      ▼
                      ┌──────────────────────────────────┐
                      │      Flask auth proxy :5000      │
                      │      (auth_proxy package)        │
                      │                                  │
                      │  GET  /auth-check                │
                      │  POST /oauth/device              │
                      │  POST /oauth/token               │
                      │  GET  /.well-known/openid-config │
                      └───────────────┬──────────────────┘
                                      │ JWT validation
                                      │ (JWKS fetch + cache)
                                      ▼
                      ┌──────────────────────────────────┐
                      │     Upstream IdP (external)      │
                      │     URL: $IDP_BASE_URL           │
                      │                                  │
                      │  GET  $IDP_JWKS_URI              │
                      │  POST $IDP_DEVICE_AUTH_ENDPOINT  │
                      │  POST $IDP_TOKEN_ENDPOINT        │
                      └──────────────────────────────────┘
```

## Repository Layout

```
repo-root/
├── pyproject.toml              # pixi project + Python package
├── Caddyfile                   # Caddy configuration
├── .env.example                # environment variable template (checked in)
├── .env                        # real values (gitignored)
├── .gitignore
├── src/
│   └── auth_proxy/
│       ├── __init__.py
│       ├── app.py              # Flask application factory + routes
│       └── config.py           # env var loading + validation
├── recipes/
│   ├── greet/
│   │   └── recipe.yaml         # noarch pure-python package
│   └── timeutils/
│       └── recipe.yaml         # noarch pure-python package
├── channel/                    # gitignored — rattler-build output
│   ├── linux-64/
│   ├── osx-arm64/
│   └── noarch/
└── certs/                      # gitignored — mkcert output
    ├── repo.thath.local.pem
    └── repo.thath.local-key.pem
```

## pyproject.toml Structure

```toml
[project]
name = "auth-proxy"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["flask", "authlib", "python-dotenv", "requests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pixi.project]
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64"]

[tool.pixi.dependencies]
python = ">=3.11"
caddy = "*"
mkcert = "*"
rattler-build = "*"
flask = "*"
authlib = "*"
python-dotenv = "*"
requests = "*"
hatchling = "*"

[tool.pixi.tasks]
setup-tls     = "mkdir -p certs && mkcert -install && mkcert -cert-file certs/repo.thath.local.pem -key-file certs/repo.thath.local-key.pem repo.thath.local"
build-channel = "rattler-build build recipes/greet/recipe.yaml --output-dir channel && rattler-build build recipes/timeutils/recipe.yaml --output-dir channel"
serve-flask   = "flask --app auth_proxy.app run --port 5000"
serve-caddy   = "caddy run --config Caddyfile"
serve         = { depends-on = ["serve-flask", "serve-caddy"] }
dev           = { depends-on = ["setup-tls", "build-channel", "serve"] }
```

> Note: `serve-flask` and `serve-caddy` run concurrently. Pixi runs `depends-on` tasks that are not sequential in parallel; tasks in `serve` will both start.

## Caddy Configuration

```
{
    auto_https off
}

repo.thath.local:8443 {
    tls /path/to/certs/repo.thath.local.pem /path/to/certs/repo.thath.local-key.pem

    # OAuth2 endpoints — pass through to Flask
    handle /oauth/* {
        reverse_proxy localhost:5000
    }

    handle /.well-known/* {
        reverse_proxy localhost:5000
    }

    # Protected conda channel
    handle /channel/* {
        forward_auth localhost:5000 {
            uri /auth-check
            copy_headers Authorization
        }
        file_server {
            root {$CHANNEL_DIR:./channel}
        }
    }
}
```

Key points:
- `auto_https off` — we're supplying our own mkcert certificate
- `forward_auth` calls Flask `/auth-check` before serving any channel file
- On 401 from Flask, Caddy returns 401 with the `WWW-Authenticate` header Flask set
- `/oauth/*` and `/.well-known/*` routes are unauthenticated pass-throughs to Flask

## Flask Auth Proxy

### `/auth-check` (called by Caddy forward_auth)

```
Request has Authorization: Bearer <token>?
  YES → validate JWT (signature, expiry, aud, iss)
          OK  → 200 (Caddy proceeds to serve file)
          BAD → 401 + WWW-Authenticate header
  NO  → 401 + WWW-Authenticate header
```

WWW-Authenticate header format:
```
WWW-Authenticate: Bearer realm="repo.thath.local",
                  device_authorization_endpoint="https://repo.thath.local:8443/oauth/device",
                  client_id="<IDP_CLIENT_ID>"
```

### `/oauth/device` (Device Flow initiation)

Relays POST to `$IDP_DEVICE_AUTH_ENDPOINT`. Returns the IdP response body verbatim (contains `device_code`, `user_code`, `verification_uri`, `interval`).

### `/oauth/token` (Device Flow polling)

Relays POST to `$IDP_TOKEN_ENDPOINT`. Returns IdP response. The `conda-auth` plugin polls this until it gets an `access_token`.

### JWT Validation

Uses `authlib.jose.JsonWebToken`. On startup:
1. Fetch JWKS from `$IDP_JWKS_URI`
2. Cache key set in memory
3. On each `/auth-check`: decode + verify signature, `exp`, `iss`, `aud`

JWKS is refreshed if a token presents an unknown `kid` (key rotation support).

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `IDP_BASE_URL` | Base URL of upstream IdP | `https://auth.example.local` |
| `IDP_JWKS_URI` | Full URL to JWKS endpoint | `https://auth.example.local/.well-known/jwks.json` |
| `IDP_DEVICE_AUTH_ENDPOINT` | Device authorization endpoint | `https://auth.example.local/oauth/device_authorization` |
| `IDP_TOKEN_ENDPOINT` | Token endpoint | `https://auth.example.local/oauth/token` |
| `IDP_AUDIENCE` | Expected `aud` claim in JWT | `conda-channel` |
| `IDP_ISSUER` | Expected `iss` claim in JWT | `https://auth.example.local` |
| `IDP_CLIENT_ID` | Client ID (embedded in WWW-Authenticate) | `conda-client` |

## Device Flow — End-to-End Sequence

```
conda-auth plugin                Flask proxy              Upstream IdP
      │                               │                        │
      │  GET /channel/noarch/...      │                        │
      │ ──────────────────────────────▶ (Caddy → /auth-check)  │
      │  401 WWW-Authenticate:Bearer  │                        │
      │ ◀──────────────────────────── │                        │
      │                               │                        │
      │  POST /oauth/device           │                        │
      │ ─────────────────────────────▶│                        │
      │                               │  POST /device_auth     │
      │                               │ ──────────────────────▶│
      │                               │  {device_code,...}     │
      │                               │ ◀──────────────────────│
      │  {user_code, verify_uri, ...} │                        │
      │ ◀─────────────────────────────│                        │
      │                               │                        │
      │  [prints: go to X, enter Y]   │                        │
      │  [user authenticates in browser]                       │
      │                               │                        │
      │  POST /oauth/token (polling)  │                        │
      │ ─────────────────────────────▶│                        │
      │                               │  POST /token           │
      │                               │ ──────────────────────▶│
      │                               │  {access_token,...}    │
      │                               │ ◀──────────────────────│
      │  {access_token}               │                        │
      │ ◀─────────────────────────────│                        │
      │                               │                        │
      │  GET /channel/noarch/... + Bearer token               │
      │ ──────────────────────────────▶ (Caddy → /auth-check)  │
      │                               │  validate JWT          │
      │                               │ ──────────────────────▶│
      │                               │  (JWKS cached)         │
      │                               │ ◀──────────────────────│
      │                               │  200                   │
      │  200 + channel file           │                        │
      │ ◀──────────────────────────── │                        │
```

## rattler-build Recipes

Both packages are `noarch: python`, no compiled components.

### `greet` recipe

```yaml
package:
  name: greet
  version: 0.1.0
source:
  path: .
build:
  noarch: python
  script: python -m pip install .
requirements:
  host: [python, pip]
  run: [python]
```

Package provides `greet.hello(name: str) -> str`.

### `timeutils` recipe

```yaml
package:
  name: timeutils
  version: 0.1.0
source:
  path: .
build:
  noarch: python
  script: python -m pip install .
requirements:
  host: [python, pip]
  run: [python]
```

Package provides `timeutils.now() -> str` (ISO 8601 current datetime).

## Security Notes

- Flask proxy runs on HTTP internally — it is only reachable via Caddy on the same machine
- mkcert CA is trusted only on the local machine via system trust store
- `.env` and `certs/` are gitignored
- Short-lived JWTs limit the blast radius of token leakage
- JWKS is fetched over HTTPS from the upstream IdP
