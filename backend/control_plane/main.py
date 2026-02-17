"""Control-plane service entrypoint."""

from __future__ import annotations

import uvicorn

from backend.control_plane.app import create_app


def main() -> None:
    """Run control-plane service."""
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
