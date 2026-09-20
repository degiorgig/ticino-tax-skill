from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import DocumentType
    from .validate_tax_year import require_tax_year
except ImportError:
    from common import DocumentType
    from validate_tax_year import require_tax_year

KEYWORDS: list[tuple[DocumentType, tuple[str, ...]]] = [
    (DocumentType.SALARY_CERTIFICATE, ("salary certificate", "certificato di salario", "lohnausweis")),
    (DocumentType.BUSINESS_BANK_STATEMENT, ("business account", "conto aziendale", "business bank")),
    (DocumentType.BANK_STATEMENT, ("bank statement", "estratto conto", "kontoauszug")),
    (DocumentType.SECURITIES_STATEMENT, ("securities", "titoli", "depot", "portfolio")),
    (DocumentType.PILLAR_3A_CERTIFICATE, ("pillar 3a", "pilastro 3a", "säule 3a")),
    (DocumentType.MORTGAGE_STATEMENT, ("mortgage", "ipoteca", "hypothek")),
    (DocumentType.REAL_ESTATE_DOCUMENT, ("real estate", "immobile", "property", "valore locativo")),
    (DocumentType.INSURANCE_CERTIFICATE, ("insurance", "assicurazione", "versicherung", "cassa malati", "premi")),
    (DocumentType.MEDICAL_EXPENSE, ("medical", "medico", "fattura medico", "pharmacy", "farmacia")),
    (DocumentType.FAMILY_STATUS_DOCUMENT, ("libretto di famiglia", "stato civile", "atto di nascita", "familienbüchlein", "family certificate")),
    (DocumentType.CHILDCARE_INVOICE, ("asilo nido", "nido", "doposcuola", "mensa scolastica", "kita", "childcare", "famiglia diurna")),
    (DocumentType.DONATION, ("donation", "donazione", "spenden")),
    (DocumentType.BUSINESS_INVOICE, ("invoice", "fattura", "rechnung")),
    (DocumentType.BUSINESS_RECEIPT, ("receipt", "ricevuta", "quittung")),
    (DocumentType.SOCIAL_SECURITY_CERTIFICATE, ("avs", "ahv", "social security", "contributi sociali")),
    (DocumentType.PREVIOUS_TAX_RETURN, ("tax return", "dichiarazione d'imposta", "steuererklärung")),
    (DocumentType.TAX_STATEMENT, ("tax statement", "attestato fiscale", "tax certificate")),
]

def classify_document(path: str, text: str = "", confidence_threshold: float = 0.85, *, tax_year: int | str) -> dict[str, Any]:
    year = require_tax_year(tax_year)
    haystack = f"{Path(path).name} {text}".lower()
    matches: list[tuple[DocumentType, int]] = []
    for doc_type, keywords in KEYWORDS:
        score = sum(1 for kw in keywords if kw in haystack)
        if score:
            matches.append((doc_type, score))
    if not matches:
        return {"tax_year": year, "document": path, "document_type": DocumentType.UNKNOWN.value, "confidence": 0.0, "status": "REVIEW_REQUIRED", "reason": "No known document keywords matched."}
    matches.sort(key=lambda item: item[1], reverse=True)
    best, score = matches[0]
    confidence = min(0.99, 0.55 + score * 0.2)
    status = "REVIEW_REQUIRED"  # Keyword scores are heuristic, not reviewed document evidence.
    return {"tax_year": year, "document": path, "document_type": best.value, "confidence": round(confidence, 2), "status": status, "reason": f"Matched {score} keyword(s)."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify a tax document conservatively.")
    parser.add_argument("path")
    parser.add_argument("--tax-year", required=True)
    parser.add_argument("--text", default="")
    args = parser.parse_args(argv)
    try:
        result = classify_document(args.path, args.text, tax_year=args.tax_year)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
