#!/usr/bin/env python3
"""Triage: how much of the arena-human-preference-140k corpus is about public-interest topics?

This script deliberately does NOT estimate anything causal or produce a leaderboard.
It answers the questions you must answer before designing a study:

  1. What is actually in the release (schema, winner classes, languages, date range)?
  2. How many votes plausibly touch each public-interest domain, under a transparent
     keyword lexicon?
  3. Do tie / both_bad rates look different on those domains vs. the corpus baseline?
     (A first descriptive cut, with no controls and no confidence intervals.)

Everything here is intentionally conservative and inspectable: the topic labels are
regex hits on the FIRST user turn, so they favor recall over precision and will
over-count. Precision must be established by hand-labeling a sample before any of
these counts go into a paper.

Usage
-----
    pip install datasets pandas
    python scripts/topic_prevalence.py                      # full corpus (1.6 GB download)
    python scripts/topic_prevalence.py --limit 20000        # quick look
    python scripts/topic_prevalence.py --local data/*.parquet
    python scripts/topic_prevalence.py --outdir outputs

Outputs (CSV + markdown tables on stdout):
    corpus_summary.csv, topic_prevalence.csv, topic_outcomes.csv, model_wins_by_topic.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DATASET = "lmarena-ai/arena-human-preference-140k"

COLUMNS = [
    "id",
    "model_a",
    "model_b",
    "winner",
    "evaluation_session_id",
    "evaluation_order",
    "conversation_a",
    "language",
    "timestamp",
    "is_code",
]

# Starter lexicon. Each pattern is matched case-insensitively against the first
# user turn. Regexes are intentionally broad (recall > precision) because this is
# a triage pass; record your edits here so the taxonomy stays versioned.
TOPIC_PATTERNS: dict[str, str] = {
    "elections_politics": (
        r"\b(?:election|elections|electoral|vote|votes|voting|ballot|ballots|candidate|"
        r"candidates|president|presidential|parliament|parliamentary|congress|congressional|"
        r"senate|senator|democrat|democratic party|republican|prime minister|chancellor|"
        r"coalition|referendum|gerrymander|impeach\w*)\b"
    ),
    "policy_governance": (
        r"\b(?:policy|policies|legislation|legislative|bill|lawmakers?|regulation|regulatory|"
        r"government|governance|public sector|tax|taxes|taxation|subsid\w+|welfare|"
        r"social security|bureaucrac\w+|constitution\w*)\b"
    ),
    "health_public_health": (
        r"\b(?:vaccin\w+|pandemic|epidemic|public health|medicare|medicaid|nhs|healthcare|"
        r"health care|insulin|opioid\w*|abortion|mental health|drug approval|fda|who)\b"
    ),
    "climate_environment": (
        r"\b(?:climate change|global warming|emissions?|carbon|greenhouse|renewable\w*|"
        r"solar|wind power|fossil fuel\w*|net zero|biodiversity|deforestation|"
        r"pollution|epa|paris agreement)\b"
    ),
    "immigration": (
        r"\b(?:immigra\w+|migrant\w*|asylum|refugee\w*|border control|deport\w+|"
        r"visa|green card|citizenship|undocumented)\b"
    ),
    "economy_labor": (
        r"\b(?:inflation|recession|unemployment|minimum wage|monetary policy|interest rates?|"
        r"central bank|federal reserve|tariffs?|trade war|gig economy|union\w*|"
        r"housing crisis|rent control|inequality|cost of living)\b"
    ),
    "education": (
        r"\b(?:public school\w*|curriculum|student loans?|tuition|school district|"
        r"education policy|standardized test\w*|teachers? union|charter school\w*)\b"
    ),
    "foreign_affairs_security": (
        r"\b(?:war|warfare|invasion|ceasefire|sanctions?|nato|united nations|terroris\w+|"
        r"genocide|military aid|arms deal|nuclear weapon\w*|geopolitic\w*)\b"
    ),
    "civil_rights_law": (
        r"\b(?:free speech|first amendment|second amendment|gun control|discrimination|"
        r"affirmative action|lgbtq?\w*|same-sex|supreme court|judicial|voting rights|"
        r"police reform|death penalty|civil liberties)\b"
    ),
    "tech_regulation": (
        r"\b(?:ai regulation|data privacy|gdpr|antitrust|section 230|content moderation|"
        r"surveillance|encryption|net neutrality|deepfake\w*|copyright|open source)\b"
    ),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", default=DATASET, help=f"HF dataset id (default: {DATASET})")
    p.add_argument("--local", nargs="*", default=None, help="local parquet file(s); skips the HF download")
    p.add_argument("--limit", type=int, default=None, help="only read the first N rows (for a quick look)")
    p.add_argument("--first-order-only", action="store_true", help="restrict to evaluation_order == 1")
    p.add_argument("--min-battles", type=int, default=30, help="min decided battles before a model is reported per topic")
    p.add_argument("--outdir", default="outputs", help="where to write CSVs")
    return p


def first_user_text(conversation) -> str:
    """Pull the text of the first user turn out of a conversation column.

    Accepts lists, tuples, numpy arrays, and anything else iterable of turns --
    `to_pandas()` gives back different container types depending on the datasets
    version, so duck-type instead of checking for `list`.
    """
    if conversation is None or isinstance(conversation, (str, bytes, dict)):
        return ""
    for turn in conversation:
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        blocks, chunks = turn.get("content"), []
        if isinstance(blocks, str):
            return blocks.strip()
        for block in blocks or []:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    chunks.append(text)
            elif isinstance(block, str):
                chunks.append(block)
        if chunks:
            return "\n".join(chunks).strip()
    return ""


def load_frame(args) -> pd.DataFrame:
    if args.local:
        import glob

        paths = [p for pattern in args.local for p in (glob.glob(pattern) or [pattern])]
        df = pd.read_parquet(paths)
        keep = [c for c in COLUMNS if c in df.columns]
        return df[keep]
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("pip install datasets pandas")
    try:
        ds = load_dataset(args.dataset, split="train", columns=COLUMNS)
    except TypeError:  # older datasets: no `columns=` kwarg
        ds = load_dataset(args.dataset, split="train")
        ds = ds.remove_columns([c for c in ds.column_names if c not in COLUMNS])
    if args.limit:
        ds = ds.select(range(min(args.limit, len(ds))))
    return ds.to_pandas()


def main() -> None:
    args = build_parser().parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = load_frame(args)
    n_rows_raw = len(df)

    # ---- corpus summary ----------------------------------------------------
    summary = {
        "rows_loaded": n_rows_raw,
        "unique_votes": df["id"].nunique() if "id" in df else None,
        "unique_sessions": df["evaluation_session_id"].nunique() if "evaluation_session_id" in df else None,
        "unique_models": pd.concat([df["model_a"], df["model_b"]]).nunique(),
        "unique_languages": df["language"].nunique() if "language" in df else None,
        "share_english": round((df["language"] == "en").mean(), 4) if "language" in df else None,
        "share_is_code": round(df["is_code"].mean(), 4) if "is_code" in df else None,
        "share_first_order": round((df["evaluation_order"] == 1).mean(), 4) if "evaluation_order" in df else None,
        "timestamp_min": str(df["timestamp"].min()) if "timestamp" in df else None,
        "timestamp_max": str(df["timestamp"].max()) if "timestamp" in df else None,
        "share_tie": round((df["winner"] == "tie").mean(), 4),
        "share_both_bad": round((df["winner"] == "both_bad").mean(), 4),
        "share_model_a_wins_of_decided": round((df["winner"] == "model_a").sum() / max(
            (df["winner"].isin(["model_a", "model_b"])).sum(), 1), 4),
    }
    pd.Series(summary).to_csv(outdir / "corpus_summary.csv", header=["value"])
    print("== corpus summary ==")
    for k, v in summary.items():
        print(f"  {k:34s} {v}")

    # ---- topic labeling ----------------------------------------------------
    work = df
    if args.first_order_only and "evaluation_order" in df:
        work = df[df["evaluation_order"] == 1].copy()
        print(f"\nRestricted to evaluation_order == 1: {len(work):,} rows")

    work = work.copy()
    work["prompt"] = work["conversation_a"].map(first_user_text)
    for topic, pattern in TOPIC_PATTERNS.items():
        work[f"topic::{topic}"] = work["prompt"].str.contains(
            f"(?:{pattern})", case=False, regex=True, na=False
        )

    topic_cols = [c for c in work.columns if c.startswith("topic::")]
    work["n_topics_hit"] = work[topic_cols].sum(axis=1)

    prevalence = pd.DataFrame(
        {
            "topic": [c.removeprefix("topic::") for c in topic_cols],
            "votes": [int(work[c].sum()) for c in topic_cols],
        }
    )
    prevalence["share_of_rows"] = (prevalence["votes"] / len(work)).round(4)
    prevalence = prevalence.sort_values("votes", ascending=False)
    prevalence.to_csv(outdir / "topic_prevalence.csv", index=False)
    print("\n== keyword prevalence (multi-label, recall-oriented) ==")
    print(prevalence.to_string(index=False))
    print(f"  rows with >=1 topic hit : {int((work['n_topics_hit'] > 0).sum()):,} "
          f"({(work['n_topics_hit'] > 0).mean():.2%})")
    print(f"  rows with >=2 topic hits: {int((work['n_topics_hit'] > 1).sum()):,}")

    # ---- outcomes per topic ------------------------------------------------
    decided = work["winner"].isin(["model_a", "model_b"])
    rows = []
    for col in topic_cols:
        sub = work[work[col]]
        if sub.empty:
            continue
        rows.append(
            {
                "topic": col.removeprefix("topic::"),
                "votes": len(sub),
                "tie_rate": round((sub["winner"] == "tie").mean(), 4),
                "both_bad_rate": round((sub["winner"] == "both_bad").mean(), 4),
                "decided_rate": round(sub["winner"].isin(["model_a", "model_b"]).mean(), 4),
                "model_a_win_rate_of_decided": round(
                    (sub["winner"] == "model_a").sum() / max(sub["winner"].isin(["model_a", "model_b"]).sum(), 1), 4
                ),
            }
        )
    baselines = {
        "topic": "(baseline: all rows)",
        "votes": len(work),
        "tie_rate": round((work["winner"] == "tie").mean(), 4),
        "both_bad_rate": round((work["winner"] == "both_bad").mean(), 4),
        "decided_rate": round(decided.mean(), 4),
        "model_a_win_rate_of_decided": round(
            (work["winner"] == "model_a").sum() / max(decided.sum(), 1), 4
        ),
    }
    outcomes = pd.DataFrame(rows + [baselines])
    outcomes.to_csv(outdir / "topic_outcomes.csv", index=False)
    print("\n== outcomes by topic (no controls, no CIs -- descriptive only) ==")
    print(outcomes.to_string(index=False))

    # ---- naive per-model win rate, per topic -------------------------------
    win_rows = []
    for col in topic_cols:
        sub = work[work[col] & decided]
        if sub.empty:
            continue
        long = pd.concat(
            [
                pd.DataFrame({"model": sub["model_a"], "won": (sub["winner"] == "model_a").astype(int)}),
                pd.DataFrame({"model": sub["model_b"], "won": (sub["winner"] == "model_b").astype(int)}),
            ]
        )
        agg = long.groupby("model")["won"].agg(["sum", "count"])
        agg = agg[agg["count"] >= args.min_battles]
        agg["win_rate"] = (agg["sum"] / agg["count"]).round(4)
        agg["topic"] = col.removeprefix("topic::")
        win_rows.append(agg.reset_index()[["topic", "model", "count", "win_rate"]])
    if win_rows:
        win_df = pd.concat(win_rows).sort_values(["topic", "win_rate"], ascending=[True, False])
        win_df.to_csv(outdir / "model_wins_by_topic.csv", index=False)
        print(f"\n== naive per-model win rates written to {outdir / 'model_wins_by_topic.csv'}"
              f" ({len(win_df)} topic-model cells with >= {args.min_battles} decided battles) ==")
        print("   WARNING: unadjusted for model strength, style, position, or model mix.")

    print(f"\nWrote CSVs to {outdir.resolve()}")
    print("Next: hand-label ~150 prompts per candidate topic and measure precision before using these counts.")


if __name__ == "__main__":
    main()
