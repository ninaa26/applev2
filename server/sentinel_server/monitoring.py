"""Error reports to Sentry (https://sentry.io), when SENTRY_DSN is set.

Unset or empty, nothing is sent and sentry_sdk isn't imported. Set, uncaught exceptions and log
records at ERROR or above go to the Sentry project, with the request path but no request bodies,
cookies, headers or IP addresses. No performance tracing, so the free quota goes on errors.
"""

from __future__ import annotations

import os
import socket

from . import __version__
from .settings import _load_dotenv


def init_sentry(component: str) -> bool:
    """Start reporting errors from this process; returns whether Sentry is on."""
    _load_dotenv()  # the server keeps SENTRY_DSN in .env with its other settings
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        release=f"sentinel-server@{__version__}",
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        server_name=socket.gethostname(),
        send_default_pii=False,
    )
    sentry_sdk.set_tag("component", component)
    return True
