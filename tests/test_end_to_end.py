"""Runs the nine SKILL.md workflow steps on the invented household in examples/fictional-2025."""
import copy
import csv
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.build_profit_loss import build_profit_loss
from scripts.classify_document import classify_document
from scripts.compare_previous_year import compare_previous_year
from scripts.generate_etax_checklist import generate_rows, write_checklist
from scripts.validate_return import validate_return
from scripts.validate_tax_year import validate_tax_year

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "fictional-2025"


def load(name):
    return json.loads((EXAMPLE / name).read_text(encoding="utf-8"))


class EndToEndTests(unittest.TestCase):
    def test_step1_year(self):
        self.assertEqual(validate_tax_year(2025)["status"], "VERIFIED")

    def test_step2_every_document_is_classified_or_unknown(self):
        types = {}
        for path in sorted((EXAMPLE / "documents").glob("*.txt")):
            result = classify_document(str(path), path.read_text(encoding="utf-8"), tax_year=2025)
            self.assertEqual(result["status"], "REVIEW_REQUIRED")
            types[path.name] = result["document_type"]
        self.assertEqual(types["certificato_salario_anna_2025.txt"], "SALARY_CERTIFICATE")
        self.assertEqual(types["libretto_famiglia.txt"], "FAMILY_STATUS_DOCUMENT")
        self.assertEqual(types["scan_0042.txt"], "UNKNOWN")

    def test_step3_every_source_value_quotes_its_document(self):
        for field in load("workpaper.json")["final_fields"]:
            for source in field["source_document"]:
                text = " ".join((EXAMPLE / source["document"]).read_text(encoding="utf-8").split())
                self.assertIn(" ".join(source["original_text"].split()), text, source["document"])

    def test_step5_profit_and_loss(self):
        result = build_profit_loss(load("transactions.json"), False, tax_year=2025)
        self.assertEqual(result["revenue_total"], 18500.0)
        self.assertEqual(result["provisional_business_expenses_total"], 636.0)  # 348 + 30% of 960
        self.assertEqual(result["capital_assets_total"], 1890.0)
        self.assertEqual(result["provisional_profit_before_depreciation"], 17864.0)
        self.assertTrue(result["depreciation_pending"])
        self.assertIsNone(result["provisional_profit_or_loss"])
        self.assertIsNone(result["profit_or_loss"])

    def test_step7_previous_year(self):
        result = compare_previous_year(load("previous_year_summary.json"), load("current_year_summary.json"), 2025)
        self.assertEqual({f["type"] for f in result["findings"]},
                         {"missing_bank_accounts", "significant_business_revenue_change", "deduction_present_last_year_absent_current"})

    def test_step8_and_9_validation_and_checklist(self):
        workpaper = load("workpaper.json")
        result = validate_return(workpaper, 2025)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(all(e["message"].startswith("Unresolved") or e["field"] == "status" for e in result["errors"]), result["errors"])
        rows = generate_rows(workpaper, tax_year=2025)
        verified = [(r["jurisdiction"], r["person"], r["field"], r["value"]) for r in rows if r["verification_status"] == "VERIFIED"]
        self.assertEqual(verified, [
            ("CH-TI", "P1", "pillar_3a", "7000.0"), ("CH-TI", "HOUSEHOLD", "insurance_premiums", "12100.0"),
            ("CH", "HOUSEHOLD", "insurance_premiums", "4400.0"), ("CH-TI", "HOUSEHOLD", "child_deduction", "11500.0"),
            ("CH", "HOUSEHOLD", "child_deduction", "6800.0"), ("CH", "P1", "other_professional_costs", "2550.0"),
            ("CH", "P2", "other_professional_costs", "2000.0")])
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            write_checklist(workpaper, None, tax_year=2025)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(buffer.getvalue())))), len(rows))


class RuleLimitTests(unittest.TestCase):
    def setUp(self):
        self.workpaper = load("workpaper.json")
        self.workpaper["final_fields"] = self.workpaper["final_fields"][:7]
        self.workpaper["review_items"] = []
        self.workpaper["status"] = "VERIFIED"

    def messages(self):
        return [e["message"] for e in validate_return(self.workpaper, 2025)["errors"]]

    def test_resolved_example_is_verified(self):
        self.assertEqual(self.messages(), [])

    def test_amount_above_the_legal_maximum_is_rejected(self):
        field = self.workpaper["final_fields"][0]  # pillar 3a, max 7'258
        field["source_document"][0]["extracted_value"] = 9000
        field["value"] = field["calculation"]["result"] = 9000
        self.assertIn("Calculation result does not match sources or final amount", self.messages())
        field["value"] = field["calculation"]["result"] = 7258
        self.assertEqual(self.messages(), [])

    def test_cap_cannot_be_omitted_when_the_rule_has_a_limit(self):
        del self.workpaper["final_fields"][0]["calculation"]["cap"]
        self.assertTrue(any("must declare 'cap'" in m for m in self.messages()))

    def test_unknown_rule_value_key(self):
        self.workpaper["final_fields"][3]["calculation"]["value_key"] = "per_kid"
        self.assertTrue(any("does not define" in m for m in self.messages()))

    def test_rule_value_times_needs_a_whole_number(self):
        field = self.workpaper["final_fields"][3]
        field["source_document"][0]["extracted_value"] = 1.5
        self.assertTrue(any("whole-number" in m for m in self.messages()))

    def test_percent_clamped_applies_minimum_and_maximum(self):
        field = copy.deepcopy(self.workpaper["final_fields"][5])
        field["source_document"][0]["extracted_value"] = 200000  # 3% = 6'000 -> max 4'000
        field["value"] = field["calculation"]["result"] = 4000
        self.workpaper["final_fields"][5] = field
        self.assertEqual(self.messages(), [])

    def test_person_is_required_when_taxpayers_are_listed(self):
        del self.workpaper["final_fields"][0]["person"]
        self.assertTrue(any("needs 'person'" in m for m in self.messages()))
        self.workpaper["final_fields"][0]["person"] = "P9"
        self.assertTrue(any("needs 'person'" in m for m in self.messages()))


if __name__ == "__main__":
    unittest.main()
