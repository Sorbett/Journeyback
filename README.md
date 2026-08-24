# JourneyBack

JourneyBack is a proactive travel-disruption recovery MVP for the Amex AI Hackathon 2026. It monitors a customer's itinerary, Card payment and carrier status; when a disruption is detected, it automatically matches the event to potentially relevant public benefit wording, asks for the single fact currently blocking progress and prepares an evidence pack for formal review.

The product is deliberately presented as a recovery workspace rather than a chatbot or a passive benefits dashboard. The UI exposes what the agent checked, which source supports the guidance, what changed after new evidence and which server-backed artifact was created.

## Random-traveller demonstration

The MVP randomly selects one traveller from the deterministic 600-case synthetic benchmark. Each selection changes the journey, Card or insurance product, disruption, language, policy outcome and available evidence. Use `Try another traveller` to sample a new case and `Simulate disruption` to materialise its expected result.

The initial disruption path is deliberately instant and offline: it materialises the benchmark's expected recovery route without making a model call. This keeps product demonstrations fluid and makes every displayed result reproducible. It is clearly labelled as a synthetic coverage scenario, not a model-accuracy result. Selecting a Card product or uploading the requested evidence then runs the real LLM and retrieval pipeline before the workspace changes its guidance.

Recovery actions are not cosmetic checkboxes. The server can create and persist a carrier-confirmation request or a structured human-review pack under the ignored local upload directory, and the browser can download the result.

The real pipeline remains available through `POST /api/analyze` and `POST /api/evaluate`. In production, its operational event would come from a carrier, travel platform or monitoring feed.

## Run the MVP

The application uses the Python standard library, DeepSeek for structured text generation and SiliconFlow-hosted BGE-M3 for semantic embeddings. No package installation is required.

1. Copy the configuration template:

   ```bash
   cp .env.example .env
   ```

2. Add both provider keys to `.env`:

   ```env
   DEEPSEEK_API_KEY=replace-with-your-deepseek-api-key
   DEEPSEEK_BASE_URL=https://api.deepseek.com
   JOURNEYBACK_LLM_PROVIDER=deepseek
   JOURNEYBACK_LLM_MODEL=deepseek-v4-flash

   SILICONFLOW_API_KEY=replace-with-your-siliconflow-api-key
   SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
   JOURNEYBACK_EMBEDDING_PROVIDER=siliconflow
   JOURNEYBACK_EMBEDDING_MODEL=BAAI/bge-m3
   ```

3. Start the application:

   ```bash
   python3 run_mvp.py
   ```

4. Open `http://127.0.0.1:8000`.

The real `.env`, local embedding cache and locally uploaded demo evidence are excluded by `.gitignore`. Never place an API key in `web/app.js`, commit it to Git, or send it to the browser.

## Proactive pipeline

```text
Itinerary + Card payment + carrier status
                    ↓
          Operational event detected
                    ↓
        Structured LLM fact extraction
                    ↓
 BM25 + BGE-M3 retrieval over 107 public chunks
                    ↓
       Grounded recovery-plan generation
                    ↓
 Citation validation + evidence-pack assembly
                    ↓
          Formal human review remains required
```

There is no hand-authored event threshold table or product-specific keyword score in the live request path. Generic BM25 and BGE-M3 ranks are combined with reciprocal-rank fusion; deterministic code is otherwise limited to event assembly, input validation, citation allow-listing, evidence-pack state and safety postconditions.

The first **live** request embeds any missing or changed knowledge chunks and writes a model-specific cache under `.journeyback_cache/`. Server startup itself does not call the embedding API. Later live requests normally embed only the new event query unless the corpus or embedding model changes. `GET /api/health` exposes safe cache diagnostics (`cache_present`, cache size and in-memory state) without exposing credentials.

The default hybrid implementation uses DeepSeek Chat Completions JSON Output for the two text stages and SiliconFlow's [Embeddings endpoint](https://api-docs.siliconflow.cn/docs/api/embeddings-post) with BGE-M3 for semantic retrieval. Generated JSON is validated against the application schema before use. OpenAI remains an optional text or embedding provider through configuration, but is not required by the default setup.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DEEPSEEK_API_KEY` | required for default mode | Server-side credential for text generation |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek Chat Completions API base |
| `JOURNEYBACK_LLM_PROVIDER` | `deepseek` | Text provider: `deepseek` or `openai` |
| `JOURNEYBACK_LLM_MODEL` | `deepseek-v4-flash` | Operational fact extraction and grounded guidance |
| `SILICONFLOW_API_KEY` | required | Server-side credential for semantic embeddings |
| `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | SiliconFlow API base |
| `JOURNEYBACK_EMBEDDING_PROVIDER` | `siliconflow` | Embedding provider: `siliconflow` or `openai` |
| `JOURNEYBACK_EMBEDDING_MODEL` | `BAAI/bge-m3` | Multilingual semantic retrieval model |
| `JOURNEYBACK_REASONING_EFFORT` | `low` | Latency and quality control |
| `JOURNEYBACK_RAG_TOP_K` | `8` | Evidence chunks passed to the guidance stage |
| `JOURNEYBACK_LLM_TIMEOUT` | `60` | API timeout in seconds |

`deepseek-v4-flash` is the economical default for the two text stages, while the standard SiliconFlow `BAAI/bge-m3` endpoint keeps multilingual retrieval inexpensive. To use OpenAI instead, set the relevant provider to `openai`, configure `OPENAI_API_KEY` and `OPENAI_BASE_URL`, and choose the corresponding model. Model choices should still be evaluated on representative cases before a production decision.

In DeepSeek mode, JourneyBack maps `none` and `low` to non-thinking mode for predictable demo latency; `medium` and `high` use DeepSeek's high reasoning tier, while `xhigh` and `max` use its max tier.

## API

- `GET /api/trip` randomly selects a normal monitored synthetic itinerary.
- `GET /api/trip?case_id=JB-SYN-0001` returns a reproducible benchmark traveller.
- `POST /api/detect` materialises the selected case's expected result immediately; pass `{"case_id":"JB-SYN-0001","live":true}` to explicitly run the real LLM/RAG pipeline.
- `POST /api/evidence` validates and stores a selected PDF, JPG, PNG or TXT file under the ignored local `.journeyback_uploads/` directory.
- `POST /api/product-confirmation` validates and persists the selected Card before live policy analysis begins.
- `POST /api/reanalyse` validates a submitted Card product and uploaded evidence, then runs the real LLM + embedding-policy retrieval pipeline before updating the recovery case.
- `POST /api/action` creates a persisted carrier-request draft or formal-review pack instead of toggling local UI state.
- `GET /api/artifact` downloads a server-created recovery artifact after validating its case and artifact identifiers.
- `GET /api/demo/insights` aggregates the product-need metrics shown on the page.
- `GET /api/demo/pipeline-test-kit?case_id=...` returns the integrity-checked synthetic evidence package for any upload-blocked benchmark case. Post-confirmation packages also require `product_code=...` so their documents are bound to the Card the user selected.
- `GET /api/health` reports service readiness, model names, embedding-cache state and knowledge-base status without exposing an API key.
- `GET /evaluation` serves the product-outcome benchmark overview.
- `GET /evaluation/retrieval` serves the supporting retrieval benchmark report.
- `GET /evaluation/scenarios` serves the synthetic scenario-coverage report.

The recovery case contains the detected event, validated benefit evidence, ordered actions and evidence-pack completion state. It never returns an expected payout and always requires formal human review.

Evidence progress is server-backed. Selecting a Card product or file does not mark an item complete by itself: the server must validate the submission and complete live policy reanalysis first. Any new evidence gaps identified by the model are added back to the evidence wallet for another upload-and-review cycle.

All 120 cases blocked by uploadable documents include a matched synthetic TXT evidence package. The page exposes a one-click guided pipeline for these cases, dynamically uploads the case's actual missing documents, runs live policy reanalysis and creates a specialist review pack. All 23 product-blocked flight-delay cases also receive a runtime-bound ticket, carrier confirmation and itemised receipt after Card selection. Card-loss and hotel cases without a defensible matched benefit, such as `JB-SYN-0543`, still make a safe operational or specialist handoff instead of inventing irrelevant evidence. Regenerate the fixtures with `python3 scripts/generate_pipeline_evidence.py` after changing the benchmark data.

Uploaded originals remain in the ignored local `.journeyback_uploads/` directory. For plain-text files, the server sends a bounded extracted-text excerpt plus the user's document note to the configured model. For PDFs and images in this zero-dependency prototype, only verified metadata and the user-entered note are sent; the UI does not claim that unreadable binary contents were analysed.

## Test and evaluate

Run the offline suite. Model calls use a deterministic test double, so tests do not require a key or create API spend:

```bash
python3 -m unittest discover -s tests -v
```

Run the single-case live pipeline check after configuring the text and embedding API keys:

```bash
python3 scripts/test_pipeline.py
```

This uses three curated TXT files for `JB-SYN-0331`—ticket/itinerary, carrier confirmation and itemised receipts—and verifies the actual HTTP path from evidence upload through LLM extraction, BGE-M3 hybrid retrieval, grounded citations and a downloadable review pack. It writes a five-stage PASS/FAIL report to `outputs/pipeline_validation/latest.html`; it is intentionally separate from the 600-case scenario benchmark.

Run all 600 generated journeys and rebuild the standalone visual report:

```bash
PYTHONPATH=src python3 scripts/evaluate_synthetic_cases.py
```

This writes:

- `outputs/synthetic_evaluation/results.jsonl` — one materialised expected result per case.
- `outputs/synthetic_evaluation/summary.json` — aggregate distributions and safety metrics.
- `outputs/synthetic_evaluation/report.html` — responsive charts explaining the product need.

The deterministic report validates scenario coverage and expected routing; it does not claim live-model accuracy or real-world claim incidence.

Build the product-outcome-first benchmark overview after refreshing the component reports:

```bash
python3 scripts/evaluate_product.py
```

This makes customer and specialist outcomes the primary scorecard—first-pass evidence readiness, time to a review-ready pack, follow-up burden, reviewer acceptance and safe handoff. It deliberately leaves business uplift unscored until a static-form baseline and blinded human review are available. Retrieval metrics appear only as supporting evidence.

Run the separate author-reviewed retrieval holdout with the offline BM25 baseline:

```bash
PYTHONPATH=src python3 scripts/evaluate_retrieval.py
```

After configuring SiliconFlow, compare BM25, BGE-M3 and their reciprocal-rank-fusion hybrid:

```bash
PYTHONPATH=src python3 scripts/evaluate_retrieval.py --semantic
```

This writes `outputs/retrieval_evaluation/metrics.json` and `report.html`. The 22-query English/Chinese holdout is maintained separately from the 600-case generator. Its labels are author-reviewed rather than independently policy-adjudicated, so it measures component retrieval only—not claim eligibility or customer value.

After configuring a real key, run the live smoke evaluation:

```bash
PYTHONPATH=src python3 scripts/evaluate_mvp.py
```

The report in `outputs/mvp_evaluation/metrics.json` measures API completion, validated citations, guardrails and latency. It is not a real claim-accuracy score; that requires current internal policy data and human-labelled historical cases.

## Knowledge base

`data/knowledge_base/` contains the Singapore-first public corpus:

- 107 RAG chunks from 14 official sources.
- Formal wording for four Card products and My Travel Insurance.
- Product metadata, source URLs, sections, pages and authority scores.
- Corpus quality and retrieval QA reports.

Refresh an approved corpus with:

```bash
python3 scripts/import_knowledge_base.py --source /path/to/approved/knowledge_base
```

## Safety and privacy boundary

- The production design should minimise personal data sent to any model provider.
- Retrieved text is treated as data rather than model instructions.
- Citations that were not retrieved are removed before reaching the customer.
- The system does not approve claims, reject claims or guarantee payment.
- Public benefit wording must be checked for currency before production use.
