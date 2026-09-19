import unittest

from scripts.compare_previous_year import compare_previous_year


class PreviousYearTests(unittest.TestCase):
    def test_detects_missing_account_and_income_variance(self):
        previous = {"tax_year": 2024, "bank_accounts": [{"iban": "CH00-OLD"}], "employment_income_total": 100000,
                    "deductions_present": ["pillar_3a"]}
        current = {"tax_year": 2025, "bank_accounts": [], "employment_income_total": 70000, "deductions_present": []}
        result = compare_previous_year(previous, current, 2025)
        types = {item["type"] for item in result["findings"]}
        self.assertIn("missing_bank_accounts", types)
        self.assertIn("significant_income_change", types)
        self.assertIn("deduction_present_last_year_absent_current", types)
        self.assertTrue(result["comparison_only"])

    def test_missing_item_followed_by_incomplete_category(self):
        # Regression: the loop variable used to shadow the missing() helper and crash here.
        previous = {"tax_year": 2024, "bank_accounts": [{"iban": "CH00-OLD"}], "securities": [{"id": "S1"}],
                    "employment_income_total": None}
        current = {"tax_year": 2025, "bank_accounts": [], "employment_income_total": 1}
        result = compare_previous_year(previous, current, 2025)
        fields = {item.get("field") for item in result["findings"] if item["type"] == "comparison_data_missing"}
        self.assertEqual(fields, {"securities", "employment_income_total"})

    def test_baseline_must_precede_current_year(self):
        with self.assertRaises(ValueError):
            compare_previous_year({"tax_year": 2025}, {"tax_year": 2025}, 2025)


if __name__ == "__main__":
    unittest.main()
