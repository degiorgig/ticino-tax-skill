from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, TextIO

try:
    from .common import ROOT, SUPPORTED_STATUSES, load_json, parse_tax_year
    from .validate_tax_year import require_tax_year, load_rule_catalog
    from .validate_return import validate_return
except ImportError:
    from common import ROOT, SUPPORTED_STATUSES, load_json, parse_tax_year
    from validate_tax_year import require_tax_year, load_rule_catalog
    from validate_return import validate_return

FIELDS = ["tax_year", "jurisdiction", "person", "section", "field", "value", "source_document", "calculation", "rule", "verification_status", "notes"]


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)
    return str(value)


def generate_rows(workpaper: dict[str, Any], *, tax_year: int | str, root: Path = ROOT) -> list[dict[str, str]]:
    year = require_tax_year(tax_year, root)
    if not isinstance(workpaper, dict) or parse_tax_year(workpaper.get("tax_year")) != year:
        raise ValueError("Workpaper tax_year must match the export year")
    validation = validate_return(workpaper, year, root)
    catalog = load_rule_catalog(year, root)
    rows = []
    failed = {error["field"] for error in validation["errors"]}
    global_failure = bool(failed & {"tax_year", "final_fields"})
    for collection in ("final_fields", "review_items"):
        items = workpaper.get(collection, [])
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            status = item.get("status", "REVIEW_REQUIRED")
            # A VERIFIED claim survives only if this very item passed validation; other items' problems
            # are reported in their own rows instead of downgrading the whole checklist.
            rejected = global_failure or f"{collection}[{index}]" in failed
            if not isinstance(status, str) or status not in SUPPORTED_STATUSES or (status == "VERIFIED" and rejected):
                status = "REVIEW_REQUIRED"
            rule = item.get("rule")
            rule_id = rule.get("rule_id") if isinstance(rule, dict) else rule
            if isinstance(rule_id, str) and rule_id in catalog:
                rule = catalog[rule_id]
            rows.append({
                "tax_year": str(year), "jurisdiction": _stringify(item.get("jurisdiction")),
                "person": _stringify(item.get("person")), "section": _stringify(item.get("section", "Review")),
                "field": _stringify(item.get("field", item.get("type", "review_item"))),
                "value": _stringify(item.get("value")),
                "source_document": _stringify(item.get("source_document")),
                "calculation": _stringify(item.get("calculation")), "rule": _stringify(rule),
                "verification_status": status,
                "notes": _stringify(item.get("notes", item.get("message", item.get("reason", "")))),
            })
    for error in validation["errors"]:
        if error["message"].startswith("Unresolved"):
            continue  # the item's own row already shows its open status
        row = dict.fromkeys(FIELDS, "")
        row.update(tax_year=str(year), section="Validation", field=error["field"],
                   verification_status="REVIEW_REQUIRED", notes=error["message"])
        rows.append(row)
    return rows


def write_checklist(workpaper: dict[str, Any], output: str | None = None, *, tax_year: int | str, root: Path = ROOT) -> list[dict[str, str]]:
    # Validate and materialize all rows before opening/truncating the output file.
    rows = generate_rows(workpaper, tax_year=tax_year, root=root)
    handle: TextIO = Path(output).open("w", newline="", encoding="utf-8") if output else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if output:
            handle.close()
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export an eTax checklist with validated status and full provenance.")
    parser.add_argument("workpaper_json")
    parser.add_argument("--tax-year", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        rows = write_checklist(load_json(args.workpaper_json), args.output, tax_year=args.tax_year)
    except ValueError as exc:
        parser.error(str(exc))
    return 2 if any(row["verification_status"] not in ("VERIFIED", "NOT_APPLICABLE") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
