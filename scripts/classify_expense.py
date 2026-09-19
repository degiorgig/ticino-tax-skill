from __future__ import annotations

import argparse
import re
from decimal import Decimal
from typing import Any

try:
    from .common import money, dump_json
    from .validate_tax_year import require_tax_year
except ImportError:
    from common import money, dump_json
    from validate_tax_year import require_tax_year

CAPITAL_KEYWORDS = ("laptop", "notebook", "computer", "hardware", "equipment", "furniture", "vehicle", "server", "monitor",
                    "portatile", "attrezzatura", "macchinario", "mobili", "arredamento", "veicolo", "stampante")
BUSINESS_KEYWORDS = ("software", "hosting", "domain", "professional service", "accounting", "office supplies", "business insurance", "training",
                     "dominio", "licenza", "contabilità", "fiduciaria", "cancelleria", "formazione", "assicurazione aziendale")
PRIVATE_KEYWORDS = ("groceries", "holiday", "vacation", "private use", "clothing", "restaurant family",
                    "vacanza", "vacanze", "uso privato", "abbigliamento", "spesa alimentare")
MIXED_KEYWORDS = ("phone", "internet", "home office", "vehicle", "car", "fuel", "rent", "electricity", "leasing",
                  "telefono", "cellulare", "natel", "ufficio in casa", "auto", "automobile", "benzina", "affitto", "pigione", "elettricità")


def _matches(description: str, keywords: tuple[str, ...]) -> bool:
    """Whole-word match (optional English plural); substrings such as 'car' in 'card' must not match."""
    return any(re.search(rf"(?<!\w){re.escape(k)}(?:s|es)?(?!\w)", description) for k in keywords)


def classify_expense(
    amount: float,
    description: str,
    document: str | None = None,
    business_percentage: float | None = None,
    force_capital_asset: bool = False,
    *, tax_year: int | str,
) -> dict[str, Any]:
    year = require_tax_year(tax_year)
    amt = money(amount)
    if amt < 0:
        raise ValueError("Expense amount must be non-negative")
    percentage = None
    if business_percentage is not None:
        percentage = money(business_percentage)
        if not 0 <= Decimal(str(business_percentage)) <= 100:
            raise ValueError("business_percentage must be between 0 and 100")
    if not isinstance(description, str):
        raise ValueError("Expense description must be text")
    desc = description.lower().strip()
    classification = "REVIEW_REQUIRED"
    reason = "No reliable classification matched; document and treatment require review."
    if force_capital_asset or _matches(desc, CAPITAL_KEYWORDS):
        classification = "CAPITAL_ASSET"
        reason = "Potential capital asset; no expense deduction until tax-year treatment is verified."
    elif _matches(desc, PRIVATE_KEYWORDS):
        classification = "PRIVATE_EXPENSE"
        reason = "Private-use indicator; conflicting professional allocation requires review."
    elif _matches(desc, MIXED_KEYWORDS) or (percentage is not None and 0 < percentage < 100):
        classification = "MIXED"
        reason = "Mixed expense; explicit allocation is provisional and requires supporting evidence."
    elif _matches(desc, BUSINESS_KEYWORDS):
        classification = "BUSINESS_EXPENSE"
        reason = "Potential business expense; keywords do not establish business percentage or deductibility."
    allocated = money(Decimal(str(amt)) * Decimal(str(percentage)) / 100) if percentage is not None else None
    candidate = allocated if classification in ("BUSINESS_EXPENSE", "MIXED") else None
    return {
        "tax_year": year,
        "classification": classification,
        "original_amount": amt,
        "business_percentage": percentage,
        "private_percentage": money(100 - percentage) if percentage is not None else None,
        "business_amount": allocated,
        "potential_deductible_amount": candidate,
        "deductible_amount": None,
        "status": "REVIEW_REQUIRED",
        "classification_reasoning": reason,
        "source_document": document,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify an expense; allocations are not verified deductions.")
    parser.add_argument("--tax-year", required=True)
    parser.add_argument("--amount", type=float, required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--document")
    parser.add_argument("--business-percentage", type=float)
    parser.add_argument("--force-capital-asset", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = classify_expense(args.amount, args.description, args.document, args.business_percentage,
                                  args.force_capital_asset, tax_year=args.tax_year)
    except ValueError as exc:
        parser.error(str(exc))
    print(dump_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
