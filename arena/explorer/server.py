#!/usr/bin/env python3
"""Political-content explorer for the Arena 140k shortlist.

Dependency-free HTTP server (Python standard library only).  It serves the
single-page UI and a small JSON/CSV API over the full-text data produced by
``arena/extract_full_text.py``.

    python arena/explorer/server.py --port 8000 --host 0.0.0.0
    open http://localhost:8000/

Endpoints (all relative to the server origin, so the preview proxy works):
    GET /api/bootstrap      manifest + corpus summary + available filter values
    GET /api/query?...      filtered rows + facets for the charts
    GET /api/row?id=...     one row with FULL, untruncated text
    GET /api/export?...     CSV of all matching rows, incl. full prompt text
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import random
import re
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RESULTS = ROOT.parent / "results"

TOPICS = ["elections", "voting", "public_policy", "immigration",
          "political_figures", "parties_ideology", "geopolitics",
          "non_english_politics"]


def _read_jsonl_gz(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _hay(r: dict) -> str:
    parts = [r.get("prompt") or ""]
    parts.extend(r.get("user_turns") or [])
    parts.append(r.get("assistant_a") or "")
    parts.append(r.get("assistant_b") or "")
    return "\n".join(parts).lower()


def _public(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


class Store:
    def __init__(self):
        self.conv = _read_jsonl_gz(DATA / "conversations.jsonl.gz")
        self._prompts: list[dict] | None = None
        for r in self.conv:
            r["_hay"] = _hay(r)
            r["_scope"] = "core"
        self.by_id = {r["id"]: r for r in self.conv}
        self.manifest = self._load_manifest()
        self.summary = self._load_summary()

    @property
    def prompts(self) -> list[dict]:
        if self._prompts is None:
            self._prompts = _read_jsonl_gz(DATA / "prompts_all.jsonl.gz")
            for r in self._prompts:
                r["_hay"] = _hay(r)
                r["_scope"] = "all"
        return self._prompts

    def _load_manifest(self):
        p = DATA / "manifest.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _load_summary(self):
        p = RESULTS / "summary.json"
        if not p.exists():
            return {}
        s = json.loads(p.read_text(encoding="utf-8"))
        return s

    def scoped(self, scope: str) -> list[dict]:
        return self.conv if scope != "all" else self.prompts


STORE: Store


def facets(rows: list[dict]) -> dict:
    def top(counter: Counter, n: int = 20) -> dict:
        return dict(counter.most_common(n))

    topic = Counter(t for r in rows for t in (r.get("categories") or []))
    model = Counter(m for r in rows for m in (r.get("model_a"), r.get("model_b")) if m)
    score = Counter()
    cross: dict[str, Counter] = {}
    for r in rows:
        s = int(r.get("score") or 0)
        bucket = "0-4" if s < 5 else "5-9" if s < 10 else "10-19" if s < 20 else "20+"
        score[bucket] += 1
        cross.setdefault(r.get("tier", "unknown"), Counter())[r.get("basis", "unknown")] += 1
    return {
        "cross": {k: dict(v) for k, v in cross.items()},
        "prompt_tier": top(Counter(r.get("prompt_tier") for r in rows)),
        "tier": top(Counter(r.get("tier") for r in rows)),
        "basis": top(Counter(r.get("basis") for r in rows)),
        "topic": top(topic, len(TOPICS) + 2),
        "language": top(Counter(r.get("language") for r in rows), 15),
        "winner": top(Counter(r.get("winner") for r in rows)),
        "month": dict(sorted(Counter((r.get("timestamp") or "")[:7] for r in rows).items())),
        "model": top(model, 15),
        "code": top(Counter("code" if r.get("is_code") else "non_code" for r in rows)),
        "score_band": dict(sorted(score.items())),
        "total": len(rows),
    }


def apply_filters(rows: list[dict], q: dict) -> list[dict]:
    def one(name, default=""):
        vals = q.get(name)
        return vals[0] if vals else default

    text = one("q").strip()
    regex = None
    if text.startswith("re:"):
        try:
            regex = re.compile(text[3:], re.IGNORECASE)
        except re.error:
            regex = None
            text = ""
    else:
        text = text.lower()

    tier = one("tier")
    basis = one("basis")
    topic = one("topic")
    lang = one("lang")
    winner = one("winner")
    model = one("model")
    code = one("code")
    date_from = one("date_from")
    date_to = one("date_to")
    try:
        min_score = int(one("min_score", "0"))
    except ValueError:
        min_score = 0

    out = []
    for r in rows:
        if tier and tier != "all" and r.get("tier") != tier:
            continue
        if basis and basis != "all" and r.get("basis") != basis:
            continue
        if topic and topic != "all" and topic not in (r.get("categories") or []):
            continue
        if lang and lang != "all" and r.get("language") != lang:
            continue
        if winner and winner != "all" and r.get("winner") != winner:
            continue
        if model and model != "all" and model not in (r.get("model_a"), r.get("model_b")):
            continue
        if code and code != "all":
            want = code == "code"
            if bool(r.get("is_code")) != want:
                continue
        ts = (r.get("timestamp") or "")[:10]
        if date_from and ts < date_from:
            continue
        if date_to and ts > date_to:
            continue
        if int(r.get("score") or 0) < min_score:
            continue
        if regex is not None:
            if not regex.search(r.get("_hay", "")):
                continue
        elif text and text not in r.get("_hay", ""):
            continue
        out.append(r)

    sort = one("sort", "score")
    if sort == "date":
        out.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    elif sort == "prompt_len":
        out.sort(key=lambda r: r.get("prompt_chars", len(r.get("prompt") or "")), reverse=True)
    elif sort == "random":
        random.Random(1337).shuffle(out)
    else:
        out.sort(key=lambda r: (int(r.get("score") or 0), r.get("id") or ""), reverse=True)
    return out


def compact(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "row_idx": r.get("row_idx"),
        "tier": r.get("tier"),
        "basis": r.get("basis"),
        "prompt_tier": r.get("prompt_tier"),
        "categories": r.get("categories") or [],
        "language": r.get("language"),
        "is_code": r.get("is_code"),
        "winner": r.get("winner"),
        "model_a": r.get("model_a"),
        "model_b": r.get("model_b"),
        "timestamp": r.get("timestamp"),
        "score": r.get("score"),
        "prompt_chars": r.get("prompt_chars", len(r.get("prompt") or "")),
        "has_answers": bool(r.get("assistant_a") or r.get("assistant_b")),
        "prompt_preview": (r.get("prompt") or "").replace("\n", " ")[:260],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            return  # keep the preview log readable
        super().log_message(fmt, *args)

    def _send(self, body: bytes, ctype: str, status: int = 200, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    def do_GET(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return super().do_GET()
        q = parse_qs(parsed.query)
        try:
            return self.api(parsed.path, q)
        except Exception as exc:  # keep the UI alive on a bad query
            return self._json({"error": str(exc)}, 500)

    def api(self, path: str, q: dict):
        if path == "/api/bootstrap":
            s = STORE.summary
            return self._json({
                "manifest": STORE.manifest,
                "corpus": {
                    "rows_scanned": s.get("rows_scanned"),
                    "counts": s.get("counts", {}),
                    "unique_prompts_by_tier": s.get("unique_prompts_by_tier", {}),
                    "top_strong_terms_prompt": s.get("top_strong_terms_prompt", {}),
                    "categories_prompt_strict_or_probable": s.get("categories_prompt_strict_or_probable", {}),
                    "by_winner": s.get("by_winner", {}),
                    "by_is_code": s.get("by_is_code", {}),
                    "by_month": s.get("by_month", {}),
                },
                "options": {
                    "topics": TOPICS,
                    "tiers": ["strict", "probable"],
                    "bases": ["prompt", "response", "both"],
                    "winners": ["model_a", "model_b", "tie", "both_bad"],
                    "languages": [k for k, _ in Counter(
                        r.get("language") for r in STORE.conv).most_common(20)],
                    "models": [k for k, _ in Counter(
                        m for r in STORE.conv for m in (r.get("model_a"), r.get("model_b")) if m
                    ).most_common(30)],
                },
                "data_counts": {
                    "conversations": len(STORE.conv),
                    "prompts_all": _count_prompt_rows(),
                },
            })

        if path == "/api/query":
            scope = (q.get("scope") or ["core"])[0]
            rows = apply_filters(STORE.scoped(scope), q)
            f = facets(rows)
            try:
                limit = max(1, min(200, int((q.get("limit") or ["25"])[0])))
                offset = max(0, int((q.get("offset") or ["0"])[0]))
            except ValueError:
                limit, offset = 25, 0
            page = [_public_compact(r) for r in rows[offset:offset + limit]]
            return self._json({
                "total": len(rows), "offset": offset, "limit": limit,
                "facets": f, "rows": page,
                "scope": scope,
            })

        if path == "/api/row":
            rid = unquote((q.get("id") or [""])[0])
            r = STORE.by_id.get(rid)
            if r is None:
                # fall back to the prompt-only index
                for pr in STORE.prompts:
                    if pr.get("id") == rid:
                        r = pr
                        break
            if r is None:
                return self._json({"error": "id not found"}, 404)
            return self._json(_public(r))

        if path == "/api/export":
            scope = (q.get("scope") or ["core"])[0]
            rows = apply_filters(STORE.scoped(scope), q)
            buf = io.StringIO()
            w = csv.writer(buf, quoting=csv.QUOTE_ALL)
            w.writerow(["id", "row_idx", "tier", "basis", "prompt_tier", "categories",
                        "language", "is_code", "winner", "model_a", "model_b",
                        "timestamp", "score", "prompt_full_untruncated"])
            for r in rows:
                w.writerow([r.get("id"), r.get("row_idx"), r.get("tier"), r.get("basis"),
                            r.get("prompt_tier"), "|".join(r.get("categories") or []),
                            r.get("language"), r.get("is_code"), r.get("winner"),
                            r.get("model_a"), r.get("model_b"), r.get("timestamp"),
                            r.get("score"), r.get("prompt") or ""])
            return self._send(
                buf.getvalue().encode("utf-8"),
                "text/csv; charset=utf-8",
                extra={"Content-Disposition": 'attachment; filename="political_prompts_full.csv"'},
            )

        return self._json({"error": "unknown endpoint"}, 404)


def _public_compact(r: dict) -> dict:
    return compact(r)


def _count_prompt_rows() -> int:
    p = DATA / "prompts_all.jsonl.gz"
    if not p.exists():
        return 0
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def main():
    global STORE
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    STORE = Store()
    print(f"[explorer] {len(STORE.conv):,} full conversations loaded", flush=True)
    print(f"[explorer] serving http://{args.host}:{args.port}/", flush=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
