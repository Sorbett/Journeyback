# JourneyBack Benefits RAG Knowledge Base v1

## Scope

Singapore-first public knowledge base for JourneyBack. It covers embedded travel benefits for The Platinum Card, Platinum Reserve, KrisFlyer Ascend and True Cashback; separately purchased My Travel Insurance; and public Amex Travel, Membership Rewards and Global Assist guidance.

## Files

- `rag/knowledge_base.jsonl`: 107 RAG-ready chunks with citations, authority, product binding and safety fields.
- `rag/source_manifest.csv`: source registry and public URLs.
- `normalized/policy_facts.json`: structured, paraphrased policy facts with page/section locators.
- `normalized/sources.json`: normalized source metadata and hashes.
- `rag/retrieval_qa.json`: ten smoke-test queries and top-5 results.
- `rag/chunk_schema.json`: machine-readable JSON Schema for every RAG chunk.
- `rag/retrieval_policy.json`: strict product filtering, source precedence, conflict and abstention rules.
- `quality_report.json`: automated validation results.
- `raw/html/pages.json`: browser-captured public HTML text snapshots used as staging input.

## Authority order

1. Formal policy wording.
2. Official legal terms.
3. Official operational FAQs and service pages.
4. Product and benefit summaries.

If sources conflict, the formal policy wins only after confirming that the market, product and version are current. Marketing pages must never decide eligibility or limits.

## Retrieval filters

Filter by `market`, `product_code`, `document_type`, `version_status` and `decision_use` before semantic ranking. For a customer answer, require a formal-policy result plus a second operational or claims-support result where relevant.

## Safety boundary

This corpus supports retrieval and explanation. It does not approve insurance claims, promise coverage, trigger payments or replace the latest policy wording and human review.
