#!/usr/bin/env python3
"""Experiment #4 — fact-sensitivity probe (Fable run-2, missing experiment 4).

For each of the 6 defect-bearing units from the full-coverage Stage A golden run,
send the unit's state to Jev 3x exactly as production packaging builds it (clean),
and 3x with a hand-written deterministic fact row of the P2/P3 shape appended under
a `structural_facts` key. Record is_real / severity / category per call.

NOTE (Opus m1/m6, honest baseline): states here are HAND-BUILT — `location`
uses the golden anchor, `code_before_change` is 3 context lines, no diff
entries — NOT byte-faithful production packaging (clean scores track
production within ~0.04 but N3 sits on the opposite side of the gate: 0.52
here vs 0.48 there). V2-priming runs must rebuild states via `hunk_state()`
instead. This script imports the INSTALLED binary, not repo source.

36 calls, fractions of a cent. Read-only w.r.t. the repo; appends NOTHING to
metrics.jsonl (calls are made directly, not through main()).
"""
import importlib.util, importlib.machinery, json, os, subprocess, statistics, time

SOR = "/home/kv-thinkpad-t420-ubuntu/.local/bin/system-one-reviewer"
REPO = "/home/kv-thinkpad-t420-ubuntu/code/github/equationalapplications/SynapseTree-login"
REV = "d70d225"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fact-probe-results.json")

spec = importlib.util.spec_from_loader("sor", importlib.machinery.SourceFileLoader("sor", SOR))
sor = importlib.util.module_from_spec(spec); spec.loader.exec_module(sor)
ask = sor.make_provider("jev", None, sor.load_api_key())

def img(path):
    return subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"],
                          capture_output=True, text=True).stdout.splitlines()

UNITS = [
    dict(id="B1+N1-custody-tables", file="src/control-plane/custody-tables.ts",
         span=(1, 64), anchor=64,
         facts=[
             "IAM: condition key 'kms:EncryptionContextKeys' is MULTIVALUED; the operator in use here is StringEquals, the SINGLE-VALUED form. Single-valued operators never match multivalued keys — the condition fails closed and denies every Decrypt.",
             "IAM: actions kms:VerifyMac and kms:GenerateMac are granted on the symmetric ENCRYPT_DECRYPT CMK; MAC operations are valid only on HMAC keys, so these grants are dead.",
         ]),
    dict(id="B2+M2-stack-trail", file="infra/stack.ts",
         span=(748, 846), anchor=789,
         facts=[
             "CloudTrail: eventCategory 'Data' selects data events; AWS KMS cryptographic calls (Decrypt, GenerateDataKey, GenerateMac, VerifyMac) are MANAGEMENT events. A KMS selector using eventCategory Data captures no KMS crypto calls.",
             "CloudTrail: the cloudWatchLogsLogGroupArn property takes the bare log-group ARN — no ':*' or ':log-stream:*' suffix.",
         ]),
    dict(id="M1-stack-filter", file="infra/stack.ts",
         span=(847, 935), anchor=854,
         facts=[
             "CloudTrail log-event record field is $.resources[0].ARN (uppercase ARN). A metric filter using $.resources[0].arn (lowercase) never matches any event.",
         ]),
    dict(id="M3-envelope-mapkms", file="src/control-plane/custody-envelope.ts",
         span=(114, 221), anchor=157,
         facts=[
             "Error-taxonomy polarity: the condition tests for KMS-UNAVAILABILITY names, but the DEFAULT branch (no match) maps to CustodyIntegrityError — i.e. any unexpected KMS error (network failure, timeout variant, unknown name) reads as tampering. The safe default is the retryable unavailability error.",
         ]),
    dict(id="N3-envelope-opengate", file="src/control-plane/custody-envelope.ts",
         span=(222, 335), anchor=322,
         facts=[
             "Interface field envelopeVersion is declared with literal type 1 and always constructed as 1, but NO consuming function ever compares it. The sibling field keyVersion HAS a rejection gate. A blob claiming an unsupported envelopeVersion is accepted.",
         ]),
    dict(id="N4-placeholder-test", file="tests/unit/custody-stack.test.ts",
         span=(102, 212), anchor=200,
         facts=[
             "This test block's only assertion is a typeof check on an imported identifier (Match.objectLike); no function under test is called. It exists to justify the import.",
         ]),
]

REPEATS = 3
results = []
for u in UNITS:
    lines = img(u["file"])
    s, e = u["span"]
    body = lines[s - 1:e]
    ctx_before = lines[max(0, s - 4):s - 1]
    base_state = {
        "file": u["file"],
        "location": f"around line {u['anchor']}",
        "change_type": "code-change",
        "code_before_change": ctx_before,
        "code_after_change": body,
    }
    fact_state = dict(base_state)
    fact_state["structural_facts"] = u["facts"]
    for variant, state in (("clean", base_state), ("fact", fact_state)):
        for rep in range(REPEATS):
            t0 = time.time()
            try:
                payload, ms = ask(state, sor.HUNK_QUESTIONS)
                ans = payload.get("answers", payload)
                rec = dict(unit=u["id"], variant=variant, rep=rep + 1,
                           severity=ans.get("severity"), is_real=ans.get("is_real_issue"),
                           category=ans.get("category"), latency_ms=round(ms, 1),
                           ok=True, raw=ans)
            except Exception as ex:
                rec = dict(unit=u["id"], variant=variant, rep=rep + 1, ok=False,
                           error=repr(ex)[:300])
            rec["wall_s"] = round(time.time() - t0, 1)
            results.append(rec)
            print(f"{u['id']:28} {variant:5} r{rec['rep']}  is_real={rec.get('is_real')} sev={rec.get('severity')} cat={rec.get('category')} {'ERR '+rec.get('error','')[:80] if not rec['ok'] else ''}", flush=True)

with open(OUT, "w") as f:
    json.dump(results, f, indent=1)

print("\n==== SUMMARY (is_real means) ====")
for u in UNITS:
    for variant in ("clean", "fact"):
        vals = [r["is_real"] for r in results if r["unit"] == u["id"] and r["variant"] == variant and r["ok"]]
        sevs = [r["severity"] for r in results if r["unit"] == u["id"] and r["variant"] == variant and r["ok"]]
        if vals:
            print(f"{u['id']:28} {variant:5} is_real mean={statistics.mean(vals):.3f} (min {min(vals):.2f} max {max(vals):.2f})  sev mean={statistics.mean(sevs):.2f}")
        else:
            print(f"{u['id']:28} {variant:5} ALL CALLS FAILED")
