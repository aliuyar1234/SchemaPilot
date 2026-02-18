"""Control-plane service entrypoint."""

from __future__ import annotations

import uvicorn

from backend.control_plane.app import create_app
from backend.shared_domain.config import load_settings

CONTROL_PLANE_PORT = 8000


def main() -> None:
    """Run control-plane service."""
    settings = load_settings()
    app = create_app(settings_factory=lambda: settings)
    uvicorn.run(app, host=settings.bind_address, port=CONTROL_PLANE_PORT)


if __name__ == "__main__":
    main()
