import unittest

from scripts.build_profit_loss import build_profit_loss


class ProfitLossTests(unittest.TestCase):
    def test_vat_registered_effective_method_keeps_vat_separate(self):
        result = build_profit_loss([
            {"type": "revenue", "amount": 1000, "amount_basis": "net", "output_vat": 81, "document": "out.pdf"},
            {"type": "expense", "amount": 100, "amount_basis": "net", "description": "software subscription",
             "input_vat": 8.1, "recoverable_input_vat": 8.1, "business_percentage": 100, "document": "inv.pdf"},
        ], True, tax_year=2025, vat_accounting_method="effective")
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["vat_treatment"], "SEPARATE_FROM_INCOME_TAX")
        self.assertEqual(result["revenue_total"], 1000.0)
        self.assertEqual(result["provisional_business_expenses_total"], 100.0)
        self.assertEqual(result["provisional_profit_or_loss"], 900.0)
        self.assertEqual(result["vat"]["vat_payable"], 72.9)
        self.assertIsNone(result["profit_or_loss"])
        self.assertIsNone(result["deductible_expenses_total"])

    def test_not_registered_uses_gross_amounts(self):
        result = build_profit_loss([
            {"type": "revenue", "amount": 500, "amount_basis": "gross", "document": "out.pdf"},
            {"type": "expense", "amount": 108.1, "amount_basis": "gross", "description": "hosting",
             "business_percentage": 100, "document": "inv.pdf"},
        ], False, tax_year=2025)
        self.assertEqual(result["provisional_profit_or_loss"], 391.9)
        self.assertEqual(result["vat"]["status"], "NOT_APPLICABLE")

    def test_missing_allocation_blocks_profit(self):
        result = build_profit_loss([
            {"type": "revenue", "amount": 500, "amount_basis": "gross", "document": "out.pdf"},
            {"type": "expense", "amount": 200, "amount_basis": "gross", "description": "phone", "document": "p.pdf"},
        ], False, tax_year=2025)
        self.assertEqual(result["revenue_total"], 500.0)
        self.assertIsNone(result["provisional_profit_or_loss"])

    def test_unknown_vat_status_or_basis_yields_no_totals(self):
        result = build_profit_loss([{"type": "revenue", "amount": 500, "amount_basis": "gross", "document": "o.pdf"}], None, tax_year=2025)
        self.assertIsNone(result["revenue_total"])
        result = build_profit_loss([{"type": "revenue", "amount": 500, "document": "o.pdf"}], False, tax_year=2025)
        self.assertIsNone(result["revenue_total"])
        self.assertTrue(any("amount_basis" in item["reason"] for item in result["review_items"]))


if __name__ == "__main__":
    unittest.main()
