from __future__ import annotations

import os
import time
from typing import Any

import httpx

WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "http://localhost:8080").rstrip("/")
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "kibo-dev-key")
TEST_PHONE = os.getenv("WHATSAPP_TEST_PHONE")


def _resolve_instance_name() -> str:
    raw = os.getenv("WHATSAPP_INSTANCE_NAME")
    if raw is None:
        return "agenda-dev"

    normalized = raw.strip()
    if not normalized or normalized.lower() in {"undefined", "null", "none"}:
        # Fall back to a deterministic local name when env var is invalid.
        return "agenda-dev"

    return normalized


INSTANCE_NAME = _resolve_instance_name()


def _looks_like_html(content_type: str, body: str) -> bool:
    lowered = body.lower()
    return "text/html" in content_type.lower() or "<html" in lowered


def _looks_like_wordpress(body: str) -> bool:
    lowered = body.lower()
    markers = ["wp-content", "wp-includes", "wordpress", "elementor"]
    return any(marker in lowered for marker in markers)


def _check_api_target(client: httpx.Client) -> None:
    try:
        response = client.get("/")
    except Exception:
        # Connection errors are handled by request fallbacks below.
        return

    body = response.text[:4000]
    if _looks_like_html(response.headers.get("content-type", ""), body):
        hint = ""
        if _looks_like_wordpress(body):
            hint = " It looks like WordPress is running on this URL/port."
        raise RuntimeError(
            "WHATSAPP_API_URL is not pointing to Evolution API."
            f" URL={WHATSAPP_API_URL}.{hint}"
            " Check port mapping and use the Evolution API endpoint before running this script."
        )


def _headers() -> dict[str, str]:
    return {
        "apikey": WHATSAPP_API_KEY,
        "Content-Type": "application/json",
    }


def _request_with_fallback(
    client: httpx.Client,
    attempts: list[tuple[str, str, dict[str, Any] | None]],
) -> dict[str, Any]:
    last_error: str | None = None

    for method, path, payload in attempts:
        try:
            response = client.request(method, path, json=payload)
            if response.status_code < 400:
                return response.json()

            response_text = response.text[:1200]
            if _looks_like_html(response.headers.get("content-type", ""), response_text):
                wp_hint = ""
                if _looks_like_wordpress(response_text):
                    wp_hint = " WordPress markers detected in response."
                last_error = (
                    f"{method} {path} -> {response.status_code}. "
                    f"Received HTML from {WHATSAPP_API_URL}, expected Evolution API JSON.{wp_hint}"
                )
            else:
                last_error = f"{method} {path} -> {response.status_code}: {response_text}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{method} {path} -> {exc}"

    raise RuntimeError(last_error or "Request attempts failed")


def create_instance(client: httpx.Client) -> dict[str, Any]:
    attempts = [
        (
            "POST",
            "/instance/create",
            {
                "instanceName": INSTANCE_NAME,
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS",
            },
        ),
        (
            "POST",
            "/instance/create",
            {
                "instanceName": INSTANCE_NAME,
                "integration": "WHATSAPP-BAILEYS",
            },
        ),
    ]

    try:
        return _request_with_fallback(client, attempts)
    except RuntimeError as exc:
        message = str(exc)
        if "already in use" in message:
            # Continue with an existing instance instead of failing hard.
            return {
                "instance": {
                    "instanceName": INSTANCE_NAME,
                    "status": "already_exists",
                }
            }
        raise


def fetch_qr(client: httpx.Client) -> dict[str, Any]:
    attempts = [
        ("GET", f"/instance/connect/{INSTANCE_NAME}", None),
        ("GET", f"/instance/qrcode/{INSTANCE_NAME}", None),
    ]
    return _request_with_fallback(client, attempts)


def fetch_status(client: httpx.Client) -> dict[str, Any]:
    attempts = [
        ("GET", f"/instance/connectionState/{INSTANCE_NAME}", None),
        ("GET", f"/instance/connection-state/{INSTANCE_NAME}", None),
    ]
    return _request_with_fallback(client, attempts)


def wait_for_open(client: httpx.Client, timeout_seconds: int = 120) -> dict[str, Any]:
    start = time.time()
    last_payload: dict[str, Any] = {}

    while time.time() - start <= timeout_seconds:
        payload = fetch_status(client)
        last_payload = payload
        payload_str = str(payload).lower()
        if "open" in payload_str or "connected" in payload_str:
            return payload
        time.sleep(3)

    raise TimeoutError(f"Connection did not reach open state. Last payload: {last_payload}")


def send_test_message(client: httpx.Client, phone: str) -> dict[str, Any]:
    normalized_phone = "".join(ch for ch in phone if ch.isdigit())
    if not normalized_phone:
        raise ValueError("WHATSAPP_TEST_PHONE must contain digits")

    attempts = [
        (
            "POST",
            f"/message/sendText/{INSTANCE_NAME}",
            {
                "number": normalized_phone,
                "text": "Agenda backend local Evolution API test message.",
            },
        ),
        (
            "POST",
            f"/message/sendText/{INSTANCE_NAME}",
            {
                "phone": normalized_phone,
                "message": "Agenda backend local Evolution API test message.",
            },
        ),
    ]
    return _request_with_fallback(client, attempts)


def main() -> None:
    with httpx.Client(base_url=WHATSAPP_API_URL, headers=_headers(), timeout=20.0) as client:
        _check_api_target(client)

        print(f"Using instance: {INSTANCE_NAME}")

        print("Step 1/4 - creating instance")
        created = create_instance(client)
        print(created)

        print("Step 2/4 - fetching QR code")
        qr_payload = fetch_qr(client)
        print(qr_payload)

        print("Step 3/4 - waiting for connection state=open")
        state_payload = wait_for_open(client)
        print(state_payload)

        if not TEST_PHONE:
            print("Step 4/4 - skipped send test message (set WHATSAPP_TEST_PHONE)")
            return

        print("Step 4/4 - sending test message")
        send_payload = send_test_message(client, TEST_PHONE)
        print(send_payload)


if __name__ == "__main__":
    main()
