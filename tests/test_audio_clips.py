import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audio_clips


class AudioClipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "artifact_audio"
        self.state = Path(self.temp.name) / "state.json"
        self.event = {
            "rank": 396, "title": "Sad But True",
            "started_at": "2026-10-20T05:29:00+02:00",
        }

    def test_no_clip_if_recording_began_too_late(self):
        with patch.object(audio_clips, "OUT", self.out):
            self.assertIsNone(audio_clips.create_clip(Path("none.wav"), 2, self.event))
        self.assertFalse(self.out.exists())

    def test_create_clip_writes_mp3_and_manifest(self):
        def fake_ffmpeg(argv, **kwargs):
            Path(argv[-1]).write_bytes(b"x" * 25000)

        with patch.object(audio_clips, "OUT", self.out), patch(
            "audio_clips.subprocess.run", side_effect=fake_ffmpeg
        ) as process:
            clip = audio_clips.create_clip(Path("sample.wav"), 150, self.event)
        self.assertEqual(clip.suffix, ".mp3")
        self.assertTrue(clip.is_file())
        self.assertEqual(json.loads((self.out / "clip_manifest.json").read_text())["title"], "Sad But True")
        argv = process.call_args.args[0]
        self.assertEqual(argv[argv.index("-t") + 1], "115.0")
        self.assertEqual(argv[argv.index("-ss") + 1], "60.0")

    def test_register_audio_only_after_confirmed_artifact_upload(self):
        self.out.mkdir()
        (self.out / "clip_manifest.json").write_text(json.dumps({
            "title": "Sad But True",
            "started_at": self.event["started_at"],
            "filename": "clip.mp3",
            "duration_max_seconds": 115,
        }))
        self.state.write_text(json.dumps({"events": [dict(self.event)]}))
        with patch.object(audio_clips, "OUT", self.out), patch.object(
            audio_clips, "STATE", self.state
        ), patch.dict("os.environ", {"AUDIO_ARTIFACT_ID": "", "GITHUB_RUN_ID": "123456"}):
            self.assertFalse(audio_clips.register_artifact())
        self.assertNotIn("audio", json.loads(self.state.read_text())["events"][0])
        with patch.object(audio_clips, "OUT", self.out), patch.object(
            audio_clips, "STATE", self.state
        ), patch.dict("os.environ", {"AUDIO_ARTIFACT_ID": "5555", "GITHUB_RUN_ID": "123456"}):
            self.assertTrue(audio_clips.register_artifact())
        record = json.loads(self.state.read_text())["events"][0]
        self.assertEqual(record["audio"]["artifact_id"], 5555)
        self.assertEqual(record["audio"]["run_id"], 123456)


if __name__ == "__main__":
    unittest.main()
