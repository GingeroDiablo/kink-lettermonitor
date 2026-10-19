"""Send deduplicated GitHub notifications for Metallica detections and letter proposals.

Requires GITHUB_TOKEN with issues:write; no third party push service.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

DATA = Path(__file__).resolve().parent / "docs/data/state.json"
TZ = ZoneInfo("Europe/Amsterdam")
log = logging.getLogger("alerts")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def emit():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "GingeroDiablo/kink-lettermonitor")
    recipient = os.environ.get("NOTIFY_USER", "GingeroDiablo")
    if not token:
        log.info("No GitHub token; skipping GitHub notifications")
        return
    state = json.loads(DATA.read_text(encoding="utf-8"))
    api = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    dirty = False
    published = 0
    latest = datetime.now(TZ)

    for event in state.get("events", []):
        try:
            when = datetime.fromisoformat(event["started_at"])
        except (KeyError, ValueError):
            continue
        # Do not send historical alerts from older playlist scans.
        if not timedelta(0) <= latest - when <= timedelta(hours=12):
            continue
        rank = event.get("rank", "?")
        song = str(event.get("title", "onbekend nummer"))[:120]
        key = f"{event.get('started_at','')} | {song}"
        letter = event.get("suggested_letter")
        target_url = "https://gingerodiablo.github.io/kink-lettermonitor/"

        try:
            if not event.get("notification_issue"):
                body = (
                    f"@{recipient} — **Metallica is op KINK gedraaid!**\n\n"
                    f"Nummer: **{song}** (positie {rank})\n"
                    f"Tijd: {event.get('started_at', '?')}\n"
                    f"Lettervoorstel: **{letter or 'nog onbekend'}** "
                    "(niet automatisch bevestigd).\n\n"
                    f"Controleer {target_url} en luister indien nodig de herhaling.\n\n"
                    f"Unieke uitzending: {key}\n"
                    "_Automatisch gemeld door KINK Lettermonitor. Niet officieel van KINK._"
                )
                response = requests.post(api, headers=headers, json={
                    "title": f"🎸 Metallica op KINK: {song} — controleer de codeletter",
                    "body": body,
                }, timeout=20)
                response.raise_for_status()
                event["notification_issue"] = response.json()["number"]
                event["notified_letter"] = letter
                dirty = True
                published += 1
                log.info("Notification issue created: #%s", event["notification_issue"])
            elif letter and letter != event.get("notified_letter"):
                url = f"{api}/{event['notification_issue']}/comments"
                response = requests.post(url, headers=headers, json={
                    "body": (f"@{recipient} — **Nieuw, onbevestigd lettervoorstel: "
                             f"{letter}** bij **{song}**. "
                             f"Controleer de transcriptie op {target_url}.")
                }, timeout=20)
                response.raise_for_status()
                event["notified_letter"] = letter
                dirty = True
                published += 1
                log.info("Letter proposal updated for issue #%s", event["notification_issue"])
        except (requests.RequestException, KeyError, TypeError) as exc:
            log.warning("Could not deliver GitHub alert (%s): %s", song, exc)
        if published >= 5:
            break
    if dirty:
        DATA.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("%d new notification(s)", published)


if __name__ == "__main__":
    emit()
