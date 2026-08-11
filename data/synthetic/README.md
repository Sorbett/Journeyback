# Journeyback Synthetic Dataset v1

This folder contains 600 deterministic, fully synthetic travel-disruption cases grounded in the imported Singapore Amex public-policy corpus.

## Files

- `journeyback_cases.jsonl`: runtime and evaluation cases.
- `case_schema.json`: field contract.
- `evaluation_framework.json`: weighted 100-point system evaluation framework and hard safety caps.
- `quality_report.json`: exact distributions and automated validation results.

## Strict allocation

- 30% potentially eligible with complete evidence.
- 25% unlikely under a stated rule.
- 20% missing required evidence.
- 15% threshold or timing boundary cases.
- 10% unknown or currently uncovered products.
- Split: 60% development, 20% validation, 20% held-out test.

## Safety

Every record has `synthetic=true`, `expected_payout_sgd=null` and `human_review_required=true`. The labels support benchmarking and demonstration only; they do not approve insurance claims or promise coverage.

## Regenerate

```bash
python3 scripts/generate_synthetic_data.py
```
