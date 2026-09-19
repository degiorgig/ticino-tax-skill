"""Test fixtures. The rule below is a FAKE used only to exercise validation; it is not tax data."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
FAKE_RULE = {
    "rule_id": "TEST_TI_2025_FAKE", "tax_year": 2025, "jurisdiction": "CH-TI", "status": "VERIFIED",
    "source": {"authority": "TEST", "document": "TEST FIXTURE - not a real rule", "url": "https://www4.ti.ch/test",
               "page": "p. 1", "retrieved_at": "2026-01-01", "verified": True},
}


def make_root(with_rule: bool = True) -> Path:
    root = Path(tempfile.mkdtemp(prefix="ticino-tax-test-"))
    shutil.copy(REPO / "config.yaml", root / "config.yaml")
    shutil.copytree(REPO / "rules", root / "rules")
    if with_rule:
        path = root / "rules" / "2025" / "ticino.yaml"
        book = yaml.safe_load(path.read_text(encoding="utf-8"))
        book["rules"] = [FAKE_RULE]
        path.write_text(yaml.safe_dump(book), encoding="utf-8")
    return root


def verified_field(value: float = 1200.0, **overrides) -> dict:
    field = {
        "section": "Test", "field": "test_amount", "value": value, "tax_year": 2025, "jurisdiction": "CH-TI",
        "status": "VERIFIED", "rule": {"rule_id": FAKE_RULE["rule_id"]},
        "source_document": [{"document": "doc.pdf", "page": 1, "field": "amount", "original_text": "CHF 1'200.00",
                             "extracted_value": value, "confidence": 0.99, "tax_year": 2025, "status": "VERIFIED"}],
        "calculation": {"calculation_id": "calc-1", "status": "VERIFIED", "tax_year": 2025,
                        "rule_ids": [FAKE_RULE["rule_id"]], "operation": "identity",
                        "inputs": [{"document": "doc.pdf", "field": "amount"}], "result": value},
    }
    field.update(overrides)
    return field
