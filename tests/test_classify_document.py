import unittest

from scripts.classify_document import classify_document


class ClassifyDocumentTests(unittest.TestCase):
    def test_keyword_match_is_a_suggestion_not_evidence(self):
        result = classify_document("certificato di salario 2025.pdf", "Lohnausweis", tax_year=2025)
        self.assertEqual(result["document_type"], "SALARY_CERTIFICATE")
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_unknown_document(self):
        result = classify_document("scan001.pdf", tax_year=2025)
        self.assertEqual(result["document_type"], "UNKNOWN")
        self.assertEqual(result["status"], "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
