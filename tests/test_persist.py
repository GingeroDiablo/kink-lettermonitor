import unittest

from persist_state import merge_state


class PersistTests(unittest.TestCase):
    def test_preserves_newer_remote_heartbeat(self):
        remote = {"last_checked": "2026-10-20T06:50:00+02:00", "status": "new",
                  "events": [], "tracks": [{"rank": 100, "title": "New"}]}
        stale = {"last_checked": "2026-10-20T06:30:00+02:00", "status": "old",
                 "events": [], "tracks": [{"rank": 100, "title": "Old"}]}
        merged = merge_state(remote, stale)
        self.assertEqual(merged["status"], "new")
        self.assertEqual(merged["tracks"][0]["title"], "New")
        self.assertEqual(merged["last_checked"], remote["last_checked"])

    def test_preserves_new_letter_and_issue_from_both_sources(self):
        recent = {"last_checked": "2026-10-20T06:55:00+02:00",
                  "events": [
                      {"started_at": "2026-10-20T05:29:00+02:00", "title": "One",
                       "rank": 34, "suggested_letter": "R", "notification_issue": None}
                  ]}
        old = {"last_checked": "2026-10-20T06:50:00+02:00",
               "events": [
                   {"started_at": "2026-10-20T05:29:00+02:00", "title": "One",
                    "rank": 34, "suggested_letter": None, "notification_issue": 27},
                   {"started_at": "2026-10-20T04:00:00+02:00", "title": "Sad But True",
                    "rank": 396},
               ]}
        merged = merge_state(old, recent)
        self.assertEqual(len(merged["events"]), 2)
        target = next(e for e in merged["events"] if e["title"] == "One")
        self.assertEqual(target["notification_issue"], 27)
        self.assertEqual(target["suggested_letter"], "R")

    def test_anchor_history_is_unioned(self):
        remote = {"last_checked": "2026-10-20T06:40:00+02:00", "events": [],
                  "forecast_anchors": [{"started_at": "2026-10-19T09:00:00+02:00", "rank": 1499}]}
        candidate = {"last_checked": "2026-10-20T06:50:00+02:00", "events": [],
                     "forecast_anchors": [
                         {"started_at": "2026-10-19T09:00:00+02:00", "rank": 1499},
                         {"started_at": "2026-10-19T10:00:00+02:00", "rank": 1482},
                     ]}
        merged = merge_state(remote, candidate)
        self.assertEqual(len(merged["forecast_anchors"]), 2)


if __name__ == "__main__":
    unittest.main()
