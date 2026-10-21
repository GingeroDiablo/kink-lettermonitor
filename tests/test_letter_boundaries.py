import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import monitor

TZ = ZoneInfo("Europe/Amsterdam")


class RecognitionBoundaryTests(unittest.TestCase):
    def test_letter_announced_before_song_in_sentence(self):
        s = "En de codeletter voor het Metallica-nummer Wherever I May Roam is de R!"
        self.assertEqual(monitor.letter_from_text(s), "R")

    def test_one_announcement_before_the_song(self):
        fake = types.ModuleType("faster_whisper")

        class Model:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, path, **kwargs):
                text = ("De codeletter voor het volgende nummer is de Q"
                        if "voor" in path else "Dit was Metallica")
                return ([types.SimpleNamespace(text=text)], None)

        fake.WhisperModel = Model
        clips = {"voor": Path("kink-voor.mp3"), "na": Path("kink-na.mp3")}
        with patch.dict(sys.modules, {"faster_whisper": fake}):
            transcript, letter, issue = monitor.recognize_clips(clips)
        self.assertEqual(letter, "Q")
        self.assertIsNone(issue)
        self.assertIn("VOOR:", transcript)
        self.assertIn("NA:", transcript)

    def test_conflicting_announcements_require_manual_verification(self):
        fake = types.ModuleType("faster_whisper")

        class Model:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, path, **kwargs):
                text = ("De codeletter is B" if "voor" in path else "De letter is P")
                return ([types.SimpleNamespace(text=text)], None)

        fake.WhisperModel = Model
        with patch.dict(sys.modules, {"faster_whisper": fake}):
            transcript, letter, issue = monitor.recognize_clips(
                {"voor": Path("voor.mp3"), "na": Path("na.mp3")})
        self.assertIsNone(letter)
        self.assertIn("Tegenstrijdige", issue)

    def test_top_ten_works_without_ranked_playlist_entries(self):
        t = datetime(2026, 10, 30, 18, 10, tzinfo=TZ)
        played = [{"artist": "Muse", "title": "Unknown",
                   "started_at": t.isoformat()}]
        state = {"events": [], "tracks": [], "top10_unrevealed": list(range(1, 11))}
        with patch.object(monitor, "now", return_value=t):
            self.assertEqual(monitor.pick_target(state, {}, played), 0)


if __name__ == "__main__":
    unittest.main()
