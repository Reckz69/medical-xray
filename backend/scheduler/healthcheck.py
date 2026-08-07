"""Container healthcheck — exit non-zero if the scheduler heartbeat went stale.

The scheduler stamps ``HEARTBEAT_FILE`` every poll cycle; this script exits 0
while the stamp is fresh, 1 otherwise. Used by the Docker scheduler service so
compose reports an unhealthy container (and restarts it) if the loop stalls.
"""

from __future__ import annotations

import os
import sys
import time

_HEARTBEAT_FILE = os.environ.get("SCHEDULER_HEARTBEAT_FILE", "/tmp/scheduler.heartbeat")
_MAX_AGE_SECONDS = int(os.environ.get("SCHEDULER_HEARTBEAT_MAX_AGE_SECONDS", "180"))


def main() -> int:
    try:
        age = time.time() - os.path.getmtime(_HEARTBEAT_FILE)
    except OSError:
        print("scheduler heartbeat file missing", file=sys.stderr)
        return 1
    if age > _MAX_AGE_SECONDS:
        print(f"scheduler heartbeat stale ({age:.0f}s)", file=sys.stderr)
        return 1
    print(f"scheduler heartbeat fresh ({age:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
