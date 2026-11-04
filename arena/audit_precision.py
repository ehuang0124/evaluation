#!/usr/bin/env python3
"""Manual precision/recall audit helper for the political screen.

`analyze_political.py` writes a random `audit_sample.csv` (flagged, broad-only,
and unflagged rows).  This helper prints a fixed, stratified selection for a
human to label, and then scores a labels file.

  1. python arena/audit_precision.py print  > /tmp/audit_sheet.txt
  2. A human writes arena/results/precision_labels.csv with columns
     id,label     where label is 1 = genuinely political, 0 = not political
  3. python arena/audit_precision.py score

The scores are Wilson 95% intervals, reported separately for `strict`,
`probable` (flagged group) and `unflagged` (false-negative check).
"""
from __future__ import annotations

import csv
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
SAMPLE = RESULTS / "audit_sample.csv"
LABELS = RESULTS / "precision_labels.csv"


def load_sample():
    with SAMPLE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def stratified(rows, n_per_group=40):
    rng = random.Random(2026)
    groups = defaultdict(list)
    for r in rows:
        groups[r["audit_group"]].append(r)
    out = []
    for g in ("flagged", "broad_only", "unflagged"):
        pool = sorted(groups.get(g, []), key=lambda r: r["id"])
        rng.shuffle(pool)
        out.extend(pool[:n_per_group])
    return out


def print_sheet():
    for i, r in enumerate(stratified(load_sample()), 1):
        print(f"#{i:03d} id={r['id']} group={r['audit_group']} tier={r.get('tier','')} "
              f"basis={r.get('basis','')} lang={r.get('language','')} code={r.get('is_code','')}")
        print(f"     PROMPT : {r['prompt_excerpt'][:300]}")
        print(f"     ANSWER : {r['response_a_excerpt'][:300]}")
    print("\nWrite judgments to arena/results/precision_labels.csv as: id,label")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def score():
    if not LABELS.exists():
        sys.exit(f"missing {LABELS}")
    with LABELS.open(encoding="utf-8", newline="") as f:
        labels = {r["id"]: int(r["label"]) for r in csv.DictReader(f)}
    rows = {r["id"]: r for r in stratified(load_sample())}
    buckets = defaultdict(lambda: [0, 0])
    for rid, label in labels.items():
        if rid not in rows:
            continue
        r = rows[rid]
        key = f"{r['audit_group']}/{r.get('tier','')}"
        buckets[key][0] += label
        buckets[key][1] += 1
    print(f"{'group/tier':<28} {'political':>10} {'n':>6} {'rate':>8}   wilson95")
    for key in sorted(buckets):
        k, n = buckets[key]
        lo, hi = wilson(k, n)
        print(f"{key:<28} {k:>10} {n:>6} {k/n:>8.2%}   [{lo:.2%}, {hi:.2%}]")
    tot = [sum(v[0] for v in buckets.values()), sum(v[1] for v in buckets.values())]
    print(f"labeled rows: {tot[1]}, political: {tot[0]}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "print"
    {"print": print_sheet, "score": score}[cmd]()
