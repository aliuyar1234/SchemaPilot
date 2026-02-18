"""Compatibility wrapper for retention purge helpers."""

from backend.shared_domain.purge import PurgeExecution, purge_workspace_artifacts

__all__ = ["PurgeExecution", "purge_workspace_artifacts"]
