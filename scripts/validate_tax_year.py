from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

try:
    from .common import ROOT, REQUIRED_RULE_FILES, dump_json, load_yaml, parse_tax_year, is_missing
except ImportError:
    from common import ROOT, REQUIRED_RULE_FILES, dump_json, load_yaml, parse_tax_year, is_missing


def rule_provenance_errors(rule: dict[str, Any], year: int) -> list[str]:
    errors = []
    if rule.get("status") != "VERIFIED":
        errors.append("Rule is not VERIFIED")
    if rule.get("tax_year") != year or isinstance(rule.get("tax_year"), bool):
        errors.append("Rule tax_year mismatch")
    if rule.get("jurisdiction") not in ("CH", "CH-TI"):
        errors.append("Unsupported rule jurisdiction")
    source = rule.get("source")
    if not isinstance(source, dict):
        return errors + ["Missing official source provenance"]
    for key in ("authority", "document", "url", "page", "retrieved_at"):
        if is_missing(source.get(key)):
            errors.append(f"Official source missing {key}")
    if source.get("verified") is not True:
        errors.append("Official source has not been reviewed")
    try:
        url = urlsplit(str(source.get("url", "")))
        host = url.hostname or ""
        domains = ("ti.ch",) if rule.get("jurisdiction") == "CH-TI" else ("estv.admin.ch", "fedlex.admin.ch")
        if url.scheme != "https" or url.username or not any(host == d or host.endswith("." + d) for d in domains):
            errors.append("Official source URL does not match the jurisdiction's authority")
        date.fromisoformat(str(source.get("retrieved_at", "")))
    except ValueError:
        errors.append("Invalid official source URL or retrieval date")
    return errors


def load_rule_catalog(year: int, root: Path = ROOT) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    jurisdictions = dict(zip(REQUIRED_RULE_FILES, ("CH-TI", "CH", "CH-TI", "CH")))
    for filename, jurisdiction in jurisdictions.items():
        book = load_yaml(root / "rules" / str(year) / filename)
        if book.get("tax_year") != year or book.get("jurisdiction") != jurisdiction:
            raise ValueError(f"Rule file year/jurisdiction mismatch: {filename}")
        if not isinstance(book.get("rules"), list):
            raise ValueError(f"rules must be a list: {filename}")
        for rule in book["rules"]:
            if not isinstance(rule, dict) or not isinstance(rule.get("rule_id"), str) or not rule["rule_id"].strip():
                raise ValueError(f"Rule must have a nonempty rule_id: {filename}")
            if rule["rule_id"] in catalog:
                raise ValueError(f"Duplicate rule_id: {rule['rule_id']}")
            if rule.get("tax_year") != year or rule.get("jurisdiction") != jurisdiction:
                raise ValueError(f"Rule year/jurisdiction mismatch: {rule['rule_id']}")
            catalog[rule["rule_id"]] = rule
    return catalog


def validate_tax_year(tax_year: int | str, root: Path = ROOT) -> dict[str, Any]:
    result = {"tax_year": tax_year, "status": "REVIEW_REQUIRED", "structure_valid": False, "errors": []}
    try:
        year = parse_tax_year(tax_year)
        result["tax_year"] = year
        config = load_yaml(root / "config.yaml")["skill"]
        if year not in config["supported_tax_years"]:
            raise ValueError(f"Unsupported tax_year: {year}")
        rules = load_rule_catalog(year, root)
    except (ValueError, OSError, KeyError, TypeError, yaml.YAMLError) as exc:
        result["errors"].append(str(exc))
        return result
    result["structure_valid"] = True
    result["status"] = "UNVERIFIED"
    if not rules:
        result["errors"].append("No verified rules: year contains only skeleton files")
    for rule_id, rule in rules.items():
        result["errors"].extend(f"{rule_id}: {message}" for message in rule_provenance_errors(rule, year))
    if not result["errors"]:
        result["status"] = "VERIFIED"
    result["verification_scope"] = "loaded rule provenance only; not tax coverage or legal correctness"
    return result


def require_tax_year(tax_year: int | str, root: Path = ROOT) -> int:
    """Allow preparation with skeletons, but never an invalid year/catalog."""
    result = validate_tax_year(tax_year, root)
    if not result["structure_valid"]:
        raise ValueError("; ".join(result["errors"]))
    return result["tax_year"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate year structure and available rule provenance.")
    parser.add_argument("tax_year")
    args = parser.parse_args(argv)
    result = validate_tax_year(args.tax_year)
    print(dump_json(result))
    return 0 if result["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
