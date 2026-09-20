import shutil
import unittest

import yaml

from scripts.validate_tax_year import load_rule_catalog, require_tax_year, rule_provenance_errors, validate_tax_year
from tests.helpers import FAKE_RULE, make_root


class ValidateTaxYearTests(unittest.TestCase):
    def test_skeleton_year_is_structurally_valid_but_unverified(self):
        result = validate_tax_year(2026)  # 2026 rule files are still skeletons
        self.assertTrue(result["structure_valid"])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(require_tax_year("2026"), 2026)

    def test_shipped_2025_rules_have_complete_provenance(self):
        from scripts.validate_tax_year import load_rule_catalog, rule_provenance_errors
        catalog = load_rule_catalog(2025)
        self.assertTrue(catalog)
        for rule_id, rule in catalog.items():
            self.assertEqual(rule_provenance_errors(rule, 2025), [], rule_id)
            self.assertTrue(rule_id.startswith("CH_2025_" if rule["jurisdiction"] == "CH" else "TI_2025_"), rule_id)
            self.assertTrue(rule.get("values"), rule_id)
            application = rule.get("application")
            if application:  # every key an application names must exist in the rule's values
                keys = application.get("base_keys", []) + application.get("per_unit_keys", []) + [
                    application[k] for k in ("percent_key", "min_key", "max_key", "value_key") if k in application]
                self.assertTrue(keys and all(key in rule["values"] for key in keys), rule_id)
                self.assertTrue(application.get("field_names"), rule_id)

    def test_clean_provenance_is_not_a_green_light_while_gaps_are_declared(self):
        result = validate_tax_year(2025)
        self.assertTrue(result["rule_provenance_valid"])
        self.assertFalse(result["coverage_complete"])
        self.assertIn("vat.yaml: no rules", result["open_topics"])
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_year_with_verified_rule_provenance(self):
        root = make_root()
        self.addCleanup(shutil.rmtree, root)
        result = validate_tax_year(2025, root)
        self.assertTrue(result["rule_provenance_valid"])
        self.assertEqual(result["status"], "UNVERIFIED")  # other rule books are still empty
        for name in ("federal", "sole-proprietorship", "vat", "ticino"):  # one sourced rule everywhere, no declared gaps
            path = root / "rules" / "2025" / f"{name}.yaml"
            book = yaml.safe_load(path.read_text(encoding="utf-8"))
            jurisdiction = "CH" if name in ("federal", "vat") else "CH-TI"
            url = "https://www.estv.admin.ch/test" if jurisdiction == "CH" else FAKE_RULE["source"]["url"]
            book["rules"] = [{**FAKE_RULE, "rule_id": f"TEST_{name}", "jurisdiction": jurisdiction, "source": {**FAKE_RULE["source"], "url": url}}]
            book.pop("pending_rules", None)
            path.write_text(yaml.safe_dump(book), encoding="utf-8")
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
        self.assertTrue(validate_tax_year(2025, root)["rule_provenance_valid"])

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
