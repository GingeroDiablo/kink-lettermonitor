"""Short-lived, opt-in personal listen-back clips for KINK monitor events.

Never put sound files in /docs or git. Sound is transferred only as a
short-retention GitHub Actions artifact, requiring a GitHub download.
"""
import json
import logging
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifact_audio"
STATE = ROOT / "docs/data/state.json"
log = logging.getLogger("clips")


def clip_name(event):
    stamp = re.sub(r"[^0-9]", "", event.get("started_at", ""))[:12] or "unknown"
    rank = str(event.get("rank", "?")).replace("-", "m")
    name = re.sub(r"[^a-z0-9]+", "-", event.get("title", "").lower()).strip("-")[:36]
    return f"kink-{stamp}-{rank}-{name}.mp3"


def create_clip(recording, ending_offset, event):
    """Create <=115 seconds near next-track start; DJ speech is typically before it.

    The playlist records when the *following song starts*, not necessarily
    when Metallica stops. Keep a pre-roll to capture spoken announcements.
    """
    if ending_offset < 15:
        log.info("No recording around handoff; clip is unavailable")
        return None
    start = max(0, float(ending_offset) - 90)
    duration = min(115.0, max(0.0, float(ending_offset) + 25 - start))
    if duration < 10:
        return None
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / clip_name(event)
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", str(round(start, 2)), "-t", str(round(duration, 2)),
             "-i", str(recording), "-vn", "-ac", "1", "-ar", "22050",
             "-c:a", "libmp3lame", "-b:a", "56k", str(dest)],
            check=True, capture_output=True, timeout=75,
        )
        if dest.stat().st_size < 20000:
            dest.unlink(missing_ok=True)
            log.warning("Audio clip too short, not uploading")
            return None
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        dest.unlink(missing_ok=True)
        log.warning("Audio clip extraction failed: %s", exc)
        return None
    manifest = {
        "title": event["title"],
        "started_at": event["started_at"],
        "filename": dest.name,
        "duration_max_seconds": int(duration),
    }
    (OUT / "clip_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Created listen-back clip for %s: %s", event["title"], dest.name)
    return dest



def create_announcement_clips(recording, event, song_offset=None, next_offset=None):
    """Extract before-song and after-song fragments when available.

    Offsets are seconds relative to recording start; a late recorder
    cannot recover a pre-song announcement.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    clips = {}
    base = clip_name(event).removesuffix(".mp3")
    windows = []
    # Give the presenter room to speak well into the song. Playlist timestamps
    # can be approximate; the older +25s cutoff truncated real announcements.
    # Include ~4 minutes before and ~3 minutes into Metallica if recorded.
    if song_offset is not None and song_offset >= 25:
        windows.append(("voor", max(0, song_offset - 240), song_offset + 180))
    if next_offset is not None and next_offset >= 25:
        windows.append(("na", max(0, next_offset - 80), next_offset + 75))
    duration_estimate = (recording.stat().st_size - 78) / 32000 if recording.exists() else 0
    for label, first, last in windows:
        if duration_estimate < first + 12:
            continue
        duration = min(420.0 if label == "voor" else 160.0,
                       last - first, duration_estimate - first)
        if duration < 12:
            continue
        dest = OUT / f"{base}-{label}.mp3"
        try:
            subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-ss", str(round(first, 2)), "-t", str(round(duration, 2)),
                 "-i", str(recording), "-vn", "-ac", "1", "-ar", "22050",
                 "-c:a", "libmp3lame", "-b:a", "56k", str(dest)],
                capture_output=True, timeout=75, check=True,
            )
            if dest.stat().st_size < 20000:
                dest.unlink(missing_ok=True)
                continue
            clips[label] = str(dest)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log.warning("Audio %s was not created: %s", label, exc)
            dest.unlink(missing_ok=True)
    if clips:
        (OUT / "clip_manifest.json").write_text(json.dumps({
            "title": event["title"], "started_at": event["started_at"],
            "filename": Path(next(iter(clips.values()))).name,
            "files": {k: Path(v).name for k, v in clips.items()},
            "duration_max_seconds": 420,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Prepared %s listen-back clip(s) for %s", len(clips), event["title"])
    return clips


def register_artifact():
    """Attach link only after upload-artifact has returned a real artifact ID."""
    artifact = os.getenv("AUDIO_ARTIFACT_ID", "").strip()
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    if not artifact.isdecimal() or not run_id.isdecimal():
        log.info("Artifact was not uploaded; no public link will be shown")
        return False
    manifest_path = OUT / "clip_manifest.json"
    if not manifest_path.is_file():
        log.info("No audio manifest; nothing to link")
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8"))
    matched = False
    for event in state.get("events", []):
        if event.get("started_at") == manifest["started_at"] and event.get("title") == manifest["title"]:
            event["audio"] = {
                "run_id": int(run_id),
                "artifact_id": int(artifact),
                "filename": manifest["filename"],
                "files": manifest.get("files", {"na": manifest["filename"]}),
                "retention_days": 3,
                "duration_max_seconds": manifest["duration_max_seconds"],
            }
            matched = True
            break
    if matched:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log.info("Attached GitHub Actions audio artifact %s", artifact)
    else:
        log.warning("No matching playlist event for audio clip; artifact remains in run")
    return matched


if __name__ == "__main__":
    register_artifact()
