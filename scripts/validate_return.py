from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from .common import ROOT, SUPPORTED_STATUSES, dump_json, is_missing, load_json, load_yaml, money, parse_tax_year
    from .validate_tax_year import require_tax_year, load_rule_catalog, rule_provenance_errors
except ImportError:
    from common import ROOT, SUPPORTED_STATUSES, dump_json, is_missing, load_json, load_yaml, money, parse_tax_year
    from validate_tax_year import require_tax_year, load_rule_catalog, rule_provenance_errors


def validate_return(workpaper: dict[str, Any], tax_year: int | str, root: Path = ROOT) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    def error(path: str, message: str) -> None:
        errors.append({"field": path, "status": "REVIEW_REQUIRED", "message": message})

    result = {"tax_year": tax_year, "status": "REVIEW_REQUIRED", "errors": errors,
              "verification_scope": "recorded provenance and supported arithmetic; not legal correctness or completeness of tax coverage"}
    try:
        year = require_tax_year(tax_year, root)
        result["tax_year"] = year
        catalog = load_rule_catalog(year, root)
        threshold = float(load_yaml(root / "config.yaml")["skill"]["extraction"]["review_confidence_threshold"])
        if not 0 <= threshold <= 1:
            raise ValueError("Invalid extraction confidence threshold")
        if not isinstance(workpaper, dict):
            raise ValueError("Workpaper must be an object")
        if parse_tax_year(workpaper.get("tax_year")) != year:
            raise ValueError("Workpaper tax_year does not match requested tax_year")
    except (ValueError, TypeError, KeyError) as exc:
        error("tax_year", str(exc))
        return result

    if workpaper.get("status") not in (None, "VERIFIED"):
        error("status", "Workpaper has unresolved status")
    reviews = workpaper.get("review_items", [])
    if not isinstance(reviews, list):
        error("review_items", "Expected a list")
    else:
        for index, item in enumerate(reviews):
            if not isinstance(item, dict) or item.get("status") not in ("VERIFIED", "NOT_APPLICABLE"):
                error(f"review_items[{index}]", "Unresolved review item")

    fields = workpaper.get("final_fields")
    if not isinstance(fields, list) or not fields:
        error("final_fields", "At least one final field is required")
        return result
    for idx, field in enumerate(fields):
        path = f"final_fields[{idx}]"
        if not isinstance(field, dict):
            error(path, "Final field must be an object")
            continue
        status = field.get("status")
        if status not in SUPPORTED_STATUSES:
            error(path, "Unsupported or missing status")
            continue
        if status == "NOT_APPLICABLE":
            if not is_missing(field.get("value")) or is_missing(field.get("notes")):
                error(path, "NOT_APPLICABLE requires an explanation and no amount")
            continue
        if status != "VERIFIED":
            error(path, f"Unresolved field: {status}")
            continue
        for required in ("section", "field", "value", "calculation", "rule", "source_document"):
            if is_missing(field.get(required)):
                error(path, f"VERIFIED field missing {required}")
        if field.get("tax_year", year) != year:
            error(path, "Final field tax_year mismatch")
        jurisdiction = field.get("jurisdiction")
        if jurisdiction not in ("CH", "CH-TI"):
            error(path, "Missing or unsupported final field jurisdiction")

        reference = field.get("rule")
        reference = reference if isinstance(reference, dict) else {"rule_id": reference}
        rule_id = reference.get("rule_id")
        rule = catalog.get(rule_id) if isinstance(rule_id, str) else None
        if rule is None:
            error(path, "Rule must resolve to the requested year's local rule catalog")
        else:
            for message in rule_provenance_errors(rule, year):
                error(path, message)
            if rule.get("jurisdiction") != jurisdiction:
                error(path, "Rule and field jurisdictions differ")
            for key, value in reference.items():
                if key not in rule or value != rule[key]:
                    error(path, f"Inline rule {key} conflicts with canonical rule")

        sources = field.get("source_document")
        sources = sources if isinstance(sources, list) else [sources]
        source_values: dict[tuple[str, str], Decimal] = {}
        for source in sources:
            if not isinstance(source, dict):
                error(path, "Source document provenance must be an object")
                continue
            for key in ("document", "page", "field", "original_text", "extracted_value", "confidence"):
                if is_missing(source.get(key)):
                    error(path, f"Source document missing {key}")
            if source.get("status") != "VERIFIED" or source.get("tax_year") != year:
                error(path, "Source document must be reviewed for the requested tax_year")
            page = source.get("page")
            if type(page) is not int or page < 1:
                error(path, "Source page must be a positive integer")
            confidence = source.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (float, int)) or not threshold <= confidence <= 1:
                error(path, "Source confidence is invalid or below the review threshold")
            if not all(isinstance(source.get(k), str) and source[k].strip() for k in ("document", "field", "original_text")):
                error(path, "Source document, field and original_text must be nonempty text")
                continue
            try:
                value = Decimal(str(money(source.get("extracted_value"))))
                key = (source["document"], source["field"])
                if key in source_values:
                    error(path, "Duplicate source document/field reference")
                source_values[key] = value
            except ValueError as exc:
                error(path, str(exc))

        calculation = field.get("calculation")
        if not isinstance(calculation, dict):
            error(path, "Calculation must contain a reproducible operation and source references")
            continue
        if (not calculation.get("calculation_id") or calculation.get("status") != "VERIFIED"
                or calculation.get("tax_year") != year or calculation.get("rule_ids") != [rule_id]):
            error(path, "Calculation ID, review status, year or rule references are invalid")
        try:
            inputs = calculation.get("inputs")
            if not isinstance(inputs, list) or not inputs:
                raise ValueError("Calculation requires source inputs")
            values = []
            for operand in inputs:
                if not isinstance(operand, dict):
                    raise ValueError("Calculation input must reference a source document and field")
                key = (operand.get("document"), operand.get("field"))
                if key not in source_values:
                    raise ValueError("Calculation input does not resolve to extracted evidence")
                values.append(source_values[key])
            operation = calculation.get("operation")
            if operation == "identity" and len(values) == 1:
                computed = values[0]
            elif operation == "sum":
                computed = sum(values, Decimal(0))
            elif operation == "difference" and len(values) == 2:
                computed = values[0] - values[1]
            else:
                raise ValueError("Unsupported operation or input count; manual review required")
            if money(computed) != money(field.get("value")) or money(computed) != money(calculation.get("result")):
                raise ValueError("Calculation result does not match sources or final amount")
        except (ValueError, TypeError) as exc:
            error(path, str(exc))

    result["status"] = "REVIEW_REQUIRED" if errors else "VERIFIED"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a workpaper's provenance and arithmetic.")
    parser.add_argument("workpaper_json")
    parser.add_argument("--tax-year", required=True)
    args = parser.parse_args(argv)
    result = validate_return(load_json(args.workpaper_json), args.tax_year)
    print(dump_json(result))
    return 0 if result["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
