from __future__ import annotations

import io
import logging
import os
import wave
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

_SERVICE_CACHE: Any = None


def is_configured() -> bool:
    """Return True if Google Drive credentials and folder ID are set in the environment."""
    return bool(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH") and os.getenv("DRIVE_MEDIA_FOLDER_ID")
    )


def get_parent_folder_id() -> str:
    folder_id = os.getenv("DRIVE_MEDIA_FOLDER_ID")
    if not folder_id:
        raise ValueError("DRIVE_MEDIA_FOLDER_ID is not set.")
    return folder_id


def create_week_folder(week_date: str, parent_folder_id: str) -> str:
    """Create a dated subfolder inside the parent folder. Returns the new folder ID."""
    service = _get_service()
    metadata = {
        "name": week_date,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id],
    }
    folder = service.files().create(body=metadata, fields="id", supportsAllDrives=True).execute()
    folder_id: str = folder["id"]
    _make_public(service, folder_id)
    return folder_id


def upload_file(
    folder_id: str,
    local_path: str | Path,
    display_name: str | None = None,
) -> dict[str, str]:
    """Upload a local file to a Drive folder, make it public, and return URL dict."""
    import mimetypes

    from googleapiclient.http import MediaFileUpload

    path = Path(local_path)
    name = display_name or path.name
    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    service = _get_service()
    file_meta = {"name": name, "parents": [folder_id]}
    media = MediaFileUpload(str(path), mimetype=mime_type, resumable=False)
    result = (
        service.files().create(body=file_meta, media_body=media, fields="id", supportsAllDrives=True).execute()
    )
    file_id: str = result["id"]
    _make_public(service, file_id)
    return _build_urls(file_id)


def upload_audio_placeholder(folder_id: str) -> dict[str, str]:
    """Upload a tiny silent WAV as podcast.mp3 placeholder. Returns URL dict."""
    from googleapiclient.http import MediaIoBaseUpload

    service = _get_service()
    file_meta = {"name": "podcast.mp3", "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(_silent_wav_bytes()), mimetype="audio/wav", resumable=False
    )
    result = (
        service.files().create(body=file_meta, media_body=media, fields="id", supportsAllDrives=True).execute()
    )
    file_id: str = result["id"]
    _make_public(service, file_id)
    return _build_urls(file_id)


def upload_video_placeholder(folder_id: str) -> dict[str, str]:
    """Upload a tiny silent WAV as video.mp4 placeholder. Returns URL dict."""
    from googleapiclient.http import MediaIoBaseUpload

    service = _get_service()
    file_meta = {"name": "video.mp4", "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(_silent_wav_bytes()), mimetype="audio/wav", resumable=False
    )
    result = (
        service.files().create(body=file_meta, media_body=media, fields="id", supportsAllDrives=True).execute()
    )
    file_id: str = result["id"]
    _make_public(service, file_id)
    return _build_urls(file_id)


def _get_service() -> Any:
    global _SERVICE_CACHE
    if _SERVICE_CACHE is not None:
        return _SERVICE_CACHE

    from google.auth.exceptions import GoogleAuthError
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
    if not creds_path:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_PATH is required for Google Drive publishing."
        )

    try:
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(
            f"Failed to load service account credentials from {creds_path}: {exc}"
        ) from exc

    _SERVICE_CACHE = build("drive", "v3", credentials=credentials)
    return _SERVICE_CACHE


def _make_public(service: Any, file_id: str) -> None:
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
    except Exception:
        # Shared Drive items inherit the drive's sharing settings — permission change not needed.
        pass


def _build_urls(file_id: str) -> dict[str, str]:
    return {
        "file_id": file_id,
        "embed_url": f"https://drive.google.com/file/d/{file_id}/preview",
        "direct_url": f"https://lh3.googleusercontent.com/d/{file_id}",
    }


def _silent_wav_bytes() -> bytes:
    """Generate a ~850-byte silent WAV (100 ms, 8 kHz, mono, 8-bit unsigned)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(b"\x80" * 800)  # 0x80 = silence for unsigned 8-bit PCM
    return buf.getvalue()
