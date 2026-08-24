# JourneyBack pipeline golden path

This directory contains one deliberately small end-to-end test set. It is not another benchmark and it does not mirror all 600 synthetic cases.

`JB-SYN-0331` is used because its Card product and payment are already known, while the benchmark-authored blocking gap is `flight_ticket`. Three readable TXT files provide the actual contents needed for semantic validation: the ticket and itinerary, the carrier's event confirmation and the itemised receipts. There is no manifest or per-case bundle machinery.

Run the live validation with:

```bash
python3 scripts/test_pipeline.py
```

The script starts a temporary local JourneyBack server, uses the configured text and embedding APIs, uploads the three files, runs live LLM + BGE-M3 policy reanalysis and downloads the generated review pack. Results are written to `outputs/pipeline_validation/latest.json` and `latest.html`.
