"""Regressions for the PR review: checks the validator must make so a VERIFIED row can be trusted."""
import copy
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

import yaml

from scripts import generate_etax_checklist
from scripts.generate_etax_checklist import generate_rows
from scripts.validate_return import validate_return
from tests.helpers import make_root, verified_field

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "fictional-2025" / "workpaper.json"


def resolved_example() -> dict:
    workpaper = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    workpaper["final_fields"] = [f for f in workpaper["final_fields"] if f["status"] == "VERIFIED"]
    workpaper["review_items"] = []
    workpaper["status"] = "VERIFIED"
    return workpaper


def ti_insurance(workpaper: dict) -> dict:
    return next(f for f in workpaper["final_fields"]
                if f["field"] == "insurance_premiums" and f["jurisdiction"] == "CH-TI")


class QuoteTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root)

    def messages(self, field):
        return [e["message"] for e in validate_return({"tax_year": 2025, "final_fields": [field]}, 2025, self.root)["errors"]]

    def test_quote_must_contain_the_extracted_number(self):
        field = verified_field()
        field["source_document"][0]["original_text"] = "Totale versamenti 2025: CHF 9'999.00"
        self.assertTrue(any("original_text does not contain the extracted value" in m for m in self.messages(field)))

    def test_swiss_number_formats_are_recognised_in_the_quote(self):
        for quote in ("CHF 98'000.00", "CHF 98’000.00", "Totale 98 000.00", "Fr. 98000.-", "Saldo: 98000"):
            field = verified_field(98000.0)
            field["source_document"][0]["original_text"] = quote
            self.assertEqual(self.messages(field), [], quote)

    def test_a_count_next_to_a_date_is_found(self):
        field = verified_field(1.0)
        field["source_document"][0]["original_text"] = "Figli a carico al 31.12.2025: 1"
        self.assertEqual(self.messages(field), [])

    def test_apostrophe_is_never_a_decimal_point(self):
        field = verified_field(1.2)
        field["source_document"][0]["original_text"] = "CHF 1'200"
        self.assertTrue(any("original_text does not contain the extracted value" in m for m in self.messages(field)))


    def test_sign_of_the_extracted_value_must_match_the_quote(self):
        field = verified_field(-1200.0)  # helper quote is "CHF 1'200.00"
        self.assertTrue(any("original_text does not contain the extracted value" in m for m in self.messages(field)))
        for quote in ("Storno CHF -1'200.00", "Saldo: −1200.00"):
            field = verified_field(-1200.0)
            field["source_document"][0]["original_text"] = quote
            self.assertEqual(self.messages(field), [], quote)

    def test_a_hyphen_inside_a_date_or_range_is_not_a_minus_sign(self):
        field = verified_field(12.0)
        field["source_document"][0]["original_text"] = "Periodo 01-12 mesi"
        self.assertEqual(self.messages(field), [])


class NestedYearTests(unittest.TestCase):
    """PR review: nested years are read like the top-level one, so "2025" equals 2025."""
    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root)

    def messages(self, field):
        return [e["message"] for e in validate_return({"tax_year": "2025", "final_fields": [field]}, "2025", self.root)["errors"]]

    def test_year_written_as_text_is_accepted_everywhere(self):
        field = verified_field(tax_year="2025")
        field["source_document"][0]["tax_year"] = "2025"
        field["calculation"]["tax_year"] = "2025"
        self.assertEqual(self.messages(field), [])

    def test_wrong_or_malformed_nested_year_is_still_rejected(self):
        for bad in (2024, "2024", "25", True, None, 2025.0):
            field = verified_field()
            field["source_document"][0]["tax_year"] = bad
            self.assertIn("Source document must be reviewed for the requested tax_year", self.messages(field), repr(bad))
        field = verified_field(tax_year="2024")
        self.assertIn("Final field tax_year mismatch", self.messages(field))
        field = verified_field()
        field["calculation"]["tax_year"] = "2024"
        self.assertTrue(any("Calculation ID" in m for m in self.messages(field)))


class CrossFieldTests(unittest.TestCase):
    def messages(self, workpaper, root=None):
        args = (workpaper, 2025) if root is None else (workpaper, 2025, root)
        return [e["message"] for e in validate_return(*args)["errors"]]

    def test_resolved_example_is_still_verified(self):
        self.assertEqual(self.messages(resolved_example()), [])

    def test_same_deduction_cannot_be_claimed_twice(self):
        workpaper = resolved_example()
        twin = copy.deepcopy(workpaper["final_fields"][0])
        twin["calculation"]["calculation_id"] += "-again"
        workpaper["final_fields"].append(twin)
        self.assertTrue(any("claimed twice" in m for m in self.messages(workpaper)))

    def test_same_field_for_another_person_is_not_a_duplicate(self):
        workpaper = resolved_example()
        fields = [f for f in workpaper["final_fields"] if f["field"] == "other_professional_costs"]
        self.assertEqual({f["person"] for f in fields}, {"P1", "P2"})
        self.assertEqual(self.messages(workpaper), [])

    def test_limit_for_people_without_pillar_3a_conflicts_with_a_pillar_3a_claim(self):
        workpaper = resolved_example()
        field = ti_insurance(workpaper)
        field["calculation"]["cap"][0]["key"] = "married_without_pillar2_and_3a"  # 15'400 instead of 10'900
        field["value"] = field["calculation"]["result"] = 13200.0
        self.assertTrue(any("conflicts with the 'pillar_3a' field" in m for m in self.messages(workpaper)))

    def test_higher_limit_is_accepted_when_no_pillar_3a_is_claimed(self):
        workpaper = resolved_example()
        workpaper["final_fields"] = [f for f in workpaper["final_fields"] if f["field"] != "pillar_3a"]
        field = ti_insurance(workpaper)
        field["calculation"]["cap"][0]["key"] = "married_without_pillar2_and_3a"
        field["value"] = field["calculation"]["result"] = 13200.0
        self.assertEqual(self.messages(workpaper), [])

    def test_a_zero_amount_written_as_text_is_not_a_claim(self):
        """PR review: "0" must count as zero, or it wrongly triggers the pillar 3a conflict."""
        workpaper = resolved_example()
        workpaper["final_fields"] = [f for f in workpaper["final_fields"] if f["field"] != "pillar_3a"]
        workpaper["final_fields"].append({"field": "pillar_3a", "status": "NOT_APPLICABLE", "notes": ["none paid"]})
        workpaper["final_fields"].append({"field": "pillar_3a", "status": "REVIEW_REQUIRED", "value": "0.00"})
        field = ti_insurance(workpaper)
        field["calculation"]["cap"][0]["key"] = "married_without_pillar2_and_3a"
        field["value"] = field["calculation"]["result"] = 13200.0
        self.assertFalse(any("conflicts with" in m for m in self.messages(workpaper)))

    def test_cap_is_mandatory_whenever_the_rule_application_is_a_cap(self):
        """PR review: limit detection must not depend on how the rule's value keys are spelled."""
        root = make_root(with_rule=False)
        self.addCleanup(shutil.rmtree, root)
        path = root / "rules" / "2025" / "ticino.yaml"
        book = yaml.safe_load(path.read_text(encoding="utf-8"))
        rule = next(r for r in book["rules"] if r["rule_id"] == "TI_2025_INSURANCE_PREMIUMS_MAX")
        rule["values"]["each_dependant"] = rule["values"].pop("per_child_or_supported_person")
        rule["application"]["per_unit_keys"] = ["each_dependant"]
        path.write_text(yaml.safe_dump(book, allow_unicode=True), encoding="utf-8")
        workpaper = resolved_example()
        field = ti_insurance(workpaper)
        del field["calculation"]["cap"]
        field["value"] = field["calculation"]["result"] = 13200.0  # everything paid, above the 12'100 limit
        self.assertTrue(any("must declare 'cap'" in m for m in self.messages(workpaper, root)))


class TaxpayerIdTests(unittest.TestCase):
    def test_taxpayer_id_with_surrounding_whitespace_is_rejected_with_a_clear_message(self):
        workpaper = resolved_example()
        workpaper["taxpayers"][0]["id"] = " P1"
        errors = validate_return(workpaper, 2025)["errors"]
        self.assertEqual([e["field"] for e in errors], ["taxpayers"])
        self.assertIn("whitespace", errors[0]["message"])


class ChecklistTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root)

    def test_open_items_are_not_repeated_as_validation_rows(self):
        workpaper = {"tax_year": 2025, "final_fields": [verified_field(), {"status": "REVIEW_REQUIRED", "field": "open", "value": 1}]}
        rows = generate_rows(workpaper, tax_year=2025, root=self.root)
        self.assertEqual([r["field"] for r in rows], ["test_amount", "open"])

    def test_malformed_review_item_stays_visible(self):
        """PR review: an item without its own checklist row must keep its validation row."""
        workpaper = {"tax_year": 2025, "final_fields": [verified_field()], "review_items": ["check the foreign account"]}
        rows = generate_rows(workpaper, tax_year=2025, root=self.root)
        self.assertIn(("Validation", "review_items[0]"), [(r["section"], r["field"]) for r in rows])

    def test_only_item_level_open_status_errors_are_suppressed(self):
        """PR review: a workpaper-level error must stay visible even if its text starts like an item one."""
        workpaper = {"tax_year": 2025, "final_fields": [verified_field()]}
        fake = {"status": "REVIEW_REQUIRED", "errors": [
            {"field": "status", "status": "REVIEW_REQUIRED", "message": "Unresolved workpaper-level problem"}]}
        with mock.patch.object(generate_etax_checklist, "validate_return", return_value=fake):
            rows = generate_rows(workpaper, tax_year=2025, root=self.root)
        self.assertIn(("Validation", "status"), [(r["section"], r["field"]) for r in rows])


if __name__ == "__main__":
    unittest.main()
