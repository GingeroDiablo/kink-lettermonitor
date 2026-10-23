"""Higher-frequency checks inside one scheduled GitHub Actions job.

GitHub's cron minimum is five minutes, but within a running job we can
poll KINK every ~45 seconds. Only the final state is committed/deployed,
so this improves detection, not the displayed published heartbeat.
"""
import logging
import os
import time

import monitor

log = logging.getLogger("poll")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def run_window(duration=180, interval=45, clock=time.monotonic,
               sleep=time.sleep, scan=None, state_loader=None):
    """Poll without overlapping or restarting an in-progress recording."""
    if scan is None:
        scan = monitor.main
    if state_loader is None:
        state_loader = monitor.load
    duration = max(0.0, min(float(duration), 240.0))
    interval = max(20.0, float(interval))
    deadline = clock() + duration
    initial_recorded = state_loader().get("last_recording")
    count = 0
    while True:
        count += 1
        log.info("KINK live playlist poll %d", count)
        scan()
        state = state_loader()
        if state.get("last_recording") != initial_recorded:
            log.info("Audio was recorded in this job; stop extra polling")
            break
        remaining = deadline - clock()
        if remaining <= interval:
            break
        sleep(interval)
    log.info("Scheduled runner completed %d checks", count)
    return count


if __name__ == "__main__":
    run_window(
        duration=int(os.getenv("POLL_WINDOW_SECONDS", "180")),
        interval=int(os.getenv("POLL_INTERVAL_SECONDS", "45")),
    )
