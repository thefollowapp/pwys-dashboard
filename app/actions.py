import os

import httpx


class CancellationNoticeError(Exception):
    """Raised when the Make.com cancellation webhook isn't configured or rejects the request."""


def send_cancellation_notice(location: str, message: str, triggered_by: str) -> None:
    webhook_url = os.getenv("CANCELLATION_WEBHOOK_URL")
    if not webhook_url:
        raise CancellationNoticeError(
            "CANCELLATION_WEBHOOK_URL is not configured on the server yet. "
            "Set it in Railway once the Make.com cancellation scenario's webhook is live."
        )

    try:
        response = httpx.post(
            webhook_url,
            json={"location": location, "message": message, "triggered_by": triggered_by},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise CancellationNoticeError(f"Make.com didn't accept the request: {exc}") from exc
