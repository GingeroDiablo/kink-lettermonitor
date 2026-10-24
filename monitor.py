"""KINK 1500 Metallica codeletter watcher; runs on free public GitHub Actions."""
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from forecast import update_forecasts, is_original_airtime
from audio_clips import create_announcement_clips

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "docs/data/state.json"
TZ = ZoneInfo("Europe/Amsterdam")
UTC = timezone.utc
LIST_URL = "https://kink.nl/hitlists/kink-1500"
PLAY_URL = "https://kink.nl/gedraaid/kink/{}"
STREAM_URL = os.getenv("STREAM_URL", "https://playerservices.streamtheworld.com/api/livestream-redirect/KINKAAC.aac")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kink")
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (KINK 1500 persoonlijke codelettermonitor)"})

def now():
    return datetime.now(TZ)

def normalized(s):
    x = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", x).strip()

def strings(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    return [t.strip() for t in root.stripped_strings if t.strip()]

def fetch(url):
    response = session.get(url, params={"cache": int(time.time() / 60)}, timeout=22)
    response.raise_for_status()
    return response.text

def rankings():
    values = strings(fetch(LIST_URL))
    result = {}
    for i in range(len(values) - 1):
        if not re.fullmatch(r"[1-9]\d{0,3}", values[i]):
            continue
        rank = int(values[i])
        match = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", values[i + 1])
        if 1 <= rank <= 1500 and match:
            result[rank] = {"artist": match.group(1).strip(), "title": match.group(2).strip()}
        elif 1 <= rank <= 1500 and i + 3 < len(values) and values[i + 2] in ("-", "–", "—"):
            result[rank] = {"artist": values[i + 1].strip(), "title": values[i + 3].strip()}
    if len(result) < 1100:
        log.warning("Hitlijst debug: %s tokens, eerste 35 = %r", len(values), values[:35])
        raise ValueError("KINK hitlijst niet volledig leesbaar (" + str(len(result)) + " posities)")
    return result

def plays_for(day):
    values = strings(fetch(PLAY_URL.format(day.isoformat())))
    unique = {}
    for i in range(len(values) - 2):
        artist, title, clock = values[i:i + 3]
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
            continue
        if len(artist) > 100 or len(title) > 150 or not artist or not title:
            continue
        # KINK pages can contain schedule headings such as "06:00 - 09:00".
        # They are not playable songs, even though they resemble a three-token row.
        if artist.strip() in ("-", "–", "—") or title.strip() in ("-", "–", "—"):
            continue
        if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", artist):
            continue
        if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", title):
            continue
        hour, minute = map(int, clock.split(":"))
        dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)
        if normalized(artist) in ("kink 1500", "kink", "gedraaid op kink"):
            continue
        unique[(dt.isoformat(), normalized(artist), normalized(title))] = {
            "started_at": dt.isoformat(), "artist": artist, "title": title
        }
    return sorted(unique.values(), key=lambda p: p["started_at"])

def recent():
    t = now()
    items = plays_for(t.date())
    if t.hour == 0:
        try:
            items = plays_for(t.date() - timedelta(days=1)) + items
        except Exception as exc:
            log.warning("Gisteren niet beschikbaar: %s", exc)
    # A malformed page block may look like an item scheduled in the future.
    items = [p for p in items if datetime.fromisoformat(p["started_at"]) <= t + timedelta(minutes=1)]
    if len(items) < 4:
        raise ValueError("KINK afspeellijst bevat onvoldoende nummers")
    return sorted(items, key=lambda p: p["started_at"])

def in_window(t):
    return t.year == 2026 and t.month == 10 and (
        (19 <= t.day <= 30 and (t.day != 19 or t.hour >= 8)) or
        (t.day == 31 and t.hour < 8)
    )

def load():
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(state.get("events"), list):
            return state
    except (OSError, ValueError, TypeError):
        pass
    return {"version": 2, "tracks": [], "events": [], "last_checked": None}

def save(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def update_tracks(state, rankmap, played):
    official = [{"rank": k, "title": v["title"]} for k, v in rankmap.items()
                if normalized(v["artist"]) == "metallica"]
    known = {normalized(t["title"]): t["rank"] for t in official}
    unknown_rank = {normalized(t["title"]): t["rank"] for t in state.get("tracks", [])
                    if t.get("rank", 0) < 0}
    for old in state.get("tracks", []):
        if old["rank"] < 0 and normalized(old["title"]) not in known:
            official.append(old)
    for e in state["events"]:
        if e.get("rank", 0) < 0 and normalized(e["title"]) in known:
            e["rank"] = known[normalized(e["title"])]
    # Track every heard Metallica title, including undisclosed top-10 songs.
    for p in played:
        if normalized(p["artist"]) != "metallica":
            continue
        song = normalized(p["title"])
        if song not in known and song not in {normalized(t["title"]) for t in official}:
            temp_rank = unknown_rank.get(song)
            if temp_rank is None:
                temp_rank = min([0] + [t["rank"] for t in official]) - 1
            official.append({"rank": temp_rank, "title": p["title"], "provisional": True})
            unknown_rank[song] = temp_rank
    state["tracks"] = sorted(official, key=lambda t: -t["rank"])
    state["top10_unrevealed"] = [rank for rank in range(1, 11) if rank not in rankmap]

def update_events(state, played):
    title_to_rank = {normalized(t["title"]): t["rank"] for t in state["tracks"]}
    found = {(e["rank"], e["started_at"]): e for e in state["events"]}
    for i, p in enumerate(played):
        if normalized(p["artist"]) != "metallica" or normalized(p["title"]) not in title_to_rank:
            continue
        dt = datetime.fromisoformat(p["started_at"])
        if not in_window(dt):
            continue
        rank = title_to_rank[normalized(p["title"])]
        key = (rank, p["started_at"])
        if key not in found:
            event = {"rank": rank, "title": p["title"], "started_at": p["started_at"],
                     "ended_at": None, "status": "Gezien; nog geen letter",
                     "suggested_letter": None, "transcript": None, "evidence": None,
                     "replay": not is_original_airtime(dt)}
            state["events"].append(event)
            found[key] = event
        # Re-evaluate older stored observations using the actual weekend
        # countdown schedule; 06:00–08:00 on Sat/Sun is NOT a replay.
        found[key]["replay"] = not is_original_airtime(dt)
        if i + 1 < len(played):
            found[key]["ended_at"] = played[i + 1]["started_at"]
    state["events"].sort(key=lambda e: e["started_at"])

def replay_delay_minutes(state):
    """Infer overnight replay offset from confirmed original/replay pairs."""
    found = {}
    for event in state.get("events", []):
        dt = datetime.fromisoformat(event["started_at"]).astimezone(TZ)
        kind = "original" if is_original_airtime(dt) else "replay"
        # Night repeats after midnight refer to the preceding broadcast day.
        broadcast_day = (dt - timedelta(days=1)).date() if (
            kind == "replay" and dt.hour < 6
        ) else dt.date()
        key = (normalized(event["title"]), broadcast_day)
        found.setdefault(key, {}).setdefault(kind, []).append(dt)
    intervals = []
    for pair in found.values():
        for original in pair.get("original", []):
            for repeat in pair.get("replay", []):
                delta = (repeat - original).total_seconds() / 60
                if 600 <= delta <= 780:
                    intervals.append(delta)
    # Fallback across the variable weekend/weekday repeat schedule.
    if not intervals:
        return 660
    return round(sorted(intervals)[len(intervals)//2])


def upcoming_replay(state, timestamp):
    """Select an upcoming repeated song before GitHub's next delayed run."""
    local = timestamp.astimezone(TZ)
    # KINK repeats the daytime list after 19:00, not a continuously
    # advancing ranking at night. Predict from *today's* original plays.
    if is_original_airtime(local):
        return None
    broadcast_date = (local - timedelta(days=1)).date() if local.hour < 6 else local.date()
    shift = replay_delay_minutes(state)
    options = []
    for event in state.get("events", []):
        original = datetime.fromisoformat(event["started_at"]).astimezone(TZ)
        if not is_original_airtime(original) or original.date() != broadcast_date:
            continue
        if event.get("rank", 0) <= 0:
            continue
        repeats = [
            repeat for repeat in state.get("events", [])
            if repeat.get("title") == event.get("title")
            and repeat.get("replay")
            and datetime.fromisoformat(repeat["started_at"]).astimezone(TZ).date() >= broadcast_date
        ]
        # A replay already heard with no clip cannot be recovered afterwards.
        if repeats:
            continue
        estimated = original + timedelta(minutes=shift)
        seconds_to_start = (estimated - timestamp).total_seconds()
        if -150 <= seconds_to_start <= 40 * 60:
            options.append((abs(seconds_to_start - 16*60), event["rank"]))
    return min(options)[1] if options else None


def pick_target(state, rankmap, played):
    t = now()
    if not in_window(t):
        return None
    # Check expected overnight repeats even when the current rank has moved
    # backwards to the start of the day's list.
    replay_target = upcoming_replay(state, t)
    if replay_target is not None:
        return replay_target
    last = [p for p in played if -45 <= (t - datetime.fromisoformat(p["started_at"])).total_seconds() <= 14 * 60]
    if not last:
        return None
    tracks = state["tracks"]
    lastplay = last[-1]
    if normalized(lastplay["artist"]) == "metallica":
        age = (t - datetime.fromisoformat(lastplay["started_at"])).total_seconds()
        if 0 <= age <= 9 * 60:
            for track in tracks:
                if normalized(track["title"]) == normalized(lastplay["title"]):
                    return track["rank"]
            return 0  # Unknown Metallica title: listen even if not on published list.
    ranked = {}
    for rank, item in rankmap.items():
        ranked[(normalized(item["artist"]), normalized(item["title"]))] = rank
    last_rank = None
    for p in reversed(last[-8:]):
        x = ranked.get((normalized(p["artist"]), normalized(p["title"])))
        if x:
            last_rank = x
            break
    # At the end of the final broadcast day, published ranks can run out
    # altogether. Continue listening for any new Metallica title.
    if (state.get("top10_unrevealed") and t.year == 2026 and t.month == 10
            and t.day == 30 and 15 <= t.hour < 19):
        return 0
    if not last_rank:
        return None
    # Don't presume the secret top 10 contains zero Metallica titles.
    if last_rank <= 19 and state.get("top10_unrevealed"):
        return 0
    # Arm as far as ten playlist places before Metallica. GitHub can start
    # many minutes late, so waiting until the song itself is visible loses
    # the presenter introduction. Early runs can time out; later runs retry.
    for track in tracks:
        if track["rank"] < 1 or not 0 <= last_rank - track["rank"] <= 10:
            continue
        proposals = sum(bool(e.get("suggested_letter")) for e in state["events"] if e["rank"] == track["rank"])
        if proposals >= 2:
            continue
        recent_ended = [datetime.fromisoformat(e["ended_at"]) for e in state["events"]
                        if e["rank"] == track["rank"] and e.get("ended_at")]
        if recent_ended and 0 <= (t - max(recent_ended)).total_seconds() < 25 * 60:
            continue
        return track["rank"]
    return None

def letter_from_text(text):
    candidates = re.findall(
        r"\b(?:codeletter|code\s*letter|de\s+letter|letter)\s*"
        r"(?:is|was|luidt|wordt|:|van)?\s*(?:de\s+)?([A-Za-z])(?=\W|$)",
        text, flags=re.IGNORECASE
    )
    # Presenters sometimes say the letter *before* the song, with the
    # song title between "letter" and "is". Keep the explicit cue requirement.
    candidates += re.findall(
        r"\b(?:codeletter|code\s*letter|de\s+letter|letter)\b"
        r"[^.!?\n]{0,100}?\b(?:is|was|wordt|luidt)\s+(?:de\s+)?([A-Za-z])(?=\W|$)",
        text, flags=re.IGNORECASE,
    )
    candidates = {c.upper() for c in candidates}
    return next(iter(candidates)) if len(candidates) == 1 else None

def recognize_clips(clips):
    """Transcribe BEFORE and AFTER snippets independently and compare proposals."""
    if not clips:
        return None, None, "Geen geluidsfragment ontvangen"
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        subprocess.run(
            ["python", "-m", "pip", "install", "-q", "faster-whisper>=1.1,<2", "av<19"],
            check=True, timeout=300,
        )
        from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    texts = {}
    candidates = set()
    for label, path in clips.items():
        segments, _ = model.transcribe(str(path), language="nl",
                                       vad_filter=True, beam_size=3,
                                       condition_on_previous_text=False)
        speech = " ".join(part.text.strip() for part in segments)[:1300]
        texts[label] = speech
        proposed = letter_from_text(speech)
        if proposed:
            candidates.add(proposed)
    summary = " | ".join(f"{k.upper()}: {v or '(niets herkend)'}" for k, v in texts.items())
    if len(candidates) == 1:
        return summary, next(iter(candidates)), None
    if len(candidates) > 1:
        return summary, None, "Tegenstrijdige letters gehoord; controleer zelf"
    return summary, None, "Geen expliciete codeletter herkend; luister fragmenten terug"


def record(state, rank, rankmap):
    """Begin before the track where possible; retain speech from both sides."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg ontbreekt; opname is niet uitgevoerd")
    target = next((track for track in state["tracks"] if track["rank"] == rank), None)
    requested_title = normalized(target["title"]) if target else None
    log.info("Live stream bewaken rond %s",
             target["title"] if target else "onbekend top-10 Metallica-nummer")
    with tempfile.TemporaryDirectory(prefix="kink-") as directory:
        audio = Path(directory) / "live.wav"
        errorlog = Path(directory) / "ffmpeg-stderr.log"
        origin = datetime.now(UTC)
        with errorlog.open("wb") as errors:
            process = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-reconnect", "1", "-reconnect_streamed", "1",
                 "-reconnect_delay_max", "5",
                 "-i", STREAM_URL, "-t", "2100", "-vn", "-ac", "1",
                 "-ar", "16000", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=errors,
            )
            detected = None
            started = ended = None
            try:
                deadline = time.monotonic() + 2050
                while time.monotonic() < deadline and process.poll() is None:
                    time.sleep(18)
                    try:
                        playlist = recent()
                        update_tracks(state, rankmap, playlist)
                        update_events(state, playlist)
                        matches = [
                            (i, p) for i, p in enumerate(playlist)
                            if normalized(p["artist"]) == "metallica"
                            and (requested_title is None
                                 or normalized(p["title"]) == requested_title)
                            and -540 <= (now() - datetime.fromisoformat(
                                p["started_at"])).total_seconds() <= 15 * 60
                            and (datetime.fromisoformat(p["started_at"])
                                 .astimezone(UTC) >= origin - timedelta(minutes=6))
                        ]
                        if not matches:
                            continue
                        i, p = matches[-1]
                        detected = p
                        started = datetime.fromisoformat(p["started_at"])
                        if i + 1 < len(playlist):
                            ended = datetime.fromisoformat(playlist[i + 1]["started_at"])
                            if now() >= ended + timedelta(seconds=78):
                                break
                    except Exception as exc:
                        log.warning("Afspeellijst tijdelijk niet leesbaar: %s", exc)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        size = audio.stat().st_size if audio.exists() else 0
        if size < 70000:
            details = errorlog.read_text(errors="replace")[-420:]
            raise ValueError("Geen geluid uit KINK-stream ontvangen: " + details)
        state["last_recording"] = now().isoformat()
        if not detected:
            log.info("Binnen opnamevenster geen Metallica-uitzending gedetecteerd")
            return False

        # Always associate the recording with a playlist event, even if the
        # next song has not yet appeared and the post-song clip is impossible.
        event = next((e for e in state["events"]
                      if e["started_at"] == detected["started_at"]
                      and normalized(e["title"]) == normalized(detected["title"])), None)
        if event is None:
            update_tracks(state, rankmap, [detected])
            update_events(state, [detected])
            event = next((e for e in state["events"]
                          if e["started_at"] == detected["started_at"]
                          and normalized(e["title"]) == normalized(detected["title"])), None)
        if event is None:
            state["last_error"] = "Geluid opgenomen maar uitzending niet gekoppeld aan playlist"
            log.warning(state["last_error"])
            return False

        begin_offset = (started.astimezone(UTC) - origin).total_seconds()
        end_offset = ((ended.astimezone(UTC) - origin).total_seconds()
                      if ended else None)
        # This is a measurement, not a promise: a GitHub runner cannot
        # recover the announcer's speech from before FFmpeg actually started.
        event["recording_started_at"] = origin.isoformat()
        event["pre_song_recorded_seconds"] = round(max(0.0, begin_offset))
        event["pre_song_available"] = begin_offset >= 25
        if begin_offset < 25:
            log.warning("Opname van %s startte %ds na de geregistreerde start "
                        "(of met minder dan 25s voorloop); geen 'voor'-fragment",
                        event["title"], max(0, round(-begin_offset)))
        else:
            log.info("Opname van %s begon circa %ds voor de track",
                     event["title"], round(begin_offset))
        clips = create_announcement_clips(audio, event, begin_offset, end_offset)
        if not clips:
            event["status"] = "OPNAME ONVOLLEDIG"
            event["evidence"] = "Geen bruikbaar audiofragment rond begin of einde"
            state["last_error"] = event["evidence"]
            return False
        try:
            text, suggestion, issue = recognize_clips(clips)
        except Exception as exc:
            text, suggestion, issue = None, None, "Spraakherkenning: " + str(exc)[:160]
        event.update(transcript=text, suggested_letter=suggestion,
                     evidence=("Onbevestigd voorstel; luister fragmenten terug"
                               if suggestion else issue),
                     status=("LETTERVOORSTEL" if suggestion else
                             "AUDIO BESCHIKBAAR – LETTER CONTROLEREN"))
        log.info("Metallica %s: %s (voor/na: %s)",
                 event["title"], suggestion or "geen bevestigde letter",
                 ",".join(clips))
        return True

def main():
    prior = load()
    state = json.loads(json.dumps(prior))
    t = now()
    if not in_window(t):
        log.info("Buiten de wedstrijdperiode; geen actie.")
        return
    try:
        rankmap = rankings()
        played = recent()
        update_tracks(state, rankmap, played)
        update_events(state, played)
        update_forecasts(state, rankmap, played)
        last = played[-1]
        state["now_playing"] = {k: last[k] for k in ("artist", "title", "started_at")}
        target = pick_target(state, rankmap, played)
        state["status"] = "KINK gedraaid gecontroleerd; wacht op Metallica"
        state["last_error"] = None
        if target is not None:
            state["status"] = "Opname gestart rond Metallica #" + str(target)
            captured = record(state, target, rankmap)
            if captured:
                state["status"] = "Audiofragmenten gemaakt; codeletter zelf controleren"
            elif not state.get("last_error"):
                state["status"] = "Luistervenster voltooid; geen nieuw fragment"
    except Exception as exc:
        log.exception("Monitorcontrole mislukt")
        state["last_error"] = str(exc)[:300]
        state["status"] = "Controlefout"
    state["last_checked"] = now().isoformat()
    # Persist an explicit heartbeat on every completed scan. A static GitHub
    # Pages site otherwise looks frozen when nothing interesting is playing.
    # GitHub's scheduler can still delay or skip an entire scan.
    save(state)
    log.info("Controle afgerond en laatste scantijd opgeslagen")

if __name__ == "__main__":
    main()
