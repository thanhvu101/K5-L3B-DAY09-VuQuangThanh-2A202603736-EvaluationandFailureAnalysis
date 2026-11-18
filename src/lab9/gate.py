"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item


def _ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    """On the same eval-set version thresholds may only get stricter (ratchet)."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    problems: list[str] = []
    current = {m["id"]: m for m in spec.get("metrics") or []}
    for old in base_spec.get("metrics") or []:
        mid = old["id"]
        now = current.get(mid)
        if now is None:
            problems.append(f"metric {mid} disappeared (ratchet)")
            continue
        ot, nt = old.get("threshold") or {}, now.get("threshold") or {}
        if "max" in ot and ("max" not in nt or nt["max"] > ot["max"]):
            problems.append(f"metric {mid}: max rose {ot['max']} -> {nt.get('max')} (ratchet)")
        if "min" in ot and ("min" not in nt or nt["min"] < ot["min"]):
            problems.append(f"metric {mid}: min fell {ot['min']} -> {nt.get('min')} (ratchet)")
        if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
            problems.append(f"metric {mid}: no_significant_drop removed (ratchet)")
        if old.get("blocking") and not now.get("blocking"):
            problems.append(f"metric {mid}: blocking removed (ratchet)")
    current_slices = {x["name"]: x for x in spec.get("slices") or []}
    for old in base_spec.get("slices") or []:
        name = old["name"]
        now = current_slices.get(name)
        if now is None:
            problems.append(f"slice {name} disappeared (ratchet)")
            continue
        if old.get("metric") != now.get("metric"):
            problems.append(f"slice {name}: metric changed (ratchet)")
        if "min" in old and ("min" not in now or now["min"] < old["min"]):
            problems.append(f"slice {name}: min fell (ratchet)")
        if old.get("no_significant_drop") and not now.get("no_significant_drop"):
            problems.append(f"slice {name}: no_significant_drop removed (ratchet)")
        if old.get("blocking") and not now.get("blocking"):
            problems.append(f"slice {name}: blocking removed (ratchet)")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Catches NaN/inf metrics, dropped or duplicated rows, cherry-picked (item, seed) sets,
    evaluator failures or crashed (None) grader values, hand-edited metric values, relabelled
    slices, and a loosened spec on the same eval-set version (ratchet)."""
    problems: list[str] = []
    metrics = pr.get("metrics") or {}
    for mid, val in metrics.items():
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            problems.append(f"metric {mid} is {val}")
    rows = pr.get("rows") or []
    manifest = pr.get("manifest") or {}
    items, seeds = manifest.get("items"), manifest.get("seeds") or []
    if not isinstance(items, int) or not seeds or not rows:
        problems.append("manifest items/seeds or rows missing")
        return problems
    expected = items * len(seeds)
    if len(rows) != expected:
        problems.append(f"row count {len(rows)} != {items} items x {len(seeds)} seeds = {expected}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append("duplicate (item_id, seed) rows")
    base_rows = base.get("rows") or []
    if set(keys) != {(r.get("item_id"), r.get("seed")) for r in base_rows}:
        problems.append("(item_id, seed) set differs from the baseline's")
    base_slices = {r.get("item_id"): tuple(sorted(r.get("slices") or [])) for r in base_rows}
    for row in rows:
        iid = row.get("item_id")
        if iid in base_slices and tuple(sorted(row.get("slices") or [])) != base_slices[iid]:
            problems.append(f"{iid}: slice tags differ from the baseline's")
            break
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the report")
    row_keys = set(rows[0])
    graded = [m["id"] for m in spec.get("metrics") or [] if m["id"] in row_keys]
    for row in rows:
        missing = [mid for mid in graded if row.get(mid) is None]
        if missing:
            problems.append(f"{row.get('item_id')}@{row.get('seed')}: no value for {missing}")
            break
    computed = aggregate([{**r, "cost": r.get("cost", 0.0)} for r in rows], graded,
                        k_values=spec.get("pass_k", []))
    for mid, val in metrics.items():
        got = computed.get(mid)
        if isinstance(val, (int, float)) and isinstance(got, (int, float)):
            if abs(float(val) - float(got)) > 1e-6:
                problems.append(f"metric {mid} {val} != recomputed {got} (report edited?)")
    if base_spec is not None:
        problems += _ratchet_problems(spec, base_spec)
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each spec["slices"] entry compute the mean of per_item() over the slice's items; fail
    below "min" or when the paired CI of the slice lies entirely below 0 (no_significant_drop).
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for entry in spec.get("slices") or []:
        name, metric = entry["name"], entry["metric"]
        left = per_item(pr, metric, slice_name=name)
        right = per_item(base, metric, slice_name=name)
        keys = sorted(set(left) & set(right))
        if not keys:
            lines.append(f"  slice:{name}/{metric:<14} {'-':<8} {'no rows in PR and baseline':<40} skip")
            continue
        val = round(sum(left[k] for k in keys) / len(keys), 4)
        fail = "min" in entry and val < entry["min"]
        note = ""
        if entry.get("no_significant_drop") and len(keys) > 1:
            d, lo, hi = stats.paired_bootstrap([left[k] for k in keys], [right[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"{chr(0x394)} {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            fail = fail or hi < 0
        label = ("BLOCK" if entry.get("blocking") else "warn") if fail else "ok"
        shown = json.dumps({k: entry[k] for k in ("min", "no_significant_drop") if k in entry})
        lines.append(f"  slice:{name}/{metric:<14} {val!s:<8} {shown:<40} {note:<28} {label}")
        if fail and entry.get("blocking"):
            blocked.append(f"slice:{name}/{metric}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
