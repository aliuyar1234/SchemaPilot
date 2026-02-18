"""AI service entrypoint."""

from __future__ import annotations

import uvicorn

from backend.ai_service.app import create_ai_service_app
from backend.shared_domain.config import load_settings

AI_SERVICE_PORT = 8002


def main() -> None:
    """Run optional AI service."""
    settings = load_settings()
    app = create_ai_service_app(settings_factory=lambda: settings)
    uvicorn.run(app, host=settings.bind_address, port=AI_SERVICE_PORT)


if __name__ == "__main__":
    main()
