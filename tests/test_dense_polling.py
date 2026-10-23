"""Regression tests: longer pre-song clip and denser in-job polling."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audio_clips
import poll_monitor


class MoreReliableCaptureTests(unittest.TestCase):
    def test_pre_song_audio_continues_three_minutes_into_song(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wav = root / "recording.wav"
            wav.write_bytes(b"\0" * (32000 * 900 + 78))
            out = root / "clips"
            calls = []

            def fake_ffmpeg(args, **kwargs):
                calls.append(args)
                Path(args[-1]).write_bytes(b"MP3" * 30000)

            with patch.object(audio_clips, "OUT", out), patch(
                "audio_clips.subprocess.run", side_effect=fake_ffmpeg
            ):
                clips = audio_clips.create_announcement_clips(
                    wav, {"rank": 937, "title": "Turn The Page",
                          "started_at": "2026-10-23T10:41:00+02:00"},
                    song_offset=330, next_offset=690,
                )

            self.assertEqual(set(clips), {"voor", "na"})
            before = next(x for x in calls if x[-1].endswith("-voor.mp3"))
            self.assertEqual(float(before[before.index("-ss")+1]), 90)
            self.assertEqual(float(before[before.index("-t")+1]), 420)
            # Window ends at 330 + 180 = 510 seconds; no more +25-second cutoff.
            self.assertEqual(
                float(before[before.index("-ss")+1]) +
                float(before[before.index("-t")+1]), 510,
            )
            self.assertEqual(
                json.loads((out/"clip_manifest.json").read_text())["duration_max_seconds"], 420
            )

    def test_short_recording_ends_clip_at_actual_available_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); wav=root/"recording.wav"
            wav.write_bytes(b"\0" * (32000*330+78))
            calls=[]
            def fake_ffmpeg(args, **kw):
                calls.append(args)
                Path(args[-1]).write_bytes(b"MP3"*20000)
            with patch.object(audio_clips, "OUT", root/"clips"), patch(
                "audio_clips.subprocess.run", side_effect=fake_ffmpeg):
                audio_clips.create_announcement_clips(
                    wav, {"rank":937,"title":"Turn The Page",
                    "started_at":"2026-10-23T10:41:00+02:00"},
                    song_offset=260, next_offset=None)
            self.assertEqual(len(calls),1)
            self.assertEqual(float(calls[0][calls[0].index("-t")+1]), 330)

    def test_45_second_polls_keep_running_until_window_expires(self):
        ticks=[0.]
        sleeps=[]
        state={"last_recording":None}
        def clock():return ticks[0]
        def sleep(seconds):
            sleeps.append(seconds)
            ticks[0]+=seconds
        scans=[]
        result=poll_monitor.run_window(
            duration=180,interval=45,clock=clock,sleep=sleep,
            scan=lambda:scans.append(True),
            state_loader=lambda:state,
        )
        self.assertEqual(result,4)
        self.assertEqual(len(scans),4)
        self.assertEqual(sleeps,[45,45,45])

    def test_no_extra_polls_once_recording_has_happened(self):
        state={"last_recording":None}
        def scan():state["last_recording"]="2026-10-23T10:48:33+02:00"
        count=poll_monitor.run_window(
            duration=180,interval=45,scan=scan,
            state_loader=lambda:state,
            clock=lambda:0,
            sleep=lambda x: self.fail("Must not sleep after recording")
        )
        self.assertEqual(count,1)

    def test_manual_dispatch_completes_after_one_poll(self):
        calls=[]
        count=poll_monitor.run_window(
            duration=0,interval=45,scan=lambda:calls.append(1),
            state_loader=lambda:{"last_recording":None},
            clock=lambda:0,sleep=lambda t:self.fail("No sleep on push")
        )
        self.assertEqual((count,len(calls)),(1,1))


if __name__=="__main__":
    unittest.main()
