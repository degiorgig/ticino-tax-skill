import shutil
import unittest

import yaml

from scripts.validate_tax_year import load_rule_catalog, require_tax_year, rule_provenance_errors, validate_tax_year
from tests.helpers import FAKE_RULE, make_root


class ValidateTaxYearTests(unittest.TestCase):
    def test_skeleton_year_is_structurally_valid_but_unverified(self):
        result = validate_tax_year(2025)
        self.assertTrue(result["structure_valid"])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(require_tax_year("2025"), 2025)

    def test_year_with_verified_rule_provenance(self):
        root = make_root()
        self.addCleanup(shutil.rmtree, root)
        self.assertEqual(validate_tax_year(2025, root)["status"], "VERIFIED")

    def test_fedlex_article_and_bsv_web_section_are_valid_locators(self):
        for url, locator in (
            ("https://www.fedlex.admin.ch/eli/cc/example/it", {"article": "art. 18 LIFD"}),
            ("https://www.bsv.admin.ch/it/contributi-panoramica", {"section": "Indipendenti"}),
        ):
            with self.subTest(url=url):
                rule = {**FAKE_RULE, "jurisdiction": "CH", "source": {**FAKE_RULE["source"], "url": url, "page": None, **locator}}
                self.assertEqual(rule_provenance_errors(rule, 2025), [])

    def test_missing_locator_and_domain_spoofing_are_rejected(self):
        rule = {**FAKE_RULE, "jurisdiction": "CH", "source": {**FAKE_RULE["source"], "url": "https://bsv.admin.ch.evil.example/rule", "page": " "}}
        errors = rule_provenance_errors(rule, 2025)
        self.assertTrue(any("locator" in error for error in errors))
        self.assertTrue(any("URL" in error for error in errors))

    def test_sole_proprietorship_book_accepts_federal_and_cantonal_rules(self):
        root = make_root()
        self.addCleanup(shutil.rmtree, root)
        path = root / "rules" / "2025" / "sole-proprietorship.yaml"
        book = yaml.safe_load(path.read_text(encoding="utf-8"))
        federal = {**FAKE_RULE, "rule_id": "TEST_CH_SOLE", "jurisdiction": "CH",
                   "source": {**FAKE_RULE["source"], "url": "https://www.fedlex.admin.ch/eli/cc/example/it", "page": None, "article": "art. 18 LIFD"}}
        cantonal = {**FAKE_RULE, "rule_id": "TEST_TI_SOLE"}
        book["rules"] = [federal, cantonal]
        path.write_text(yaml.safe_dump(book), encoding="utf-8")
        catalog = load_rule_catalog(2025, root)
        self.assertEqual(catalog["TEST_CH_SOLE"]["jurisdiction"], "CH")
        self.assertEqual(catalog["TEST_TI_SOLE"]["jurisdiction"], "CH-TI")
        self.assertEqual(validate_tax_year(2025, root)["status"], "VERIFIED")

    def test_unsupported_year_is_rejected(self):
        result = validate_tax_year(2024)
        self.assertFalse(result["structure_valid"])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        with self.assertRaises(ValueError):
            require_tax_year(2024)

    def test_tax_year_is_mandatory(self):
        for bad in ("", None, True, "25", "20x5"):
            self.assertFalse(validate_tax_year(bad)["structure_valid"], bad)


if __name__ == "__main__":
    unittest.main()
