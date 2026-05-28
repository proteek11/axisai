"""
ZoomService — Server-to-Server OAuth integration for Zoom Meetings API.

Auth flow (Server-to-Server OAuth — no per-user login needed):
  1. POST https://zoom.us/oauth/token  →  access_token (expires in 1 hour)
  2. Cache token in Redis with 55-minute TTL (5 min safety margin)
  3. All subsequent API calls use: Authorization: Bearer <access_token>

Zoom credentials are stored encrypted in tenant.config JSONB:
  {
    "zoom_account_id":    "abc123",
    "zoom_client_id":     "XXXX",
    "zoom_client_secret": "<fernet-encrypted>",
    "zoom_webhook_secret": "<fernet-encrypted>",
    "zoom_enabled":       true,
    "zoom_default_auto_record":       true,
    "zoom_default_import_recording":  true,
    "zoom_default_import_attendance": true,
    "zoom_default_generate_ai":       true
  }

Credential encryption uses Fernet (symmetric AES-128-CBC) — same approach as
the video pipeline's video_encryption_key in config.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional

import httpx
import structlog

log = structlog.get_logger(__name__)

_ZOOM_API = "https://api.zoom.us/v2"
_ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
_TOKEN_CACHE_KEY = "zoom_token:{account_id}"
_TOKEN_TTL = 55 * 60  # 55 minutes (Zoom tokens last 60 min)


# ── Encryption helpers ────────────────────────────────────────────────────────

def _get_fernet():
    """Lazy-import Fernet to avoid top-level import cost."""
    try:
        from cryptography.fernet import Fernet
        return Fernet
    except ImportError:
        raise RuntimeError(
            "cryptography package not installed — run: pip install cryptography"
        )


def encrypt_secret(plaintext: str, encryption_key: str) -> str:
    """Encrypt a secret string using Fernet (AES-128-CBC). Returns base64 token."""
    Fernet = _get_fernet()
    # Derive a 32-byte key from the encryption_key string
    key_bytes = hashlib.sha256(encryption_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    f = Fernet(fernet_key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str, encryption_key: str) -> str:
    """Decrypt a Fernet token back to plaintext."""
    Fernet = _get_fernet()
    key_bytes = hashlib.sha256(encryption_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    f = Fernet(fernet_key)
    return f.decrypt(token.encode()).decode()


# ── Redis token cache ─────────────────────────────────────────────────────────

async def _cache_get(key: str) -> Optional[str]:
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        val = await redis.get(key)
        return val.decode() if val else None
    except Exception:
        return None


async def _cache_set(key: str, value: str, ttl: int) -> None:
    try:
        from app.core.redis import get_redis
        redis = await get_redis()
        await redis.setex(key, ttl, value)
    except Exception:
        pass


# ── ZoomService ───────────────────────────────────────────────────────────────

class ZoomService:
    """
    Async Zoom Meetings API client for axis-ai.

    Usage:
        svc = ZoomService(account_id, client_id, client_secret)
        meeting = await svc.create_meeting(...)
    """

    def __init__(self, account_id: str, client_id: str, client_secret: str):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret

    async def _get_token(self) -> str:
        """Get a valid OAuth access token — cached in Redis."""
        cache_key = _TOKEN_CACHE_KEY.format(account_id=self.account_id)
        cached = await _cache_get(cache_key)
        if cached:
            return cached

        # Request new token
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _ZOOM_TOKEN_URL,
                params={"grant_type": "account_credentials", "account_id": self.account_id},
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

        if resp.status_code != 200:
            log.error("zoom_token_failed", status=resp.status_code, body=resp.text[:200])
            raise ZoomAPIError(f"Failed to get Zoom token: {resp.status_code} {resp.text[:100]}")

        data = resp.json()
        token = data["access_token"]
        await _cache_set(cache_key, token, _TOKEN_TTL)
        return token

    async def _api(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict | None:
        """Make an authenticated Zoom API call."""
        token = await self._get_token()
        url = f"{_ZOOM_API}{path}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code == 204:
            return None
        if resp.status_code >= 400:
            log.error("zoom_api_error", method=method, path=path,
                      status=resp.status_code, body=resp.text[:300])
            raise ZoomAPIError(
                f"Zoom API {method} {path} → {resp.status_code}: {resp.text[:150]}"
            )
        return resp.json()

    # ── Meeting CRUD ──────────────────────────────────────────────────────────

    async def create_meeting(
        self,
        *,
        title: str,
        description: str,
        start_iso: str,      # ISO 8601 UTC e.g. "2026-05-25T10:00:00Z"
        duration_minutes: int,
        auto_record: bool = True,
        password: str | None = None,
    ) -> dict:
        """
        Create a Zoom scheduled meeting.
        Returns the full Zoom meeting object:
          { id, uuid, join_url, start_url, password, ... }
        """
        body: dict[str, Any] = {
            "topic": title,
            "type": 2,               # 2 = scheduled meeting
            "start_time": start_iso,
            "duration": duration_minutes,
            "timezone": "UTC",
            "agenda": description or "",
            "settings": {
                "host_video": True,
                "participant_video": True,
                "join_before_host": False,
                "mute_upon_entry": True,
                "waiting_room": True,
                "auto_recording": "cloud" if auto_record else "none",
                # Requires attention tracking to be enabled in Zoom account settings
                "focus_mode": False,
            },
        }
        if password:
            body["password"] = password

        result = await self._api("POST", "/users/me/meetings", json_body=body)
        log.info("zoom_meeting_created", meeting_id=result.get("id"), title=title)
        return result

    async def get_meeting(self, meeting_id: str) -> dict:
        """Get meeting details by Zoom meeting ID."""
        return await self._api("GET", f"/meetings/{meeting_id}")

    async def delete_meeting(self, meeting_id: str) -> None:
        """Delete / cancel a Zoom meeting."""
        await self._api("DELETE", f"/meetings/{meeting_id}")
        log.info("zoom_meeting_deleted", meeting_id=meeting_id)

    async def update_meeting(self, meeting_id: str, *, title: str | None = None,
                              scheduled_at: str | None = None,
                              duration_minutes: int | None = None) -> None:
        """Patch a Zoom meeting's schedule."""
        body: dict[str, Any] = {}
        if title:
            body["topic"] = title
        if scheduled_at:
            body["start_time"] = scheduled_at
        if duration_minutes:
            body["duration"] = duration_minutes
        if body:
            await self._api("PATCH", f"/meetings/{meeting_id}", json_body=body)

    # ── Recording ─────────────────────────────────────────────────────────────

    async def get_recording(self, meeting_uuid: str) -> dict | None:
        """
        Get cloud recording details for a meeting UUID.
        Returns None if not yet available.
        meeting_uuid must be double-URL-encoded when it contains slashes.
        """
        encoded = meeting_uuid.replace("/", "%2F").replace("+", "%2B")
        try:
            return await self._api("GET", f"/meetings/{encoded}/recordings")
        except ZoomAPIError as e:
            if "3301" in str(e):  # Error code 3301 = no recording found
                return None
            raise

    async def download_recording_mp4(self, download_url: str, access_token: str,
                                      dest_path: str) -> int:
        """
        Download a Zoom recording MP4 to dest_path.
        Returns file size in bytes.
        """
        import aiofiles
        import os

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get(
                download_url,
                params={"access_token": access_token},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()

        async with aiofiles.open(dest_path, "wb") as f:
            await f.write(resp.content)

        size = os.path.getsize(dest_path)
        log.info("zoom_recording_downloaded", path=dest_path, size_bytes=size)
        return size

    # ── Participants / Attendance ─────────────────────────────────────────────

    async def get_participants(self, meeting_id: str) -> list[dict]:
        """
        Get the participant report for a completed meeting.
        Requires Zoom Reports scope. Returns list of participant dicts.
        Note: Zoom only retains this data for 30 days.
        """
        all_participants: list[dict] = []
        next_page_token = ""

        while True:
            params: dict[str, Any] = {"page_size": 300}
            if next_page_token:
                params["next_page_token"] = next_page_token

            data = await self._api(
                "GET", f"/report/meetings/{meeting_id}/participants", params=params
            )
            if not data:
                break

            all_participants.extend(data.get("participants", []))
            next_page_token = data.get("next_page_token", "")
            if not next_page_token:
                break

        log.info("zoom_participants_fetched",
                 meeting_id=meeting_id, count=len(all_participants))
        return all_participants

    # ── Connection test ───────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        """
        Validate credentials by calling GET /users/me.
        Returns {"ok": True, "email": "...", "account_id": "..."} on success.
        """
        me = await self._api("GET", "/users/me")
        return {
            "ok": True,
            "email": me.get("email"),
            "account_id": me.get("account_id"),
            "plan_type": me.get("type"),  # 1=Basic, 2=Licensed, 3=On-Prem
        }


# ── Webhook verification ──────────────────────────────────────────────────────

def verify_zoom_webhook(
    *,
    body_bytes: bytes,
    timestamp: str,
    signature: str,
    webhook_secret: str,
) -> bool:
    """
    Verify a Zoom webhook signature using HMAC-SHA256.
    Zoom signs: "v0:{timestamp}:{body}"
    Sent in header: x-zm-signature = "v0=<hex>"
    """
    message = f"v0:{timestamp}:{body_bytes.decode('utf-8', errors='replace')}"
    expected = "v0=" + hmac.new(
        webhook_secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def handle_zoom_url_validation(body: dict, webhook_secret: str) -> dict:
    """
    Respond to Zoom's URL validation challenge (sent when first registering webhook).
    Must return {"plainToken": ..., "encryptedToken": ...}
    """
    plain_token = body.get("payload", {}).get("plainToken", "")
    encrypted = hmac.new(
        webhook_secret.encode(),
        plain_token.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {"plainToken": plain_token, "encryptedToken": encrypted}


# ── Errors ────────────────────────────────────────────────────────────────────

class ZoomAPIError(Exception):
    """Raised when Zoom API returns a 4xx/5xx response."""


# ── Factory — build from tenant config ───────────────────────────────────────

def zoom_service_from_config(tenant_config: dict, encryption_key: str) -> ZoomService:
    """
    Build a ZoomService from the decrypted tenant config dict.
    Raises ValueError if Zoom is not configured.
    """
    if not tenant_config.get("zoom_enabled"):
        raise ValueError("Zoom is not enabled for this tenant")

    account_id = tenant_config.get("zoom_account_id", "")
    client_id = tenant_config.get("zoom_client_id", "")
    client_secret_enc = tenant_config.get("zoom_client_secret", "")

    if not all([account_id, client_id, client_secret_enc]):
        raise ValueError("Zoom credentials incomplete (account_id / client_id / client_secret)")

    client_secret = decrypt_secret(client_secret_enc, encryption_key)
    return ZoomService(account_id, client_id, client_secret)


def get_zoom_webhook_secret(tenant_config: dict, encryption_key: str) -> str:
    """Decrypt and return the Zoom webhook secret from tenant config."""
    enc = tenant_config.get("zoom_webhook_secret", "")
    if not enc:
        raise ValueError("Zoom webhook secret not configured")
    return decrypt_secret(enc, encryption_key)
