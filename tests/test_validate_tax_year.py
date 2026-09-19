import shutil
import unittest

from scripts.validate_tax_year import require_tax_year, validate_tax_year
from tests.helpers import make_root


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
