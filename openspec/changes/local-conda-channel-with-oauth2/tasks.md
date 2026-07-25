# Tasks: Local Conda Channel with OAuth2 Authentication

## Phase 1: Project Scaffold

- [x] Create `pyproject.toml` with `[project]` for `auth_proxy` package, `[build-system]` using hatchling, and all `[tool.pixi.*]` configuration (dependencies, platforms, tasks)
- [x] Create `.gitignore` with `channel/`, `certs/`, `.env`
- [x] Create `.env.example` with all required variable names, placeholder values, and inline comments
- [x] Create `src/auth_proxy/__init__.py` (empty or version string)

## Phase 2: Caddy Configuration

- [x] Create `Caddyfile` with:
  - Global block: `auto_https off`
  - `repo.thath.local:8443` virtual host with mkcert cert paths
  - `/channel/*` route with `forward_auth` + `file_server`
  - `/oauth/*` route reverse-proxied to Flask
  - `/.well-known/*` route reverse-proxied to Flask

## Phase 3: Flask Auth Proxy

- [x] Create `src/auth_proxy/config.py`:
  - Load all `IDP_*` env vars via `python-dotenv`
  - Fail fast with descriptive error if required vars are missing
  - Expose typed config object
- [x] Create `src/auth_proxy/app.py`:
  - Flask application factory (`create_app()`)
  - `GET /auth-check`: extract Bearer token, validate JWT, return 200 or 401 with `WWW-Authenticate`
  - `POST /oauth/device`: relay to `IDP_DEVICE_AUTH_ENDPOINT`
  - `POST /oauth/token`: relay to `IDP_TOKEN_ENDPOINT`
  - `GET /.well-known/openid-configuration`: proxy to IdP (optional)
  - JWKS fetch + in-memory cache with `kid`-triggered refresh

## Phase 4: rattler-build Recipes

- [x] Create `recipes/greet/` directory with:
  - `recipe.yaml` (noarch python, version 0.1.0)
  - Python source: `greet/__init__.py` with `hello(name: str) -> str`
  - `pyproject.toml` for the package
- [x] Create `recipes/timeutils/` directory with:
  - `recipe.yaml` (noarch python, version 0.1.0)
  - Python source: `timeutils/__init__.py` with `now() -> str`
  - `pyproject.toml` for the package

## Phase 5: Verification

- [x] Run `pixi install` — confirmed environment resolves
- [x] Run `pixi run setup-tls` — confirmed certs generated in `certs/`
- [x] Run `pixi run build-channel` — confirmed `channel/noarch/` populated with both packages (uses `-r recipes/<name>` flag)
- [x] Run `pixi run serve-flask` — confirmed Flask starts on `:5000`
- [x] Run `pixi run serve-caddy` — confirmed Caddy validates and starts on `:8443`
- [x] Test `/auth-check` without token — confirmed `401` with `WWW-Authenticate` header
- [x] Test `/auth-check` with a bad JWT — confirmed `401` with JWKS fetch attempt
- [x] Test `GET https://repo.thath.local:8443/channel/noarch/repodata.json` without token — confirmed `401` + `WWW-Authenticate` header propagated through Caddy
- [x] Test `POST /oauth/device` relay — confirmed relay reaches Flask and attempts IdP contact

## Notes

- `pixi.toml`-style `[tool.pixi.project]` is deprecated; using `[tool.pixi.workspace]` instead
- rattler-build recipe flag is `-r <dir>` not a positional argument
- `authlib.jose` is deprecated; using `joserfc` (ships with authlib) for JWT validation
- Platform `linux-aarch64` added to support ARM64 sandbox/machines
