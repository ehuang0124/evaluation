#!/usr/bin/env python3
"""Screen comparia-fr-arena for political-study candidates using pandas.

Default I/O streams Parquet batches through PyArrow/fsspec into pandas DataFrames
so the ~9.5 GB source does not have to fit in RAM. --direct-pandas instead uses
pd.read_parquet(path, columns=...) for the exact pandas reader requested.

Two passes:
  1. Screen visible user/assistant turn text and source topic metadata.
  2. Export every turn belonging to a shortlisted conversation, plus one
     sanitized full-conversation row per comparison_id. The full transcript is
     taken from the highest-turn source row, not an arbitrary first row.

The main `political_conversations.parquet` includes both model transcripts in
`full_conversation_a` and `full_conversation_b`, as well as the model names.
Only user/assistant `content` is screened/exported. `reasoning_content`, system
prompts, and tool payloads are excluded. Matches are review candidates, not
validated political labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

HF_REPO = "ministere-culture/comparia-fr-arena"
HF_FILE = "comparia-fr-arena.parquet"
DEFAULT_INPUT = f"hf://datasets/{HF_REPO}/{HF_FILE}"
RULES_PATH = Path(__file__).with_name("political_rules.json")
RULES_VERSION = "1.0.0"

TURN_COLUMNS = [
    "response_id", "comparison_id", "timestamp", "turn", "model_a", "model_b",
    "response_a", "response_b", "choice", "metadata",
]
FULL_COLUMNS = TURN_COLUMNS + ["full_conversation_a", "full_conversation_b"]
ADJACENT_CATEGORIES = {
    "law justice",
    "society social issues human rights",
    "environment",
}
PROMPT_COLUMNS = [
    "comparison_id", "turn", "response_id", "timestamp", "prompt",
    "prompt_political", "metadata_political", "conversation_political",
    "prompt_topics", "conversation_topics", "prompt_evidence_json",
    "model_a", "model_b", "choice", "languages", "categories", "mode",
    "prompt_mismatch", "shortlist_reason", "review_priority",
]
RESPONSE_COLUMNS = PROMPT_COLUMNS[:4] + [
    "side", "model", "response", "response_political", "prompt_political",
    "metadata_political", "conversation_political", "response_topics",
    "conversation_topics", "response_evidence_json", "choice", "languages",
    "categories", "mode", "shortlist_reason", "review_priority",
]
CONVERSATION_COLUMNS = [
    "comparison_id", "timestamp", "last_timestamp", "n_source_turns",
    "max_turn", "model_a", "model_b", "shortlist_reason", "review_priority",
    "review_status", "candidate_topics", "matched_turns",
    "prompt_political_turns", "assistant_responses_political",
    "metadata_political", "adjacent_metadata_only", "languages", "categories",
    "mode", "model_pairs", "evidence_json", "full_conversation_a",
    "full_conversation_b", "full_conversation_a_user_messages",
    "full_conversation_a_assistant_messages", "full_conversation_b_user_messages",
    "full_conversation_b_assistant_messages", "conversation_export_status",
    "conversation_export_complete",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Accent-fold text while retaining normalized->original character offsets."""
    out: list[str] = []
    mapping: list[int] = []
    for i, ch in enumerate(text):
        if ch in "’‘ʼ":
            ch = "'"
        if ch in "œŒ":
            piece = "oe"
        elif ch in "æÆ":
            piece = "ae"
        else:
            piece = "".join(c for c in unicodedata.normalize("NFKD", ch)
                            if not unicodedata.combining(c))
        piece = piece.lower()
        piece = re.sub(r"\s+", " ", piece)
        for c in piece:
            out.append(c)
            mapping.append(i)
    return "".join(out), mapping


def normalize(text: str) -> str:
    return normalize_with_map(text)[0]


def term_pattern(terms: list[str]) -> re.Pattern:
    cleaned = sorted({normalize(t).strip() for t in terms if normalize(t).strip()},
                     key=lambda x: (-len(x), x))
    if not cleaned:
        return re.compile(r"(?!)")
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in cleaned) + r")(?!\w)")


class PoliticalRules:
    def __init__(self, path: Path = RULES_PATH):
        self.path = path
        self.raw = json.loads(path.read_text())
        self.version = self.raw.get("version", RULES_VERSION)
        self.compiled: dict[str, list[dict[str, Any]]] = {}
        for topic, spec in self.raw["topics"].items():
            rules = []
            for rule in spec["rules"]:
                rules.append({
                    "label": rule["label"],
                    "pattern": term_pattern(rule["terms"]),
                    "context": term_pattern(rule["context_terms"]) if rule.get("context_terms") else None,
                })
            self.compiled[topic] = rules

    def screen(self, text: str, max_evidence_per_topic: int = 4) -> dict[str, list[dict]]:
        if not text or not text.strip():
            return {}
        norm, mapping = normalize_with_map(text)
        evidence: dict[str, list[dict]] = {}
        for topic, rules in self.compiled.items():
            hits: list[dict] = []
            for rule in rules:
                for match in rule["pattern"].finditer(norm):
                    if rule["context"] is not None and not rule["context"].search(norm):
                        continue
                    start = mapping[match.start()] if mapping else 0
                    end = mapping[match.end() - 1] + 1 if mapping else 0
                    lo = max(0, start - 100)
                    hi = min(len(text), end + 100)
                    hits.append({
                        "rule": rule["label"],
                        "matched_term": text[start:end],
                        "snippet": ("…" if lo else "") + text[lo:hi].replace("\n", " ") + ("…" if hi < len(text) else ""),
                    })
                    if len(hits) >= max_evidence_per_topic:
                        break
                if len(hits) >= max_evidence_per_topic:
                    break
            if hits:
                evidence[topic] = hits
        return evidence


def messages(value: Any) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, (list, tuple)):
        return [m for m in value if isinstance(m, dict)]
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return [m for m in value.tolist() if isinstance(m, dict)]
    except Exception:
        pass
    return []


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
        return "\n".join(p for p in parts if p)
    return ""


def visible_text(value: Any, role: str) -> str:
    parts = []
    for msg in messages(value):
        if msg.get("role") == role:
            text = content_text(msg.get("content"))
            if text:
                parts.append(text)
    return "\n".join(parts)


def sanitize_conversation(value: Any) -> list[dict]:
    """Keep visible user/assistant text while dropping system/tool/reasoning data."""
    out = []
    for msg in messages(value):
        role = msg.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = content_text(msg.get("content"))
        if text:
            out.append({"role": role, "content": text})
    return out


def transcript_counts(conversation: list[dict]) -> tuple[int, int]:
    """Return visible user and assistant message counts in a sanitized transcript."""
    users = sum(msg.get("role") == "user" for msg in conversation)
    assistants = sum(msg.get("role") == "assistant" for msg in conversation)
    return users, assistants


def transcript_export_status(
    full_a: list[dict], full_b: list[dict], expected_turns: int
) -> tuple[str, tuple[int, int, int, int]]:
    """Check both model transcripts contain visible messages for every source turn."""
    a_users, a_assistants = transcript_counts(full_a)
    b_users, b_assistants = transcript_counts(full_b)
    counts = (a_users, a_assistants, b_users, b_assistants)
    missing = []
    if a_users < expected_turns or a_assistants < expected_turns:
        missing.append("model_a")
    if b_users < expected_turns or b_assistants < expected_turns:
        missing.append("model_b")
    if not missing:
        return "complete", counts
    return "incomplete_" + "_and_".join(missing), counts


def metadata_dict(row: dict) -> dict:
    md = row.get("metadata")
    return md if isinstance(md, dict) else {}


def category_flags(categories: list[str]) -> tuple[bool, bool, list[str]]:
    political = False
    adjacent = False
    evidence = []
    for cat in categories:
        norm = normalize(str(cat)).replace("&", " ")
        norm = re.sub(r"\s+", " ", norm).strip()
        if "politics" in norm and "government" in norm:
            political = True
            evidence.append(str(cat))
        if norm in ADJACENT_CATEGORIES:
            adjacent = True
    return political, adjacent, evidence


def clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(x) for x in list(value) if x is not None and str(x)]
    except TypeError:
        return []


def screen_turn(row: dict, rules: PoliticalRules) -> dict:
    md = metadata_dict(row)
    categories = clean_list(md.get("categories"))
    languages = clean_list(md.get("languages"))
    metadata_political, adjacent, category_evidence = category_flags(categories)

    prompt_a = visible_text(row.get("response_a"), "user")
    prompt_b = visible_text(row.get("response_b"), "user")
    prompts = list(dict.fromkeys(p for p in [prompt_a, prompt_b] if p))
    prompt = "\n".join(prompts)
    prompt_mismatch = bool(prompt_a and prompt_b and normalize(prompt_a) != normalize(prompt_b))
    response_a = visible_text(row.get("response_a"), "assistant")
    response_b = visible_text(row.get("response_b"), "assistant")

    prompt_evidence = rules.screen(prompt)
    response_a_evidence = rules.screen(response_a)
    response_b_evidence = rules.screen(response_b)
    prompt_topics = sorted(prompt_evidence)
    response_a_topics = sorted(response_a_evidence)
    response_b_topics = sorted(response_b_evidence)
    text_topics = sorted(set(prompt_topics) | set(response_a_topics) | set(response_b_topics))
    conversation_topics = sorted(set(text_topics) | ({"politics_government_metadata"} if metadata_political else set()))
    political = bool(conversation_topics)

    reasons = []
    if prompt_topics:
        reasons.append("prompt_text")
    if metadata_political:
        reasons.append("source_topic")
    if response_a_topics or response_b_topics:
        reasons.append("response_text")
    priority = "1_prompt_or_source_topic" if (prompt_topics or metadata_political) else ("2_response_only" if political else "3_not_shortlisted")

    evidence = []
    for source, ev in [("prompt", prompt_evidence), ("response_a", response_a_evidence), ("response_b", response_b_evidence)]:
        for topic, hits in ev.items():
            for hit in hits[:2]:
                evidence.append({"source": source, "topic": topic, **hit})
    if category_evidence:
        evidence.append({"source": "metadata", "topic": "politics_government_metadata",
                         "rule": "source_category", "matched_term": ", ".join(category_evidence),
                         "snippet": ", ".join(category_evidence)})

    return {
        "prompt": prompt,
        "response_a": response_a,
        "response_b": response_b,
        "prompt_mismatch": prompt_mismatch,
        "prompt_political": bool(prompt_topics),
        "response_a_political": bool(response_a_topics),
        "response_b_political": bool(response_b_topics),
        "metadata_political": metadata_political,
        "adjacent_metadata": adjacent,
        "political": political,
        "prompt_topics": prompt_topics,
        "response_a_topics": response_a_topics,
        "response_b_topics": response_b_topics,
        "conversation_topics": conversation_topics,
        "prompt_evidence": prompt_evidence,
        "response_a_evidence": response_a_evidence,
        "response_b_evidence": response_b_evidence,
        "evidence": evidence,
        "shortlist_reason": reasons,
        "review_priority": priority,
        "categories": categories,
        "languages": languages,
        "mode": md.get("mode"),
    }


def source_column_names(path: str) -> set[str]:
    """Read the Parquet schema without loading the conversation data into RAM."""
    import fsspec
    with fsspec.open(path, "rb") as f:
        return set(pq.ParquetFile(f).schema_arrow.names)


def iter_batches(path: str, columns: list[str], batch_size: int, direct_pandas: bool) -> Iterator[pd.DataFrame]:
    if direct_pandas:
        df = pd.read_parquet(path, columns=columns)
        for start in range(0, len(df), batch_size):
            yield df.iloc[start:start + batch_size].copy()
        return
    import fsspec
    with fsspec.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        missing = set(columns) - set(pf.schema_arrow.names)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        for batch in pf.iter_batches(batch_size=batch_size, columns=columns):
            yield batch.to_pandas()


class PartWriter:
    def __init__(self, root: Path, name: str, columns: list[str], flush_rows: int = 5000):
        self.dir = root / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.columns = columns
        self.flush_rows = flush_rows
        self.buffer: list[dict] = []
        self.part = 0
        self.rows = 0

    def write(self, row: dict) -> None:
        self.buffer.append({k: row.get(k) for k in self.columns})
        self.rows += 1
        if len(self.buffer) >= self.flush_rows:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        pd.DataFrame(self.buffer, columns=self.columns).to_parquet(self.dir / f"part-{self.part:05d}.parquet", index=False)
        self.part += 1
        self.buffer.clear()

    def compact(self, final: Path) -> int:
        self.flush()
        files = sorted(self.dir.glob("*.parquet"))
        if not files:
            pd.DataFrame(columns=self.columns).to_parquet(final, index=False)
            return 0
        schemas = [pq.ParquetFile(file).schema_arrow for file in files]
        schema = pa.unify_schemas(schemas, promote_options="default")
        writer = None
        total = 0
        try:
            writer = pq.ParquetWriter(final, schema)
            for file in files:
                pf = pq.ParquetFile(file)
                for batch in pf.iter_batches(batch_size=8192):
                    table = pa.Table.from_batches([batch], schema=pf.schema_arrow).cast(schema)
                    writer.write_table(table)
                    total += batch.num_rows
        finally:
            if writer is not None:
                writer.close()
        return total


def new_aggregate() -> dict:
    return {
        "topics": set(), "reasons": set(), "evidence": [], "matched_turns": set(),
        "prompt_political_turns": 0, "assistant_responses_political": 0,
        "metadata_political": False, "adjacent_metadata": False,
        "languages": set(), "categories": set(), "modes": set(), "model_pairs": set(),
        "n_source_turns": 0, "max_turn": -1, "timestamp": None, "last_timestamp": None,
        "priority": "2_response_only",
    }


def update_aggregate(agg: dict, row: dict, screened: dict) -> None:
    agg["topics"].update(screened["conversation_topics"])
    agg["reasons"].update(screened["shortlist_reason"])
    agg["matched_turns"].add(int(row["turn"]))
    agg["prompt_political_turns"] += int(screened["prompt_political"])
    agg["assistant_responses_political"] += int(screened["response_a_political"]) + int(screened["response_b_political"])
    agg["metadata_political"] |= screened["metadata_political"]
    agg["adjacent_metadata"] |= screened["adjacent_metadata"]
    agg["languages"].update(screened["languages"])
    agg["categories"].update(screened["categories"])
    if screened.get("mode"):
        agg["modes"].add(str(screened["mode"]))
    agg["model_pairs"].add(f"{row.get('model_a')} || {row.get('model_b')}")
    agg["n_source_turns"] += 1
    agg["max_turn"] = max(agg["max_turn"], int(row["turn"]))
    ts = row.get("timestamp")
    if ts is not None:
        if agg["timestamp"] is None or str(ts) < str(agg["timestamp"]):
            agg["timestamp"] = ts
        if agg["last_timestamp"] is None or str(ts) > str(agg["last_timestamp"]):
            agg["last_timestamp"] = ts
    if screened["prompt_political"] or screened["metadata_political"]:
        agg["priority"] = "1_prompt_or_source_topic"
    for ev in screened["evidence"]:
        if len(agg["evidence"]) < 12:
            agg["evidence"].append({"turn": int(row["turn"]), **ev})


def aggregate_record(comparison_id: str, agg: dict) -> dict:
    return {
        "comparison_id": comparison_id,
        "timestamp": agg["timestamp"],
        "last_timestamp": agg["last_timestamp"],
        "n_source_turns": agg["n_source_turns"],
        "max_turn": agg["max_turn"],
        "shortlist_reason": sorted(agg["reasons"]),
        "review_priority": agg["priority"],
        "review_status": "needs_review",
        "candidate_topics": sorted(agg["topics"]),
        "matched_turns": sorted(agg["matched_turns"]),
        "prompt_political_turns": agg["prompt_political_turns"],
        "assistant_responses_political": agg["assistant_responses_political"],
        "metadata_political": agg["metadata_political"],
        "adjacent_metadata_only": bool(agg["adjacent_metadata"] and not agg["topics"]),
        "languages": sorted(agg["languages"]),
        "categories": sorted(agg["categories"]),
        "mode": sorted(agg["modes"]),
        "model_pairs": sorted(agg["model_pairs"]),
        "evidence_json": json.dumps(agg["evidence"], ensure_ascii=False),
    }


def run(args: argparse.Namespace) -> dict:
    rules = PoliticalRules(Path(args.rules))
    input_path = args.input
    if args.revision and input_path.startswith("hf://") and "@" not in input_path:
        input_path = input_path.replace(f"/{HF_FILE}", f"@{args.revision}/{HF_FILE}")
    available_columns = source_column_names(input_path)
    missing = set(FULL_COLUMNS) - available_columns
    if missing:
        raise ValueError(
            "Full-text export requires these source Parquet columns, which are missing: "
            f"{sorted(missing)}. No annotation-only dataset was written."
        )

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    aggregates: dict[str, dict] = {}
    seen_response_ids: set[str] = set()
    seen_turns: set[tuple[str, int]] = set()
    seen_conversations: set[str] = set()
    eligible_conversations: set[str] = set()
    total_turns_by_conversation: Counter = Counter()
    max_turn_by_conversation: dict[str, int] = {}
    counts = Counter()
    topic_prompt_counts = Counter()
    topic_response_counts = Counter()
    topic_conversation_ids: dict[str, set[str]] = defaultdict(set)

    with tempfile.TemporaryDirectory(prefix=".political_parts_", dir=output) as tmp:
        tmp_root = Path(tmp)
        prompt_writer = PartWriter(tmp_root, "prompts", PROMPT_COLUMNS)
        response_writer = PartWriter(tmp_root, "responses", RESPONSE_COLUMNS)
        conversation_writer = PartWriter(tmp_root, "conversations", CONVERSATION_COLUMNS)

        # Pass 1: identify shortlisted conversations and aggregate turn-level signals.
        for df in iter_batches(input_path, TURN_COLUMNS, args.batch_size, args.direct_pandas):
            for row in df.to_dict("records"):
                if args.limit_rows and counts["source_rows_read"] >= args.limit_rows:
                    break
                counts["source_rows_read"] += 1
                rid = str(row.get("response_id"))
                cid = str(row.get("comparison_id"))
                try:
                    turn = int(row.get("turn"))
                except (TypeError, ValueError):
                    counts["invalid_turn_rows"] += 1
                    continue
                if not cid or cid == "None":
                    counts["missing_comparison_id_rows"] += 1
                    continue
                if rid in seen_response_ids:
                    counts["duplicate_response_id_rows"] += 1
                    continue
                seen_response_ids.add(rid)
                key = (cid, turn)
                if key in seen_turns:
                    counts["duplicate_turn_rows"] += 1
                    continue
                seen_turns.add(key)
                seen_conversations.add(cid)
                screened = screen_turn(row, rules)
                if args.french_only and "fr" not in screened["languages"]:
                    counts["non_french_rows_skipped"] += 1
                    continue
                eligible_conversations.add(cid)
                total_turns_by_conversation[cid] += 1
                max_turn_by_conversation[cid] = max(max_turn_by_conversation.get(cid, -1), turn)
                counts["unique_turns"] += 1
                counts["prompt_turns"] += int(bool(screened["prompt"]))
                counts["assistant_responses"] += int(bool(screened["response_a"])) + int(bool(screened["response_b"]))
                counts["prompt_turns_with_political_text"] += int(screened["prompt_political"])
                counts["assistant_responses_with_political_text"] += int(screened["response_a_political"]) + int(screened["response_b_political"])
                counts["turns_with_any_political_signal"] += int(screened["political"])
                topic_prompt_counts.update(screened["prompt_topics"])
                topic_response_counts.update(screened["response_a_topics"])
                topic_response_counts.update(screened["response_b_topics"])
                if screened["metadata_political"]:
                    counts["turns_with_politics_metadata"] += 1
                if screened["political"]:
                    agg = aggregates.setdefault(cid, new_aggregate())
                    update_aggregate(agg, row, screened)
                    for topic in screened["conversation_topics"]:
                        topic_conversation_ids[topic].add(cid)
                elif screened["adjacent_metadata"]:
                    counts["adjacent_metadata_only_turns"] += 1
            if args.limit_rows and counts["source_rows_read"] >= args.limit_rows:
                break

        shortlisted = set(aggregates)
        for cid, agg in aggregates.items():
            agg["n_source_turns"] = total_turns_by_conversation[cid]
            agg["max_turn"] = max_turn_by_conversation[cid]
        counts["shortlisted_conversations"] = len(shortlisted)
        counts["source_conversations"] = len(seen_conversations)
        counts["eligible_conversations"] = len(eligible_conversations)
        counts["metadata_political_conversations"] = sum(a["metadata_political"] for a in aggregates.values())
        counts["prompt_text_political_conversations"] = sum(a["prompt_political_turns"] > 0 for a in aggregates.values())
        counts["response_text_political_conversations"] = sum(a["assistant_responses_political"] > 0 for a in aggregates.values())
        counts["response_only_conversations"] = sum(a["priority"] == "2_response_only" for a in aggregates.values())
        counts["french_shortlisted_conversations"] = sum("fr" in a["languages"] for a in aggregates.values())

        # Pass 2: export all turns in shortlisted conversations and the transcript
        # snapshot from each conversation's highest source turn. The first row is
        # not necessarily a complete multi-turn transcript.
        exported_full: set[str] = set()
        exported_turns: set[tuple[str, int]] = set()
        transcript_status_counts = Counter()
        for df in iter_batches(input_path, FULL_COLUMNS, args.batch_size, args.direct_pandas):
            for row in df.to_dict("records"):
                cid = str(row.get("comparison_id"))
                if cid not in shortlisted:
                    continue
                try:
                    turn = int(row.get("turn"))
                except (TypeError, ValueError):
                    continue
                key = (cid, turn)
                if key not in seen_turns or key in exported_turns:
                    continue
                screened = screen_turn(row, rules)
                if args.french_only and "fr" not in screened["languages"]:
                    continue
                exported_turns.add(key)
                agg = aggregates[cid]
                base = {
                    "comparison_id": cid, "turn": turn, "response_id": row.get("response_id"),
                    "timestamp": row.get("timestamp"), "model_a": row.get("model_a"),
                    "model_b": row.get("model_b"), "choice": row.get("choice"),
                    "languages": screened["languages"], "categories": screened["categories"],
                    "mode": screened.get("mode"), "metadata_political": screened["metadata_political"],
                    "conversation_political": True, "conversation_topics": sorted(agg["topics"]),
                    "shortlist_reason": sorted(agg["reasons"]), "review_priority": agg["priority"],
                }
                prompt_writer.write({
                    **base, "prompt": screened["prompt"], "prompt_political": screened["prompt_political"],
                    "prompt_topics": screened["prompt_topics"],
                    "prompt_evidence_json": json.dumps(screened["prompt_evidence"], ensure_ascii=False),
                    "prompt_mismatch": screened["prompt_mismatch"],
                })
                for side in ["a", "b"]:
                    text = screened[f"response_{side}"]
                    if not text:
                        continue
                    response_writer.write({
                        **base, "side": side, "model": row.get(f"model_{side}"), "response": text,
                        "response_political": screened[f"response_{side}_political"],
                        "prompt_political": screened["prompt_political"],
                        "response_topics": screened[f"response_{side}_topics"],
                        "response_evidence_json": json.dumps(screened[f"response_{side}_evidence"], ensure_ascii=False),
                    })

                if turn == max_turn_by_conversation[cid] and cid not in exported_full:
                    full_a = sanitize_conversation(row.get("full_conversation_a"))
                    full_b = sanitize_conversation(row.get("full_conversation_b"))
                    status, message_counts = transcript_export_status(
                        full_a, full_b, total_turns_by_conversation[cid]
                    )
                    record = aggregate_record(cid, agg)
                    record.update({
                        "model_a": row.get("model_a"),
                        "model_b": row.get("model_b"),
                        "full_conversation_a": full_a,
                        "full_conversation_b": full_b,
                        "full_conversation_a_user_messages": message_counts[0],
                        "full_conversation_a_assistant_messages": message_counts[1],
                        "full_conversation_b_user_messages": message_counts[2],
                        "full_conversation_b_assistant_messages": message_counts[3],
                        "conversation_export_status": status,
                        "conversation_export_complete": status == "complete",
                    })
                    conversation_writer.write(record)
                    exported_full.add(cid)
                    transcript_status_counts[status] += 1

        # Retain one row for every shortlisted conversation even if the source
        # did not expose a matching final-turn transcript row; flag it explicitly.
        for cid in sorted(shortlisted - exported_full):
            agg = aggregates[cid]
            record = aggregate_record(cid, agg)
            record.update({
                "model_a": None,
                "model_b": None,
                "full_conversation_a": [],
                "full_conversation_b": [],
                "full_conversation_a_user_messages": 0,
                "full_conversation_a_assistant_messages": 0,
                "full_conversation_b_user_messages": 0,
                "full_conversation_b_assistant_messages": 0,
                "conversation_export_status": "missing_max_turn_source_row",
                "conversation_export_complete": False,
            })
            conversation_writer.write(record)
            transcript_status_counts["missing_max_turn_source_row"] += 1

        counts["conversations_with_complete_transcripts"] = transcript_status_counts["complete"]
        counts["conversations_with_incomplete_transcripts"] = sum(
            n for status, n in transcript_status_counts.items() if status != "complete"
        )
        counts["conversations_with_missing_max_turn_source_row"] = transcript_status_counts[
            "missing_max_turn_source_row"
        ]

        prompt_rows = prompt_writer.compact(output / "political_prompts.parquet")
        response_rows = response_writer.compact(output / "political_responses.parquet")
        conversation_rows = conversation_writer.compact(output / "political_conversations.parquet")

    review = pd.DataFrame([aggregate_record(cid, agg) for cid, agg in aggregates.items()])
    if not review.empty:
        review = review.sort_values(["review_priority", "timestamp", "comparison_id"], na_position="last")
    review.to_csv(output / "review_queue.csv", index=False)
    topic_rows = []
    for topic in sorted(set(topic_prompt_counts) | set(topic_response_counts) | set(topic_conversation_ids)):
        topic_rows.append({
            "topic": topic,
            "conversations": len(topic_conversation_ids[topic]),
            "prompt_turns": topic_prompt_counts[topic],
            "assistant_responses": topic_response_counts[topic],
        })
    topic_df = pd.DataFrame(topic_rows, columns=["topic", "conversations", "prompt_turns", "assistant_responses"])
    topic_df.to_csv(output / "topic_counts.csv", index=False)

    summary = {
        "status": "partial_smoke_test" if args.limit_rows else "complete_source_scan",
        "source_read_succeeded": True,
        "input": input_path,
        "revision_requested": args.revision,
        "reader": "pandas.read_parquet" if args.direct_pandas else "pyarrow batches -> pandas",
        "rules_version": rules.version,
        "rules_sha256": sha256_file(Path(args.rules)),
        "french_only": args.french_only,
        "limit_rows": args.limit_rows,
        "counts": dict(counts),
        "output_rows": {
            "political_conversations": conversation_rows,
            "political_prompts": prompt_rows,
            "political_responses": response_rows,
        },
        "full_conversation_dataset": {
            "file": "political_conversations.parquet",
            "full_transcripts_included": True,
            "transcript_columns": ["full_conversation_a", "full_conversation_b"],
            "model_columns": ["model_a", "model_b"],
            "transcripts_are_visible_user_and_assistant_content_only": True,
            "transcripts_selected_from_highest_source_turn": True,
            "transcript_status_counts": dict(transcript_status_counts),
        },
        "percentages": {
            "shortlisted_conversations_of_eligible": 100 * len(shortlisted) / len(eligible_conversations) if eligible_conversations else None,
            "prompt_turns_with_political_text": 100 * counts["prompt_turns_with_political_text"] / counts["prompt_turns"] if counts["prompt_turns"] else None,
            "assistant_responses_with_political_text": 100 * counts["assistant_responses_with_political_text"] / counts["assistant_responses"] if counts["assistant_responses"] else None,
        },
        "topic_counts_file": "topic_counts.csv",
        "caveats": [
            "Rule matches are high-recall review candidates, not verified political labels or causal classifications.",
            "Prompt counts are unique comparison_id+turn instances, not unique prompt strings across conversations.",
            "Response counts are individual assistant responses with political text, not both responses to every political prompt.",
            "Conversation shortlist includes prompt-text, response-text, or source Politics & Government metadata signals.",
            "Adjacent Law/Society/Environment metadata alone does not shortlist a conversation.",
            "Full A/B transcripts come from each conversation's highest source turn; incomplete transcripts are retained but flagged.",
            "Only visible user/assistant content is exported; hidden reasoning_content, system prompts, and tool payloads are excluded.",
            "Keyword and surname rules can produce false positives; manual validation is required before prevalence claims.",
        ],
        "packages": {"pandas": pd.__version__, "pyarrow": pa.__version__},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n")
    manifest = {"format_version": 1, "files": {}}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest.json" and not path.name.startswith("."):
            manifest["files"][path.name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Local Parquet path or hf:// URI")
    parser.add_argument("--output-dir", default="french-arena/data/full")
    parser.add_argument("--revision", default=None, help="Optional Hugging Face revision to pin")
    parser.add_argument("--rules", default=str(RULES_PATH))
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--limit-rows", type=int, default=None, help="Partial smoke test only; not a prevalence estimate")
    parser.add_argument("--french-only", action="store_true", help="Require metadata.languages to contain fr")
    parser.add_argument("--direct-pandas", action="store_true", help="Use pd.read_parquet directly; may require substantial RAM")
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
