import csv
import shutil
import unittest

import yaml

from scripts.generate_etax_checklist import generate_rows, write_checklist
from scripts.validate_return import validate_return
from tests.helpers import FAKE_RULE, make_root, verified_field


class ValidateReturnTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root)

    def messages(self, workpaper):
        return [e["message"] for e in validate_return(workpaper, 2025, self.root)["errors"]]

    def test_fully_traced_field_is_verified(self):
        result = validate_return({"tax_year": 2025, "final_fields": [verified_field()]}, 2025, self.root)
        self.assertEqual(result["status"], "VERIFIED", result["errors"])

    def test_empty_or_unresolved_workpaper_is_never_verified(self):
        self.assertEqual(validate_return({"tax_year": 2025, "final_fields": []}, 2025, self.root)["status"], "REVIEW_REQUIRED")
        unresolved = {"tax_year": 2025, "final_fields": [{"status": "REVIEW_REQUIRED", "value": 5000}]}
        self.assertEqual(validate_return(unresolved, 2025, self.root)["status"], "REVIEW_REQUIRED")

    def test_verified_field_needs_a_verified_local_rule(self):
        workpaper = {"tax_year": 2025, "final_fields": [verified_field()]}
        result = validate_return(workpaper, 2025)  # real repo: skeleton rules only
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn("Rule must resolve to the requested year's local rule catalog", [e["message"] for e in result["errors"]])

    def test_federal_sole_proprietorship_rule_can_support_a_federal_field(self):
        path = self.root / "rules" / "2025" / "sole-proprietorship.yaml"
        book = yaml.safe_load(path.read_text(encoding="utf-8"))
        book["rules"] = [{**FAKE_RULE, "rule_id": "TEST_CH_SOLE", "jurisdiction": "CH",
                          "source": {**FAKE_RULE["source"], "url": "https://www.fedlex.admin.ch/eli/cc/example/it",
                                     "page": None, "article": "art. 18 LIFD"}}]
        path.write_text(yaml.safe_dump(book), encoding="utf-8")
        field = verified_field(jurisdiction="CH", rule={"rule_id": "TEST_CH_SOLE"})
        field["calculation"]["rule_ids"] = ["TEST_CH_SOLE"]
        result = validate_return({"tax_year": 2025, "final_fields": [field]}, 2025, self.root)
        self.assertEqual(result["status"], "VERIFIED", result["errors"])

    def test_arithmetic_and_confidence_are_checked(self):
        bad_sum = verified_field()
        bad_sum["calculation"]["result"] = 1300.0
        self.assertIn("Calculation result does not match sources or final amount", self.messages({"tax_year": 2025, "final_fields": [bad_sum]}))
        low = verified_field()
        low["source_document"][0]["confidence"] = 0.5
        self.assertIn("Source confidence is invalid or below the review threshold", self.messages({"tax_year": 2025, "final_fields": [low]}))

    def test_year_mismatch(self):
        self.assertEqual(validate_return({"tax_year": 2026, "final_fields": [verified_field()]}, 2025, self.root)["status"], "REVIEW_REQUIRED")

    def test_checklist_downgrades_only_the_failing_field(self):
        broken = verified_field(field="broken")
        broken["calculation"]["result"] = 1.0
        workpaper = {"tax_year": 2025, "final_fields": [verified_field(), broken],
                     "review_items": [{"type": "open_question", "status": "REVIEW_REQUIRED", "message": "check"}]}
        rows = generate_rows(workpaper, tax_year=2025, root=self.root)
        by_field = {row["field"]: row["verification_status"] for row in rows}
        self.assertEqual(by_field["test_amount"], "VERIFIED")
        self.assertEqual(by_field["broken"], "REVIEW_REQUIRED")
        self.assertEqual(by_field["open_question"], "REVIEW_REQUIRED")
        self.assertTrue(any(row["section"] == "Validation" for row in rows))

    def test_checklist_csv_is_written(self):
        out = self.root / "checklist.csv"
        write_checklist({"tax_year": 2025, "final_fields": [verified_field()]}, str(out), tax_year=2025, root=self.root)
        with out.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verification_status"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
