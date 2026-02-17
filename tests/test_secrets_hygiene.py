from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from backend.shared_domain.secrets import contains_secret, redact_secrets


def test_secret_redaction() -> None:
    token = "sk-" + "abc123xyz456"
    text = f"token={token}"
    assert contains_secret(text)
    redacted = redact_secrets(text)
    assert "[REDACTED]" in redacted


def test_secrets_hygiene_check_passes() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/secrets_hygiene_check.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "PASS CHK-SECRETS-HYGIENE" in result.stdout
