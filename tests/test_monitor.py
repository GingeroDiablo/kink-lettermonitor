import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import monitor

class KinkTests(unittest.TestCase):
    def test_ranking_split_fields(self):
        parts = ["<main>"]
        for rank in range(11, 1300):
            parts.extend((f"<p>{rank}</p>", "<p>Metallica</p>" if rank == 20 else "<p>Radiohead</p>",
                          "<p>-</p>", "<p>One</p>" if rank == 20 else "<p>Track</p>"))
        parts.append("</main>")
        with patch.object(monitor, "fetch", return_value="".join(parts)):
            data = monitor.rankings()
        self.assertEqual(data[20], {"artist": "Metallica", "title": "One"})
        self.assertEqual(len(data), 1289)

    def test_ranking_combined_fields(self):
        parts = ["<main>"]
        for rank in range(11, 1300):
            parts.extend((f"<p>{rank}</p>", "<p>Metallica - One</p>" if rank == 20 else "<p>Radiohead - Track</p>"))
        parts.append("</main>")
        with patch.object(monitor, "fetch", return_value="".join(parts)):
            self.assertEqual(monitor.rankings()[20]["title"], "One")

    def test_plays(self):
        html = "<main><p>Metallica</p><p>One</p><p>18:42</p><p>Radiohead</p><p>Creep</p><p>18:35</p></main>"
        with patch.object(monitor, "fetch", return_value=html):
            records = monitor.plays_for(datetime(2026, 10, 19).date())
        self.assertEqual([p["title"] for p in records], ["Creep", "One"])

    def test_letters_are_conservative(self):
        self.assertEqual(monitor.letter_from_text("De codeletter is de R!"), "R")
        self.assertEqual(monitor.letter_from_text("De letter is B en de letter is Q"), None)
        self.assertIsNone(monitor.letter_from_text("Het woord letter kwam voorbij"))

    def test_weekend_original_and_replay_classification(self):
        rankmap = {850: {"artist": "Metallica", "title": "One"}}
        state = {"tracks": [{"rank": 850, "title": "One"}], "events": []}
        plays = [
            {"started_at": "2026-10-24T07:10:00+02:00",
             "artist": "Metallica", "title": "One"},
            {"started_at": "2026-10-24T20:10:00+02:00",
             "artist": "Metallica", "title": "One"},
        ]
        monitor.update_events(state, plays)
        self.assertEqual(len(state["events"]), 2)
        self.assertFalse(state["events"][0]["replay"])
        self.assertTrue(state["events"][1]["replay"])

    def test_weekend_replay_forecast_not_armed_during_original(self):
        t = datetime(2026, 10, 25, 7, 15,
                     tzinfo=ZoneInfo("Europe/Amsterdam"))
        self.assertIsNone(monitor.upcoming_replay({"events": []}, t))

    def test_contest_window(self):
        tz = ZoneInfo("Europe/Amsterdam")
        self.assertTrue(monitor.in_window(datetime(2026, 10, 19, 20, tzinfo=tz)))
        self.assertTrue(monitor.in_window(datetime(2026, 10, 31, 7, tzinfo=tz)))
        self.assertFalse(monitor.in_window(datetime(2026, 10, 31, 10, tzinfo=tz)))

if __name__ == "__main__":
    unittest.main()
