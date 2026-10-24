import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import forecast

TZ = ZoneInfo("Europe/Amsterdam")


class ForecastTests(unittest.TestCase):
    def test_twelve_days_with_weekend_and_dst_transition(self):
        self.assertEqual(len(forecast.DAYS), 12)
        self.assertEqual(forecast.TOTAL_MINUTES, 8040)
        self.assertEqual(forecast.to_broadcast_minute("2026-10-19T21:15:00+02:00"), None)
        self.assertEqual(forecast.to_broadcast_minute("2026-10-20T08:00:00+02:00"), 660)
        self.assertEqual(forecast.to_broadcast_minute("2026-10-24T06:00:00+02:00"), 3300)
        self.assertEqual(forecast.to_broadcast_minute("2026-10-24T10:15:00+02:00"), 3555)
        self.assertEqual(forecast.to_broadcast_minute("2026-10-24T18:15:00+02:00"), None)
        self.assertEqual(forecast.to_broadcast_minute("2026-10-25T06:00:00+01:00"), 4020)
        self.assertEqual(forecast.to_broadcast_minute("2026-10-25T08:00:00+01:00"), 4140)
        self.assertEqual(forecast.to_broadcast_minute("2026-10-26T08:00:00+01:00"), 4740)

    def test_scheduled_times_include_weekend_but_exclude_replays(self):
        self.assertEqual(forecast.from_broadcast_minute(660)[:16], "2026-10-20T08:00")
        self.assertEqual(forecast.from_broadcast_minute(3300)[:16], "2026-10-24T06:00")
        self.assertEqual(forecast.from_broadcast_minute(4020)[:16], "2026-10-25T06:00")
        self.assertEqual(forecast.from_broadcast_minute(4740)[:16], "2026-10-26T08:00")
        self.assertEqual(forecast.from_broadcast_minute(8039)[:16], "2026-10-30T18:59")

    def test_unobserved_songs_may_be_predicted_during_weekend(self):
        state = {"tracks": [{"rank": 850, "title": "Saturday Song"},
                            {"rank": 700, "title": "Sunday Song"}],
                 "events": []}
        forecast.update_forecasts(state, {}, [])
        self.assertTrue(state["tracks"][0]["prediction"]["estimated_at"].startswith("2026-10-24"))
        self.assertTrue(state["tracks"][1]["prediction"]["estimated_at"].startswith("2026-10-25"))

    def test_forecast_uses_anchors_and_marks_aired(self):
        rankmap = {1485: {"artist": "Radiohead", "title": "Creep"},
                   1460: {"artist": "Metallica", "title": "The Unforgiven"}}
        played = [
            {"started_at": "2026-10-19T09:00:00+02:00", "artist": "Radiohead", "title": "Creep"},
            {"started_at": "2026-10-19T21:00:00+02:00", "artist": "Radiohead", "title": "Creep"},
        ]
        state = {"tracks": [{"rank": 1460, "title": "The Unforgiven"}], "events": []}
        forecast.update_forecasts(state, rankmap, played)
        self.assertEqual(len(state["forecast_anchors"]), 1)
        result = state["tracks"][0]["prediction"]
        self.assertEqual(result["status"], "verwacht")
        self.assertLess(forecast.to_broadcast_minute(result["estimated_at"]), 660)

        state["events"] = [{"rank": 1460, "started_at": "2026-10-19T11:08:00+02:00"}]
        forecast.update_forecasts(state, rankmap, played)
        self.assertEqual(state["tracks"][0]["prediction"]["status"], "gedraaid")
        self.assertEqual(state["tracks"][0]["prediction"]["estimated_at"],
                         "2026-10-19T11:08:00+02:00")

    def test_repeated_records_are_deduplicated(self):
        rankmap = {1490: {"artist": "Muse", "title": "Uprising"}}
        played = [{"started_at": "2026-10-19T09:00:00+02:00",
                   "artist": "Muse", "title": "Uprising"}]
        state = {"tracks": [{"rank": 1000, "title": "One"}], "events": []}
        forecast.update_forecasts(state, rankmap, played)
        forecast.update_forecasts(state, rankmap, played)
        self.assertEqual(len(state["forecast_anchors"]), 1)

    def test_calibrates_with_multiple_daytime_songs(self):
        rankmap = {}
        played = []
        for i, minute in enumerate([30, 120, 210, 300]):
            rank = 1490 - i * 20
            title = f"Track {i}"
            rankmap[rank] = {"artist": "Band", "title": title}
            played.append({
                "artist": "Band", "title": title,
                "started_at": (
                    datetime(2026, 10, 19, 8, 0, tzinfo=TZ)
                    .replace(minute=0)
                ).isoformat()
            })
            played[-1]["started_at"] = datetime(
                2026, 10, 19, 8 + minute // 60, minute % 60, tzinfo=TZ
            ).isoformat()
        state = {"tracks": [{"rank": 1400, "title": "Seek & Destroy"}], "events": []}
        forecast.update_forecasts(state, rankmap, played)
        self.assertTrue(state["forecast_meta"]["calibrated"])
        self.assertEqual(state["forecast_meta"]["observations"], 4)

    def test_unranked_track_has_no_false_prediction(self):
        state = {"tracks": [{"rank": -1, "title": "Unknown"}], "events": []}
        forecast.update_forecasts(state, {}, [])
        self.assertIsNone(state["tracks"][0]["prediction"])


if __name__ == "__main__":
    unittest.main()
