#!/usr/bin/env python3
"""Verify signed pack registry artifacts and compatibility metadata."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from tools.pack_lint import (
        DEFAULT_MATRIX_PATH,
        DEFAULT_REGISTRY_PATH,
        DEFAULT_SIGNING_KEY,
        validate_pack_registry,
    )
except ModuleNotFoundError:  # pragma: no cover - script execution fallback
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tools.pack_lint import (
        DEFAULT_MATRIX_PATH,
        DEFAULT_REGISTRY_PATH,
        DEFAULT_SIGNING_KEY,
        validate_pack_registry,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help="Path to pack registry file.",
    )
    parser.add_argument(
        "--matrix",
        default=DEFAULT_MATRIX_PATH,
        help="Path to compatibility matrix file.",
    )
    parser.add_argument(
        "--signing-key",
        default=os.getenv("SCHEMAPILOT_PACK_SIGNING_KEY", DEFAULT_SIGNING_KEY),
        help="Signing key used for signature verification.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    errors = validate_pack_registry(
        root,
        registry_path=args.registry,
        matrix_path=args.matrix,
        signing_key=args.signing_key,
    )
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("PASS CHK-PACK-VERIFY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
