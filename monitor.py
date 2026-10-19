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
    for old in state.get("tracks", []):
        if old["rank"] < 0 and normalized(old["title"]) not in known:
            official.append(old)
    for e in state["events"]:
        if e.get("rank", 0) < 0 and normalized(e["title"]) in known:
            e["rank"] = known[normalized(e["title"])]
    for p in played[-12:]:
        dt = datetime.fromisoformat(p["started_at"])
        if normalized(p["artist"]) != "metallica":
            continue
        if not (0 <= (now() - dt).total_seconds() <= 18 * 60):
            continue
        if normalized(p["title"]) not in {normalized(t["title"]) for t in official}:
            temp_rank = min([0] + [t["rank"] for t in official]) - 1
            official.append({"rank": temp_rank, "title": p["title"]})
    state["tracks"] = sorted(official, key=lambda t: -t["rank"])

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
                     "replay": dt.hour >= 19 or dt.hour < 8}
            state["events"].append(event)
            found[key] = event
        if i + 1 < len(played):
            found[key]["ended_at"] = played[i + 1]["started_at"]
    state["events"].sort(key=lambda e: e["started_at"])

def pick_target(state, rankmap, played):
    t = now()
    if not in_window(t):
        return None
    last = [p for p in played if -45 <= (t - datetime.fromisoformat(p["started_at"])).total_seconds() <= 14 * 60]
    if not last:
        return None
    tracks = state["tracks"]
    lastplay = last[-1]
    if normalized(lastplay["artist"]) == "metallica":
        for track in tracks:
            if normalized(track["title"]) == normalized(lastplay["title"]):
                age = (t - datetime.fromisoformat(lastplay["started_at"])).total_seconds()
                if 0 <= age <= 8 * 60:
                    return track["rank"]
    ranked = {}
    for rank, item in rankmap.items():
        ranked[(normalized(item["artist"]), normalized(item["title"]))] = rank
    last_rank = None
    for p in reversed(last[-8:]):
        x = ranked.get((normalized(p["artist"]), normalized(p["title"])))
        if x:
            last_rank = x
            break
    if not last_rank:
        return None
    for track in tracks:
        if not 0 <= last_rank - track["rank"] <= 3:
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
    candidates = {c.upper() for c in candidates}
    return next(iter(candidates)) if len(candidates) == 1 else None

def recognize(wav, ending_offset):
    # Crop only around the announcement, never publish or persist music.
    if ending_offset < 25:
        return None, None, "Opname begon te laat"
    clip = wav.parent / "announcement.wav"
    start = max(0, ending_offset - 75)
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(start), "-t", "180", "-i", str(wav),
                    "-vn", "-ac", "1", "-ar", "16000", str(clip)],
                   capture_output=True, timeout=80, check=True)
    if clip.stat().st_size < 40000:
        return None, None, "Audioclip leeg"
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        subprocess.run(["python", "-m", "pip", "install", "-q", "faster-whisper>=1.1,<2"],
                       check=True, timeout=300)
        from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(clip), language="nl", vad_filter=True, beam_size=5,
        initial_prompt="KINK 1500 Metallica, de codeletter is een letter van het alfabet."
    )
    transcript = " ".join(s.text.strip() for s in segments)[:1500]
    return transcript, letter_from_text(transcript), None

def record(state, rank):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg ontbreekt")
    target = next(t for t in state["tracks"] if t["rank"] == rank)
    log.info("Live KINK opnemen rond Metallica #%s %s", rank, target["title"])
    with tempfile.TemporaryDirectory(prefix="kink-") as directory:
        audio = Path(directory) / "live.wav"
        start_time = datetime.now(UTC)
        process = subprocess.Popen(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
             "-i", STREAM_URL, "-t", "1650", "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(audio)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        start = end = None
        try:
            deadline = time.monotonic() + 1600
            while time.monotonic() < deadline and process.poll() is None:
                time.sleep(30)
                try:
                    played = recent()
                    update_events(state, played)
                    matches = [(i, p) for i, p in enumerate(played)
                               if normalized(p["artist"]) == "metallica"
                               and normalized(p["title"]) == normalized(target["title"])
                               and -30 <= (now() - datetime.fromisoformat(p["started_at"])).total_seconds() <= 2400]
                    if not matches:
                        continue
                    i, p = matches[-1]
                    start = p["started_at"]
                    if i + 1 < len(played):
                        end = datetime.fromisoformat(played[i + 1]["started_at"])
                        if now() >= end + timedelta(seconds=115):
                            break
                except Exception as exc:
                    log.warning("Playlist tijdelijk niet leesbaar: %s", exc)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if not audio.exists() or audio.stat().st_size < 70000:
            raise ValueError("Geen audio ontvangen van de KINK-radiostream")
        state["last_recording"] = now().isoformat()
        if start is None or end is None:
            state["last_error"] = "Opname gemaakt, maar geen eindtijd van Metallica bevestigd"
            return
        offset = (end.astimezone(UTC) - start_time).total_seconds()
        try:
            text, suggestion, issue = recognize(audio, offset)
        except Exception as exc:
            text, suggestion, issue = None, None, "Spraakherkenning: " + str(exc)[:160]
        event = next((e for e in state["events"] if e["rank"] == rank and e["started_at"] == start), None)
        if event is None:
            event = {"rank": rank, "title": target["title"], "started_at": start, "replay": False}
            state["events"].append(event)
        event.update(ended_at=end.isoformat(), transcript=text,
                     suggested_letter=suggestion,
                     evidence=("Automatisch herkend; controleer transcript" if suggestion else issue),
                     status=("LETTERVOORSTEL" if suggestion else "TRANSCRIPT CONTROLEREN"))
        state["last_error"] = issue

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
        last = played[-1]
        state["now_playing"] = {k: last[k] for k in ("artist", "title", "started_at")}
        target = pick_target(state, rankmap, played)
        state["status"] = "KINK gedraaid gecontroleerd; wacht op Metallica"
        state["last_error"] = None
        if target is not None:
            state["status"] = "Opname gestart rond Metallica #" + str(target)
            record(state, target)
            state["status"] = "Opname afgerond; letters zelf verifiëren"
    except Exception as exc:
        log.exception("Monitorcontrole mislukt")
        state["last_error"] = str(exc)[:300]
        state["status"] = "Controlefout"
    state["last_checked"] = now().isoformat()
    meaningful = any(prior.get(k) != state.get(k) for k in ("tracks", "events", "last_error", "last_recording"))
    if not meaningful and prior.get("last_checked"):
        try:
            meaningful = (datetime.fromisoformat(state["last_checked"]) -
                          datetime.fromisoformat(prior["last_checked"])).total_seconds() > 40 * 60
        except (ValueError, TypeError):
            meaningful = True
    if meaningful or not prior.get("last_checked"):
        save(state)
        log.info("Status en resultaten opgeslagen")
    else:
        log.info("Geen wijzigingen")

if __name__ == "__main__":
    main()
