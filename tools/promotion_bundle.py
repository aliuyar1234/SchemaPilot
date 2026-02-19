#!/usr/bin/env python3
"""Sign and verify promotion bundle envelopes deterministically."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_SIGNING_KEY = "schemapilot-promotion-signing-key-dev-v1"
DEFAULT_KEY_ID = "promotion-v1"
SIGNATURE_ALGORITHM = "HMAC-SHA256"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sign_parser = subparsers.add_parser("sign", help="Sign bundle envelope in-place.")
    sign_parser.add_argument("--input", required=True, help="Path to promotion envelope JSON.")
    sign_parser.add_argument("--output", help="Optional output path; default writes --input.")
    sign_parser.add_argument(
        "--signing-key",
        default=os.getenv("SCHEMAPILOT_PROMOTION_SIGNING_KEY", DEFAULT_SIGNING_KEY),
        help="HMAC key for signature generation.",
    )
    sign_parser.add_argument(
        "--key-id",
        default=DEFAULT_KEY_ID,
        help="Signing key identifier stored in signature metadata.",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify bundle checksum and signature.")
    verify_parser.add_argument("--input", required=True, help="Path to promotion envelope JSON.")
    verify_parser.add_argument(
        "--signing-key",
        default=os.getenv("SCHEMAPILOT_PROMOTION_SIGNING_KEY", DEFAULT_SIGNING_KEY),
        help="HMAC key used for signature verification.",
    )
    return parser.parse_args()


def compute_bundle_checksum(bundle: dict[str, object]) -> str:
    canonical = _canonical_json(bundle).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def sign_envelope(
    envelope: dict[str, object], *, signing_key: str, key_id: str
) -> dict[str, object]:
    bundle_raw = envelope.get("bundle", {})
    bundle = bundle_raw if isinstance(bundle_raw, dict) else {}
    checksum = compute_bundle_checksum(bundle)
    signature_payload: dict[str, object] = {"bundle": bundle, "bundle_checksum": checksum}
    envelope["bundle"] = bundle
    envelope["bundle_checksum"] = checksum
    envelope["signature"] = {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "signature": _sign_payload(signature_payload, key=signing_key),
    }
    return envelope


def verify_envelope(envelope: dict[str, object], *, signing_key: str) -> tuple[bool, str]:
    bundle_raw = envelope.get("bundle", {})
    checksum = str(envelope.get("bundle_checksum", "")).strip()
    signature_raw = envelope.get("signature", {})
    bundle = bundle_raw if isinstance(bundle_raw, dict) else {}
    signature = signature_raw if isinstance(signature_raw, dict) else {}
    if not bundle:
        return False, "missing bundle payload"
    if not checksum:
        return False, "missing bundle_checksum"
    computed = compute_bundle_checksum(bundle)
    if not hmac.compare_digest(checksum, computed):
        return False, "bundle checksum mismatch"
    algorithm = str(signature.get("algorithm", "")).strip().upper()
    if algorithm != SIGNATURE_ALGORITHM:
        return False, "unsupported signature algorithm"
    provided = str(signature.get("signature", "")).strip()
    if not provided:
        return False, "missing signature value"
    signature_payload: dict[str, object] = {"bundle": bundle, "bundle_checksum": checksum}
    expected = _sign_payload(signature_payload, key=signing_key)
    if not hmac.compare_digest(provided, expected):
        return False, "signature verification failed"
    return True, "ok"


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json_object_required")
    return {str(key): value for key, value in payload.items()}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sign_payload(payload: dict[str, object], *, key: str) -> str:
    canonical = _canonical_json(payload).encode("utf-8")
    return hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"FAIL input file not found: {input_path.as_posix()}")
        return 1
    try:
        envelope = _load_json(input_path)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"FAIL invalid input payload: {exc}")
        return 1

    if args.command == "sign":
        signed = sign_envelope(
            envelope,
            signing_key=str(args.signing_key),
            key_id=str(args.key_id),
        )
        output_path = Path(args.output) if args.output else input_path
        _write_json(output_path, signed)
        print(output_path.as_posix())
        print("PASS CHK-PROMOTION-BUNDLE-SIGN")
        return 0

    ok, reason = verify_envelope(envelope, signing_key=str(args.signing_key))
    if not ok:
        print(f"FAIL {reason}")
        return 1
    print("PASS CHK-PROMOTION-BUNDLE-VERIFY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
