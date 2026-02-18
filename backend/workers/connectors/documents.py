"""Read-only document discovery connector for PDF/EML/MBOX sources."""

from __future__ import annotations

from backend.workers.connectors.filesystem import DiscoveredFile, discover_files

DOCUMENT_EXTENSIONS = {".pdf", ".eml", ".mbox", ".txt"}
DEFAULT_INCLUDE_GLOBS = ["**/*.pdf", "**/*.eml", "**/*.mbox", "**/*.txt"]


def discover_document_files(
    *,
    root_path: str,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[DiscoveredFile]:
    """Discover document-like files using read-only filesystem scanning."""
    discovered = discover_files(
        root_path=root_path,
        include_globs=include_globs or DEFAULT_INCLUDE_GLOBS,
        exclude_globs=exclude_globs or [],
    )
    return [item for item in discovered if _normalized_extension(item.path) in DOCUMENT_EXTENSIONS]


def _normalized_extension(path: str) -> str:
    lower = path.strip().lower()
    if "." not in lower:
        return ""
    return "." + lower.rsplit(".", 1)[1]
