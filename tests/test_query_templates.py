from __future__ import annotations

from pathlib import Path

from backend.shared_domain.query_templates import (
    list_query_template_summaries,
    render_query_template,
)


def test_query_templates_list_contains_invoice_defaults() -> None:
    templates = list_query_template_summaries()
    template_ids = [str(item["template_id"]) for item in templates]
    assert "invoice_count" in template_ids
    assert "invoice_revenue_by_region" in template_ids


def test_render_query_template_substitutes_params() -> None:
    rendered = render_query_template(
        template_id="invoice_count",
        params={"table_name": "silver.invoice"},
    )
    assert rendered["template_id"] == "invoice_count"
    assert "silver.invoice" in str(rendered["sql"])
    assert "{{" not in str(rendered["sql"])


def test_render_query_template_rejects_unsafe_params() -> None:
    try:
        render_query_template(
            template_id="invoice_count",
            params={"table_name": "silver.invoice;drop table x"},
        )
    except ValueError as exc:
        assert str(exc) == "invalid_template_param:table_name"
    else:  # pragma: no cover
        raise AssertionError("expected invalid_template_param")


def test_render_query_template_supports_custom_file(tmp_path: Path) -> None:
    path = tmp_path / "query_templates.json"
    path.write_text(
        """{
  "templates": [
    {
      "template_id": "t1",
      "name": "T1",
      "description": "",
      "dataset_id": "dataset-1",
      "sql": "select * from {{table_name}}"
    }
  ]
}
""",
        encoding="utf-8",
    )
    rendered = render_query_template(
        template_id="t1",
        params={"table_name": "silver.invoice"},
        path=path,
    )
    assert rendered["sql"] == "select * from silver.invoice"
