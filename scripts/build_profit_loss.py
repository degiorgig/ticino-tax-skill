from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal
from typing import Any

try:
    from .common import dump_json, load_json, money, parse_tax_year
    from .classify_expense import classify_expense
    from .validate_tax_year import require_tax_year
except ImportError:
    from common import dump_json, load_json, money, parse_tax_year
    from classify_expense import classify_expense
    from validate_tax_year import require_tax_year


def build_profit_loss(
    transactions: list[dict[str, Any]], vat_registered: bool | None = None,
    *, tax_year: int | str, vat_accounting_method: str | None = None,
) -> dict[str, Any]:
    year = require_tax_year(tax_year)
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")
    totals = defaultdict(Decimal)
    reviews: list[dict[str, Any]] = []
    classified_expenses = []
    incomplete = not transactions
    allocation_incomplete = False
    depreciation_pending = False

    def review(reason: str, index: int | None = None) -> None:
        reviews.append({"transaction_index": index, "status": "REVIEW_REQUIRED", "reason": reason})

    if not transactions:
        review("No transactions supplied")
    if type(vat_registered) is not bool:
        incomplete = True
        review("Explicit VAT registration status is required")
    elif vat_registered and vat_accounting_method != "effective":
        incomplete = True
        review("Only an explicitly selected effective VAT method is supported")

    for idx, tx in enumerate(transactions):
        try:
            if not isinstance(tx, dict):
                raise ValueError("Transaction must be an object")
            if parse_tax_year(tx.get("tax_year", year)) != year:
                raise ValueError("Transaction tax_year mismatch")
            amount = Decimal(str(money(tx.get("amount"))))
            if amount < 0:
                raise ValueError("Negative transactions/credit notes need explicit treatment")
            kind = tx.get("type")
            if not tx.get("document"):
                review("Missing source document", idx)
            if kind in ("accounts_receivable", "accounts_payable"):
                totals[kind] += amount
                continue
            if kind not in ("revenue", "expense"):
                raise ValueError(f"Unsupported transaction type: {kind}")
            basis = tx.get("amount_basis")
            if basis not in ("gross", "net"):
                raise ValueError("amount_basis must explicitly be gross or net")
            vat_key = "output_vat" if kind == "revenue" else "input_vat"
            if vat_registered is True:
                vat = Decimal(str(money(tx.get(vat_key))))
                if vat < 0 or (basis == "gross" and vat > amount):
                    raise ValueError("VAT amount is invalid for the supplied amount")
            elif vat_registered is False:
                if basis != "gross" or any(money(tx.get(key, 0)) != 0 for key in ("output_vat", "input_vat", "recoverable_input_vat")):
                    raise ValueError("Non-registered transactions require gross amounts and no recoverable/collected VAT")
                vat = Decimal(0)
            else:
                raise ValueError("VAT registration status is unknown")
            gross = amount if basis == "gross" else amount + vat
            if kind == "revenue":
                totals["revenue_total"] += gross - vat
                totals["output_vat"] += vat
                continue

            recoverable = Decimal(str(money(tx.get("recoverable_input_vat")))) if vat_registered else Decimal(0)
            if not 0 <= recoverable <= vat:
                raise ValueError("Recoverable input VAT must be explicitly supplied between zero and input_vat")
            classified = classify_expense(
                float(gross), tx.get("description", ""), tx.get("document"),
                tx.get("business_percentage"), bool(tx.get("force_capital_asset", False)), tax_year=year,
            )
            classified["transaction_index"] = idx
            classified["entered_amount"] = float(amount)
            classified["amount_basis"] = basis
            allocated = classified["business_amount"]
            percentage = classified["business_percentage"]
            if percentage is None:
                if recoverable:
                    raise ValueError("Recoverable VAT requires an explicit business allocation")
                allocation_incomplete = True
            elif recoverable > Decimal(str(money(vat * Decimal(str(percentage)) / 100))):
                raise ValueError("Recoverable VAT exceeds the allocated business share of input VAT")
            candidate = classified["potential_deductible_amount"]
            if candidate is not None:
                candidate = money(Decimal(str(candidate)) - recoverable)
                classified["potential_deductible_amount"] = candidate
                totals["provisional_business_expenses_total"] += Decimal(str(candidate))
            elif classified["classification"] == "CAPITAL_ASSET":
                if allocated is not None:
                    totals["capital_assets_total"] += Decimal(str(allocated)) - recoverable
                else:
                    allocation_incomplete = True
                depreciation_pending = True  # the year's depreciation is unknown: no profit figure
            elif percentage != 0:
                allocation_incomplete = True
            totals["input_vat"] += vat
            totals["recoverable_input_vat"] += recoverable
            classified_expenses.append(classified)
            review(classified["classification_reasoning"], idx)
        except (ValueError, TypeError) as exc:
            incomplete = True
            review(str(exc), idx)

    review("Accounting totals are provisional; source evidence and tax treatment require validation")
    balance = totals["output_vat"] - totals["recoverable_input_vat"]
    before_depreciation = None if incomplete or allocation_incomplete else money(totals["revenue_total"] - totals["provisional_business_expenses_total"])
    provisional = None if depreciation_pending else before_depreciation
    if depreciation_pending:
        review("Capital assets present: depreciation for the year is not computed, so no profit figure is given")
    return {
        "tax_year": year, "status": "REVIEW_REQUIRED", "totals_are_provisional": True,
        "vat_registered": vat_registered, "vat_accounting_method": vat_accounting_method,
        "vat_treatment": "SEPARATE_FROM_INCOME_TAX",
        "revenue_total": None if incomplete else money(totals["revenue_total"]),
        "deductible_expenses_total": None,
        "provisional_business_expenses_total": None if incomplete or allocation_incomplete else money(totals["provisional_business_expenses_total"]),
        "capital_assets_total": None if incomplete or allocation_incomplete else money(totals["capital_assets_total"]),
        "accounts_receivable": None if incomplete else money(totals["accounts_receivable"]),
        "accounts_payable": None if incomplete else money(totals["accounts_payable"]),
        "profit_or_loss": None, "provisional_profit_or_loss": provisional,
        "provisional_profit_before_depreciation": before_depreciation, "depreciation_pending": depreciation_pending,
        "vat": {
            "status": "REVIEW_REQUIRED" if vat_registered is not False else "NOT_APPLICABLE",
            "output_vat": None if incomplete else money(totals["output_vat"]),
            "input_vat": None if incomplete else money(totals["input_vat"]),
            "recoverable_input_vat": None if incomplete else money(totals["recoverable_input_vat"]),
            "vat_payable": money(max(balance, 0)) if vat_registered is True and not incomplete else None,
            "vat_receivable": money(max(-balance, 0)) if vat_registered is True and not incomplete else None,
        },
        "classified_expenses": classified_expenses, "review_items": reviews,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build provisional accounting totals; no verified tax profit is inferred.")
    parser.add_argument("transactions_json")
    parser.add_argument("--tax-year", required=True)
    registration = parser.add_mutually_exclusive_group(required=True)
    registration.add_argument("--vat-registered", dest="vat_registered", action="store_true")
    registration.add_argument("--no-vat-registered", dest="vat_registered", action="store_false")
    parser.add_argument("--vat-accounting-method", choices=["effective"])
    args = parser.parse_args(argv)
    try:
        result = build_profit_loss(load_json(args.transactions_json), args.vat_registered,
                                   tax_year=args.tax_year, vat_accounting_method=args.vat_accounting_method)
    except ValueError as exc:
        parser.error(str(exc))
    print(dump_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
