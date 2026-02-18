"""Gateway service entrypoint."""

from __future__ import annotations

import uvicorn

from backend.gateway.app import create_gateway_app
from backend.shared_domain.config import load_settings

GATEWAY_PORT = 8001


def main() -> None:
    """Run gateway service."""
    settings = load_settings()
    app = create_gateway_app(settings_factory=lambda: settings)
    uvicorn.run(app, host=settings.bind_address, port=GATEWAY_PORT)


if __name__ == "__main__":
    main()
