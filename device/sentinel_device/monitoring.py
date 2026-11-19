"""Error reports to Sentry (https://sentry.io), when SENTRY_DSN is set.

Unset or empty, nothing is sent and sentry_sdk isn't imported. On a hub, sentinel-gateway.service reads
SENTRY_DSN from /etc/sentinel/sentry.env. Set, uncaught exceptions and log records at ERROR or above go to
the Sentry project (a hub that can't reach the server logs a warning, so a dropped connection isn't one).
"""

from __future__ import annotations

import os
import socket

from . import __version__


def init_sentry(component: str) -> bool:
    """Start reporting errors from this process; returns whether Sentry is on."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        release=f"sentinel-device@{__version__}",
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        server_name=socket.gethostname(),
        send_default_pii=False,
    )
    sentry_sdk.set_tag("component", component)
    return True
