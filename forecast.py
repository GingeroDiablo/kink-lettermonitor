"""KINK 1500 original daytime airtime forecast.

The contest airs on weekdays 08:00–19:00 Europe/Amsterdam between
19 and 30 October 2026. Overnight repeats are deliberately NOT treated
as evidence of the main list's progress.

All projected times are estimates, not a published KINK timetable.
"""
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo
import math
import unicodedata
import re

TZ = ZoneInfo("Europe/Amsterdam")
DAY_MINUTES = 11 * 60
START = datetime(2026, 10, 19, 8, tzinfo=TZ)
END = datetime(2026, 10, 30, 19, tzinfo=TZ)
DAYS = [
    (START + timedelta(days=i)).date()
    for i in range(12)
    if (START + timedelta(days=i)).weekday() < 5
]
TOTAL_MINUTES = len(DAYS) * DAY_MINUTES
DEFAULT_PACE = TOTAL_MINUTES / 1500


def norm(s):
    value = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def to_broadcast_minute(moment):
    """Map live daytime airtimes onto a continuous 10 x 11-hour timeline."""
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    if moment.tzinfo is None:
        return None
    local = moment.astimezone(TZ)
    if local.date() not in DAYS or not 8 <= local.hour < 19:
        return None
    day = DAYS.index(local.date())
    return day * DAY_MINUTES + (local.hour - 8) * 60 + local.minute + local.second / 60


def from_broadcast_minute(value):
    # Never return a weekend, overnight hour or date after the contest.
    minute = max(0.0, min(TOTAL_MINUTES - 0.01, float(value)))
    day = min(int(minute // DAY_MINUTES), len(DAYS) - 1)
    offset = minute - day * DAY_MINUTES
    return (datetime.combine(DAYS[day], datetime.min.time(), tzinfo=TZ)
            + timedelta(hours=8, minutes=offset)).isoformat(timespec="minutes")


def sample_anchors(state, rankmap, played):
    lookup = {(norm(t.get("artist")), norm(t.get("title"))): rank for rank, t in rankmap.items()}
    gathered = {
        (x["started_at"], x["rank"]): x
        for x in state.get("forecast_anchors", [])
        if isinstance(x, dict) and "started_at" in x and "rank" in x
        and to_broadcast_minute(x["started_at"]) is not None
        and isinstance(x["rank"], int) and 1 <= x["rank"] <= 1500
    }
    for p in played:
        rank = lookup.get((norm(p.get("artist", "")), norm(p.get("title", ""))))
        if rank is None:
            continue
        coord = to_broadcast_minute(p["started_at"])
        if coord is None:
            continue
        key = (p["started_at"], rank)
        gathered[key] = {"started_at": p["started_at"], "rank": rank, "minute": round(coord, 2)}
    valid = sorted(gathered.values(), key=lambda x: to_broadcast_minute(x["started_at"]))
    # Keep a bounded set of samples, including early reference observations.
    state["forecast_anchors"] = (valid[:8] + valid[-100:]) if len(valid) > 108 else valid
    return state["forecast_anchors"]


def estimate_pace(anchors):
    if len(anchors) < 3:
        return DEFAULT_PACE, False
    recent = anchors[-70:]
    sampled = []
    for i, first in enumerate(recent):
        for second in recent[i + 1:]:
            delta_rank = first["rank"] - second["rank"]
            if delta_rank < 15:
                continue
            elapsed = to_broadcast_minute(second["started_at"]) - to_broadcast_minute(first["started_at"])
            if elapsed <= 0:
                continue
            pace = elapsed / delta_rank
            if 2.5 <= pace <= 7.5:
                sampled.append(pace)
    if len(sampled) < 4:
        return DEFAULT_PACE, False
    # Blend with the schedule-wide rate to limit overreaction to talk breaks.
    return round(min(6.2, max(3.1, 0.7 * median(sampled) + 0.3 * DEFAULT_PACE)), 3), True


def update_forecasts(state, rankmap, played):
    anchors = sample_anchors(state, rankmap, played)
    pace, calibrated = estimate_pace(anchors)
    last = anchors[-1] if anchors else None
    last_coord = to_broadcast_minute(last["started_at"]) if last else None
    state["forecast_meta"] = {
        "observations": len(anchors),
        "calibrated": calibrated,
        "pace_minutes_per_position": round(pace, 2),
        "last_observation": last["started_at"] if last else None,
        "assumption": "Werkdagen 08:00-19:00, nachtelijke herhaling niet voorspeld",
    }

    original_events = {}
    for event in state.get("events", []):
        rank = event.get("rank")
        dt = event.get("started_at")
        if not isinstance(rank, int) or not isinstance(dt, str) or to_broadcast_minute(dt) is None:
            continue
        if rank not in original_events or dt < original_events[rank]:
            original_events[rank] = dt

    for track in state.get("tracks", []):
        rank = track.get("rank")
        if not isinstance(rank, int) or not 1 <= rank <= 1500:
            track["prediction"] = None
            continue
        if rank in original_events:
            track["prediction"] = {
                "status": "gedraaid", "estimated_at": original_events[rank],
                "window_start": None, "window_end": None,
                "confidence": "bevestigde playlistwaarneming",
            }
            continue

        baseline_coord = (1500 - rank) * DEFAULT_PACE
        if last is not None:
            gap = last["rank"] - rank
            calibrated_coord = last_coord + gap * pace
            weight_baseline = min(0.55, max(0.0, (abs(gap) - 100) / 900 * 0.55))
            center = calibrated_coord * (1 - weight_baseline) + baseline_coord * weight_baseline
            is_past = gap <= 0
            distance = abs(gap)
        else:
            center, is_past, distance = baseline_coord, False, 1500 - rank

        if last is None:
            spread = 380 + 0.18 * distance
            quality = "globale schatting"
        elif distance <= 30 and calibrated:
            spread, quality = 50, "op basis van actuele uitzending"
        elif distance <= 120 and calibrated:
            spread, quality = 90 + distance * 0.6, "op basis van uitzendtempo"
        else:
            spread = min(840, 145 + 1.2 * distance + (0 if calibrated else 100))
            quality = "ruwe indicatie"
        if is_past:
            status = "waarschijnlijk_al_geweest"
        else:
            status = "verwacht"
        if center > TOTAL_MINUTES - 1:
            center = TOTAL_MINUTES - 1
            quality = "ruwe indicatie (einde van de lijst)"
        if center < 0:
            center = 0
            quality = "ruwe indicatie (begin van de lijst)"
        track["prediction"] = {
            "status": status,
            "estimated_at": from_broadcast_minute(center),
            "window_start": from_broadcast_minute(center - spread),
            "window_end": from_broadcast_minute(center + spread),
            "confidence": quality,
        }
