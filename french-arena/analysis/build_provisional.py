#!/usr/bin/env python3
"""Build an ID-only political-review shortlist from a pinned public derivative.

This does NOT read or claim to classify the full gated Hugging Face release.
The derivative contains one French, decisively voted conversation per row and
its first source-assigned topic. No prompt/response text is available here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

REFERENCE_REVISION = "25a17f883945c2229736bfe17702d966bc94aa0d"
SOURCE_REVISION = "8cd6488c5d0c3b8dfcb9339d11ae9624c84359be"
EXPECTED_SHA256 = {
    "fr_battles.parquet": "83071d14e4335c7e047677f2767205454ff3981be1999f9cf62c67f388bb6cd1",
    "timestamps.parquet": "836e902b3005f0295d8ba9b1b5991f60d6eb9cc76665138391961a813b440a0c",
}
ADJACENT_TOPICS = [
    "Law & Justice",
    "Society & Social Issues & Human Rights",
    "Environment",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build(reference: Path, output: Path) -> dict:
    paths = {name: reference / "data" / name for name in EXPECTED_SHA256}
    for name, path in paths.items():
        actual = sha256(path)
        if actual != EXPECTED_SHA256[name]:
            raise ValueError(f"Unexpected input hash for {name}: {actual}")

    battles = pd.read_parquet(paths["fr_battles.parquet"])
    timestamps = pd.read_parquet(paths["timestamps.parquet"])
    if not battles["conversation_pair_id"].is_unique:
        raise ValueError("Expected one row per conversation")
    if not timestamps["conversation_pair_id"].is_unique:
        raise ValueError("Timestamp table must have unique conversation IDs")
    df = battles.merge(
        timestamps, on="conversation_pair_id", how="left", validate="one_to_one"
    )
    if df["timestamp"].isna().any():
        raise ValueError("Some conversations have no timestamp")

    base = df[[
        "conversation_pair_id", "timestamp", "primary_topic", "mode",
        "model_a_name", "model_b_name", "winner", "vote_turn", "conv_turns",
        "final_turn", "post_vote_turns",
    ]].rename(columns={
        "conversation_pair_id": "comparison_id",
        "primary_topic": "source_primary_topic",
        "model_a_name": "model_a",
        "model_b_name": "model_b",
        "conv_turns": "user_turns_through_vote",
    })
    base["assistant_responses_through_vote"] = 2 * base["user_turns_through_vote"]
    base["responses_at_decisive_vote"] = 2
    base["source_dataset"] = "ministere-culture/comparia-fr-arena"
    base["source_revision"] = SOURCE_REVISION
    base["derived_repository_revision"] = REFERENCE_REVISION
    base["review_status"] = "needs_text_review"

    politics = base[base["source_primary_topic"].eq("Politics & Government")].copy()
    politics["shortlist_reason"] = "source_topic: Politics & Government"
    politics["candidate_topics"] = [["politics_government_unspecified"]] * len(politics)
    politics["review_priority"] = "1_source_politics_topic"
    politics = politics.sort_values(["timestamp", "comparison_id"]).reset_index(drop=True)

    adjacent = base[base["source_primary_topic"].isin(ADJACENT_TOPICS)].copy()
    adjacent["shortlist_reason"] = "adjacent topic; political relevance unknown"
    adjacent["candidate_topics"] = [[] for _ in range(len(adjacent))]
    adjacent["review_priority"] = "2_adjacent_topic_not_labeled_political"
    adjacent = adjacent.sort_values(["timestamp", "comparison_id"]).reset_index(drop=True)

    output.mkdir(parents=True, exist_ok=True)
    politics.to_parquet(output / "political_shortlist_provisional.parquet", index=False)
    # CSV is an ID/metadata review queue, not a raw conversation export.
    csv = politics.copy()
    csv["candidate_topics"] = csv["candidate_topics"].map(json.dumps)
    csv.to_csv(output / "political_shortlist_provisional.csv", index=False)
    adjacent.to_parquet(output / "adjacent_topic_review_provisional.parquet", index=False)

    topic_counts = (
        df["primary_topic"].fillna("(missing)").value_counts().rename_axis("topic")
        .reset_index(name="conversations")
    )
    topic_counts["percent_of_derived_sample"] = 100 * topic_counts["conversations"] / len(df)
    topic_counts.to_csv(output / "topic_counts_provisional.csv", index=False)

    monthly = df.assign(month=df["timestamp"].dt.strftime("%Y-%m"))
    monthly = monthly.groupby("month").agg(
        conversations=("conversation_pair_id", "size"),
        politics_topic_conversations=("primary_topic", lambda s: int(s.eq("Politics & Government").sum())),
    ).reset_index()
    monthly["politics_topic_percent"] = (
        100 * monthly["politics_topic_conversations"] / monthly["conversations"]
    )
    monthly.to_csv(output / "monthly_topic_counts_provisional.csv", index=False)

    summary = {
        "analysis_date": "2026-11-03",
        "status": "provisional_topic_label_only",
        "full_source_read_succeeded": False,
        "full_source_blocker": "Hugging Face connections fail in this sandbox; gated file access also requires accepted conditions.",
        "source_dataset": "ministere-culture/comparia-fr-arena",
        "source_revision": SOURCE_REVISION,
        "derived_repository": "https://github.com/simonaszilinskas/style-control-analysis",
        "derived_repository_revision": REFERENCE_REVISION,
        "source_publication_date_reported_by_derivative": "2026-07-08",
        "input_sha256": EXPECTED_SHA256,
        "derived_conversations": int(len(df)),
        "political_candidate_conversations": int(len(politics)),
        "political_candidate_percent": float(100 * len(politics) / len(df)),
        "user_prompt_turns_through_vote": int(politics["user_turns_through_vote"].sum()),
        "assistant_response_turns_through_vote": int(politics["assistant_responses_through_vote"].sum()),
        "responses_at_decisive_vote": int(2 * len(politics)),
        "single_turn_conversations_through_vote": int(politics["user_turns_through_vote"].eq(1).sum()),
        "multi_turn_conversations_through_vote": int(politics["user_turns_through_vote"].gt(1).sum()),
        "first_conversation_timestamp": df["timestamp"].min().isoformat(),
        "last_conversation_timestamp": df["timestamp"].max().isoformat(),
        "adjacent_topic_review_conversations": int(len(adjacent)),
        "adjacent_topics": ADJACENT_TOPICS,
        "mode_counts": {str(k): int(v) for k, v in politics["mode"].value_counts().items()},
        "contains_prompt_or_response_text": False,
        "human_validated_political_labels": False,
        "caveats": [
            "Only the last decisive French vote per conversation is represented; unrated and non-decisive conversations are excluded.",
            "Only the first source-assigned topic is available. Political conversations assigned another primary topic can be missed.",
            "Source topic labels are not human validation of political relevance.",
            "Prompt/response counts are turn instances through the retained vote, not unique prompt strings or all responses in the full source.",
            "Adjacent-topic records are a separate review queue, not political positives.",
            "Do not extrapolate this sample percentage to the current full release or the French population.",
        ],
    }
    (output / "summary_provisional.json").write_text(json.dumps(summary, indent=2) + "\n")
    license_src = reference / "LICENSE"
    if license_src.exists():
        (output / "LICENSE_ETALAB_2.0.txt").write_text(license_src.read_text())
    files = {}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest_provisional.json":
            files[path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    manifest = {"format_version": 1, "files": files, "pandas_version": pd.__version__}
    (output / "manifest_provisional.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("french-arena/data"))
    args = parser.parse_args()
    print(json.dumps(build(args.reference_dir, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
