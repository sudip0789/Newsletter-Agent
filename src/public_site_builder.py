from __future__ import annotations

import json
import logging
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape
from src.media_config import (
    LOCAL_PODCAST_AUDIO_FILENAME,
    MEDIA_INPUTS_FILENAME,
    build_local_podcast_audio_path,
    load_media_inputs,
)
from src.publish_dates import normalize_issue_date, resolve_publication_date
from src.template_assembler import TemplateAssembler

LOGGER = logging.getLogger(__name__)

# Background color the generated headline images are normalized to, so the square
# DALL-E art blends seamlessly into the headline card. Keep this in sync with the
# `.headline-card` background in templates/newsletter.html.
HEADLINE_CARD_BG = (0xF6, 0xF4, 0xF1)


def _load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_issue_date(issue_date: str) -> str:
    try:
        resolved_date = datetime.fromisoformat(issue_date).date()
    except ValueError:
        return issue_date.strip()

    day = resolved_date.day
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return resolved_date.strftime("%B ") + f"{day}{suffix}, {resolved_date.year}"


def _load_archive_headlines(root: Path) -> dict[str, str]:
    archive_path = root / "data" / "output" / "archive.json"
    if not archive_path.exists():
        return {}
    try:
        data = json.loads(archive_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(data, dict):
        return {str(key): str(value) for key, value in data.items()}
    return {}


def _collect_issue_snapshots(root: Path) -> list[dict[str, Any]]:
    issues_root = root / "issue_snapshots"
    if not issues_root.exists():
        return []

    archive_headlines = _load_archive_headlines(root)
    template_path = str(root / "templates" / "newsletter.html")

    issues: list[dict[str, Any]] = []
    for issue_dir in sorted(
        [path for path in issues_root.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    ):
        headlines_path = issue_dir / "headline_picks.json"
        stories_path = issue_dir / "summarized_stories.json"
        if not headlines_path.exists() or not stories_path.exists():
            continue

        headlines = _load_json(headlines_path)
        title = headlines[0]["title"] if headlines else issue_dir.name

        # Same numbers the issue masthead shows (sections / stories / read time)
        # plus the issue label and date parts, computed from the snapshot data.
        try:
            metadata = TemplateAssembler(
                stories_path=str(stories_path),
                headlines_path=str(headlines_path),
                template_path=template_path,
            ).compute_metadata(issue_dir.name, publish_date_is_resolved=True)
        except Exception as exc:  # pragma: no cover - per-issue resilience
            LOGGER.warning("Could not compute stats for %s: %s", issue_dir.name, exc)
            metadata = {}

        headline = archive_headlines.get(issue_dir.name) or title

        issues.append(
            {
                "issue_date": issue_dir.name,
                "display_date": _format_issue_date(issue_dir.name),
                "title": title,
                "headline": headline,
                "issue_label": metadata.get("issue_label", ""),
                "weekday": metadata.get("weekday", ""),
                "month_day": metadata.get("month_day", ""),
                "year": metadata.get("year", ""),
                "section_count": metadata.get("section_count", 0),
                "story_count": metadata.get("story_count", 0),
                "read_time_minutes": metadata.get("read_time_minutes", 0),
                "source_dir": str(issue_dir),
            }
        )
    return issues


def _copy_generated_assets(source_dir: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    if not source_dir.exists():
        return
    shutil.copytree(source_dir, target_dir)


def _copy_optional_directory(source_dir: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    if not source_dir.exists():
        return
    shutil.copytree(source_dir, target_dir)


def _normalize_headline_image_backgrounds(
    generated_dir: Path,
    target_rgb: tuple[int, int, int] = HEADLINE_CARD_BG,
    tolerance: float = 40.0,
    skip_atol: int = 4,
) -> None:
    """Repaint the flat background of headline_{1,2,3}.png to ``target_rgb``.

    DALL-E renders each headline image on a slightly different warm off-white, so
    the square art shows a faint edge against the fixed headline-card color. This
    recolors only the background — the region of near-background pixels connected
    to the image border — leaving the foreground artwork untouched. It is
    idempotent (images already on target are skipped via a cheap corner check)
    and a no-op if the imaging libraries are unavailable (e.g. on a build host
    without them — the committed images are already normalized).
    """
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
    except ImportError as exc:
        LOGGER.warning("Skipping headline background normalization: %s", exc)
        return

    target = np.array(target_rgb)
    for index in (1, 2, 3):
        path = generated_dir / f"headline_{index}.png"
        if not path.exists():
            continue
        try:
            image = Image.open(path).convert("RGB")
        except OSError as exc:
            LOGGER.warning("Could not open %s for normalization: %s", path, exc)
            continue

        arr = np.asarray(image).astype(np.int16)
        # Background reference = median of the four 8x8 corner patches.
        corners = np.concatenate(
            [
                arr[:8, :8].reshape(-1, 3),
                arr[:8, -8:].reshape(-1, 3),
                arr[-8:, :8].reshape(-1, 3),
                arr[-8:, -8:].reshape(-1, 3),
            ]
        )
        reference = np.median(corners, axis=0)
        # Cheap early-out: background already on target — nothing to do.
        if np.all(np.abs(reference - target) <= skip_atol):
            continue

        # Pixels close to the background reference, then keep only the connected
        # regions touching the border (the true outer background, never interior
        # foreground shapes that happen to be light).
        distance = np.sqrt(((arr - reference) ** 2).sum(axis=2))
        close = distance <= tolerance
        labels, _count = ndimage.label(close)
        border_labels = (
            set(labels[0, :].tolist())
            | set(labels[-1, :].tolist())
            | set(labels[:, 0].tolist())
            | set(labels[:, -1].tolist())
        )
        border_labels.discard(0)
        if not border_labels:
            continue

        background_mask = np.isin(labels, list(border_labels))
        arr[background_mask] = target
        Image.fromarray(arr.astype("uint8"), "RGB").save(path)
        LOGGER.info(
            "Normalized %s background to #%02X%02X%02X", path.name, *target_rgb
        )


def _build_archive_index(root: Path, issues: list[dict[str, str]]) -> None:
    template_path = root / "templates" / "archive_index.html"
    env = Environment(
        autoescape=select_autoescape(default_for_string=True, default=True)
    )
    template = env.from_string(template_path.read_text(encoding="utf-8"))

    archive_output = root / "public" / "issues" / "index.html"
    archive_output.parent.mkdir(parents=True, exist_ok=True)
    archive_output.write_text(
        template.render(issues=issues, latest_issue_url="../"),
        encoding="utf-8",
    )


def _load_media(path: Path) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _convert_to_mp3(source_path: Path) -> Path:
    """Convert audio to mp3 via ffmpeg for browser seek compatibility. Returns mp3 path."""
    import subprocess

    output_path = source_path.with_suffix(".mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source_path), "-q:a", "2", str(output_path)],
        check=True,
        capture_output=True,
    )
    return output_path


def _copy_local_podcast_audio(
    source_path: Path,
    target_root: Path,
    issue_date: str,
) -> str | None:
    if not source_path.exists():
        return None

    relative_path = Path(build_local_podcast_audio_path(issue_date, source_path.suffix))
    target_path = target_root / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return relative_path.as_posix()


def _sync_media_to_snapshot(
    root: Path,
    issue_date: str,
    audio_source: Path,
    media_updates: dict,
) -> None:
    """Sync local audio file and media metadata back into the issue snapshot.

    Called by build_public_site so that adding audio/video after the initial
    publish_issue run keeps the snapshot up to date for future archive builds.
    """
    snapshot_dir = root / "issue_snapshots" / issue_date
    if not snapshot_dir.exists():
        return

    if audio_source.exists():
        relative = Path(build_local_podcast_audio_path(issue_date, audio_source.suffix))
        target = snapshot_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audio_source, target)

    if media_updates:
        media_json_path = snapshot_dir / "media.json"
        existing = _load_media(media_json_path) or {}
        merged = {**existing, **media_updates}
        media_json = json.dumps(merged, indent=2, ensure_ascii=False)
        media_json_path.write_text(media_json, encoding="utf-8")
        output_media_path = root / "data" / "output" / "media.json"
        output_media_path.parent.mkdir(parents=True, exist_ok=True)
        output_media_path.write_text(media_json, encoding="utf-8")


def _sync_current_issue_outputs_to_snapshot(root: Path, issue_date: str) -> None:
    snapshot_dir = root / "issue_snapshots" / issue_date
    if not snapshot_dir.exists():
        return

    output_dir = root / "data" / "output"
    for filename in ("summarized_stories.json", "headline_picks.json"):
        source = output_dir / filename
        if source.exists():
            shutil.copy2(source, snapshot_dir / filename)

    generated_assets = root / "assets" / "generated"
    snapshot_generated_assets = snapshot_dir / "assets" / "generated"
    if generated_assets.exists():
        _copy_generated_assets(generated_assets, snapshot_generated_assets)


def build_public_site(
    project_root: Path | None = None,
    publish_date: date | datetime | str | None = None,
    publish_date_is_resolved: bool = False,
) -> str:
    root = (project_root or Path(__file__).resolve().parent.parent).resolve()
    source_assets = root / "assets"
    target_assets = root / "public" / "assets"
    latest_issue_date = (
        normalize_issue_date(publish_date)
        if publish_date is not None and publish_date_is_resolved
        else normalize_issue_date(resolve_publication_date(publish_date))
    )

    # Normalize the generated headline image backgrounds to the headline-card
    # color before they are snapshotted and copied into public/, so the art
    # blends seamlessly into the card.
    _normalize_headline_image_backgrounds(source_assets / "generated")

    if publish_date is not None:
        _sync_current_issue_outputs_to_snapshot(root, latest_issue_date)

    if target_assets.exists():
        shutil.rmtree(target_assets)
    shutil.copytree(source_assets, target_assets)

    issues_public_root = root / "public" / "issues"
    if issues_public_root.exists():
        shutil.rmtree(issues_public_root)

    issue_snapshots = _collect_issue_snapshots(root)

    # Load media.json for the latest issue: prefer the issue snapshot (when publish_date
    # is known), fall back to data/output/media.json (committed alongside headline_picks.json).
    if publish_date is not None:
        if publish_date_is_resolved:
            issue_date = normalize_issue_date(publish_date)
        else:
            issue_date = normalize_issue_date(resolve_publication_date(publish_date))
        current_media = (
            _load_media(root / "issue_snapshots" / issue_date / "media.json")
            or _load_media(root / "data" / "output" / "media.json")
            or load_media_inputs(root / "data" / "output" / MEDIA_INPUTS_FILENAME)
        )
    else:
        current_media = (
            _load_media(root / "data" / "output" / "media.json")
            or load_media_inputs(root / "data" / "output" / MEDIA_INPUTS_FILENAME)
        )
    media_inputs = load_media_inputs(root / "data" / "output" / MEDIA_INPUTS_FILENAME)
    current_media = {**dict(current_media or {}), **media_inputs}

    mp3_path = root / "data" / "output" / "audio.mp3"
    m4a_path = root / "data" / "output" / LOCAL_PODCAST_AUDIO_FILENAME
    snapshot_audio = next(
        (root / "issue_snapshots" / latest_issue_date / "assets" / "media").glob("podcast-*.mp3"),
        None,
    ) if (root / "issue_snapshots" / latest_issue_date / "assets" / "media").exists() else None
    if mp3_path.exists():
        audio_source = mp3_path
    elif m4a_path.exists():
        audio_source = _convert_to_mp3(m4a_path)
    elif snapshot_audio:
        audio_source = snapshot_audio
    else:
        audio_source = mp3_path
    latest_audio_path = _copy_local_podcast_audio(
        audio_source,
        root / "public",
        latest_issue_date,
    )
    if latest_audio_path:
        current_media["podcast_audio_url"] = latest_audio_path
        current_media.pop("podcast_embed_url", None)

    _sync_media_to_snapshot(root, latest_issue_date, audio_source, current_media)

    assembler = TemplateAssembler(
        stories_path=str(root / "data" / "output" / "summarized_stories.json"),
        headlines_path=str(root / "data" / "output" / "headline_picks.json"),
        template_path=str(root / "templates" / "newsletter.html"),
        media=current_media,
    )
    latest_pdf_path = root / "public" / "newsletter.pdf"
    latest_pdf_name = f"ai-upload-weekly-digest-{latest_issue_date}.pdf"
    latest_html = assembler.run(
        publish_date=publish_date,
        output_path=str(root / "public" / "index.html"),
        archive_url="issues/" if len(issue_snapshots) > 1 else None,
        pdf_url="newsletter.pdf",
        pdf_download_name=latest_pdf_name,
        publish_date_is_resolved=publish_date_is_resolved,
    )
    try:
        from src.pdf_renderer import PdfRenderError, render_html_to_pdf
        render_html_to_pdf(root / "public" / "index.html", latest_pdf_path)
    except ModuleNotFoundError:
        pass
    except PdfRenderError as exc:
        LOGGER.warning("Skipping PDF render: %s", exc)

    for issue in issue_snapshots:
        issue_source_dir = Path(issue["source_dir"])
        issue_output_dir = issues_public_root / issue["issue_date"]
        issue_media = _load_media(issue_source_dir / "media.json")

        _copy_generated_assets(
            issue_source_dir / "assets" / "generated",
            issue_output_dir / "assets" / "generated",
        )
        _copy_optional_directory(
            issue_source_dir / "assets" / "media",
            issue_output_dir / "assets" / "media",
        )

        issue_assembler = TemplateAssembler(
            stories_path=str(issue_source_dir / "summarized_stories.json"),
            headlines_path=str(issue_source_dir / "headline_picks.json"),
            template_path=str(root / "templates" / "newsletter.html"),
            headline_asset_root=issue_output_dir,
            media=issue_media,
        )
        issue_assembler.run(
            publish_date=issue["issue_date"],
            output_path=str(issue_output_dir / "index.html"),
            latest_issue_url="../../",
            publish_date_is_resolved=True,
        )

    _build_archive_index(root, issue_snapshots)
    return latest_html
