"""In-process scheduler counters (ADR-009).

Observability for the scheduler stays in-process until the observability
phase; these counters drive `run_once`'s report and the scheduler tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class SchedulerMetrics:
    last_run_at: datetime | None = None
    cycles: int = 0
    jobs_republished: int = 0
    jobs_recovered: int = 0
    jobs_failed_terminal: int = 0
    jobs_payload_missing: int = 0
    scans_purged: int = 0
    objects_purged: int = 0
    last_error: str | None = None

    def snapshot(self) -> dict:
        return {
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "cycles": self.cycles,
            "jobs_republished": self.jobs_republished,
            "jobs_recovered": self.jobs_recovered,
            "jobs_failed_terminal": self.jobs_failed_terminal,
            "jobs_payload_missing": self.jobs_payload_missing,
            "scans_purged": self.scans_purged,
            "objects_purged": self.objects_purged,
            "last_error": self.last_error,
        }


#: Process-wide singleton shared by the scheduler loops and run_once.
metrics = SchedulerMetrics()
