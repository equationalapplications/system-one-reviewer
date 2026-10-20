# OPTIONAL research suggestions — for reviewer adoption into SOR v0.9

Per Kurt's direction (msg 1561794344611221605): these are OPTIONAL items the
review cycle may adopt into the spec. None is a commitment. Sources: the
external landscape research digest (`docs/benchmarks/2026-10-19-landscape-research.md`,
Sonnet run with URLs per claim) and the day's measured record.

| # | Suggestion | Source | Where it would land | Adoption cost |
|---|---|---|---|---|
| OS1 | Hard FP-rate retirement gate per reflex class, Tricorder-style: a class whose measured FP rate crosses the line is auto-demoted to telemetry | Google Tricorder production practice (digest §2) | INTENT rule 6b already has ship/retire bars; add the automatic demotion trigger to ROADMAP S0 | Low — ledger math only |
| OS2 | Embed-and-match reflex: embed prepared sites, rank against a library of known bug shapes; ranking as the reflex instead of free-form judgment | Feature Slice Matching (arXiv 2512.24858 — rejected LLM judges as unstable) | New E7 candidate; needs an embedding step (cost envelope question) | Medium |
| OS3 | Calibration audit of the 0.80 gate: check the gate is CALIBRATED (0.80 ≈ 80% correct) not merely FP-reducing | Selective-prediction/abstention literature (digest §4) | V2/V3 reporting: add a reliability diagram over golden+adjudicated scores | Low — reporting only |
| OS4 | "Memories"-style feedback: per-repo dispositions feed future fact rows (hide-don't-delete default for noisy findings) | Semgrep Assistant (digest §3) | S0 ledger schema: reserve a dispositions-feed field | Low-medium |
| OS5 | Cite BugLens' 0.1→0.72 precision lift (deterministic candidates + model judge) as the external benchmark in the spec's evidence section | BugLens paper (digest §2) | Problem section citation | Trivial |

Reviewer guidance: adopt only what a gate can measure. OS1/OS3/OS5 are
near-free; OS2 needs a cost-envelope answer first (INTENT rule 1); OS4 rides S0.
