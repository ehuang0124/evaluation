#!/usr/bin/env python3
"""Build the topic label file, and export a sample for hand-checking precision.

Two outputs:
  * `<outdir>/labelled.parquet` -- the analysis frame (prompt, topic, per-domain flags,
    outcome, style covariates) consumed by fit_topic_bt.py --labelled;
  * `<outdir>/handcheck_sample.csv` -- a stratified sample with blank columns for a human
    to fill in. Lexicon precision must come from this file before any topic result is
    reported; a regex on chat prompts is a prefilter, not a measurement instrument.

This script intentionally contains no LLM calls. Adjudication (LLM or human) belongs in
its own versioned step with its own prompt, so that label provenance is auditable.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

from arena_features import GENERAL_TOPIC, HF_COLUMNS, LEXICON_VERSION, prepare

DATASET = "lmarena-ai/arena-human-preference-140k"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--local", nargs="*", default=None, help="local parquet file(s)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--first-order-only", action="store_true")
    p.add_argument("--sample-per-topic", type=int, default=150)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--outdir", default="outputs")
    return p


def load_frame(args) -> pd.DataFrame:
    if args.local:
        paths = [p for pattern in args.local for p in (glob.glob(pattern) or [pattern])]
        df = pd.read_parquet(paths)
        return df[[c for c in HF_COLUMNS if c in df.columns]]
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("pip install datasets pandas pyarrow")
    try:
        ds = load_dataset(args.dataset, split="train", columns=HF_COLUMNS)
    except TypeError:
        ds = load_dataset(args.dataset, split="train")
        ds = ds.remove_columns([c for c in ds.column_names if c not in HF_COLUMNS])
    if args.limit:
        ds = ds.select(range(min(args.limit, len(ds))))
    return ds.to_pandas()


def main() -> None:
    args = build_parser().parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    frame = load_frame(args)
    if args.first_order_only and "evaluation_order" in frame:
        frame = frame[frame["evaluation_order"] == 1].copy()
    frame = prepare(frame)

    keep = [
        "id", "prompt", "topic", "winner", "decided", "y", "model_a", "model_b",
        "evaluation_session_id", "evaluation_order", "language", "is_code", "timestamp",
    ] + [c for c in frame.columns if c.startswith("flag::")] + [
        c for c in frame.columns if c.startswith("style::")
    ]
    frame[[c for c in keep if c in frame.columns]].to_parquet(outdir / "labelled.parquet", index=False)

    sample_rows = []
    for topic, sub in frame.groupby("topic"):
        n = min(args.sample_per_topic, len(sub))
        sample = sub.sample(n=n, random_state=args.seed)
        sample_rows.append(sample[["id", "prompt", "topic", "language"]].assign(
            correct_topic="", better_topic="", notes=""
        ))
    sample = pd.concat(sample_rows).sort_values(["topic", "id"])
    sample.to_csv(outdir / "handcheck_sample.csv", index=False)

    print(f"== labelled {len(frame):,} rows with lexicon {LEXICON_VERSION} ==")
    print(frame["topic"].value_counts().to_string())
    print(f"\nwrote {outdir / 'labelled.parquet'}")
    print(f"wrote {outdir / 'handcheck_sample.csv'} ({len(sample)} rows) -- "
          f"fill in correct_topic (y/n) and better_topic, then report precision per domain")
    print(f"general (no lexicon hit): {int((frame['topic'] == GENERAL_TOPIC).sum()):,} rows")


if __name__ == "__main__":
    main()
