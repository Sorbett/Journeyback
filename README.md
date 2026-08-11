# Journeyback

Journeyback is the implementation workspace for the Amex AI Hackathon travel-disruption recovery concept.

## Current status

The Singapore-first Amex travel-benefits knowledge base has been imported into `data/knowledge_base/`. It contains:

- 107 RAG-ready chunks from 14 official sources.
- Product-bound formal policy facts for four Card products and My Travel Insurance.
- Source URLs, citations, page/section locators and authority scores.
- Retrieval, conflict, abstention and human-review rules.
- Retrieval QA and corpus quality reports.

The imported corpus supports retrieval and explanation. It must not autonomously approve a claim or promise coverage.

## Synthetic benchmark

`data/synthetic/` contains 600 deterministic, policy-grounded synthetic travel-disruption cases for development and evaluation. The allocation is fixed at 30% potentially eligible, 25% rule-ineligible, 20% missing evidence, 15% boundary/manual review and 10% unknown or uncovered products. No row contains real customer data or an expected payout.

Regenerate the JSONL benchmark:

```bash
python3 scripts/generate_synthetic_data.py
```

Build the Excel review pack:

```bash
node scripts/build_synthetic_workbook.mjs
```

The review workbook is written to `outputs/synthetic_data/Journeyback_Synthetic_Data_v1.xlsx`.

## Import or refresh the knowledge base

From this directory, run:

```bash
python3 scripts/import_knowledge_base.py \
  --source /path/to/approved/knowledge_base
```

For the original corpus used in this project, the source directory is:

```text
/Users/sorbet/Documents/Codex/2026-08-05/thank-you-for-your-registration-for/Journeyback/data/knowledge_base
```

The script copies the approved runtime artifacts, verifies every file and writes `data/knowledge_base/import_manifest.json` with SHA-256 hashes. Requiring an explicit source prevents a clone on another machine from silently importing the wrong corpus.

## Verify the project data

```bash
python3 -m unittest discover -s tests -v
```

## Load from Python

```python
from journeyback.knowledge_base import KnowledgeBase

kb = KnowledgeBase.load()
print(kb.summary())

platinum_chunks = kb.filter_chunks(product_code="SG_PLATINUM_CHARGE")
```

For local imports, set `PYTHONPATH=src`, or install the project in editable mode after a packaging configuration is added.
