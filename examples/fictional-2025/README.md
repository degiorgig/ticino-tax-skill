# Fictional end-to-end example (tax year 2025)

**Everything here is invented.** Names, employers, amounts, account numbers and the municipality do not
exist. The `.txt` files stand in for the PDFs a real taxpayer would have. The example exists to exercise
all nine workflow steps of `SKILL.md` and is run by `tests/test_end_to_end.py`.

Household: Anna Esempio (P1, employee), Luca Esempio (P2, employee 60% + accessory sole proprietorship,
not VAT registered), one child. Real taxpayer data must never be stored in this repository.

What the example shows on purpose:

- fields that can be `VERIFIED` today (pillar 3a, insurance premiums cap, child deduction, other professional costs);
- fields that must stay `REVIEW_REQUIRED` because no verified 2025 rule exists yet (salary income, self-employment profit);
- a checklist where only the failing or unresolved rows are downgraded.
