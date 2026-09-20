from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_RULE_FILES = ("ticino.yaml", "federal.yaml", "sole-proprietorship.yaml", "vat.yaml")
SUPPORTED_STATUSES = {"VERIFIED", "UNVERIFIED", "REVIEW_REQUIRED", "MISSING_DOCUMENT", "NOT_APPLICABLE"}

class Status(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class ExpenseClassification(str, Enum):
    BUSINESS_EXPENSE = "BUSINESS_EXPENSE"
    PRIVATE_EXPENSE = "PRIVATE_EXPENSE"
    MIXED = "MIXED"
    CAPITAL_ASSET = "CAPITAL_ASSET"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"

class DocumentType(str, Enum):
    SALARY_CERTIFICATE = "SALARY_CERTIFICATE"
    BANK_STATEMENT = "BANK_STATEMENT"
    TAX_STATEMENT = "TAX_STATEMENT"
    SECURITIES_STATEMENT = "SECURITIES_STATEMENT"
    PILLAR_3A_CERTIFICATE = "PILLAR_3A_CERTIFICATE"
    MORTGAGE_STATEMENT = "MORTGAGE_STATEMENT"
    REAL_ESTATE_DOCUMENT = "REAL_ESTATE_DOCUMENT"
    INSURANCE_CERTIFICATE = "INSURANCE_CERTIFICATE"
    MEDICAL_EXPENSE = "MEDICAL_EXPENSE"
    DONATION = "DONATION"
    BUSINESS_INVOICE = "BUSINESS_INVOICE"
    BUSINESS_RECEIPT = "BUSINESS_RECEIPT"
    BUSINESS_BANK_STATEMENT = "BUSINESS_BANK_STATEMENT"
    SOCIAL_SECURITY_CERTIFICATE = "SOCIAL_SECURITY_CERTIFICATE"
    PREVIOUS_TAX_RETURN = "PREVIOUS_TAX_RETURN"
    FAMILY_STATUS_DOCUMENT = "FAMILY_STATUS_DOCUMENT"
    CHILDCARE_INVOICE = "CHILDCARE_INVOICE"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class SourceValue:
    document: str
    page: int | None
    field: str
    original_text: str
    extracted_value: Any
    confidence: float
    status: str

@dataclass(frozen=True)
class TraceRef:
    calculation_id: str | None
    rule_ids: list[str]
    source_values: list[dict[str, Any]]
    status: str
    notes: list[str]


def to_plain(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    return value


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(data: Any) -> str:
    return json.dumps(to_plain(data), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


def require_status(value: str) -> str:
    if value not in SUPPORTED_STATUSES:
        raise ValueError(f"Unsupported status: {value}")
    return value


def money(value: Any) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError("Boolean is not an amount")
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("Amount must be finite")
        return float(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc


def load_yaml(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value


def parse_tax_year(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("tax_year is mandatory and must be a four-digit year")
    text = str(value)
    if len(text) != 4 or not text.isascii() or not text.isdigit() or int(text) < 1000:
        raise ValueError("tax_year is mandatory and must be a four-digit year")
    return int(text)


def is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
