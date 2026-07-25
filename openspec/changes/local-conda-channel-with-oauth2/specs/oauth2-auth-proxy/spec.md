# Spec: OAuth2 Auth Proxy (Flask)

## Capability

A Flask application packaged as `auth_proxy` that acts as a JWT-validating auth layer and OAuth2 Device Flow relay between Caddy and the upstream IdP.

## Requirements

### Package Structure

```
src/
└── auth_proxy/
    ├── __init__.py
    ├── app.py        # application factory + route registration
    └── config.py     # env var loading, validation, JWKS cache
```

The package is installed inside the pixi Python environment.

### Configuration (`config.py`)

Loads and exposes the following from environment (via `python-dotenv`):

| Variable | Required | Description |
|---|---|---|
| `IDP_BASE_URL` | yes | Base URL of upstream IdP |
| `IDP_JWKS_URI` | yes | Full JWKS endpoint URL |
| `IDP_DEVICE_AUTH_ENDPOINT` | yes | Device authorization endpoint URL |
| `IDP_TOKEN_ENDPOINT` | yes | Token endpoint URL |
| `IDP_AUDIENCE` | yes | Expected `aud` claim |
| `IDP_ISSUER` | yes | Expected `iss` claim |
| `IDP_CLIENT_ID` | yes | Embedded in `WWW-Authenticate` responses |

Application fails to start with a clear error if any required variable is missing.

### Routes

#### `GET /auth-check`

Called by Caddy `forward_auth` on every channel request.

- Extracts `Authorization: Bearer <token>` header
- If missing or not Bearer: returns `401` with `WWW-Authenticate` header
- Validates JWT:
  - Verifies signature against cached JWKS
  - Validates `exp`, `iss`, `aud` claims
  - If `kid` is unknown: re-fetches JWKS and retries once (key rotation)
- Returns `200` on success
- Returns `401` with `WWW-Authenticate` header on any failure

`WWW-Authenticate` header format:
```
Bearer realm="repo.thath.local",
       device_authorization_endpoint="https://repo.thath.local:8443/oauth/device",
       client_id="<IDP_CLIENT_ID>"
```

#### `POST /oauth/device`

Relay for Device Flow initiation.

- Forwards the full request body to `$IDP_DEVICE_AUTH_ENDPOINT`
- Returns the IdP response body and status code verbatim
- On IdP unreachable: returns `502` with JSON error body

#### `POST /oauth/token`

Relay for Device Flow token polling and exchange.

- Forwards the full request body to `$IDP_TOKEN_ENDPOINT`
- Returns the IdP response body and status code verbatim
- On IdP unreachable: returns `502` with JSON error body

#### `GET /.well-known/openid-configuration` (optional)

Proxies to `$IDP_BASE_URL/.well-known/openid-configuration` if accessible. Returns `502` if IdP is unreachable.

### JWT Validation Behavior

- JWKS is fetched from `$IDP_JWKS_URI` on first request (lazy) and cached in memory
- Cache is refreshed when a token presents an unknown `kid`
- Uses `authlib.jose` for all JWT operations
- Tokens with `exp` in the past are rejected with `401`
- Tokens with wrong `iss` or `aud` are rejected with `401`

### Error Responses

All `401` responses include:
- `WWW-Authenticate` header (as above)
- JSON body: `{"error": "unauthorized", "detail": "<reason>"}`

All `502` responses include:
- JSON body: `{"error": "upstream_unavailable", "detail": "<reason>"}`

### Runtime

- Listens on `0.0.0.0:5000` (HTTP, not HTTPS — TLS is Caddy's job)
- Does NOT serve channel files
- Loads `.env` from the project root on startup
