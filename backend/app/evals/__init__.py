"""The model check (A12): exact checks on the scripted questions, retrieval metrics per embedder, the report.

- checks.py: the exact checks, a pure function of a question's `expect` and a ChatReply. No LLM judge.
- model_check.py: runs the questions against the saved model, in the background, on a copy of the state.
- retrieval.py: retrieval questions from structured fields, hit rate at 5 and MRR per embedder.
- runs.py: where runs are saved (next to the state file under evals/; STORE=gcs: the bucket's evals/, B58).
- report.py: one self-contained HTML page from saved runs.
- __main__.py: the command line, for real models and embedders by hand and for the FakeLLM report in CI.
"""
