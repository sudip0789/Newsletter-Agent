from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

MEDIA_INPUTS_FILENAME = "media_inputs.json"

_DRIVE_FILE_PATH_RE = re.compile(r"/file/d/([^/]+)")
_DRIVE_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def load_media_inputs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return normalize_media_payload(payload)


def normalize_media_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}

    media: dict[str, Any] = {}

    audio_url = _first_non_empty(
        payload.get("podcast_embed_url"),
        payload.get("podcast_url"),
        payload.get("audio_embed_url"),
        payload.get("audio_url"),
    )
    video_url = _first_non_empty(
        payload.get("video_embed_url"),
        payload.get("video_url"),
    )

    if audio_url:
        media["podcast_embed_url"] = normalize_embed_url(audio_url)
    if video_url:
        media["video_embed_url"] = normalize_embed_url(video_url)

    folder_id = _string_or_none(payload.get("folder_id"))
    folder_url = _string_or_none(payload.get("folder_url"))
    if folder_id:
        media["folder_id"] = folder_id
    if folder_url:
        media["folder_url"] = folder_url

    headline_images = payload.get("headline_images")
    if isinstance(headline_images, list):
        media["headline_images"] = [
            normalize_embed_url(item) if isinstance(item, str) and item.strip() else item
            for item in headline_images
        ]

    return media


def normalize_embed_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        return raw

    file_id = _extract_google_drive_file_id(raw)
    if file_id:
        return f"https://drive.google.com/file/d/{file_id}/preview"
    return raw


def _extract_google_drive_file_id(value: str) -> str | None:
    direct_match = _DRIVE_FILE_ID_RE.fullmatch(value)
    if direct_match:
        return value

    match = _DRIVE_FILE_PATH_RE.search(value)
    if match:
        return match.group(1)

    parsed = urlparse(value)
    if not parsed.netloc.endswith("drive.google.com"):
        return None

    query_id = parse_qs(parsed.query).get("id")
    if query_id and query_id[0]:
        return query_id[0]
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        candidate = _string_or_none(value)
        if candidate:
            return candidate
    return None


def _string_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
