"""
Flask auth proxy for the local conda channel.

Routes
------
GET  /auth-check
    Called by Caddy forward_auth on every /channel/* request.
    Validates the Bearer JWT and returns 200 or 401.

POST /oauth/device
    Relay: forwards the request body to the IdP's Device Authorization
    Endpoint (RFC 8628) and returns the response verbatim.

POST /oauth/token
    Relay: forwards the request body to the IdP's Token Endpoint and
    returns the response verbatim. Used by conda-auth to poll for the
    access token during Device Flow.

GET  /.well-known/openid-configuration
    Optional: proxies IdP discovery document.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import requests as http
from flask import Flask, Response, jsonify, request
from joserfc import jwt as jose_jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from auth_proxy.config import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

_jwks_lock = threading.Lock()
_jwks_cache: dict[str, Any] | None = None  # raw JWKS dict as returned by IdP


def _fetch_jwks() -> dict[str, Any]:
    """Fetch JWKS from the IdP and return the raw dict."""
    try:
        resp = http.get(config.jwks_uri, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch JWKS from {config.jwks_uri}: {exc}") from exc


def _get_jwks(force_refresh: bool = False) -> dict[str, Any]:
    """Return cached JWKS, fetching lazily or on forced refresh."""
    global _jwks_cache
    with _jwks_lock:
        if _jwks_cache is None or force_refresh:
            _jwks_cache = _fetch_jwks()
        return _jwks_cache


# ---------------------------------------------------------------------------
# JWT validation
# ---------------------------------------------------------------------------


def _validate_token(raw_token: str) -> tuple[bool, str]:
    """
    Validate a raw JWT string.

    Returns (True, "") on success.
    Returns (False, reason) on failure.
    """
    # Attempt validation with the cached JWKS first; if the key is unknown
    # (kid mismatch), refresh once and retry — handles key rotation.
    for attempt in range(2):
        try:
            jwks_data = _get_jwks(force_refresh=(attempt == 1))
            key_set = KeySet.import_key_set(jwks_data)
            claims_requests = jose_jwt.JWTClaimsRegistry(
                iss={"essential": True, "value": config.issuer},
                aud={"essential": True, "value": config.audience},
                exp={"essential": True},
            )
            token = jose_jwt.decode(raw_token, key_set)
            claims_requests.validate(token.claims)
            return True, ""
        except JoseError as exc:
            error_msg = str(exc)
            # On first attempt: if it's a key-not-found error, let the loop
            # retry with a fresh JWKS fetch.
            if attempt == 0 and "key" in error_msg.lower():
                logger.debug("Unknown kid, refreshing JWKS and retrying")
                continue
            return False, error_msg
        except Exception as exc:
            return False, str(exc)

    return False, "JWT validation failed after JWKS refresh"


# ---------------------------------------------------------------------------
# WWW-Authenticate challenge header
# ---------------------------------------------------------------------------


def _www_authenticate_header() -> str:
    return (
        f'Bearer realm="repo.thath.local",'
        f' device_authorization_endpoint="https://repo.thath.local:8443/oauth/device",'
        f' client_id="{config.client_id}"'
    )


def _unauthorized(detail: str) -> Response:
    resp = jsonify({"error": "unauthorized", "detail": detail})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = _www_authenticate_header()
    return resp


def _bad_gateway(detail: str) -> Response:
    resp = jsonify({"error": "upstream_unavailable", "detail": detail})
    resp.status_code = 502
    return resp


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> Flask:
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # /auth-check  —  called by Caddy forward_auth
    # ------------------------------------------------------------------
    @app.get("/auth-check")
    def auth_check() -> Response:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _unauthorized("Missing or invalid Authorization header")

        raw_token = auth_header[len("Bearer ") :]
        ok, reason = _validate_token(raw_token)
        if not ok:
            logger.debug("JWT validation failed: %s", reason)
            return _unauthorized(reason)

        return Response(status=200)

    # ------------------------------------------------------------------
    # /oauth/device  —  Device Flow initiation relay (RFC 8628)
    # ------------------------------------------------------------------
    @app.post("/oauth/device")
    def oauth_device() -> Response:
        try:
            idp_resp = http.post(
                config.device_auth_endpoint,
                data=request.get_data(),
                headers={
                    "Content-Type": request.content_type or "application/x-www-form-urlencoded",
                },
                timeout=15,
            )
        except Exception as exc:
            return _bad_gateway(f"Could not reach IdP device authorization endpoint: {exc}")

        return Response(
            idp_resp.content,
            status=idp_resp.status_code,
            content_type=idp_resp.headers.get("Content-Type", "application/json"),
        )

    # ------------------------------------------------------------------
    # /oauth/token  —  Token relay (Device Flow polling + exchange)
    # ------------------------------------------------------------------
    @app.post("/oauth/token")
    def oauth_token() -> Response:
        try:
            idp_resp = http.post(
                config.token_endpoint,
                data=request.get_data(),
                headers={
                    "Content-Type": request.content_type or "application/x-www-form-urlencoded",
                },
                timeout=15,
            )
        except Exception as exc:
            return _bad_gateway(f"Could not reach IdP token endpoint: {exc}")

        return Response(
            idp_resp.content,
            status=idp_resp.status_code,
            content_type=idp_resp.headers.get("Content-Type", "application/json"),
        )

    # ------------------------------------------------------------------
    # /.well-known/openid-configuration  —  optional IdP discovery proxy
    # ------------------------------------------------------------------
    @app.get("/.well-known/openid-configuration")
    def openid_configuration() -> Response:
        discovery_url = f"{config.idp_base_url.rstrip('/')}/.well-known/openid-configuration"
        try:
            idp_resp = http.get(discovery_url, timeout=10)
            idp_resp.raise_for_status()
        except Exception as exc:
            return _bad_gateway(f"Could not reach IdP discovery endpoint: {exc}")

        return Response(
            idp_resp.content,
            status=idp_resp.status_code,
            content_type=idp_resp.headers.get("Content-Type", "application/json"),
        )

    return app


# Allow `flask --app auth_proxy.app run` to find the app object directly.
app = create_app()
