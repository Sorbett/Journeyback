# JourneyBack evaluation holdouts

`retrieval_holdout.jsonl` is a small, manually authored component-level holdout created by reading the public Singapore corpus. It is maintained separately from the 600-case scenario generator and is intended to compare retrieval configurations.

It is not an insurance-claim accuracy benchmark and has not been adjudicated by American Express, Chubb or an independent policy expert. Before production use, replace or extend it with versioned, double-reviewed labels and a sealed test split.

Each row identifies one or more policy chunks that should be retrieved for the query. The evaluation script reports Hit@5, Recall@5, MRR@10 and nDCG@5 for BM25 and, when explicitly requested, the configured semantic embedding model.
