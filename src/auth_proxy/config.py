"""
Configuration loader for auth_proxy.

Reads all required IdP coordinates from environment variables (loaded from
.env at project root via python-dotenv). Fails fast with a clear error
message if any required variable is missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env from the project root (two levels up from src/auth_proxy/).
# This is a no-op if the file does not exist (e.g., variables are already
# in the process environment).
load_dotenv()

_REQUIRED_VARS = [
    "IDP_BASE_URL",
    "IDP_JWKS_URI",
    "IDP_DEVICE_AUTH_ENDPOINT",
    "IDP_TOKEN_ENDPOINT",
    "IDP_AUDIENCE",
    "IDP_ISSUER",
    "IDP_CLIENT_ID",
]


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}\n"
            "Copy .env.example to .env and fill in your IdP coordinates."
        )
    return value


@dataclass(frozen=True)
class Config:
    idp_base_url: str
    jwks_uri: str
    device_auth_endpoint: str
    token_endpoint: str
    audience: str
    issuer: str
    client_id: str

    @classmethod
    def from_env(cls) -> Config:
        missing = [v for v in _REQUIRED_VARS if not os.environ.get(v, "").strip()]
        if missing:
            raise RuntimeError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + "\nCopy .env.example to .env and fill in your IdP coordinates."
            )
        return cls(
            idp_base_url=_require("IDP_BASE_URL"),
            jwks_uri=_require("IDP_JWKS_URI"),
            device_auth_endpoint=_require("IDP_DEVICE_AUTH_ENDPOINT"),
            token_endpoint=_require("IDP_TOKEN_ENDPOINT"),
            audience=_require("IDP_AUDIENCE"),
            issuer=_require("IDP_ISSUER"),
            client_id=_require("IDP_CLIENT_ID"),
        )


# Module-level singleton — loaded once at import time so startup errors
# surface immediately rather than on the first request.
config: Config = Config.from_env()
