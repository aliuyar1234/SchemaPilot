"""Worker runner service for queued control-plane runs."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.workers.run_processor import process_next_queued_run


@dataclass(frozen=True)
class WorkerServiceConfig:
    """Configuration for the worker runner process."""

    database_url: str
    storage_root: str
    poll_interval_seconds: float = 2.0
    max_runs_per_tick: int = 1
    strict_ingest: bool = True


def process_queued_runs_once(
    *,
    session_factory: sessionmaker[Session],
    storage_root: str,
    max_runs: int = 1,
    strict_ingest: bool = True,
) -> int:
    """Process up to max_runs queued jobs and return processed count."""
    processed = 0
    session = session_factory()
    try:
        while processed < max_runs:
            outcome = process_next_queued_run(
                session,
                storage_root=storage_root,
                strict_ingest=strict_ingest,
            )
            if outcome is None:
                break
            processed += 1
        session.commit()
        return processed
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_forever(config: WorkerServiceConfig) -> None:
    """Continuously poll for and process queued runs."""
    engine = get_engine(config.database_url)
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory(config.database_url)
    poll_interval = max(config.poll_interval_seconds, 0.1)
    while True:
        processed = process_queued_runs_once(
            session_factory=session_factory,
            storage_root=config.storage_root,
            max_runs=max(config.max_runs_per_tick, 1),
            strict_ingest=config.strict_ingest,
        )
        if processed == 0:
            time.sleep(poll_interval)


def load_worker_service_config() -> WorkerServiceConfig:
    """Load worker config from env using control-plane compatible defaults."""
    profile = os.getenv("SCHEMAPILOT_PROFILE", "starter").strip().lower()
    strict_default = profile in {"team", "enterprise"}
    strict_raw = os.getenv("SCHEMAPILOT_INGEST_STRICT")
    strict_ingest = strict_default
    if strict_raw is not None:
        strict_ingest = strict_raw.strip().lower() in {"1", "true", "yes", "on"}
    return WorkerServiceConfig(
        database_url=os.getenv("SCHEMAPILOT_DATABASE_URL", "sqlite:///./runtime/schemapilot.db"),
        storage_root=os.getenv("SCHEMAPILOT_STORAGE_ROOT", "./runtime/storage"),
        poll_interval_seconds=float(os.getenv("SCHEMAPILOT_WORKER_POLL_SECONDS", "2")),
        max_runs_per_tick=int(os.getenv("SCHEMAPILOT_WORKER_MAX_RUNS_PER_TICK", "1")),
        strict_ingest=strict_ingest,
    )


def main() -> None:
    """Run worker service loop."""
    run_forever(load_worker_service_config())


if __name__ == "__main__":
    main()
