#!/usr/bin/env python3
"""Triage: how much of arena-human-preference-140k is about public-interest topics?

This deliberately does NOT estimate anything causal and does NOT produce a leaderboard.
It answers the questions you must answer before designing a study:

  1. What is in the release (schema, winner classes, languages, date range)?
  2. How many votes plausibly touch each public-interest domain under a transparent lexicon?
  3. Do tie / both_bad / position rates differ from the corpus baseline on those domains?

Topic labels are regex hits on the FIRST user turn: high recall, unknown precision.
Measure precision by hand-labeling ~150 prompts per domain before citing these counts.

Usage
-----
    pip install datasets pandas pyarrow
    python scripts/topic_prevalence.py                  # full 1.6 GB release
    python scripts/topic_prevalence.py --limit 20000    # quick look
    python scripts/topic_prevalence.py --local data/*.parquet
    python scripts/topic_prevalence.py --first-order-only

For the style- and position-controlled version of the topic comparison, use
scripts/fit_topic_bt.py.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

from arena_features import (
    GENERAL_TOPIC,
    HF_COLUMNS,
    LEXICON_VERSION,
    TOPIC_PATTERNS,
    prepare,
)

DATASET = "lmarena-ai/arena-human-preference-140k"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--dataset", default=DATASET, help=f"HF dataset id (default: {DATASET})")
    p.add_argument("--local", nargs="*", default=None, help="local parquet file(s); skips the download")
    p.add_argument("--limit", type=int, default=None, help="only read the first N rows")
    p.add_argument("--first-order-only", action="store_true", help="restrict to evaluation_order == 1")
    p.add_argument("--min-battles", type=int, default=30, help="min decided battles to report a model")
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
    except TypeError:  # older datasets releases lack `columns=`
        ds = load_dataset(args.dataset, split="train")
        ds = ds.remove_columns([c for c in ds.column_names if c not in HF_COLUMNS])
    if args.limit:
        ds = ds.select(range(min(args.limit, len(ds))))
    return ds.to_pandas()


def main() -> None:
    args = build_parser().parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = load_frame(args)
    if args.first_order_only and "evaluation_order" in df:
        df = df[df["evaluation_order"] == 1].copy()

    work = prepare(df)

    summary = {
        "lexicon_version": LEXICON_VERSION,
        "rows": len(work),
        "unique_votes": work["id"].nunique() if "id" in work else None,
        "unique_sessions": work["evaluation_session_id"].nunique() if "evaluation_session_id" in work else None,
        "unique_models": pd.concat([work["model_a"], work["model_b"]]).nunique(),
        "unique_languages": work["language"].nunique() if "language" in work else None,
        "share_english": round(float((work["language"] == "en").mean()), 4) if "language" in work else None,
        "share_is_code": round(float(work["is_code"].mean()), 4) if "is_code" in work else None,
        "share_first_order": round(float((work["evaluation_order"] == 1).mean()), 4)
        if "evaluation_order" in work else None,
        "timestamp_min": str(work["timestamp"].min()) if "timestamp" in work else None,
        "timestamp_max": str(work["timestamp"].max()) if "timestamp" in work else None,
        "share_tie": round(float((work["winner"] == "tie").mean()), 4),
        "share_both_bad": round(float((work["winner"] == "both_bad").mean()), 4),
        "share_decided": round(float(work["decided"].mean()), 4),
        "share_model_a_wins_of_decided": round(float(work.loc[work["decided"], "y"].mean()), 4),
    }
    pd.Series(summary).to_csv(outdir / "corpus_summary.csv", header=["value"])
    print("== corpus summary ==")
    for key, value in summary.items():
        print(f"  {key:34s} {value}")

    prevalence = (
        work["topic"].value_counts().rename_axis("topic").reset_index(name="votes")
    )
    prevalence["share_of_rows"] = (prevalence["votes"] / len(work)).round(4)
    prevalence.to_csv(outdir / "topic_prevalence.csv", index=False)
    print(f"\n== topic labels, single-label priority assignment (lexicon {LEXICON_VERSION}) ==")
    print(prevalence.to_string(index=False))

    flag_cols = [c for c in work.columns if c.startswith("flag::")]
    multi = work[flag_cols].sum(axis=1)
    print(f"  rows matching >=2 domains (multi-label view): {int((multi > 1).sum()):,}")

    # ---- outcomes per topic ------------------------------------------------
    rows = []
    for topic, sub in work.groupby("topic"):
        decided = sub["decided"]
        rows.append(
            {
                "topic": topic,
                "votes": len(sub),
                "tie_rate": round(float((sub["winner"] == "tie").mean()), 4),
                "both_bad_rate": round(float((sub["winner"] == "both_bad").mean()), 4),
                "decided_rate": round(float(decided.mean()), 4),
                "model_a_win_rate_of_decided": round(float(sub.loc[decided, "y"].mean()), 4)
                if decided.any() else None,
            }
        )
    outcomes = pd.DataFrame(rows).sort_values("votes", ascending=False)
    outcomes.to_csv(outdir / "topic_outcomes.csv", index=False)
    print("\n== outcomes by topic (descriptive, no controls, no CIs) ==")
    print(outcomes.to_string(index=False))
    print(f"  interpretation note: general = no lexicon hit "
          f"({int((work['topic'] == GENERAL_TOPIC).sum()):,} rows)")

    # ---- naive per-model win rates ----------------------------------------
    win_rows = []
    for topic, sub in work[work["decided"]].groupby("topic"):
        long = pd.concat(
            [
                pd.DataFrame({"model": sub["model_a"], "won": (sub["winner"] == "model_a").astype(int)}),
                pd.DataFrame({"model": sub["model_b"], "won": (sub["winner"] == "model_b").astype(int)}),
            ]
        )
        agg = long.groupby("model")["won"].agg(["sum", "count"])
        agg = agg[agg["count"] >= args.min_battles]
        agg["win_rate"] = (agg["sum"] / agg["count"]).round(4)
        agg["topic"] = topic
        win_rows.append(agg.reset_index()[["topic", "model", "count", "win_rate"]])
    if win_rows:
        win_df = pd.concat(win_rows).sort_values(["topic", "win_rate"], ascending=[True, False])
        win_df.to_csv(outdir / "model_wins_by_topic.csv", index=False)
        print(f"\n== naive per-model win rates -> {outdir / 'model_wins_by_topic.csv'}"
              f" ({len(win_df)} topic-model cells with >= {args.min_battles} decided battles) ==")
        print("   WARNING: unadjusted for model strength, style, position, or model mix.")
        print("   Use scripts/fit_topic_bt.py for the adjusted estimate.")

    print(f"\nWrote CSVs to {outdir.resolve()}")


if __name__ == "__main__":
    main()
