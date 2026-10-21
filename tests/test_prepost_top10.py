import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import monitor
import audio_clips

TZ = ZoneInfo("Europe/Amsterdam")


class BeforeAfterTests(unittest.TestCase):
    def test_announcements_on_both_sides_extract_two_snippets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wav = root / "radio.wav"
            wav.write_bytes(b"\0" * (32000 * 480 + 78))
            out = root / "artifacts"
            event = {"rank": 150, "title": "Master of Puppets",
                     "started_at": "2026-10-30T15:30:00+01:00"}

            def simulate(argv, **kwargs):
                Path(argv[-1]).write_bytes(b"MP3" * 9000)

            with patch.object(audio_clips, "OUT", out), patch(
                "audio_clips.subprocess.run", side_effect=simulate
            ):
                clips = audio_clips.create_announcement_clips(wav, event, song_offset=175,
                                                               next_offset=420)
            self.assertEqual(set(clips), {"voor", "na"})
            self.assertTrue(all(Path(v).is_file() for v in clips.values()))
            self.assertIn("voor", (out / "clip_manifest.json").read_text())
            self.assertIn("na", (out / "clip_manifest.json").read_text())

    def test_missing_end_still_creates_pre_song_clip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wav = root / "radio.wav"
            wav.write_bytes(b"\0" * (32000 * 200 + 78))
            with patch.object(audio_clips, "OUT", root / "artifacts"), patch(
                "audio_clips.subprocess.run",
                side_effect=lambda args, **kw: Path(args[-1]).write_bytes(b"MP3" * 10000),
            ):
                clips = audio_clips.create_announcement_clips(
                    wav, {"rank": 22, "title": "One", "started_at": "2026-10-30T18:00:00+01:00"},
                    song_offset=160, next_offset=None,
                )
            self.assertEqual(set(clips), {"voor"})

    def test_too_late_does_not_fabricate_before_audio(self):
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "radio.wav"
            wav.write_bytes(b"\0" * (32000 * 200 + 78))
            with patch.object(audio_clips, "OUT", Path(td) / "artifacts"), patch(
                "audio_clips.subprocess.run",
                side_effect=lambda args, **kw: Path(args[-1]).write_bytes(b"MP3" * 10000),
            ):
                clips = audio_clips.create_announcement_clips(
                    wav, {"rank": 22, "title": "One", "started_at": "2026-10-30T18:00:00+01:00"},
                    song_offset=-90, next_offset=110,
                )
            self.assertEqual(set(clips), {"na"})

    def test_secret_top10_title_can_be_added_from_playlist(self):
        state = {"tracks": [], "events": []}
        ranking = {11: {"artist": "Muse", "title": "Uprising"},
                   100: {"artist": "Metallica", "title": "One"}}
        played = [{"artist": "Metallica", "title": "Master of Puppets",
                   "started_at": "2026-10-30T18:30:00+01:00"}]
        monitor.update_tracks(state, ranking, played)
        self.assertIn(1, state["top10_unrevealed"])
        candidate = next(t for t in state["tracks"] if t["title"] == "Master of Puppets")
        self.assertLess(candidate["rank"], 0)
        monitor.update_events(state, played)
        self.assertEqual(state["events"][0]["title"], "Master of Puppets")

    def test_secret_top10_trigger_at_rank_15(self):
        t = datetime(2026, 10, 30, 17, 0, tzinfo=TZ)
        rankmap = {15: {"artist": "Muse", "title": "Uprising"},
                   30: {"artist": "Metallica", "title": "One"}}
        state = {"tracks": [{"rank": 30, "title": "One"}],
                 "events": [], "top10_unrevealed": list(range(1,11))}
        played = [{"artist": "Muse", "title": "Uprising", "started_at": t.isoformat()}]
        with patch.object(monitor, "now", return_value=t):
            self.assertEqual(monitor.pick_target(state, rankmap, played), 0)


if __name__ == "__main__":
    unittest.main()
