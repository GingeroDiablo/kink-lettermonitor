"""KINK 1500 original daytime airtime forecast.

The countdown runs on all 12 calendar days, 19–30 October 2026.
Weekday daytime is modelled at 08:00–19:00 (KINK's announced hours).
The published radio schedule lists weekend originals 06:00–18:00;
the evening/night programme repeats are not new ranking progress.

All projected times are estimates, not a published per-song timetable.
"""
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo
import math
import unicodedata
import re

TZ = ZoneInfo("Europe/Amsterdam")
START = datetime(2026, 10, 19, 8, tzinfo=TZ)
END = datetime(2026, 10, 30, 19, tzinfo=TZ)
DAYS = [(START + timedelta(days=i)).date() for i in range(12)]

# All 12 days advance the countdown. Published weekend programming starts at
# 06:00 and repeats from 18:00; weekdays keep the advertised 08:00–19:00
# estimate. Keep the local timezone to handle the 25 October DST change.
DAY_HOURS = {day: ((6, 18) if day.weekday() >= 5 else (8, 19)) for day in DAYS}
DAY_OFFSETS = {}
TOTAL_MINUTES = 0
for day in DAYS:
    DAY_OFFSETS[day] = TOTAL_MINUTES
    opening, closing = DAY_HOURS[day]
    TOTAL_MINUTES += (closing - opening) * 60
DEFAULT_PACE = TOTAL_MINUTES / 1500


def norm(s):
    value = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def is_original_airtime(moment):
    """Whether a local timestamp belongs to a new ranked countdown slot."""
    return to_broadcast_minute(moment) is not None


def to_broadcast_minute(moment):
    """Convert a daytime airing to the continuous 12-day countdown axis."""
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    if moment.tzinfo is None:
        return None
    local = moment.astimezone(TZ)
    day = local.date()
    if day not in DAY_HOURS:
        return None
    opening, closing = DAY_HOURS[day]
    if not opening <= local.hour < closing:
        return None
    return (DAY_OFFSETS[day] + (local.hour - opening) * 60
            + local.minute + local.second / 60)


def from_broadcast_minute(value):
    """Convert countdown progress back to a day/time, including the weekend."""
    minute = max(0.0, min(TOTAL_MINUTES - 0.01, float(value)))
    for day in DAYS:
        opening, closing = DAY_HOURS[day]
        duration = (closing - opening) * 60
        if minute < DAY_OFFSETS[day] + duration:
            return (datetime.combine(day, datetime.min.time(), tzinfo=TZ)
                    + timedelta(hours=opening, minutes=minute - DAY_OFFSETS[day])
                    ).isoformat(timespec="minutes")
    raise AssertionError("All broadcast minutes must map to a scheduled day")


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
        "assumption": "Alle 12 dagen; ma-vr 08:00-19:00, za-zo 06:00-18:00; herhalingen uitgesloten",
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
