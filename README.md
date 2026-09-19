# Ticino Tax Copilot

Production-oriented Hermes skill scaffold for preparing Swiss personal tax-return workpapers for residents of Canton Ticino with strict traceability.

This repository is **not** a tax filing system and does **not** replace the official Ticino eTax software, official instructions, or qualified professional advice. It produces preparation artifacts and checklists so a human can review and manually enter values in the official system.

## Critical Security Warning

Tax documents contain highly sensitive personal and financial data. **Never commit personal tax documents, bank statements, salary certificates, insurance certificates, mortgage statements, medical bills, business invoices, credentials, keys, or secrets.**

Keep taxpayer documents and filled workpapers **outside this repository and the installed skill directory**, in a private location of your choice. Point the scripts to those external paths. The `.gitignore` still excludes `data/` as a safeguard, but ignored files inside a skill directory can still be copied by packaging or backup tools. It also excludes `.env`, private keys, credential files, virtual environments, caches, and macOS metadata.

## First-Iteration Scope

Created in this iteration:

- repository structure for tax years 2025 and 2026;
- taxpayer schemas and templates;
- skeleton rule files for federal, Ticino, sole-proprietorship, and VAT concerns;
- official-source registry placeholders;
- Python utilities for validation, document classification, expense classification, profit/loss aggregation, previous-year comparison, return validation, and eTax checklist generation;
- tests for core behaviors.

Numeric tax rules are intentionally **not populated** until official sources are verified and recorded rule by rule.

## Supported Taxpayers

The data model supports individuals resident in Canton Ticino, employment income, sole proprietorship, mixed employment/self-employment, married taxpayers, children/dependants, bank accounts, securities, real estate, mortgages/debts, Pillar 3a, insurance, professional expenses, medical expenses, donations, standard deductions, and business assets/liabilities.

## Tax-Year Discipline

Every tax operation requires a `tax_year`. Initial supported years are:

- `2025`
- `2026`

Rules are versioned by year. If a rule cannot be verified for the requested year, return `UNVERIFIED` or `REVIEW_REQUIRED`; never copy a previous year's value.

## Jurisdictions

- `CH`: Swiss federal / IFD rules.
- `CH-TI`: Canton Ticino rules.
- Municipality: modeled separately where relevant.

## Common Commands

To make this checkout available to Hermes in any chat, link the repository directory under `~/.hermes/skills/` (for example, `~/.hermes/skills/domain/ticino-tax`). The link must point to the directory containing `SKILL.md`, `scripts/`, and `rules/`; a copy of `SKILL.md` alone is insufficient. Start a new Hermes session after linking it, then invoke `/ticino-tax`. Run the commands below from the repository directory and keep private inputs outside it.

```bash
pip install -r requirements.txt   # PyYAML
python3 scripts/validate_tax_year.py 2025
python3 scripts/classify_expense.py --tax-year 2025 --amount 99 --description "software subscription" --document receipt.pdf
python3 scripts/build_profit_loss.py transactions.json --tax-year 2025 --no-vat-registered
python3 scripts/compare_previous_year.py previous.json current.json --tax-year 2025
python3 scripts/validate_return.py workpaper.json --tax-year 2025
python3 scripts/generate_etax_checklist.py workpaper.json --tax-year 2025 --output checklist.csv
python3 -m unittest discover -s tests -t .
```

Exit code 2 from `validate_tax_year`, `validate_return`, or `generate_etax_checklist` means "not fully verified", not a crash. With the current skeleton rule files this is the expected result.

## Status Values

Use the following consistently:

- `VERIFIED`
- `UNVERIFIED`
- `REVIEW_REQUIRED`
- `MISSING_DOCUMENT`
- `NOT_APPLICABLE`

## Traceability Model

Every final checklist row should be traceable:

```text
final tax field
  -> calculation
    -> tax rule
      -> official source
    -> source document
      -> page
      -> extracted value
```

## Rule Files

Rule skeletons live in `rules/<year>/`. A verified numeric rule must include official provenance from sources such as Ticino tax authorities, ESTV/AFC, Swiss federal law/Fedlex, BSV/UFAS for social-insurance matters, or the official Ticino legal collection. Cite a specific page, article, or web-page section. `sole-proprietorship.yaml` accepts both `CH` and `CH-TI` rules; every rule retains its own jurisdiction.

Do not use blogs, accounting-company pages, forums, or AI-generated content as authoritative sources.
