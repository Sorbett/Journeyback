# JourneyBack synthetic evidence packages

This directory contains deterministic TXT fixtures for all 120 benchmark cases that are blocked by uploadable evidence. Each case directory has a `manifest.json` with the matched product, original benchmark hash, evidence codes, file names, sizes and SHA-256 digests. The root `manifest.json` indexes all packages.

The fixtures do not change the benchmark labels. For every case except `JB-SYN-0331`, the package contains exactly the documents listed in `expected_missing_documents`. `JB-SYN-0331` remains the curated golden path and intentionally includes ticket/itinerary, carrier confirmation and receipts so the full three-upload flow remains reproducible.

Regenerate the packages after changing the synthetic dataset with:

```bash
python3 scripts/generate_pipeline_evidence.py
```

The generated documents copy only synthetic case facts such as product, route, event, duration, expense and traveller relationship. They are clearly marked as synthetic and must not be treated as real tickets, carrier records, receipts or policy certificates.

## Live golden-path check

Run the live validation with:

```bash
python3 scripts/test_pipeline.py
```

The script starts a temporary local JourneyBack server, uses the configured text and embedding APIs, uploads the three `JB-SYN-0331` files, runs live LLM + BGE-M3 policy reanalysis and downloads the generated review pack. Results are written to `outputs/pipeline_validation/latest.json` and `latest.html`.
