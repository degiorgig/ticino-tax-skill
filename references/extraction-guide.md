# Extraction guide (workflow step 3)

How to turn a document into `source_document` entries. One entry per number you will use:
`document`, `page`, `field`, `original_text` (copied exactly as printed), `extracted_value`, `confidence`,
`tax_year`, `status`. Worked example: `examples/fictional-2025/workpaper.json`.

## Ground rules

- Read the document itself (PDF text or image). `classify_document.py` only suggests a class.
- `original_text` must be a literal quote that contains the number. If you cannot quote it, do not extract it.
- Swiss formats: `98'000.00`, `98’000.00`, `98 000.00` and `98000.-` all mean 98000. Never read `'` as a decimal point.
- Check the year printed on the document. A 2024 certificate in the 2025 folder is `REVIEW_REQUIRED`, not a 2025 value.
- Set `status: VERIFIED` on a source value only when the figure is unambiguous and the person it belongs to is clear.
  Scans that are hard to read, handwritten changes, totals that do not add up: confidence below the threshold, `REVIEW_REQUIRED`.
- One person per value. For couples set `person` (P1/P2/HOUSEHOLD) on the final field; a joint account or a family
  insurance policy is `HOUSEHOLD`.
- Never fill a gap from the previous year or from memory. A missing document is `MISSING_DOCUMENT`.

## What to take from each document class

| Class | Extract | Notes |
|---|---|---|
| `SALARY_CERTIFICATE` | cifra 8 gross total, 9 AVS/AI/IPG/AD/AINP, 10.1 pension ordinary, 10.2 pension buy-in, 11 net salary, 12 tax at source, 13 expenses, boxes F (free transport) and G (canteen), employment period, observations in 15 | Standard Swiss form (Lohnausweis, modulo 11). One certificate per employer and person. Box F/G change the transport and meal deductions. |
| `PILLAR_3A_CERTIFICATE` | contributions paid in the year, account holder | Cap: `TI_2025_PILLAR_3A_MAX` with `cap`. One cap per person. |
| `INSURANCE_CERTIFICATE` | premiums paid in the year, persons covered | Health/accident/life premiums. If a premium subsidy or refund is shown, extract it too and mark the field `REVIEW_REQUIRED`. |
| `BANK_STATEMENT`, `SECURITIES_STATEMENT` | balance/tax value at 31.12, gross interest/dividends, withholding tax (imposta preventiva), account holder | Every account, including zero-balance and closed ones (closing date). |
| `MORTGAGE_STATEMENT` | debt at 31.12, interest paid in the year | |
| `REAL_ESTATE_DOCUMENT` | official estimate value, valore locativo, maintenance invoices (date, work, amount) | Distinguish maintenance from value-adding work: `REVIEW_REQUIRED` unless obvious. |
| `CHILDCARE_INVOICE` | amount paid in the year, child, provider | Cap: `TI_2025_CHILDCARE_MAX` / `CH_2025_CHILDCARE_MAX`. |
| `FAMILY_STATUS_DOCUMENT` | marital status at 31.12, number of dependent children | Whole-number input for `rule_value_times`. |
| `MEDICAL_EXPENSE` | amount borne by the taxpayer after insurer reimbursement | The 5% threshold needs the intermediate net income: leave the final field `REVIEW_REQUIRED`. |
| `DONATION` | amount, recipient, date | Recipient must be a recognised tax-exempt entity: `REVIEW_REQUIRED` unless documented. |
| `BUSINESS_INVOICE`, `BUSINESS_RECEIPT` | date, counterparty, amount, VAT shown, gross/net | Feed `build_profit_loss.py`; never put VAT into income-tax figures without `amount_basis`. |
| `SOCIAL_SECURITY_CERTIFICATE` | AVS contributions of the self-employed paid/assessed for the year | No verified rule yet (`pending_rules`). |
| `PREVIOUS_TAX_RETURN` | list of accounts, properties, debts, deductions claimed | Completeness baseline only (`compare_previous_year.py`). Never copy amounts forward. |

## From source values to a final field

1. Pick the rule in `rules/<year>/` and read its `values`, `notes` and `description`. No rule: the field stays `REVIEW_REQUIRED`.
2. Choose the calculation (`taxpayer/schema.yaml`): `identity`/`sum`/`difference` with `cap`, `rule_value_times`, or `percent_clamped`.
3. Do federal (`CH`) and cantonal (`CH-TI`) separately: limits differ, so they are two final fields.
4. Run `validate_return.py`. It recomputes the amount from the source values and the rule and rejects any mismatch.
