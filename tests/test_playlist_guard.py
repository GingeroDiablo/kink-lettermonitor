import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
import monitor

TZ = ZoneInfo("Europe/Amsterdam")


class PlaylistGuardTests(unittest.TestCase):
    def test_schedule_headings_are_not_songs(self):
        html = (
            "<main><p>06:00</p><p>-</p><p>09:00</p>"
            "<p>The Beatles</p><p>Revolution</p><p>06:31</p>"
            "<p>Metallica</p><p>One</p><p>06:36</p>"
            "<p>-</p><p>Scheduled broadcast</p><p>06:40</p>"
            "</main>"
        )
        with patch.object(monitor, "fetch", return_value=html):
            records = monitor.plays_for(datetime(2026, 10, 20).date())
        self.assertEqual([x["artist"] for x in records], ["The Beatles", "Metallica"])

    def test_recent_filters_future_playlist_rows(self):
        t = datetime(2026, 10, 20, 6, 0, tzinfo=TZ)
        songs = [
            {"started_at": f"2026-10-20T0{h}:00:00+02:00",
             "artist": "Band", "title": f"Song {h}"}
            for h in range(2, 8)
        ]
        with patch.object(monitor, "now", return_value=t), patch.object(
            monitor, "plays_for", return_value=songs
        ):
            result = monitor.recent()
        self.assertEqual(len(result), 5)
        self.assertEqual(result[-1]["title"], "Song 6")


if __name__ == "__main__":
    unittest.main()
