from __future__ import annotations

import argparse
from typing import Any

try:
    from .common import ROOT, dump_json, load_json, load_yaml, money, parse_tax_year
    from .validate_tax_year import require_tax_year
except ImportError:
    from common import ROOT, dump_json, load_json, load_yaml, money, parse_tax_year
    from validate_tax_year import require_tax_year

DEFAULT_KEYS = ("bank_accounts", "mortgages_and_debts", "real_estate", "pillar_3a", "securities")


def _ids(items: list[dict[str, Any]]) -> set[str]:
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Expected a list of identified items")
    out: set[str] = set()
    for item in items or []:
        ident = item.get("id") or item.get("iban") or item.get("account_number") or item.get("property_id") or item.get("name")
        if not ident:
            raise ValueError("Item lacks an identifier")
        if str(ident) in out:
            raise ValueError("Duplicate item identifier")
        out.add(str(ident))
    return out


def compare_previous_year(previous: dict[str, Any], current: dict[str, Any], tax_year: int | str, variance_percent: float | None = None, variance_absolute: float | None = None) -> dict[str, Any]:
    year = require_tax_year(tax_year)
    if not isinstance(previous, dict) or not isinstance(current, dict):
        raise ValueError("Previous and current workpapers must be objects")
    if parse_tax_year(current.get("tax_year")) != year:
        raise ValueError("Current workpaper tax_year mismatch")
    if parse_tax_year(previous.get("tax_year")) >= year:
        raise ValueError("Baseline tax_year must precede the current tax_year")
    config = load_yaml(ROOT / "config.yaml")["skill"]["comparison"]
    variance_percent = money(config["significant_variance_percent"] if variance_percent is None else variance_percent)
    variance_absolute = money(config["significant_variance_absolute_chf"] if variance_absolute is None else variance_absolute)
    if variance_percent < 0 or variance_absolute < 0:
        raise ValueError("Variance thresholds must be non-negative")
    findings: list[dict[str, Any]] = []
    compared = 0

    def missing(key: str, message: str) -> None:
        findings.append({"type": "comparison_data_missing", "field": key, "status": "REVIEW_REQUIRED", "message": message})

    for key in DEFAULT_KEYS:
        if key not in previous and key not in current:
            continue
        if key not in previous or key not in current:
            missing(key, "Category missing in one workpaper; absence is not a confirmed empty list")
            continue
        try:
            prev_ids = _ids(previous[key])
            curr_ids = _ids(current[key])
        except ValueError as exc:
            missing(key, str(exc))
            continue
        compared += 1
        for absent in sorted(prev_ids - curr_ids):
            findings.append({"type": f"missing_{key}", "id": absent, "status": "REVIEW_REQUIRED", "message": f"Present previous year but absent in current {key}."})
        for new in sorted(curr_ids - prev_ids):
            findings.append({"type": f"new_{key}", "id": new, "status": "REVIEW_REQUIRED", "message": f"New item in current {key}."})

    numeric_checks = [
        ("employment_income_total", "significant_income_change"),
        ("business_revenue_total", "significant_business_revenue_change"),
        ("deductions_total", "significant_deduction_change"),
    ]
    for key, finding_type in numeric_checks:
        if key in previous or key in current:
            try:
                old = money(previous.get(key))
                new = money(current.get(key))
            except ValueError:
                missing(key, "Missing or invalid amount; no zero substituted")
                continue
            compared += 1
            delta = money(new - old)
            pct = abs(delta) / abs(old) * 100 if old else (100.0 if new else 0.0)
            if abs(delta) >= variance_absolute and pct >= variance_percent:
                findings.append({"type": finding_type, "field": key, "previous": old, "current": new, "delta": delta, "percent_change": round(pct, 2), "status": "REVIEW_REQUIRED"})

    if "deductions_present" in previous or "deductions_present" in current:
        if not isinstance(previous.get("deductions_present"), list) or not isinstance(current.get("deductions_present"), list):
            missing("deductions_present", "Both deduction inventories are required")
        else:
            compared += 1
    prev_deductions = set(previous.get("deductions_present") or [])
    curr_deductions = set(current.get("deductions_present") or [])
    for deduction in sorted(prev_deductions - curr_deductions):
        findings.append({"type": "deduction_present_last_year_absent_current", "deduction": deduction, "status": "REVIEW_REQUIRED"})

    if not compared:
        missing("workpaper", "No comparable data supplied")
    return {"tax_year": year, "previous_tax_year": parse_tax_year(previous["tax_year"]), "verification_scope": "comparison only; not tax correctness", "status": "REVIEW_REQUIRED" if findings else "VERIFIED", "comparison_only": True, "findings": findings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare a current workpaper against previous-year data without copying values.")
    parser.add_argument("previous_json")
    parser.add_argument("current_json")
    parser.add_argument("--tax-year", required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_previous_year(load_json(args.previous_json), load_json(args.current_json), args.tax_year)
    except ValueError as exc:
        parser.error(str(exc))
    print(dump_json(result))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
