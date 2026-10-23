"""Protect proactive pre-song capture on the KINK 1500 list."""
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import monitor

TZ = ZoneInfo("Europe/Amsterdam")


class EarlyCaptureTests(unittest.TestCase):
    def test_arms_before_metallica_when_ten_positions_away(self):
        timestamp = datetime(2026, 10, 23, 15, 55, tzinfo=TZ)
        rankmap = {
            872: {"artist": "Some Band", "title": "Earlier Track"},
            862: {"artist": "Metallica", "title": "Until it Sleeps"},
        }
        state = {
            "tracks": [{"rank": 862, "title": "Until it Sleeps"}],
            "events": [],
            "top10_unrevealed": [],
        }
        played = [{
            "artist": "Some Band", "title": "Earlier Track",
            "started_at": timestamp.isoformat(),
        }]
        with patch.object(monitor, "now", return_value=timestamp):
            self.assertEqual(monitor.pick_target(state, rankmap, played), 862)

    def test_does_not_arm_too_early(self):
        timestamp = datetime(2026, 10, 23, 15, 45, tzinfo=TZ)
        rankmap = {
            873: {"artist": "Some Band", "title": "Earlier Track"},
            862: {"artist": "Metallica", "title": "Until it Sleeps"},
        }
        state = {
            "tracks": [{"rank": 862, "title": "Until it Sleeps"}],
            "events": [],
            "top10_unrevealed": [],
        }
        played = [{
            "artist": "Some Band", "title": "Earlier Track",
            "started_at": timestamp.isoformat(),
        }]
        with patch.object(monitor, "now", return_value=timestamp):
            self.assertIsNone(monitor.pick_target(state, rankmap, played))


if __name__ == "__main__":
    unittest.main()
