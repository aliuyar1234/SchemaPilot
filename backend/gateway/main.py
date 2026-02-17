"""Gateway service entrypoint."""

from __future__ import annotations

import uvicorn

from backend.gateway.app import create_gateway_app


def main() -> None:
    """Run gateway service."""
    app = create_gateway_app()
    uvicorn.run(app, host="127.0.0.1", port=8090)


if __name__ == "__main__":
    main()
