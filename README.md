# JourneyBack

JourneyBack is a proactive travel-disruption recovery MVP for the Amex AI Hackathon 2026. It monitors a customer's itinerary, Card payment and carrier status; when a disruption is detected, it automatically matches the event to potentially relevant public benefit wording, prioritises recovery actions and prepares an evidence pack for formal review.

The product is deliberately presented as a trip-management workflow rather than a chatbot.

## Demonstration scenario

The MVP opens on a normal monitored business trip from Singapore to Tokyo:

- An outbound and return flight are present in the itinerary.
- A Tokyo hotel reservation is confirmed.
- The round-trip payment with The Platinum Card is verified.
- Itinerary, payment and carrier-status signals are connected.
- No disruption is initially shown.

The `Simulate baggage delay` control represents an incoming carrier event. JourneyBack then:

1. Creates a structured baggage-delay incident seven hours after arrival.
2. Uses an LLM to extract the operational facts.
3. Uses embeddings to retrieve relevant evidence from the 107-chunk knowledge base.
4. Uses a grounded LLM response to recommend recovery actions.
5. Validates every cited chunk before displaying it.
6. Creates an evidence checklist showing what is already verified and what remains outstanding.

The control exists only to make the automatic trigger demonstrable in Round 2. In a production integration, the event would come from a carrier, travel platform or operational feed.

## Run the MVP

The application uses the Python standard library and an OpenAI-compatible API. No package installation is required.

1. Copy the configuration template:

   ```bash
   cp .env.example .env
   ```

2. Add the API key to `.env`:

   ```env
   OPENAI_API_KEY=replace-with-your-api-key
   JOURNEYBACK_LLM_MODEL=gpt-5.4-nano
   JOURNEYBACK_EMBEDDING_MODEL=text-embedding-3-small
   ```

3. Start the application:

   ```bash
   python3 run_mvp.py
   ```

4. Open `http://127.0.0.1:8000`.

The real `.env` and local embedding cache are excluded by `.gitignore`. Never place an API key in `web/app.js`, commit it to Git, or send it to the browser.

## Proactive pipeline

```text
Itinerary + Card payment + carrier status
                    ↓
          Operational event detected
                    ↓
        Structured LLM fact extraction
                    ↓
    Embedding search over 107 public chunks
                    ↓
       Grounded recovery-plan generation
                    ↓
 Citation validation + evidence-pack assembly
                    ↓
          Formal human review remains required
```

There is no hand-authored event threshold table or keyword score in the live request path. Deterministic code is limited to event assembly, input validation, vector similarity, citation allow-listing, evidence-pack state and safety postconditions.

The first live request embeds the knowledge corpus and writes a model-specific cache under `.journeyback_cache/`. Later requests normally embed only the new event query unless the corpus or embedding model changes.

The implementation follows OpenAI's [Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) and [Embeddings](https://developers.openai.com/api/docs/guides/embeddings) guidance.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | required | Server-side API credential |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base |
| `JOURNEYBACK_LLM_MODEL` | `gpt-5.4-nano` | Operational fact extraction and grounded guidance |
| `JOURNEYBACK_EMBEDDING_MODEL` | `text-embedding-3-small` | Semantic retrieval model |
| `JOURNEYBACK_REASONING_EFFORT` | `low` | Latency and quality control |
| `JOURNEYBACK_RAG_TOP_K` | `8` | Evidence chunks passed to the guidance stage |
| `JOURNEYBACK_LLM_TIMEOUT` | `60` | API timeout in seconds |

`gpt-5.4-nano` is the economical default for the MVP. Model names remain configurable so representative cases can be evaluated against a stronger model before a production decision.

## API

- `GET /api/trip` returns the normal monitored itinerary.
- `POST /api/detect` simulates an operational disruption signal and returns the complete recovery case.
- `GET /api/health` reports service readiness, model names and knowledge-base status without exposing the API key.

The recovery case contains the detected event, validated benefit evidence, ordered actions and evidence-pack completion state. It never returns an expected payout and always requires formal human review.

## Test and evaluate

Run the offline suite. Model calls use a deterministic test double, so tests do not require a key or create API spend:

```bash
python3 -m unittest discover -s tests -v
```

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
