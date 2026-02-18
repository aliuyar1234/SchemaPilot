from __future__ import annotations

import datetime as dt
from pathlib import Path

from backend.workers.parsing import normalize_text, parse_currency, parse_date
from backend.workers.profiler import profile_csv_file


def test_parse_currency_handles_eu_and_us_formats() -> None:
    assert parse_currency("1,234.56") == 1234.56
    assert parse_currency("1.234,56") == 1234.56
    assert parse_currency("€ 42,00") == 42.0


def test_parse_date_rejects_ambiguous_without_locale_hint() -> None:
    try:
        parse_date("01/02/2026")
    except ValueError as exc:
        assert str(exc) == "date_ambiguous"
    else:  # pragma: no cover
        raise AssertionError("expected date_ambiguous")
    assert parse_date("01/02/2026", day_first=True) == dt.date(2026, 2, 1)


def test_profile_csv_file_supports_utf8_sig_exports(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_bytes("\ufeffid,name\n1,Änne\n".encode())
    profile = profile_csv_file(csv_path.as_posix())
    assert profile.row_count_sampled == 1
    assert normalize_text("ＡＢＣ") == "ABC"
