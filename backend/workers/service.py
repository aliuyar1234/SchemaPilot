"""Worker runner service for queued control-plane runs."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from backend.shared_domain.db import get_engine, get_session_factory
from backend.shared_domain.metadata_models import Base
from backend.shared_domain.observability import log_structured_event
from backend.shared_domain.scheduling import enqueue_due_scheduled_runs
from backend.shared_domain.tracing import start_trace
from backend.workers.queue_nats import NatsQueueConfig, poll_run_ids, validate_nats_config
from backend.workers.run_processor import process_next_queued_run
from backend.workers.watcher import enqueue_source_watcher_runs


@dataclass(frozen=True)
class WorkerServiceConfig:
    """Configuration for the worker runner process."""

    database_url: str
    storage_root: str
    poll_interval_seconds: float = 2.0
    max_runs_per_tick: int = 1
    max_active_per_workspace: int = 1
    strict_ingest: bool = True
    source_watcher_enabled: bool = False
    queue_backend: str = "db"
    nats_url: str | None = None
    nats_subject: str = "schemapilot.runs"


def process_queued_runs_once(
    *,
    session_factory: sessionmaker[Session],
    storage_root: str,
    max_runs: int = 1,
    max_active_per_workspace: int = 1,
    strict_ingest: bool = True,
    source_watcher_enabled: bool = False,
    queue_backend: str = "db",
    nats_url: str | None = None,
    nats_subject: str = "schemapilot.runs",
) -> int:
    """Process up to max_runs queued jobs and return processed count."""
    processed = 0
    session = session_factory()
    try:
        if queue_backend == "nats":
            nats_config = NatsQueueConfig(enabled=True, url=nats_url, subject=nats_subject)
            validate_nats_config(nats_config)
            _ = poll_run_ids(nats_config, max_items=max_runs)
        enqueue_due_scheduled_runs(session)
        if source_watcher_enabled:
            enqueue_source_watcher_runs(
                session,
                storage_root=storage_root,
                strict_ingest=strict_ingest,
            )
        while processed < max_runs:
            trace_context = start_trace(
                service_name="schemapilot-worker",
                operation="worker.process_next_queued_run",
                correlation_id=f"worker-tick-{processed}",
                enabled=os.getenv("SCHEMAPILOT_TRACING_ENABLED", "false").lower()
                in {"1", "true", "yes", "on"},
            )
            outcome = process_next_queued_run(
                session,
                storage_root=storage_root,
                max_active_per_workspace=max_active_per_workspace,
                strict_ingest=strict_ingest,
            )
            if outcome is None:
                break
            log_structured_event(
                level="info",
                msg="worker.run_processed",
                service="worker",
                correlation_id=trace_context.trace_id,
                workspace_id=outcome.workspace_id,
                actor_id="worker:runner",
                event_type="run.processed",
                extra={
                    "run_id": outcome.run_id,
                    "run_type": outcome.run_type,
                    "status": outcome.status,
                },
            )
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
    if config.queue_backend not in {"db", "nats"}:
        raise ValueError("unsupported_worker_queue_backend")
    engine = get_engine(config.database_url)
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory(config.database_url)
    poll_interval = max(config.poll_interval_seconds, 0.1)
    while True:
        processed = process_queued_runs_once(
            session_factory=session_factory,
            storage_root=config.storage_root,
            max_runs=max(config.max_runs_per_tick, 1),
            max_active_per_workspace=max(config.max_active_per_workspace, 1),
            strict_ingest=config.strict_ingest,
            source_watcher_enabled=config.source_watcher_enabled,
            queue_backend=config.queue_backend,
            nats_url=config.nats_url,
            nats_subject=config.nats_subject,
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
    watcher_enabled = (
        os.getenv("SCHEMAPILOT_SOURCE_WATCHER_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    queue_backend = os.getenv("SCHEMAPILOT_WORKER_QUEUE_BACKEND", "db").strip().lower() or "db"
    nats_url = os.getenv("SCHEMAPILOT_NATS_URL")
    nats_subject = (
        os.getenv("SCHEMAPILOT_NATS_SUBJECT", "schemapilot.runs").strip() or "schemapilot.runs"
    )
    return WorkerServiceConfig(
        database_url=os.getenv("SCHEMAPILOT_DATABASE_URL", "sqlite:///./runtime/schemapilot.db"),
        storage_root=os.getenv("SCHEMAPILOT_STORAGE_ROOT", "./runtime/storage"),
        poll_interval_seconds=float(os.getenv("SCHEMAPILOT_WORKER_POLL_SECONDS", "2")),
        max_runs_per_tick=int(os.getenv("SCHEMAPILOT_WORKER_MAX_RUNS_PER_TICK", "1")),
        max_active_per_workspace=int(os.getenv("SCHEMAPILOT_WORKER_MAX_ACTIVE_PER_WORKSPACE", "1")),
        strict_ingest=strict_ingest,
        source_watcher_enabled=watcher_enabled,
        queue_backend=queue_backend,
        nats_url=nats_url,
        nats_subject=nats_subject,
    )


def main() -> None:
    """Run worker service loop."""
    run_forever(load_worker_service_config())


if __name__ == "__main__":
    main()
