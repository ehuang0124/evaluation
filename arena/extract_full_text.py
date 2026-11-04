#!/usr/bin/env python3
"""Materialize FULL, untruncated prompts for the political shortlist.

`analyze_political.py` only keeps 420-character excerpts in `shortlist.csv` and
IDs in `matched_ids.csv.gz`.  This script streams the corpus once and writes the
complete text so the explorer can display it:

  * prompts_all.jsonl.gz     - full user prompts for ALL flagged vote IDs
                               (63,635 rows; includes the high-recall broad tier)
  * conversations.jsonl.gz   - full user turns + BOTH full model answers for the
                               "core" political shortlist (strict tier, political
                               prompts, and the ranked shortlist; ~6,820 rows)
  * manifest.json            - provenance, counts, sizes, license note
  * ../../results/shortlist_full_prompts.csv - the same full prompts in a
                               local, directly viewable CSV (gitignored: verbatim
                               user prompts can contain pasted credentials)

Target IDs are derived reproducibly from the committed scan results, so no ID
list has to be checked in separately.

Usage:
    python arena/extract_full_text.py --output-dir arena/explorer/data
    python arena/extract_full_text.py --output-dir /tmp/smoke --max-rows 500
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Reuse the exact turn-parsing logic of the screening script so the text shown
# in the explorer is byte-for-byte what was classified.
import analyze_political as ap

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def load_targets() -> tuple[dict, dict]:
    """Return (all_flagged_meta, core_ids) keyed by vote id."""
    meta = {}
    with gzip.open(RESULTS / "matched_ids.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            meta[r["id"]] = r
    core = {r["id"] for r in meta.values() if r["tier"] == "strict"}
    core |= {r["id"] for r in meta.values() if r["prompt_tier"] in ("strict", "probable")}
    with (RESULTS / "shortlist.csv").open(encoding="utf-8", newline="") as f:
        core |= {r["id"] for r in csv.DictReader(f)}
    return meta, core


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default=str(HERE / "explorer" / "data"))
    p.add_argument("--max-rows", type=int, default=0, help="0 = stream the whole split")
    p.add_argument("--csv-output", default=str(RESULTS / "shortlist_full_prompts.csv"),
                   help="path for the directly viewable full-prompt CSV")
    args = p.parse_args()

    meta, core = load_targets()
    print(f"[extract] target IDs: {len(meta):,} prompts, {len(core):,} full conversations", flush=True)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    from datasets import load_dataset

    ds = load_dataset(ap.DATASET, split=ap.SPLIT, streaming=True)
    print(f"[extract] load_dataset OK ({time.time() - t0:.1f}s)", flush=True)

    n = found_all = found_core = 0
    f_all = gzip.open(out / "prompts_all.jsonl.gz", "wt", encoding="utf-8")
    f_core = gzip.open(out / "conversations.jsonl.gz", "wt", encoding="utf-8")
    csv_path = Path(args.csv_output)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    f_csv = csv_path.open("w", encoding="utf-8", newline="")
    csv_cols = ["id", "row_idx", "tier", "basis", "prompt_tier", "response_tier",
                "score", "categories", "language", "is_code", "winner", "model_a",
                "model_b", "timestamp", "n_user_turns", "prompt_chars",
                "prompt_full_untruncated", "all_user_turns_full"]
    w_csv = csv.DictWriter(f_csv, fieldnames=csv_cols, quoting=csv.QUOTE_ALL)
    w_csv.writeheader()
    try:
        for row_idx, row in enumerate(ds):
            rid = row.get("id")
            m = meta.get(rid)
            if m is None:
                n += 1
                if n % 25000 == 0:
                    print(f"[extract] {n:,} rows | {time.time()-t0:.0f}s | "
                          f"found {found_all:,}/{found_core:,}", flush=True)
                if args.max_rows and n >= args.max_rows:
                    break
                continue

            conv_a = row.get("conversation_a") or []
            conv_b = row.get("conversation_b") or []
            user_turns = ap.turns(conv_a, "user")
            a_turns = ap.turns(conv_a, "assistant")
            b_turns = ap.turns(conv_b, "assistant")
            last_prompt = user_turns[-1] if user_turns else ""
            resp_a = a_turns[-1] if a_turns else ""
            resp_b = b_turns[-1] if b_turns else ""

            base = {
                "id": rid,
                "row_idx": row_idx,
                "evaluation_session_id": row.get("evaluation_session_id"),
                "evaluation_order": row.get("evaluation_order"),
                "tier": m["tier"],
                "basis": m["basis"],
                "prompt_tier": m["prompt_tier"],
                "response_tier": m["response_tier"],
                "score": int(m["score"]),
                "categories": [c for c in m["categories"].split("|") if c],
                "language": str(row.get("language") or "unknown"),
                "is_code": bool(row.get("is_code")),
                "winner": str(row.get("winner") or "unknown"),
                "model_a": row.get("model_a"),
                "model_b": row.get("model_b"),
                "timestamp": str(row.get("timestamp")),
                "n_user_turns": len(user_turns),
                "prompt": last_prompt,                 # FULL, untruncated
                "user_turns": user_turns,              # FULL, all turns
                "prompt_chars": len(last_prompt),
            }
            f_all.write(json.dumps(base, ensure_ascii=False) + "\n")
            found_all += 1

            if rid in core:
                full = dict(base)
                full.update({
                    "assistant_a": resp_a,            # FULL, untruncated
                    "assistant_b": resp_b,            # FULL, untruncated
                    "assistant_a_chars": len(resp_a),
                    "assistant_b_chars": len(resp_b),
                    "n_turns_a": len(conv_a),
                    "n_turns_b": len(conv_b),
                })
                f_core.write(json.dumps(full, ensure_ascii=False) + "\n")
                w_csv.writerow({
                    "id": rid, "row_idx": row_idx, "tier": m["tier"], "basis": m["basis"],
                    "prompt_tier": m["prompt_tier"], "response_tier": m["response_tier"],
                    "score": int(m["score"]), "categories": "|".join(base["categories"]),
                    "language": base["language"], "is_code": base["is_code"],
                    "winner": base["winner"], "model_a": base["model_a"],
                    "model_b": base["model_b"], "timestamp": base["timestamp"],
                    "n_user_turns": len(user_turns), "prompt_chars": len(last_prompt),
                    "prompt_full_untruncated": last_prompt,
                    "all_user_turns_full": "\n\n--- NEXT USER TURN ---\n\n".join(user_turns),
                })
                found_core += 1

            n += 1
            if n % 25000 == 0:
                print(f"[extract] {n:,} rows | {time.time()-t0:.0f}s | "
                      f"found {found_all:,}/{found_core:,}", flush=True)
            if args.max_rows and n >= args.max_rows:
                break
    finally:
        f_all.close()
        f_core.close()
        f_csv.close()

    elapsed = time.time() - t0
    sizes = {p.name: p.stat().st_size for p in sorted(out.glob("*.gz"))}
    manifest = {
        "dataset": ap.DATASET,
        "dataset_revision": "6322995ab34d7c2693e3f47dd13fa5caa0789a74 (main, 2025-08-01)",
        "split": ap.SPLIT,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script_version": "1.0.0",
        "rows_streamed": n,
        "target_prompt_ids": len(meta),
        "target_core_ids": len(core),
        "written_prompts": found_all,
        "written_conversations": found_core,
        "elapsed_seconds": round(elapsed, 2),
        "gz_sizes_bytes": sizes,
        "csv_path": str(csv_path.relative_to(HERE.parent)),
        "csv_rows": found_core,
        "fields_full_text": ["prompt", "user_turns", "assistant_a", "assistant_b"],
        "license_note": ("User prompts are CC-BY-4.0; model outputs are governed by the "
                         "terms of use of the respective model providers. Full text is "
                         "included for research review of this shortlist only."),
        "text_fidelity": ("Verbatim dataset text (content[].text joined per turn). No "
                          "truncation, paraphrase, redaction or re-generation."),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[extract] done: {n:,} rows in {elapsed:.0f}s | prompts={found_all:,} "
          f"conversations={found_core:,} | sizes={sizes}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)  # avoid huggingface_hub background-thread abort at interpreter exit


if __name__ == "__main__":
    main()
