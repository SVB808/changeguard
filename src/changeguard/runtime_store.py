from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from changeguard.runtime_contracts import RuntimeObservation, route_matches


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class RuntimeStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_observations (
                    event_id TEXT PRIMARY KEY,
                    observed_at TEXT NOT NULL,
                    consumer_service TEXT NOT NULL,
                    provider_service TEXT NOT NULL,
                    http_method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    request_count INTEGER NOT NULL,
                    consumer_version TEXT,
                    provider_version TEXT,
                    status_code INTEGER,
                    source TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runtime_contract
                ON runtime_observations(provider_service, http_method, observed_at);

                CREATE TABLE IF NOT EXISTS telemetry_coverage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_at TEXT NOT NULL,
                    end_at TEXT NOT NULL,
                    source TEXT NOT NULL
                );
                """
            )

    def ingest(self, observations: list[RuntimeObservation]) -> tuple[int, int]:
        inserted = 0
        skipped = 0
        with self._connect() as connection:
            for observation in observations:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO runtime_observations (
                        event_id, observed_at, consumer_service, provider_service,
                        http_method, path, request_count, consumer_version,
                        provider_version, status_code, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation.stable_event_id(),
                        _utc_iso(observation.observed_at),
                        observation.consumer_service,
                        observation.provider_service,
                        observation.http_method,
                        observation.path,
                        observation.request_count,
                        observation.consumer_version,
                        observation.provider_version,
                        observation.status_code,
                        observation.source,
                    ),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1
        return inserted, skipped

    def record_coverage(self, start: datetime, end: datetime, source: str) -> None:
        if end < start:
            raise ValueError("telemetry coverage end must not be before start")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO telemetry_coverage(start_at, end_at, source) VALUES (?, ?, ?)",
                (_utc_iso(start), _utc_iso(end), source),
            )

    def latest_contiguous_coverage(self) -> tuple[datetime, datetime] | None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT start_at, end_at FROM telemetry_coverage ORDER BY start_at"
            ).fetchall()

        if not rows:
            return None

        intervals = [
            (_parse_datetime(row["start_at"]), _parse_datetime(row["end_at"]))
            for row in rows
        ]
        intervals.sort(key=lambda item: item[0])

        merged: list[tuple[datetime, datetime]] = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
                continue
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        return merged[-1]

    def contract_observations(
        self,
        provider_service: str,
        http_method: str,
        path: str,
        start: datetime,
        end: datetime,
    ) -> list[RuntimeObservation]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM runtime_observations
                WHERE provider_service = ?
                  AND http_method = ?
                  AND observed_at >= ?
                  AND observed_at <= ?
                ORDER BY observed_at
                """,
                (
                    provider_service,
                    http_method.upper(),
                    _utc_iso(start),
                    _utc_iso(end),
                ),
            ).fetchall()

        observations: list[RuntimeObservation] = []
        for row in rows:
            if not route_matches(row["path"], path):
                continue
            observations.append(
                RuntimeObservation(
                    observed_at=_parse_datetime(row["observed_at"]),
                    consumer_service=row["consumer_service"],
                    provider_service=row["provider_service"],
                    http_method=row["http_method"],
                    path=row["path"],
                    request_count=row["request_count"],
                    consumer_version=row["consumer_version"],
                    provider_version=row["provider_version"],
                    status_code=row["status_code"],
                    source=row["source"],
                    event_id=row["event_id"],
                )
            )
        return observations
