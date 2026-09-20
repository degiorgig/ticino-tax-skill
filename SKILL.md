---
name: ticino-tax
description: Prepare traceable workpapers for a Canton Ticino personal tax return (dichiarazione d'imposta, eTax TI), including employment income, sole proprietorship (ditta individuale) P&L, VAT/IVA kept separate, real estate, Pillar 3a, prior-year comparison and an eTax entry checklist. Use when the user mentions Ticino taxes, tasse, dichiarazione, eTax, or tax documents for 2025/2026.
version: 0.1.0
author: Ticino Tax Copilot contributors
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tax, switzerland, ticino, personal-tax, traceability]
    related_skills: []
---

# Ticino Tax Copilot Skill

This skill helps prepare Swiss personal tax return workpapers for residents of Canton Ticino while preserving traceability from every proposed eTax field back to calculations, source documents, extracted values, tax rules, and official authorities. It does **not** replace the official eTax system, a qualified tax adviser, or user review.

The skill is intentionally conservative: incomplete verified data is preferable to complete fabricated data.

## When to Use

Use this skill when the user asks to:

- Prepare a personal tax-return workpaper for an individual resident in Canton Ticino.
- Analyze tax documents for tax year 2025 or 2026.
- Build a sole-proprietorship profit and loss statement.
- Classify a document or an expense for Swiss/Ticino tax preparation.
- Compare the current declaration against a previous-year return.
- Identify missing documents, review items, deductions, assets, liabilities, or unexplained variances.
- Generate an eTax preparation checklist with provenance for manual entry.

Do **not** use this skill to claim a return is correct, file a tax return, provide legal/tax advice, or invent rules that are not verified from official sources.

## Mandatory Safety Rules

NEVER:

- invent a tax rule;
- invent a deduction;
- invent a threshold;
- invent a tax rate;
- invent an official source;
- assume last year's rule still applies;
- copy previous-year values into the current year;
- classify an uncertain business expense as deductible;
- silently fill missing data;
- mix VAT calculations into income-tax profit without explicit accounting treatment;
- claim a tax return is correct merely because calculations execute.

Use these states consistently:

- `VERIFIED` — source, rule, value, and calculation are supported by explicit evidence.
- `UNVERIFIED` — the rule/value exists as a placeholder or external claim but lacks official verification.
- `REVIEW_REQUIRED` — human judgment or missing context is required.
- `MISSING_DOCUMENT` — the item cannot be supported because a required document is absent.
- `NOT_APPLICABLE` — the item is explicitly outside the taxpayer situation.

When uncertain, prefer `REVIEW_REQUIRED` over guessing.

## Jurisdiction and Tax-Year Discipline

Every operation must include a `tax_year`. The initial supported tax years are `2025` and `2026` only. Rule files are separated by year and jurisdiction:

- `rules/<tax_year>/federal.yaml` for Swiss Federal Direct Tax / IFD (`CH`).
- `rules/<tax_year>/ticino.yaml` for Canton Ticino (`CH-TI`).
- `rules/<tax_year>/sole-proprietorship.yaml` for income-tax treatment of self-employed activity.
- `rules/<tax_year>/vat.yaml` for VAT as a separate concern.

The sole-proprietorship rule book accepts both federal (`CH`) and Ticino (`CH-TI`) rules. Each rule must declare its own jurisdiction and use an official source appropriate to it.

Never reuse a threshold, deduction, tariff, allowance, depreciation rule, or rate across years unless that exact year is verified from an official source.

## Supported Taxpayer Situations

The current models support:

- Canton Ticino resident individuals;
- employment income;
- sole proprietorship / self-employed activity;
- combined employment and sole proprietorship;
- married taxpayers;
- children and dependants;
- bank accounts;
- securities/investments;
- real estate;
- mortgages and debts;
- Pillar 3a;
- insurance;
- professional expenses;
- medical expenses;
- donations;
- standard deductions;
- business assets and liabilities;
- VAT status, output VAT, input VAT, VAT payable, and VAT receivable.

The schema is extensible for future taxpayer situations.

## Workflow

Before running a script, use the directory containing this `SKILL.md` as the working directory. Pass absolute paths to private input files stored outside the skill directory. A global Hermes installation may load this skill while the chat's current directory is elsewhere.

1. **Validate the tax year.** Run `scripts/validate_tax_year.py <year>`. `structure_valid: true` means the year is supported in `config.yaml` and its rule files load; preparation may proceed. `status` is `VERIFIED` only when every loaded rule has complete official provenance; with skeleton rule files it is `UNVERIFIED` (exit code 2) and no final field can be `VERIFIED` yet.
2. **Inventory documents.** `scripts/classify_document.py` gives a keyword-based suggestion that is always `REVIEW_REQUIRED`. Read the document yourself and confirm or correct the class. Completion criterion: every document is categorized or marked `UNKNOWN`.
3. **Extract values conservatively.** Keep taxpayer documents and filled workpapers outside the repository and installed skill directory. Every extracted value must preserve document, page, field, original text, extracted value, confidence, tax year, and status. Confidence below `config.yaml` `extraction.review_confidence_threshold` stays `REVIEW_REQUIRED`.
4. **Build taxpayer workpapers.** Use `taxpayer/personal.yaml` and `taxpayer/sole-proprietorship.yaml` as templates and `taxpayer/schema.yaml` as the contract for `final_fields` (the scripts read JSON: convert the filled workpaper to JSON). Completion criterion: no final field lacks provenance or status.
5. **Build sole-proprietorship totals.** Use `scripts/build_profit_loss.py`. Every revenue/expense transaction needs `amount_basis` (`gross` or `net`) and a `document`; VAT registration must be stated explicitly, and only the `effective` VAT method is supported (saldo/flat-rate method: `REVIEW_REQUIRED`, handle manually). Output totals are provisional: `profit_or_loss` and `deductible_expenses_total` are always `null`; `provisional_profit_or_loss` appears only when every expense has an explicit `business_percentage` and there are no capital assets awaiting depreciation.
6. **Classify expenses.** `scripts/classify_expense.py` suggests a class by whole-word keywords (EN/IT) and never returns `VERIFIED` or a `deductible_amount`. Use your own reading of the receipt for the final class; ambiguous or mixed expenses need an explicit business percentage and reasoning.
7. **Compare prior year.** Use `scripts/compare_previous_year.py`. Both JSON files need `tax_year` (baseline earlier than current). A category present in only one file is reported as missing data, not as an empty list.
8. **Validate final workpaper.** Use `scripts/validate_return.py`. A `VERIFIED` field must reference a rule in `rules/<year>/` with verified provenance, reviewed source values, and a reproducible calculation (`identity`, `sum`, `difference`) whose result equals the value. Empty or unresolved workpapers are `REVIEW_REQUIRED`.
9. **Generate eTax checklist.** Use `scripts/generate_etax_checklist.py`. A `VERIFIED` status survives only for fields that individually passed validation; validation errors are appended as `Validation` rows. Exit code 2 means open items remain.

## Document Classes

Recognized document classes are:

`SALARY_CERTIFICATE`, `BANK_STATEMENT`, `TAX_STATEMENT`, `SECURITIES_STATEMENT`, `PILLAR_3A_CERTIFICATE`, `MORTGAGE_STATEMENT`, `REAL_ESTATE_DOCUMENT`, `INSURANCE_CERTIFICATE`, `MEDICAL_EXPENSE`, `DONATION`, `BUSINESS_INVOICE`, `BUSINESS_RECEIPT`, `BUSINESS_BANK_STATEMENT`, `SOCIAL_SECURITY_CERTIFICATE`, `PREVIOUS_TAX_RETURN`, `UNKNOWN`.

Every extracted value should use this structure:

```yaml
document: path-or-id
page: 1
field: gross_salary
original_text: "..."
extracted_value: 12345.67
confidence: 0.98
status: VERIFIED
```

Add `tax_year` to every extracted value. Confidence below the configured threshold must become `REVIEW_REQUIRED`.

## Expense Classification

Allowed expense classifications:

- `BUSINESS_EXPENSE`
- `PRIVATE_EXPENSE`
- `MIXED`
- `CAPITAL_ASSET`
- `REVIEW_REQUIRED`

Mixed expenses must preserve original amount, business percentage, private percentage, deductible amount, classification reasoning, and source document. Ambiguous expenses must never be automatically classified as fully deductible.

## Official Sources Policy

Tax rules and numeric values must come from authoritative sources only:

- Repubblica e Cantone Ticino;
- Divisione delle contribuzioni Ticino;
- Raccolta delle leggi del Canton Ticino;
- ESTV / AFC;
- Swiss federal legislation / Fedlex.
- BSV / UFAS for federal social-insurance matters relevant to the workpaper.

Blogs, accounting-company articles, forums, and AI-generated content can help discovery only. They are never authoritative provenance for a `VERIFIED` numeric rule.

Every numeric tax rule must include provenance:

```yaml
rule_id: TI_2025_EXAMPLE
tax_year: 2025
jurisdiction: CH-TI
status: VERIFIED
source:
  authority: Repubblica e Cantone Ticino
  document: "Official document title"
  url: "https://..."
  page: "p. 1"
  retrieved_at: "YYYY-MM-DD"
  verified: true
```

For a source without page numbers, use `article` (for legislation) or `section` (for a web page) instead of `page`. At least one of `page`, `article`, or `section` must identify the exact passage. For federal rules the accepted official domains are `estv.admin.ch`, `fedlex.admin.ch`, and `bsv.admin.ch`; the BSV domain is for social-insurance sources, not a substitute for tax-law authority.

If provenance cannot be established, status must not be `VERIFIED`.

## Quick Reference

Requires Python 3.10+ and PyYAML (`pip install -r requirements.txt`). Every command needs `--tax-year`.

- Validate year: `python3 scripts/validate_tax_year.py 2025`
- Classify a document: `python3 scripts/classify_document.py path/to/document.pdf --tax-year 2025 --text "certificate text"`
- Classify an expense: `python3 scripts/classify_expense.py --tax-year 2025 --amount 120 --description "software subscription" --document invoice.pdf --business-percentage 100`
- Build totals: `python3 scripts/build_profit_loss.py transactions.json --tax-year 2025 --no-vat-registered` (or `--vat-registered --vat-accounting-method effective`)
- Compare previous year: `python3 scripts/compare_previous_year.py previous.json current.json --tax-year 2025`
- Validate workpaper: `python3 scripts/validate_return.py workpaper.json --tax-year 2025`
- Generate checklist: `python3 scripts/generate_etax_checklist.py workpaper.json --tax-year 2025 --output checklist.csv`
- Tests: `python3 -m unittest discover -s tests -t .`

## Pitfalls

- `rules/2025/federal.yaml` and `rules/2025/ticino.yaml` contain a first set of deductions with official provenance (AI-extracted, see each rule's `review` note). Everything else (2026, sole proprietorship, VAT, tariffs, municipal multipliers, valore locativo, federal pillar 3a) is still a skeleton: check each file's `pending_rules` and never fill those gaps from memory.
- A rule's `values` are limits or rates, not the taxpayer's deduction: the deductible amount still depends on conditions in the law and the official instructions.
- A calculation that executes is not a verified tax result.
- Previous-year returns are a completeness baseline only; never auto-copy values into the current year.
- VAT is separate from income tax. Income-tax P&L must state whether amounts are gross, net, or otherwise adjusted for VAT.
- Municipal data is modeled separately because Canton Ticino municipal multipliers and municipality-specific facts may vary.

## Verification

Before presenting results to the user, verify:

- tax year is explicit and supported;
- jurisdiction is explicit (`CH`, `CH-TI`, and municipality where relevant);
- each numeric rule is either `VERIFIED` with official provenance or marked `UNVERIFIED` / `REVIEW_REQUIRED`;
- each final value has a document and calculation trail or a missing/review state;
- all low-confidence extraction and ambiguous classification items are included in review output;
- tests pass with `python3 -m unittest discover -s tests -t .`.
