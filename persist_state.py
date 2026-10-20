"""Persist monitor results safely when scheduled GitHub Actions use stale commits.

The generated results are captured before fetching the latest main branch. Each
retry re-reads the latest state, merges observations and commits from that base.
This avoids 'fetch first' / 'cannot lock ref' failures caused by overlapping
scheduled runs or repository edits.
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

STATE = Path("docs/data/state.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("persist")


def git(*args, check=True):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def moment(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (ValueError, TypeError, AttributeError):
        return -1


def event_key(event):
    return (event.get("started_at"), str(event.get("title", "")).casefold())


def merge_state(remote, candidate):
    """Never let a delayed run roll back newer data or lose a discovered letter."""
    if not isinstance(remote, dict):
        remote = {}
    if not isinstance(candidate, dict):
        candidate = {}
    candidate_is_newer = moment(candidate.get("last_checked")) >= moment(remote.get("last_checked"))
    merged = dict(remote)
    if candidate_is_newer:
        merged.update(candidate)
    else:
        # Keep newer remote status and forecast, yet retain other discoveries.
        for field in ("last_recording",):
            if candidate.get(field) and moment(candidate.get(field)) > moment(remote.get(field)):
                merged[field] = candidate[field]

    remote_events = {event_key(e): e for e in remote.get("events", []) if isinstance(e, dict)}
    candidate_events = {event_key(e): e for e in candidate.get("events", []) if isinstance(e, dict)}
    events = []
    for key in sorted(set(remote_events) | set(candidate_events)):
        older, newer = (remote_events.get(key, {}), candidate_events.get(key, {}))
        if not candidate_is_newer:
            older, newer = newer, older
        entry = dict(older)
        entry.update({k: v for k, v in newer.items() if v is not None})
        # A recorded notification or letter must not disappear due to a stale run.
        for field in ("notification_issue", "notified_letter", "suggested_letter", "transcript", "evidence"):
            if entry.get(field) is None:
                entry[field] = remote_events.get(key, {}).get(field) or candidate_events.get(key, {}).get(field)
        events.append(entry)
    merged["events"] = sorted(events, key=lambda e: e.get("started_at", ""))

    anchors = {}
    for e in remote.get("forecast_anchors", []) + candidate.get("forecast_anchors", []):
        if isinstance(e, dict) and e.get("started_at") and isinstance(e.get("rank"), int):
            anchors[(e["started_at"], e["rank"])] = e
    if anchors:
        merged["forecast_anchors"] = sorted(anchors.values(), key=lambda e: e["started_at"])[-110:]
    return merged


def output_changed(changed):
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(f"changed={'true' if changed else 'false'}\n")


def main():
    candidate = json.loads(STATE.read_text(encoding="utf-8"))
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    for attempt in range(1, 7):
        # Always fetch current main; a scheduled run may have checked out an old SHA.
        result = git("fetch", "--quiet", "origin", "main", check=False)
        if result.returncode:
            log.warning("Fetching main failed: %s", result.stderr.strip())
            time.sleep(2)
            continue
        git("reset", "--hard", "origin/main")
        try:
            remote = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            remote = {}
        merged = merge_state(remote, candidate)
        if merged == remote:
            log.info("No newer radio data to save")
            output_changed(False)
            return

        STATE.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        git("add", str(STATE))
        commit = git("commit", "-m", "Update KINK 1500 results [skip ci]", check=False)
        if commit.returncode:
            if "nothing to commit" in commit.stdout:
                output_changed(False)
                return
            log.error("Commit failed: %s", commit.stderr.strip())
            break
        pushed = git("push", "origin", "HEAD:main", check=False)
        if pushed.returncode == 0:
            log.info("Saved monitor state on current main branch")
            output_changed(True)
            return
        log.warning("Main advanced while saving (attempt %s/6); retrying: %s",
                    attempt, pushed.stderr.strip().splitlines()[-1:])
        time.sleep(min(attempt * 2, 10))
    # GitHub genuinely failed after retries; keep visible failure instead of
    # falsely claiming that results were saved.
    raise SystemExit("State could not be saved after six retries")


if __name__ == "__main__":
    main()
