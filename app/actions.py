import os

import httpx


class NoticeError(Exception):
    """Raised when a notice webhook isn't configured or rejects the request."""


def _post_to_webhook(url_env: str, api_key_env: str, payload: dict, webhook_label: str) -> None:
    webhook_url = os.getenv(url_env)
    if not webhook_url:
        raise NoticeError(
            f"{url_env} is not configured on the server yet. "
            f"Set it in Railway once the Make.com {webhook_label} scenario's webhook is live."
        )
    webhook_api_key = os.getenv(api_key_env)
    if not webhook_api_key:
        raise NoticeError(
            f"{api_key_env} is not configured on the server yet. "
            f"Set it in Railway to match the API key on the Make.com {webhook_label} webhook."
        )

    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            headers={"x-make-apikey": webhook_api_key},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise NoticeError(f"Make.com didn't accept the request: {exc}") from exc


def send_targeted_notice(locations: list[str], message: str, triggered_by: str, message_type: str) -> None:
    """Text everyone registered at `locations`. Shared by one-off notices, custom notice
    types, and recurring notices alike — `message_type` is just what gets logged for
    the dashboard's per-type metrics."""
    _post_to_webhook(
        "CANCELLATION_WEBHOOK_URL",
        "CANCELLATION_WEBHOOK_API_KEY",
        {"locations": locations, "message": message, "triggered_by": triggered_by, "message_type": message_type},
        "cancellation notice",
    )


def send_cancellation_notice(locations: list[str], message: str, triggered_by: str) -> None:
    send_targeted_notice(locations, message, triggered_by, "cancellation")


def send_move_indoors_notice(excluded_locations: list[str], message: str, triggered_by: str) -> None:
    _post_to_webhook(
        "MOVE_INDOORS_WEBHOOK_URL",
        "MOVE_INDOORS_WEBHOOK_API_KEY",
        {"excluded_locations": excluded_locations, "message": message, "triggered_by": triggered_by},
        "move indoors notice",
    )
