from __future__ import annotations

from pathlib import Path

from tools.check_no_bypass_ports import validate_no_bypass_ports


def _write_layout(root: Path, *, compose: str, k8s: str = "") -> None:
    deploy_root = root / "deploy"
    (deploy_root / "k8s").mkdir(parents=True, exist_ok=True)
    (deploy_root / "docker-compose.yml").write_text(compose, encoding="utf-8")
    (deploy_root / "k8s" / "services.yaml").write_text(k8s, encoding="utf-8")


def test_no_bypass_checker_flags_direct_engine_ports(tmp_path: Path) -> None:
    _write_layout(
        tmp_path,
        compose=(
            "services:\n"
            "  trino:\n"
            "    ports:\n"
            "      - \"8080:8080\"\n"
        ),
    )
    errors = validate_no_bypass_ports(tmp_path)
    assert any("8080:8080" in error for error in errors)


def test_no_bypass_checker_flags_pgwire_surface(tmp_path: Path) -> None:
    _write_layout(
        tmp_path,
        compose=(
            "services:\n"
            "  gateway:\n"
            "    ports:\n"
            "      - \"6432:6432\"\n"
        ),
    )
    errors = validate_no_bypass_ports(tmp_path)
    assert any("6432:6432" in error for error in errors)


def test_no_bypass_checker_flags_k8s_direct_bypass_port(tmp_path: Path) -> None:
    _write_layout(
        tmp_path,
        compose="services:\n  gateway:\n    ports:\n      - \"8001:8001\"\n",
        k8s=(
            "apiVersion: v1\n"
            "kind: Service\n"
            "spec:\n"
            "  ports:\n"
            "    - port: 9200\n"
            "      targetPort: 9200\n"
        ),
    )
    errors = validate_no_bypass_ports(tmp_path)
    assert any("9200" in error for error in errors)
