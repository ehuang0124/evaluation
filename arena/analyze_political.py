#!/usr/bin/env python3
"""Initial political-content screen for ``lmarena-ai/arena-human-preference-140k``.

The dataset is a collection of human preference votes: each row contains one user
conversation judged by two models.  This script screens the *user prompts* and the
two *candidate responses* for political subject matter and produces:

  * summary.json                 - every count produced by the scan
  * shortlist.csv                - capped, human-readable shortlist of flagged rows
  * matched_ids.csv.gz           - ALL flagged vote IDs (the full shortlist for labeling)
  * audit_sample.csv             - random sample for manual precision / recall checks
  * run_meta.json                - provenance (dataset revision, args, runtime)

Usage (as supplied in the request)::

    from datasets import load_dataset
    ds = load_dataset("lmarena-ai/arena-human-preference-140k")

    python arena/analyze_political.py --output-dir arena/results
    python arena/analyze_political.py --output-dir /tmp/smoke --max-rows 200
    python arena/analyze_political.py --self-test

Method in one sentence: a transparent, auditable lexicon of political terms
(elections, voting, public policy, immigration, political figures, parties &
ideology, geopolitics, plus non-English equivalents) is matched against the user
turns and the two judged assistant turns of every row; a hit is reported in one of
three tiers so that the estimate can be read as a range rather than a single
over-confident number.  See arena/README.md for the definition of each tier.

Only the Python standard library is needed for the classifier; ``datasets`` is
needed to stream the actual corpus.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

DATASET = "lmarena-ai/arena-human-preference-140k"
SPLIT = "train"
VERSION = "1.1.0"

# ---------------------------------------------------------------------------
# Lexicon.  Terms are plain phrases (regex-escaped internally).
#   "strong"   = unambiguous political signal (a single hit is enough for `strict`)
#   "weak"     = ambiguous in isolation (needs corroboration for `probable`)
# A term prefixed with "CS:" is matched case-sensitively (short acronyms).
# ---------------------------------------------------------------------------
TAXONOMY: dict[str, dict[str, list[str]]] = {
    "elections": {
        "strong": [
            "election", "elections", "electoral", "electorate", "ballot", "ballots",
            "midterm", "midterms", "inauguration", "recount", "caucus",
            "electoral college", "swing state", "presidential race",
            "presidential election", "general election", "primary election",
            "runoff election", "polling station", "campaign trail",
            "presidential debate", "nominating convention", "nomination",
            "incumbent", "electoral vote", "voter fraud", "election denier",
            "election denial", "get out the vote", "2020 election", "2024 election",
            "election result", "election results", "concession speech",
            "landslide victory", "electoral district", "electoral system",
        ],
        "weak": [
            "campaign", "campaigns", "candidate", "candidates", "nominee", "polls",
            "polling", "debate", "running for office", "primary", "front runner",
            "frontrunner", "opinion poll", "stump speech",
        ],
    },
    "voting": {
        "strong": [
            "vote", "votes", "voted", "voting", "voter", "voters", "suffrage",
            "gerrymandering", "disenfranchisement", "referendum", "plebiscite",
            "voter registration", "voter id", "voter turnout", "cast a ballot",
            "absentee ballot", "ranked choice", "ranked-choice", "ballot initiative",
            "voting rights", "secret ballot", "voting age", "poll tax", "poll taxes",
            "voting machine", "voting booth",
        ],
        "weak": ["turnout", "enfranchise", "elector", "electors", "electorate"],
    },
    "public_policy": {
        "strong": [
            "public policy", "policymaker", "policymakers", "legislation",
            "legislative", "legislature", "congress", "congressional", "senate",
            "parliament", "parliamentary", "constitution", "constitutional",
            "amendment", "supreme court", "executive order", "federal government",
            "government", "governments", "governor", "mayor", "city council",
            "white house", "president", "presidency", "prime minister", "senator",
            "congressman", "congresswoman", "bill of rights", "civil rights",
            "affirmative action", "police reform", "defund the police",
            "executive branch", "legislative branch", "judicial branch",
            "abortion", "roe v. wade", "affordable care act", "obamacare",
            "medicare", "medicaid", "social security", "minimum wage",
            "gun control", "gun laws", "universal health care", "universal healthcare",
            "healthcare reform", "climate policy", "carbon tax", "tariff", "tariffs",
            "foreign policy", "sanctions", "economic sanctions", "trade policy",
            "student loan forgiveness", "infrastructure bill", "tax policy",
            "immigration policy", "energy policy", "education policy",
            "housing policy", "public option", "national debt", "welfare reform",
            "lockdown mandate", "vaccine mandate", "zoning law", "zoning laws",
            "constitutional law", "public health policy", "state legislature",
            "act of congress", "bill signed into law", "regulatory state",
        ],
        "weak": [
            "policy", "policies", "law", "laws", "bill", "bills", "regulation",
            "regulations", "tax", "taxes", "taxation", "budget", "reform", "reforms",
            "mandate", "welfare", "public sector", "federal", "state", "national",
            "public", "statute", "statutes", "decree", "ordinance", "referenda",
        ],
    },
    "immigration": {
        "strong": [
            "immigration", "immigrant", "immigrants", "illegal immigrant",
            "illegal immigrants", "undocumented", "undocumented immigrant",
            "undocumented immigrants", "border wall", "border patrol",
            "border control", "border crisis", "border crossing", "deportation",
            "deport", "deported", "asylum", "asylum seeker", "asylum seekers",
            "refugee", "refugees", "visa", "visas", "green card", "citizenship",
            "naturalization", "CS:DACA", "dreamers", "birthright citizenship",
            "sanctuary city", "sanctuary cities", "open borders", "h-1b", "h1b",
            "customs and border protection", "CS:CBP", "ice raids", "ice agents",
            "title 42", "remain in mexico", "migrant crisis", "migrant caravan",
            "work permit", "residency permit", "illegal alien", "illegal aliens",
            "immigration law", "immigration reform", "mass deportation",
        ],
        "weak": [
            "migrant", "migrants", "migration", "border", "borders", "foreigners",
            "alien", "aliens", "citizen", "citizens", "residency", "expat",
            "crossing the border", "port of entry",
        ],
    },
    "political_figures": {
        "strong": [
            # US, current/recent
            "donald trump", "trump", "joe biden", "biden", "kamala harris",
            "barack obama", "obama", "hillary clinton", "bill clinton",
            "george w. bush", "george bush", "ronald reagan", "reagan",
            "john f. kennedy", "jfk", "franklin d. roosevelt", "fdr",
            "abraham lincoln", "richard nixon", "nixon", "jimmy carter",
            "ron desantis", "desantis", "gavin newsom", "newsom", "mike pence",
            "bernie sanders", "alexandria ocasio-cortez", "CS:AOC", "nancy pelosi",
            "mitch mcconnell", "chuck schumer", "jd vance", "tim walz",
            "nikki haley", "vivek ramaswamy", "robert f. kennedy jr", "rfk jr",
            "elon musk", "george soros", "soros", "charlie kirk", "ben shapiro",
            "tucker carlson", "mike johnson", "hakeem jeffries",
            # Non-US / historical
            "vladimir putin", "putin", "xi jinping", "narendra modi", "modi",
            "benjamin netanyahu", "netanyahu", "volodymyr zelensky", "zelensky",
            "kim jong un", "recep tayyip erdogan", "erdogan", "emmanuel macron",
            "macron", "keir starmer", "rishi sunak", "boris johnson",
            "angela merkel", "merkel", "winston churchill", "churchill",
            "adolf hitler", "hitler", "joseph stalin", "stalin", "mao zedong",
            "mao", "vladimir lenin", "lenin", "nelson mandela", "mandela",
            "martin luther king", "CS:MLK", "malcolm x", "muhammad ali",
            "saddam hussein", "muammar gaddafi", "nancy pelosi", "jacinda ardern",
            # Titles / institutions around office-holders
            "president of the united states", "CS:POTUS", "vice president",
            "first lady", "prime minister", "senator", "senators", "governor",
            "mayor", "dictator", "politician", "politicians", "congressman",
            "congresswoman", "chancellor", "secretary of state", "attorney general",
            "supreme leader", "member of parliament", "house speaker",
            "head of state", "white house", "oval office",
            "CS:MAGA", "make america great again", "qanon", "political figure",
        ],
        "weak": [
            "harris", "clinton", "bush", "washington", "kennedy", "carter",
            "vance", "johnson", "musk", "xi", "administration", "leader",
            "leaders", "king", "queen", "monarch", "presidential", "campaign",
            "candidate", "candidates", "nominee", "incumbent", "first family",
        ],
    },
    "parties_ideology": {
        "strong": [
            "democrat", "democrats", "democratic party", "republican",
            "republicans", "CS:GOP", "grand old party", "labour party",
            "conservative party", "liberal democrats", "tory", "tories",
            "left-wing", "right-wing", "far-left", "far-right", "fascism",
            "fascist", "fascists", "nazism", "nazi", "nazis", "neo-nazi",
            "communism", "communist", "communists", "socialism", "socialist",
            "socialists", "marxism", "marxist", "libertarian", "libertarians",
            "authoritarianism", "authoritarian", "partisan", "bipartisan",
            "political party", "political parties", "political ideology",
            "political spectrum", "political views", "political affiliation",
            "lobbyist", "lobbyists", "lobbying", "super pac", "political action committee",
            "political correctness", "woke", "red state", "blue state",
            "political polarization", "campaign finance", "politics", "political",
            "politically", "ideologically", "partisanship", "populism", "populist",
            "nationalism", "nationalist", "anarchism", "anarchist", "social democracy",
        ],
        "weak": [
            "liberal", "liberals", "conservative", "conservatives", "democracy",
            "democratic", "republic", "capitalism", "capitalist", "progressive",
            "progressives", "left", "right", "party", "parties", "ideology",
            "liberalism", "conservatism", "activist", "activism", "protest",
            "protests", "movement", "social justice", "equality",
        ],
    },
    "geopolitics": {
        "strong": [
            "ukraine war", "russia-ukraine war", "invasion of ukraine",
            "israel-palestine", "israeli-palestinian", "two-state solution",
            "hamas", "hezbollah", "palestinian", "palestinians", "ceasefire",
            "war crimes", "genocide", "apartheid", "CS:NATO",
            "un security council", "united nations security council",
            "geopolitics", "geopolitical", "foreign policy", "sanctions",
            "economic sanctions", "trade war", "cold war", "annexation",
            "peace treaty", "nuclear proliferation", "diplomatic relations",
            "war crime", "ethnic cleansing", "occupation of palestine",
            "international law", "human rights violations",
        ],
        "weak": [
            "ukraine", "russia", "russian", "israel", "israeli", "palestine",
            "gaza", "china", "chinese", "taiwan", "iran", "north korea",
            "united nations", "embassy", "summit", "treaty", "military", "war",
            "invasion", "conflict", "diplomacy", "foreign", "nation", "nations",
        ],
    },
    "non_english_politics": {
        # Unambiguous political vocabulary in the largest non-English language
        # groups of the corpus (en 71k, pl 14k, und 12k, ru 9k, zh 7k, de 4k,
        # ko 2.5k, ja 2.4k, fr 2.1k, es/pt 1.7k, ...). Partial coverage only.
        "strong": [
            # Polish
            "wybory", "wyborca", "wyborcy", "głosowanie", "polityka", "polityczny",
            "rząd", "parlament", "sejm", "prezydent", "imigracja", "uchodźca",
            "uchodźcy", "ustawa", "konstytucja", "CS:PiS", "platforma obywatelska",
            # Russian / Ukrainian
            "выборы", "голосование", "политика", "политический", "правительство",
            "президент", "парламент", "дума", "иммиграция", "мигрант", "беженец",
            "закон", "конституция", "путин", "депутат", "вибори", "президент україни",
            # Chinese
            "选举", "投票", "政治", "政策", "政府", "总统", "移民", "边境", "国会",
            "议员", "特朗普", "拜登", "普京", "习近平", "台湾", "民主党", "共和党",
            "法律", "法案", "难民", "总理", "主席", "人大", "共产党", "国民党",
            # German
            "wahlen", "politik", "politisch", "regierung", "bundesregierung",
            "bundestag", "kanzler", "präsident", "einwanderung", "zuwanderung",
            "flüchtlinge", "gesetz", "afd", "wähler", "parlament",
            # French / Italian / Spanish / Portuguese
            "élections", "élection", "politique", "gouvernement", "président",
            "immigration", "réfugiés", "assemblée nationale", "elezioni", "governo",
            "presidente", "immigrazione", "elecciones", "votación", "política",
            "gobierno", "inmigración", "refugiados", "congreso", "eleições",
            "governo", "imigração", "presidente", "bolsonaro", "lula",
            # Turkish / Persian / Arabic
            "seçim", "siyaset", "hükümet", "cumhurbaşkanı", "göçmen", "mülteci",
            "partisi", "erdoğan", "انتخابات", "سياسة", "حكومة", "رئيس", "مهاجرين",
            "لاجئين", "انتخاب", "سیاست", "دولت", "رئیس جمهور", "مهاجرت",
            # Korean / Japanese
            "선거", "투표", "정치", "정책", "정부", "대통령", "이민", "난민", "국회",
            "의원", "트럼프", "바이든", "選挙", "投票", "政治", "政策", "政府",
            "首相", "大統領", "移民", "難民", "国会", "議員", "トランプ", "バイデン",
            # Vietnamese / Indonesian / Dutch / Czech / Hebrew
            "bầu cử", "chính trị", "chính phủ", "người nhập cư", "pemilu",
            "politik", "pemerintah", "imigran", "verkiezingen", "regering",
            "politiek", "vluchtelingen", "volby", "vláda", "prezident",
            "בחירות", "פוליטיקה", "ממשלה", "נשיא", "מהגרים",
        ],
        "weak": [],
    },
}

# Strong terms that are known to be ambiguous in a technical / ML / gaming context
# (e.g. "leader election" in Raft, "majority vote" in ensembling, "vote" in a
# ranking poll).  If these are the *only* strong signals and a technical phrase is
# present, the hit is downgraded to the broad tier.
AMBIGUOUS_STRONG = {
    "election", "elections", "electoral", "vote", "votes", "voted", "voting",
    "voter", "voters", "ballot", "ballots", "president", "campaign", "polls",
}
TECH_CONTEXT = (
    "leader election", "election algorithm", "bully algorithm", "raft consensus",
    "paxos", "majority vote", "voting classifier", "voting ensemble",
    "majority voting", "vote counter", "distributed election", "vote on a poll",
    "election timeout", "consensus algorithm", "vote tally script",
)

# Weak terms that are far too generic to corroborate a `probable` call on their
# own (they still count for the high-recall `broad` tier).
GENERIC_WEAK = {
    "state", "national", "public", "left", "right", "party", "parties",
    "border", "borders", "war", "nation", "nations", "movement", "foreign",
    "conflict", "leader", "leaders", "king", "queen", "citizen", "citizens",
    "turnout", "alien", "aliens", "military", "summit", "diplomacy",
    "administration", "king", "equality", "expat", "residency",
}

# Political but *generic* governance vocabulary.  A single one of these in a
# 5,000-character assistant answer is usually an incidental mention ("...or
# contact your local government..."), so on the response side it is not enough
# for `strict` unless corroborated.  On the (short) user-prompt side it still is.
GENERIC_STRONG = {
    "government", "governments", "president", "presidency", "politics",
    "political", "politically", "policymaker", "policymakers", "governor",
    "mayor", "administration", "citizenship", "woke", "premier", "rząd",
    "governo", "política", "gobierno", "regierung", "правительство",
    "政府", "政策", "法律", "法案", "国会", "議員", "정책", "정부",
    "政治", "政治", "siyaset", "hükümet", "politique", "gouvernement",
    "politica", "polityka",
}

TIERS = ("none", "broad", "probable", "strict")
TIER_RANK = {t: i for i, t in enumerate(TIERS)}


def _build_matcher():
    """Compile the whole lexicon into a handful of regexes for speed."""
    from collections import OrderedDict

    term_map: dict[str, tuple[str, str, str]] = {}  # key -> (category, strength, label)
    latin_alts: list[str] = []
    cs_alts: list[str] = []
    cjk_alts: list[str] = []

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    entries: list[tuple[str, str, str, bool]] = []
    for category, groups in TAXONOMY.items():
        for strength in ("strong", "weak"):
            for raw in groups[strength]:
                case_sensitive = raw.startswith("CS:")
                term = raw[3:] if case_sensitive else raw
                entries.append((category, strength, term, case_sensitive))

    # Longest-first so "illegal immigrants" wins over "immigrants".
    entries.sort(key=lambda e: len(e[2]), reverse=True)
    for category, strength, term, case_sensitive in entries:
        key = norm(term)
        term_map.setdefault(key, (category, strength, term))
        escaped = r"\s+".join(re.escape(part) for part in term.split())
        if case_sensitive:
            cs_alts.append(escaped)
        elif any(ord(ch) > 0x2E7F for ch in term):  # CJK and other non-boundary scripts
            cjk_alts.append(escaped)
        else:
            latin_alts.append(escaped)

    patterns = []
    if latin_alts:
        patterns.append((re.compile(r"(?<!\w)(?:" + "|".join(latin_alts) + r")(?!\w)", re.IGNORECASE), "latin"))
    if cjk_alts:
        patterns.append((re.compile("(?:" + "|".join(cjk_alts) + ")"), "cjk"))
    if cs_alts:
        patterns.append((re.compile(r"(?<!\w)(?:" + "|".join(cs_alts) + r")(?!\w)"), "cs"))
    return patterns, term_map


PATTERNS, TERM_MAP = _build_matcher()


def find_hits(text: str) -> dict[str, tuple[str, str, int]]:
    """Return distinct matched terms -> (category, strength, occurrence count)."""
    if not text:
        return {}
    found: dict[str, tuple[str, str, int]] = {}
    for pattern, _kind in PATTERNS:
        for m in pattern.finditer(text):
            key = re.sub(r"\s+", " ", m.group(0).strip().lower())
            info = TERM_MAP.get(key)
            if info is None:
                continue
            category, strength, label = info
            old = found.get(label)
            found[label] = (category, strength, (old[2] + 1) if old else 1)
    return found


def classify(text: str, corroborate: bool = False) -> dict:
    """Classify one piece of text.

    ``corroborate=True`` is used for assistant responses, which are long and
    often mention a government, a law or a president in passing.  There, a
    `strict` call needs a topic-specific strong term *and* a second strong
    signal (another term, a repetition, or a short answer).
    """
    hits = find_hits(text)
    if not hits:
        return {"tier": "none", "categories": [], "strong_terms": [],
                "weak_terms": [], "strong_hits": 0, "specific_strong": []}
    strong = [(t, v[0], v[2]) for t, v in hits.items() if v[1] == "strong"]
    weak = [(t, v[0], v[2]) for t, v in hits.items() if v[1] == "weak"]

    low = text.lower()
    # Downgrade "leader election" / "majority vote" style technical false positives.
    if (strong and all(t in AMBIGUOUS_STRONG for t, _c, _n in strong)
            and any(ctx in low for ctx in TECH_CONTEXT)):
        weak = weak + [(t, c, n) for t, c, n in strong]
        strong = []

    tech = any(ctx in low for ctx in TECH_CONTEXT)
    anchoring_weak = [h for h in weak if h[0] not in GENERIC_WEAK]
    strong_hits = sum(n for _t, _c, n in strong)
    specific_strong = sorted(t for t, _c, _n in strong if t not in GENERIC_STRONG)

    if strong and not corroborate:
        tier = "strict"
    elif strong and corroborate and specific_strong and (strong_hits >= 2 or len(text) < 1000):
        tier = "strict"
    elif strong:
        # Single, uncorroborated political mention in a long answer.
        tier = "probable"
    elif tech:
        tier = "broad"
    elif len(weak) >= 2 and len({c for _t, c, _n in weak}) >= 2 and anchoring_weak:
        tier = "probable"
    else:
        tier = "broad"

    categories = sorted({v[0] for v in hits.values()})
    return {
        "tier": tier,
        "categories": categories,
        "strong_terms": sorted(t for t, _c, _n in strong),
        "weak_terms": sorted(t for t, _c, _n in weak),
        "strong_hits": strong_hits,
        "specific_strong": specific_strong,
    }


def max_tier(*tiers: str) -> str:
    return max(tiers, key=lambda t: TIER_RANK.get(t, 0))


def at_least(tier: str, threshold: str) -> bool:
    return TIER_RANK.get(tier, 0) >= TIER_RANK[threshold]


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------
def message_text(msg) -> str:
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def turns(conversation, role: str) -> list[str]:
    out = []
    if isinstance(conversation, (list, tuple)):
        for msg in conversation:
            if isinstance(msg, dict) and msg.get("role") == role:
                out.append(message_text(msg))
    return out


def excerpt(text: str, limit: int = 420) -> str:
    flat = re.sub(r"\s+", " ", (text or "")).strip()
    return flat[:limit] + ("…" if len(flat) > limit else "")


def norm_prompt(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


# ---------------------------------------------------------------------------
# Reservoir sampling helper (for the manual-audit sample)
# ---------------------------------------------------------------------------
class Reservoir:
    def __init__(self, size: int, seed: int):
        self.size = size
        self.rng = random.Random(seed)
        self.items: list[dict] = []
        self.seen = 0

    def add(self, item: dict) -> None:
        self.seen += 1
        if len(self.items) < self.size:
            self.items.append(item)
            return
        j = self.rng.randrange(self.seen)
        if j < self.size:
            self.items[j] = item


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------
def scan(args) -> dict:
    from datasets import load_dataset  # imported lazily so --self-test needs no deps

    t0 = time.time()
    print(f"[scan] dataset={DATASET} split={SPLIT} max_rows={args.max_rows or 'all'}", flush=True)
    ds = load_dataset(DATASET, split=SPLIT, streaming=True)
    print(f"[scan] load_dataset OK ({time.time() - t0:.1f}s)", flush=True)

    c: Counter = Counter()
    cat_prompt: Counter = Counter()
    cat_resp: Counter = Counter()
    strong_terms_prompt: Counter = Counter()
    strong_terms_resp: Counter = Counter()
    by_language: dict[str, Counter] = defaultdict(Counter)
    by_month: dict[str, Counter] = defaultdict(Counter)
    by_winner: dict[str, Counter] = defaultdict(Counter)
    by_code: dict[str, Counter] = defaultdict(Counter)

    shortlist: list[dict] = []
    matched_rows: list[dict] = []  # compact, all flagged rows -> gz csv
    audits = {
        "flagged": Reservoir(120, 11),
        "broad_only": Reservoir(60, 22),
        "unflagged": Reservoir(60, 33),
    }
    unique_prompts: dict[str, set] = {t: set() for t in ("strict", "probable", "broad")}
    rng = random.Random(7)

    n = 0
    for row in ds:
        n += 1
        conv_a = row.get("conversation_a") or []
        conv_b = row.get("conversation_b") or []
        user_turns = turns(conv_a, "user")
        last_prompt = user_turns[-1] if user_turns else ""
        all_prompt_text = "\n\n".join(user_turns)
        a_turns = turns(conv_a, "assistant")
        b_turns = turns(conv_b, "assistant")
        resp_a = a_turns[-1] if a_turns else ""
        resp_b = b_turns[-1] if b_turns else ""

        p_last = classify(last_prompt)
        p_any = classify(all_prompt_text)
        # Direct evidence in the answer itself (corroboration required), and the
        # topic label inherited from the prompt.  Either can label a response.
        ra = classify(resp_a, corroborate=True)
        rb = classify(resp_b, corroborate=True)
        ra_direct, rb_direct = ra["tier"], rb["tier"]
        ra_tier = max_tier(ra_direct, p_any["tier"])
        rb_tier = max_tier(rb_direct, p_any["tier"])
        r_any_tier = max_tier(ra_tier, rb_tier)
        any_tier = max_tier(p_any["tier"], r_any_tier)

        c["rows"] += 1
        c["responses_judged"] += int(bool(resp_a)) + int(bool(resp_b))
        c["rows_with_two_responses"] += int(bool(resp_a) and bool(resp_b))
        c["user_turns"] += len(user_turns)

        for tier in ("strict", "probable", "broad"):
            if at_least(p_any["tier"], tier):
                c[f"rows_prompt_{tier}"] += 1
            if at_least(p_last["tier"], tier):
                c[f"rows_current_prompt_{tier}"] += 1
            if at_least(r_any_tier, tier):
                c[f"rows_response_{tier}"] += 1
            if at_least(any_tier, tier):
                c[f"rows_any_{tier}"] += 1
            c[f"responses_direct_{tier}"] += int(at_least(ra_direct, tier)) + int(at_least(rb_direct, tier))
            c[f"responses_union_{tier}"] += int(at_least(ra_tier, tier)) + int(at_least(rb_tier, tier))

        # topic-level: a response to a political prompt is about politics even if
        # the model's wording contains none of the lexicon terms.
        for tier in ("strict", "probable", "broad"):
            if at_least(p_any["tier"], tier):
                c[f"responses_contextual_{tier}"] += int(bool(resp_a)) + int(bool(resp_b))

        if at_least(p_any["tier"], "strict"):
            c["rows_both_prompt_and_response_strict"] += int(at_least(r_any_tier, "strict"))
            c["rows_prompt_only_strict"] += int(not at_least(r_any_tier, "strict"))
        if at_least(r_any_tier, "strict") and not at_least(p_any["tier"], "strict"):
            c["rows_response_only_strict"] += 1

        # Topic / term breakdown uses strict+probable to avoid one-word noise.
        if at_least(p_any["tier"], "probable"):
            for cat in p_any["categories"]:
                cat_prompt[cat] += 1
            for t in p_any["strong_terms"]:
                strong_terms_prompt[t] += 1
        for cl in (ra, rb):
            if at_least(cl["tier"], "probable"):
                for cat in cl["categories"]:
                    cat_resp[cat] += 1
                for t in cl["strong_terms"]:
                    strong_terms_resp[t] += 1

        # Dedup repeated prompts (a session can produce several votes on one prompt).
        ph = hashlib.sha1(norm_prompt(last_prompt).encode("utf-8")).hexdigest()[:16]
        for tier in ("strict", "probable", "broad"):
            if at_least(p_any["tier"], tier):
                unique_prompts[tier].add(ph)

        lang = str(row.get("language") or "unknown")
        code = "code" if row.get("is_code") else "non_code"
        winner = str(row.get("winner") or "unknown")
        ts = row.get("timestamp")
        month = str(ts)[:7] if ts is not None else "unknown"
        for bucket, key in ((by_language, lang), (by_month, month), (by_winner, winner), (by_code, code)):
            bucket[key]["rows"] += 1
            for tier in ("strict", "probable", "broad"):
                if at_least(any_tier, tier):
                    bucket[key][f"any_{tier}"] += 1
                if at_least(p_any["tier"], tier):
                    bucket[key][f"prompt_{tier}"] += 1

        if any_tier != "none":
            cats = sorted(set(p_any["categories"] + ra["categories"] + rb["categories"]))
            strength = len(p_any["strong_terms"]) + len(ra["strong_terms"]) + len(rb["strong_terms"])
            score = 3 * strength + len(cats) + len(p_any["weak_terms"])
            rec = {
                "id": row.get("id"),
                "evaluation_session_id": row.get("evaluation_session_id"),
                "tier": any_tier,
                "prompt_tier": p_any["tier"],
                "response_tier": r_any_tier,
                "score": score,
                "categories": "|".join(cats),
                "prompt_strong_terms": "|".join(p_any["strong_terms"][:12]),
                "response_strong_terms": "|".join(sorted(set(ra["strong_terms"] + rb["strong_terms"]))[:12]),
                "language": lang,
                "is_code": bool(row.get("is_code")),
                "winner": winner,
                "model_a": row.get("model_a"),
                "model_b": row.get("model_b"),
                "timestamp": str(ts),
            }
            matched_rows.append(rec)
            audits["flagged" if at_least(any_tier, "probable") else "broad_only"].add({
                **rec, "prompt_excerpt": excerpt(last_prompt), "response_a_excerpt": excerpt(resp_a),
            })
            # Keep a bounded pool of candidate rows for the readable shortlist.
            if at_least(any_tier, "probable"):
                item = {**rec, "prompt_excerpt": excerpt(last_prompt),
                        "response_a_excerpt": excerpt(resp_a), "response_b_excerpt": excerpt(resp_b),
                        "_jitter": rng.random()}
                if len(shortlist) < args.shortlist_cap * 3:
                    shortlist.append(item)
                else:
                    j = rng.randrange(c["rows_any_probable"] + 1)
                    if j < args.shortlist_cap * 3:
                        shortlist[j] = item
        else:
            audits["unflagged"].add({
                "id": row.get("id"), "tier": "none", "language": lang,
                "is_code": bool(row.get("is_code")), "winner": winner,
                "prompt_excerpt": excerpt(last_prompt), "response_a_excerpt": excerpt(resp_a),
            })

        if n % 5000 == 0:
            el = time.time() - t0
            print(f"[scan] {n:,} rows | {el:.0f}s | {n / el:.0f} rows/s | "
                  f"strict-any={c['rows_any_strict']:,} probable-any={c['rows_any_probable']:,}", flush=True)
        if args.max_rows and n >= args.max_rows:
            break

    elapsed = time.time() - t0
    print(f"[scan] done {n:,} rows in {elapsed:.1f}s", flush=True)

    # Rank shortlist: strongest matches first, with a deterministic random tail.
    shortlist.sort(key=lambda r: (-r["score"], -r["_jitter"]))
    kept = shortlist[:args.shortlist_cap]
    for r in kept:
        r.pop("_jitter", None)

    os.makedirs(args.output_dir, exist_ok=True)
    summary = {
        "dataset": DATASET,
        "split": SPLIT,
        "rows_scanned": n,
        "counts": dict(c),
        "unique_prompts_by_tier": {k: len(v) for k, v in unique_prompts.items()},
        "categories_prompt_strict_or_probable": dict(cat_prompt.most_common()),
        "categories_response_strict_or_probable": dict(cat_resp.most_common()),
        "top_strong_terms_prompt": dict(strong_terms_prompt.most_common(40)),
        "top_strong_terms_response": dict(strong_terms_resp.most_common(40)),
        "by_language": {k: dict(v) for k, v in sorted(by_language.items(), key=lambda kv: -kv[1]["rows"])},
        "by_month": {k: dict(v) for k, v in sorted(by_month.items())},
        "by_winner": {k: dict(v) for k, v in by_winner.items()},
        "by_is_code": {k: dict(v) for k, v in by_code.items()},
        "methodology": {
            "tiers": {
                "strict": "prompt: >=1 unambiguous (strong) political term; response: a topic-specific strong term plus corroboration (a second strong term/hit, or a short answer), OR the prompt itself is strict",
                "probable": "prompt: >=2 weak terms from >=2 topic groups; response: one uncorroborated strong term, or >=2 weak terms from >=2 groups, OR the prompt itself is probable",
                "broad": "a single weak/ambiguous term; high-recall upper bound, many false positives",
            },
            "prompt_unit": "all user turns of conversation_a (current turn counted separately)",
            "response_unit": "the two judged assistant turns (last of conversation_a, last of conversation_b)",
            "response_direct_vs_union": "responses_direct_* = evidence in the answer text; responses_contextual_* = answers to political prompts; responses_union_* = either",
            "language_coverage": "English lexicon + partial strong-term lexicons for 15+ other languages",
            "known_false_positives": [
                "leader election / majority vote in code or ML contexts is downgraded",
                "company president, birthday party, CSS border, tax software, history homework",
                "assistant boilerplate that mentions a government or law in passing",
            ],
        },
    }
    with open(os.path.join(args.output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, sort_keys=True)

    fields = ["id", "evaluation_session_id", "tier", "prompt_tier", "response_tier", "score",
              "categories", "prompt_strong_terms", "response_strong_terms", "language",
              "is_code", "winner", "model_a", "model_b", "timestamp", "prompt_excerpt",
              "response_a_excerpt", "response_b_excerpt"]
    with open(os.path.join(args.output_dir, "shortlist.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in kept:
            w.writerow(r)

    id_fields = ["id", "evaluation_session_id", "tier", "prompt_tier", "response_tier",
                 "score", "categories", "language", "is_code", "winner", "timestamp"]
    with gzip.open(os.path.join(args.output_dir, "matched_ids.csv.gz"), "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=id_fields, extrasaction="ignore")
        w.writeheader()
        for r in matched_rows:
            w.writerow(r)

    audit_fields = ["audit_group", "id", "tier", "language", "is_code", "winner",
                    "prompt_excerpt", "response_a_excerpt"]
    with open(os.path.join(args.output_dir, "audit_sample.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=audit_fields, extrasaction="ignore")
        w.writeheader()
        for group, res in audits.items():
            for r in res.items:
                w.writerow({"audit_group": group, **r})

    meta = {
        "script_version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": DATASET,
        "dataset_revision": "6322995ab34d7c2693e3f47dd13fa5caa0789a74 (main, 2025-08-01)",
        "split": SPLIT,
        "max_rows": args.max_rows,
        "shortlist_cap": args.shortlist_cap,
        "rows_scanned": n,
        "elapsed_seconds": round(elapsed, 2),
        "python": sys.version,
        "term_count": len(TERM_MAP),
    }
    with open(os.path.join(args.output_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)

    print(f"[scan] wrote {len(kept):,} shortlist rows, {len(matched_rows):,} matched IDs, "
          f"{sum(len(r.items) for r in audits.values())} audit rows", flush=True)
    return summary


def self_test() -> None:
    cases = [
        ("Compare Tormenta20 with DnD5e", "none"),
        ("Who should I vote for in the 2024 election?", "strict"),
        ("Write a speech for a Democratic candidate about immigration reform", "strict"),
        ("Explain the Electoral College and gerrymandering", "strict"),
        ("Should the government raise the minimum wage?", "strict"),
        ("What do Trump and Biden disagree on about border policy?", "strict"),
        ("How does Raft leader election work?", "broad"),
        ("Implement a majority vote classifier in Python", "broad"),
        ("Who were the main candidates in the French élections?", "strict"),
        ("讨论美国选举和移民政策", "strict"),
        ("Write a birthday party invitation", "broad"),
        ("Explain the CSS border property and state management", "broad"),
    ]
    ok = True
    for text, expected in cases:
        got = classify(text)["tier"]
        flag = "OK " if got == expected else "BAD"
        ok &= got == expected
        print(f"  {flag} expected={expected:<8} got={got:<8} {text[:70]}")
    # Response side: an incidental single mention in a long answer is downgraded.
    long_answer = ("Here is a short story about a family trip to Disneyland. " * 40) + \
        "They visited the park and, on the way home, read a notice from the local government."
    resp_cases = [
        (long_answer, "probable"),
        ("Trump and Biden disagreed on immigration and tariffs in the 2024 election.", "strict"),
        ("Compose a birthday party invitation for my sister.", "broad"),
    ]
    for text, expected in resp_cases:
        got = classify(text, corroborate=True)["tier"]
        flag = "OK " if got == expected else "BAD"
        ok &= got == expected
        print(f"  {flag} expected={expected:<8} got={got:<8} [response] {text[:60]}")
    print(f"[self-test] {len(PATTERNS)} regex patterns, {len(TERM_MAP)} terms, "
          f"{'PASS' if ok else 'SOME MISMATCHES'}")
    sys.exit(0 if ok else 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-dir", default="arena/results")
    p.add_argument("--max-rows", type=int, default=0, help="0 = scan the whole split")
    p.add_argument("--shortlist-cap", type=int, default=1500)
    p.add_argument("--self-test", action="store_true", help="validate the lexicon, no download needed")
    args = p.parse_args()
    if args.self_test:
        self_test()
    scan(args)
    # huggingface_hub / fsspec leave background download threads alive when a
    # streaming IterableDataset is only partially consumed; CPython's finalizer
    # then aborts with "PyGILState_Release: no thread-state for this thread".
    # All outputs are written and closed by now, so bypass that finalization.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
