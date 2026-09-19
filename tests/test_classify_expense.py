import unittest

from scripts.classify_expense import classify_expense


class ClassifyExpenseTests(unittest.TestCase):
    def test_tax_year_is_required(self):
        with self.assertRaises(TypeError):
            classify_expense(120, "phone")
        with self.assertRaises(ValueError):
            classify_expense(120, "phone", tax_year=2024)

    def test_mixed_expense_without_percentage_requires_review(self):
        result = classify_expense(120, "phone and internet", "receipt.pdf", tax_year=2025)
        self.assertEqual(result["classification"], "MIXED")
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIsNone(result["potential_deductible_amount"])
        self.assertIsNone(result["deductible_amount"])

    def test_mixed_expense_preserves_business_percentage(self):
        result = classify_expense(200, "home office internet", "receipt.pdf", business_percentage=40, tax_year=2025)
        self.assertEqual(result["classification"], "MIXED")
        self.assertEqual(result["business_percentage"], 40.0)
        self.assertEqual(result["private_percentage"], 60.0)
        self.assertEqual(result["potential_deductible_amount"], 80.0)
        self.assertIsNone(result["deductible_amount"])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_capital_asset_not_expensed_automatically(self):
        result = classify_expense(1500, "laptop computer", "invoice.pdf", business_percentage=100, tax_year=2025)
        self.assertEqual(result["classification"], "CAPITAL_ASSET")
        self.assertIsNone(result["potential_deductible_amount"])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_keywords_match_whole_words_only(self):
        for description in ("credit card fees", "Current account fee", "personal liability insurance"):
            self.assertEqual(classify_expense(10, description, tax_year=2025)["classification"], "REVIEW_REQUIRED", description)

    def test_italian_descriptions(self):
        self.assertEqual(classify_expense(50, "Abbonamento telefono Swisscom", tax_year=2025)["classification"], "MIXED")
        self.assertEqual(classify_expense(900, "Stampante ufficio", tax_year=2025)["classification"], "CAPITAL_ASSET")

    def test_nothing_is_ever_verified_by_keyword(self):
        for description in ("groceries", "software", "xyz"):
            self.assertEqual(classify_expense(10, description, tax_year=2025)["status"], "REVIEW_REQUIRED")

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            classify_expense(-1, "software", tax_year=2025)
        with self.assertRaises(ValueError):
            classify_expense(10, "phone", business_percentage=101, tax_year=2025)


if __name__ == "__main__":
    unittest.main()
