# Proposal: Local Conda Channel with OAuth2 Authentication

## Summary

Set up a pixi project (pyproject format) that provides a locally-hosted, TLS-secured conda channel at `repo.thath.local:8443`, protected by OAuth2 authentication. The project serves as a local development and testing environment for the `conda-auth` plugin, providing a realistic OAuth2-protected channel that supports both Device Flow (CLI) and Authorization Code (browser) workflows.

## Background

Testing the `conda-auth` plugin requires a real OAuth2-protected conda channel. Rather than mocking, this project provides a fully functional local stack: Caddy as a TLS-terminating reverse proxy, a Flask auth proxy that validates JWTs from a separately-managed upstream IdP, a rattler-build-generated channel with example packages, and `mkcert` for trusted local TLS certificates.

## Goals

- Provide a pixi project (pyproject.toml) that bootstraps the entire local stack with a single task
- Run a conda channel at `https://repo.thath.local:8443/channel/` protected by JWT Bearer auth
- Support Device Flow for CLI clients (conda/pixi/micromamba + conda-auth plugin)
- Support Authorization Code flow for browser-based login
- Delegate all identity to an upstream IdP (configurable via environment variables)
- Generate example conda packages via rattler-build for channel testing

## Non-Goals

- This is not an OAuth2 Authorization Server; identity is fully delegated to an upstream IdP
- No production hardiness (single-machine local dev only)
- No multi-user or multi-machine support
- Not managing the upstream IdP lifecycle (it runs separately)

## Approach

A pixi-managed Python project running two processes:

1. **Caddy** (`repo.thath.local:8443`, HTTPS via mkcert) — serves channel static files and uses `forward_auth` to validate every channel request against the Flask proxy
2. **Flask auth proxy** (`:5000`, HTTP internal) — a proper Python package (`auth_proxy`) that validates JWT Bearer tokens against the upstream IdP's JWKS endpoint, and relays OAuth2 Device Flow requests

All IdP coordinates are injected via environment variables / `.env` file. Two trivial noarch Python packages (`greet`, `timeutils`) serve as rattler-build recipe examples for channel population.

## Key Decisions

- **JWT validation**: stateless, using upstream IdP's JWKS endpoint (no token introspection)
- **Caddy port**: 8443 (avoids privileged port 443)
- **Flask proxy**: runs as a proper installable Python package inside pixi's managed environment
- **`/etc/hosts` entry**: manual (not automated)
- **Token format**: short-lived JWTs; JWKS URI configured via env var
- **`WWW-Authenticate` header**: `Bearer realm`, `device_authorization_endpoint`, `client_id` — designed for `conda-auth` plugin consumption
