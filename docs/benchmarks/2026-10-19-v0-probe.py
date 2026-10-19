#!/usr/bin/env python3
"""V0 gate (Opus r1 B1) — re-probe with facts in the EXACT E3 structured schema.

Rows are {kind, id, span, note}: kind from a fixed enum, id an identifier, span
integer pair, note a structural COUNT/presence description — no conclusion text,
no domain prose, nothing verdict-laden. Units: M3, N3, N4 (the in-scope P2/E6
classes) 3x clean vs 3x structured-fact, plus one clean-unit anchoring control
(synthetic irrelevant row force-attached, must stay under the report gate).

21 calls. Runs under the SAME interpreter as the installed binary.
"""
import importlib.util, importlib.machinery, json, os, statistics, subprocess, time, shutil

SOR = "/home/kv-thinkpad-t420-ubuntu/.local/bin/system-one-reviewer"
REPO = "/home/kv-thinkpad-t420-ubuntu/code/github/equationalapplications/SynapseTree-login"
REV = "d70d225"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v0-probe-results.json")

spec = importlib.util.spec_from_loader("sor", importlib.machinery.SourceFileLoader("sor", SOR))
sor = importlib.util.module_from_spec(spec); spec.loader.exec_module(sor)
ask = sor.make_provider("jev", None, sor.load_api_key())

def img(path):
    return subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"],
                          capture_output=True, text=True).stdout.splitlines()

UNITS = [
    dict(id="M3-mapKmsError", file="src/control-plane/custody-envelope.ts",
         span=(114, 221), anchor=157,
         rows=[{"kind": "branch-token-polarity",
                "id": "mapKmsError",
                "span": [171, 174],
                "note": "condition identifier contains 'unavailable' (2 tokens); true-branch constructs CustodyKmsUnavailableError (1 site); false-branch constructs CustodyIntegrityError (1 site); file contains 0 other mapping branches"}]),
    dict(id="N3-envelopeVersion", file="src/control-plane/custody-envelope.ts",
         span=(222, 335), anchor=322,
         rows=[{"kind": "field-never-compared",
                "id": "envelopeVersion",
                "span": [116, 116],
                "note": "declared literal type at 1 site; constructed at 1 site; comparison sites in file: 0; sibling field keyVersion: 1 comparison site"}]),
    dict(id="N4-placeholder-test", file="tests/unit/custody-stack.test.ts",
         span=(102, 212), anchor=200,
         rows=[{"kind": "assertion-no-subject-call",
                "id": "Match.objectLike",
                "span": [200, 200],
                "note": "assertions in block: 1 (typeof check); calls into tested module in block: 0"}]),
    dict(id="CONTROL-clean-registration", file="src/control-plane/custody-registration.ts",
         span=(120, 123), anchor=121,
         rows=[{"kind": "field-never-compared",
                "id": "providerId",
                "span": [121, 121],
                "note": "declared at 1 site; comparison sites in file: 0"}]),
]

REPEATS = 3
results = []
for u in UNITS:
    lines = img(u["file"])
    s, e = u["span"]
    base_state = {
        "file": u["file"],
        "location": f"around line {u['anchor']}",
        "change_type": "code-change",
        "code_before_change": lines[max(0, s - 4):s - 1],
        "code_after_change": lines[s - 1:e],
    }
    fact_state = dict(base_state)
    fact_state["structural_facts"] = u["rows"]
    for variant, state in (("clean", base_state), ("fact", fact_state)):
        for rep in range(REPEATS):
            try:
                payload, ms = ask(state, sor.HUNK_QUESTIONS)
                ans = payload.get("answers", payload)
                rec = dict(unit=u["id"], variant=variant, rep=rep + 1, ok=True,
                           is_real=ans.get("is_real_issue"),
                           severity=ans.get("severity"),
                           category=ans.get("category"), latency_ms=round(ms, 1))
            except Exception as ex:
                rec = dict(unit=u["id"], variant=variant, rep=rep + 1, ok=False,
                           error=repr(ex)[:300])
            results.append(rec)
            print(f"{u['id']:28} {variant:5} r{rec['rep']}  {json.dumps(rec.get('is_real'))}", flush=True)

with open(OUT, "w") as f:
    json.dump(results, f, indent=1)

def num(v):
    return v.get("noul") if isinstance(v, dict) else v

print("\n==== V0 SUMMARY ====")
for u in UNITS:
    line = f"{u['id']:28}"
    for variant in ("clean", "fact"):
        vals = [num(r.get("is_real")) for r in results if r["unit"] == u["id"] and r["variant"] == variant and r["ok"]]
        line += f"  {variant}={statistics.mean(vals):.3f} [{min(vals):.2f}-{max(vals):.2f}]"
    print(line)
ctl = [num(r.get("is_real")) for r in results if r["unit"].startswith("CONTROL") and r["variant"] == "fact" and r["ok"]]
print(f"anchoring control (fact on clean unit): max={max(ctl):.2f} -> {'PASS (below 0.50)' if max(ctl) < 0.50 else 'FAIL'}")
