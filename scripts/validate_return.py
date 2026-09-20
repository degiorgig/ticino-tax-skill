from __future__ import annotations

import argparse
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from .common import ROOT, SUPPORTED_STATUSES, dump_json, is_missing, load_json, load_yaml, money, parse_tax_year
    from .validate_tax_year import require_tax_year, load_rule_catalog, rule_provenance_errors
except ImportError:
    from common import ROOT, SUPPORTED_STATUSES, dump_json, is_missing, load_json, load_yaml, money, parse_tax_year
    from validate_tax_year import require_tax_year, load_rule_catalog, rule_provenance_errors


LIMIT_MARKERS = ("max", "min", "percent", "per_", "flat", "amount", "plus")
OPEN_ITEM = "open_item"  # error code: the item's own status already says it is unresolved
# 98'000.00, 98’000.00, 98 000.00, 98000.- and 98000; a number glued to a previous "." (dates) is skipped.
QUOTED_NUMBER = re.compile(r"(?<![\d.])(\d{1,3}(?:['’\u00a0 ]\d{3})+|\d+)(?:\.(\d{1,2})(?!\d))?")


def _quoted_numbers(text: str) -> set[Decimal]:
    """Amounts literally printed in a quote. The apostrophe is a thousands separator, never a decimal point."""
    return {Decimal(str(money(re.sub(r"\D", "", whole) + "." + (cents or "0"))))
            for whole, cents in QUOTED_NUMBER.findall(text)}


def _rule_value(rule: dict[str, Any] | None, key: Any) -> Decimal:
    values = rule.get("values") if isinstance(rule, dict) else None
    if not isinstance(key, str) or not isinstance(values, dict) or key not in values:
        raise ValueError(f"Calculation references a value the rule does not define: {key!r}")
    return Decimal(str(money(values[key])))


def _application(rule: dict[str, Any] | None, operation: str, field_name: Any) -> dict[str, Any]:
    """The recipe comes from the rule file. A workpaper can neither pick which limits apply nor skip one."""
    application = rule.get("application") if isinstance(rule, dict) else None
    if not isinstance(application, dict) or application.get("operation") != operation:
        raise ValueError(f"Rule does not define a machine-checkable '{operation}' application; manual review required")
    if field_name not in (application.get("field_names") or []):
        raise ValueError(f"Rule is not applicable to field {field_name!r}")
    return application


def _pinned(calculation: dict[str, Any], application: dict[str, Any], names: tuple[str, ...]) -> None:
    for name in names:
        if name in calculation and calculation[name] != application.get(name):
            raise ValueError(f"Calculation {name} differs from the rule's application")


def _whole_number(value: Decimal, what: str) -> Decimal:
    if value < 0 or value != value.to_integral_value():
        raise ValueError(f"{what} must be a non-negative whole number taken from a source document")
    return value


def _cap_total(rule: dict[str, Any] | None, cap: Any, source_values: dict[tuple[str, str], Decimal], field_name: Any,
               claimed_fields: set[str]) -> Decimal:
    """cap: [{"key": base}, {"key": per-unit, "times_input": {document, field}}].

    Exactly one base limit (when the rule has any) plus per-unit limits whose multiplier is a documented
    source value of this field. A literal multiplier is never accepted. A base limit the rule marks as
    incompatible with another field (base_key_conflicts) is refused when the workpaper claims that field.
    """
    application = _application(rule, "cap", field_name)
    base_keys = application.get("base_keys") or []
    unit_keys = application.get("per_unit_keys") or []
    if not isinstance(cap, list) or not cap or any(not isinstance(part, dict) for part in cap):
        raise ValueError("cap must be a non-empty list of {key} / {key, times_input}")
    keys = [part.get("key") for part in cap]
    if len(set(keys)) != len(keys):
        raise ValueError("cap lists the same limit twice")
    if sum(1 for key in keys if key in base_keys) != (1 if base_keys else 0):
        raise ValueError("cap must use exactly one of the rule's base limits")
    total = Decimal(0)
    for part in cap:
        key = part.get("key")
        if key in base_keys:
            if set(part) != {"key"}:
                raise ValueError("A base limit applies once; it takes no multiplier")
            for other in (application.get("base_key_conflicts") or {}).get(key) or []:
                if other in claimed_fields:
                    raise ValueError(f"Base limit {key!r} conflicts with the {other!r} field claimed in this workpaper")
            total += _rule_value(rule, key)
        elif key in unit_keys:
            if "times" in part:
                raise ValueError("Literal 'times' is not accepted: use times_input referencing a source value")
            ref = part.get("times_input")
            ref_key = (ref.get("document"), ref.get("field")) if isinstance(ref, dict) else None
            if ref_key not in source_values:
                raise ValueError("cap times_input does not resolve to extracted evidence of this field")
            total += _rule_value(rule, key) * _whole_number(source_values[ref_key], "cap multiplier")
        else:
            raise ValueError(f"cap key is not a limit of this rule: {key!r}")
    return total


def _has_limit(rule: dict[str, Any] | None) -> bool:
    """The rule's declared application decides; key names are only a fallback for rules without one."""
    application = rule.get("application") if isinstance(rule, dict) else None
    if isinstance(application, dict) and application.get("operation") == "cap":
        return True
    values = rule.get("values") if isinstance(rule, dict) else None
    return isinstance(values, dict) and any(marker in key for key in values for marker in LIMIT_MARKERS)


def validate_return(workpaper: dict[str, Any], tax_year: int | str, root: Path = ROOT) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    def error(path: str, message: str, code: str | None = None) -> None:
        errors.append({"field": path, "status": "REVIEW_REQUIRED", "message": message, **({"code": code} if code else {})})

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
                error(f"review_items[{index}]", "Unresolved review item", OPEN_ITEM)

    people: set[str] = set()
    taxpayers = workpaper.get("taxpayers")
    if taxpayers is not None:
        if (not isinstance(taxpayers, list) or not taxpayers
                or any(not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t["id"].strip() for t in taxpayers)
                or len({t["id"] for t in taxpayers}) != len(taxpayers)):
            error("taxpayers", "taxpayers must be a list of objects with unique non-empty ids")
        elif any(t["id"] != t["id"].strip() for t in taxpayers):
            error("taxpayers", "taxpayer ids must not have leading or trailing whitespace")
        else:
            people = {t["id"] for t in taxpayers} | {"HOUSEHOLD"}

    fields = workpaper.get("final_fields")
    if not isinstance(fields, list) or not fields:
        error("final_fields", "At least one final field is required")
        return result
    # Fields that carry an amount, whatever their status: an open pillar 3a claim still rules out the
    # "no pillar 3a" limits elsewhere.
    claimed_fields = {f["field"] for f in fields if isinstance(f, dict) and isinstance(f.get("field"), str)
                      and f.get("status") != "NOT_APPLICABLE" and not is_missing(f.get("value")) and f.get("value") != 0}
    seen: set[tuple[str, str, str]] = set()
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
            error(path, f"Unresolved field: {status}", OPEN_ITEM)
            continue
        for required in ("section", "field", "value", "calculation", "rule", "source_document"):
            if is_missing(field.get(required)):
                error(path, f"VERIFIED field missing {required}")
        if field.get("tax_year", year) != year:
            error(path, "Final field tax_year mismatch")
        if people and field.get("person") not in people:
            error(path, "Workpaper lists taxpayers: every final field needs 'person' (a taxpayer id or HOUSEHOLD)")
        jurisdiction = field.get("jurisdiction")
        if jurisdiction not in ("CH", "CH-TI"):
            error(path, "Missing or unsupported final field jurisdiction")
        claim = (str(field.get("person")), str(jurisdiction), str(field.get("field")))
        if claim in seen:
            error(path, "Same person, jurisdiction and field claimed twice: combine the sources in one final field")
        seen.add(claim)

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
                if abs(value) not in _quoted_numbers(source["original_text"]):
                    error(path, "Source original_text does not contain the extracted value")
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
            elif operation == "rule_value_times" and len(values) == 1:
                # e.g. number of dependent children x per-child deduction
                application = _application(rule, "rule_value_times", field.get("field"))
                _pinned(calculation, application, ("value_key",))
                computed = _whole_number(values[0], "rule_value_times input") * _rule_value(rule, application.get("value_key"))
            elif operation == "percent_clamped":
                # e.g. 3% of net salary, min 2000, max 4000 - percentage, floor and ceiling all come from the rule
                application = _application(rule, "percent_clamped", field.get("field"))
                _pinned(calculation, application, ("percent_key", "min_key", "max_key"))
                computed = sum(values, Decimal(0)) * _rule_value(rule, application.get("percent_key")) / 100
                if application.get("min_key") is not None:
                    computed = max(computed, _rule_value(rule, application["min_key"]))
                if application.get("max_key") is not None:
                    computed = min(computed, _rule_value(rule, application["max_key"]))
            else:
                raise ValueError("Unsupported operation or input count; manual review required")
            if operation in ("identity", "sum", "difference"):
                if calculation.get("cap") is not None:
                    computed = min(computed, _cap_total(rule, calculation["cap"], source_values, field.get("field"), claimed_fields))
                elif _has_limit(rule):
                    raise ValueError("Rule defines a limit: the calculation must declare 'cap'")
            elif calculation.get("cap") is not None:
                raise ValueError("cap is only valid with identity, sum or difference")
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
