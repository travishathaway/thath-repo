# Dev OAuth2 Conda Channel

A local development environment for testing OAuth2-protected conda channels. It provides a realistic end-to-end stack: a conda channel served over HTTPS with JWT Bearer authentication, backed by an OAuth2 Identity Provider you manage separately.

Built specifically for developing and testing [`conda-auth`](https://github.com/conda-incubator/conda-auth) plugins, but useful for any work that requires a real OAuth2-gated conda channel locally.

## What's in the box

```
repo.thath.local:8443 (HTTPS, mkcert TLS)
        │
        ├── /channel/*     Protected conda channel (static files, JWT required)
        ├── /oauth/device  Device Flow relay → upstream IdP
        ├── /oauth/token   Token relay → upstream IdP
        └── /.well-known/  OpenID Connect discovery proxy
```

Two services run together:

| Service | Port | Role |
|---|---|---|
| **Caddy** | `8443` (HTTPS) | TLS termination, `forward_auth`, static file serving |
| **Flask auth proxy** | `5000` (HTTP, internal) | JWT validation, Device Flow relay |

The Flask proxy validates JWT Bearer tokens against your upstream IdP's JWKS endpoint. It never issues tokens — that's your IdP's job. All IdP coordinates are injected via environment variables so you can point this at any OAuth2/OIDC provider.

Two trivial example packages (`greet`, `timeutils`) are included as rattler-build recipes to populate the channel for testing.

## Prerequisites

- [pixi](https://pixi.sh) — manages all other dependencies (Caddy, mkcert, rattler-build, Python, Flask, etc.)
- A running OAuth2 IdP that issues JWTs and exposes a JWKS endpoint
- `sudo` access (for mkcert to install its local CA into the system trust store)

## Setup

### 1. Add the hostname to `/etc/hosts`

```bash
echo "127.0.0.1 repo.thath.local" | sudo tee -a /etc/hosts
```

This is the only manual step. Everything else is automated.

### 2. Install pixi

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

### 3. Install dependencies

```bash
pixi install
```

### 4. Configure IdP coordinates

```bash
cp .env.example .env
```

Edit `.env` and fill in the URLs and claims for your IdP:

```bash
IDP_BASE_URL=https://your-idp.example.com
IDP_JWKS_URI=https://your-idp.example.com/.well-known/jwks.json
IDP_DEVICE_AUTH_ENDPOINT=https://your-idp.example.com/oauth/device_authorization
IDP_TOKEN_ENDPOINT=https://your-idp.example.com/oauth/token
IDP_AUDIENCE=conda-channel
IDP_ISSUER=https://your-idp.example.com
IDP_CLIENT_ID=conda-client
```

See [Environment Variables](#environment-variables) for a full description of each variable.

### 5. Start everything

```bash
pixi run dev
```

This runs three things in order:

1. **`setup-tls`** — installs the mkcert local CA and generates a certificate for `repo.thath.local`
2. **`build-channel`** — builds the example packages into `channel/` using rattler-build
3. **`serve`** — starts Caddy and Flask concurrently

Once running, the channel is available at:

```
https://repo.thath.local:8443/channel/
```

## Tasks

| Task | Description |
|---|---|
| `pixi run dev` | Full bootstrap: TLS + channel build + serve |
| `pixi run serve` | Start Caddy and Flask (skips TLS setup and channel build) |
| `pixi run serve-flask` | Start only the Flask auth proxy on `:5000` |
| `pixi run serve-caddy` | Start only Caddy on `:8443` |
| `pixi run setup-tls` | (Re)generate mkcert CA and certificate — safe to re-run |
| `pixi run build-channel` | Build example packages into `channel/` |

## Using the channel

### With conda-auth (Device Flow)

When `conda-auth` is installed, accessing the channel without a token triggers Device Flow automatically:

```bash
conda install greet --channel https://repo.thath.local:8443/channel/
# → conda-auth detects 401 + WWW-Authenticate header
# → Prints: "Go to https://... and enter code: XXXX-XXXX"
# → Polls for token, retries on success
```

### Manual token test

```bash
# Get a token from your IdP via Device Flow or any grant
TOKEN="eyJ..."

# Test the auth proxy directly
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/auth-check
# → 200 on valid token, 401 on invalid

# Test through Caddy (full stack)
curl -H "Authorization: Bearer $TOKEN" \
  https://repo.thath.local:8443/channel/noarch/repodata.json
# → Returns repodata.json on success
```

### With pixi or micromamba

```toml
# pixi.toml or pyproject.toml
[tool.pixi.workspace]
channels = ["https://repo.thath.local:8443/channel/", "conda-forge"]
```

```bash
pixi add greet
```

## Architecture

```
conda-auth / pixi / micromamba
        │
        │  GET /channel/noarch/repodata.json
        │  (no token)
        ▼
  Caddy :8443
        │
        │  forward_auth → Flask /auth-check
        │  ← 401 + WWW-Authenticate: Bearer realm=...,
        │           device_authorization_endpoint=...,
        │           client_id=...
        │
        ▼
  conda-auth plugin
        │
        │  POST /oauth/device
        ▼
  Caddy → Flask /oauth/device → upstream IdP /device_authorization
        │  ← { device_code, user_code, verification_uri, interval }
        │
        │  [user opens browser, authenticates]
        │
        │  POST /oauth/token (polling)
        ▼
  Flask /oauth/token → upstream IdP /token
        │  ← { access_token, expires_in, ... }
        │
        │  GET /channel/noarch/repodata.json
        │  Authorization: Bearer <access_token>
        ▼
  Caddy forward_auth → Flask /auth-check
        │  validates JWT signature (JWKS), exp, iss, aud
        │  ← 200
        ▼
  Caddy file_server → channel/noarch/repodata.json
```

### JWT validation

The Flask proxy validates tokens **stateless** — it fetches the IdP's JWKS on first use, caches the key set in memory, and verifies signatures locally. No token introspection call is made per request. If a token presents an unknown `kid`, the key set is re-fetched once (supports key rotation).

Claims validated: `exp`, `iss` (must match `IDP_ISSUER`), `aud` (must match `IDP_AUDIENCE`).

## Environment Variables

All variables are required unless noted. Set them in `.env` (copy from `.env.example`).

| Variable | Description |
|---|---|
| `IDP_BASE_URL` | Base URL of your upstream IdP (used for discovery proxy) |
| `IDP_JWKS_URI` | Full URL to the JWKS endpoint — used to fetch public keys for JWT verification |
| `IDP_DEVICE_AUTH_ENDPOINT` | Device Authorization Endpoint (RFC 8628) — where Device Flow requests are relayed |
| `IDP_TOKEN_ENDPOINT` | Token Endpoint — where token polling requests are relayed |
| `IDP_AUDIENCE` | Expected `aud` claim in JWTs issued for this channel |
| `IDP_ISSUER` | Expected `iss` claim — must exactly match what your IdP embeds |
| `IDP_CLIENT_ID` | OAuth2 client ID — embedded in `WWW-Authenticate` challenge responses |

The Flask proxy fails to start with a clear error message if any variable is missing.

## Project structure

```
.
├── pyproject.toml          # pixi workspace + Python package definition
├── Caddyfile               # Caddy reverse proxy configuration
├── .env.example            # Environment variable template (check this in)
├── .env                    # Your real IdP values (gitignored)
├── src/
│   └── auth_proxy/
│       ├── __init__.py
│       ├── app.py          # Flask routes: /auth-check, /oauth/device, /oauth/token
│       └── config.py       # Env var loading and validation
├── recipes/
│   ├── greet/              # Example noarch package: greet.hello(name) -> str
│   │   ├── recipe.yaml
│   │   ├── pyproject.toml
│   │   └── greet/__init__.py
│   └── timeutils/          # Example noarch package: timeutils.now() -> str
│       ├── recipe.yaml
│       ├── pyproject.toml
│       └── timeutils/__init__.py
├── channel/                # Built conda packages — gitignored, populated by build-channel
└── certs/                  # mkcert TLS certificate — gitignored, populated by setup-tls
```

## Adding more packages to the channel

1. Create a new directory under `recipes/`:

```
recipes/
└── mypackage/
    ├── recipe.yaml
    ├── pyproject.toml
    └── mypackage/__init__.py
```

2. Build it:

```bash
pixi run rattler-build build -r recipes/mypackage --output-dir channel
```

Or add it to the `build-channel` task in `pyproject.toml` to include it in `pixi run build-channel`.

## Troubleshooting

**`pixi run dev` fails with "Missing required environment variable"**
Copy `.env.example` to `.env` and fill in your IdP's values.

**`pixi run setup-tls` — mkcert asks for sudo password**
mkcert installs its CA into the system trust store, which requires elevated privileges. This is expected.

**Channel requests return 502 instead of 401**
The Flask proxy can't reach the IdP JWKS endpoint. Check that your IdP is running and `IDP_JWKS_URI` is reachable from this machine.

**`curl` returns a proxy error for `repo.thath.local`**
If you're behind a corporate proxy, add `repo.thath.local` to your `no_proxy` / `NO_PROXY` environment variable.

**Caddy won't start — "certificate not found"**
Run `pixi run setup-tls` first to generate the mkcert certificate.
