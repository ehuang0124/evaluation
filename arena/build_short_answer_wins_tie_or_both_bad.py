#!/usr/bin/env python3
"""Build the "short answer wins, tie or both bad" subset of the Arena ranked shortlist.

Starts from exactly the 1,500 IDs in ``arena/results/shortlist.csv``, joins the
full final answers from ``arena/explorer/data/conversations.jsonl.gz`` and keeps
a vote when any of these holds (``inclusion_reason`` column):

* ``short_win``      – the human picked the strictly shorter answer;
* ``tie``            – the vote was a tie (any lengths);
* ``both_bad``       – the vote was both_bad (any lengths);
* ``near_equal_win`` – the longer answer won, but the lengths differ by less
  than 5% of the longer answer (``|a - b| / max(a, b) < 0.05``).

Length = character count of each side's final (judged) answer. Decisive votes
where the longer answer won by 5% or more, and rows with an empty answer or no
full text, are dropped.

The selection rule lives in ``arena/explorer/server.py`` (``short_answer_win``)
so the explorer's dataset and this CSV can never diverge.

Output: ``arena/results/short_answer_wins_tie_or_both_bad.csv`` — the shortlist.csv
columns (metadata + existing 420-char excerpts, no full text) plus length columns.
"""
import collections
import argparse
import csv
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
LENGTH_FIELDS = ['inclusion_reason', 'answer_a_chars', 'answer_b_chars', 'length_diff_pct', 'within_5pct',
                 'winner_chars', 'loser_chars', 'length_ratio']


def load_explorer():
    spec = importlib.util.spec_from_file_location('explorer_server', HERE / 'explorer/server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=HERE / 'results/short_answer_wins_tie_or_both_bad.csv')
    args = parser.parse_args()

    explorer = load_explorer()
    data = explorer.load_data()
    wins = {r['id']: r for r in data['short_wins']}

    csv.field_size_limit(100 * 1024 * 1024)
    with explorer.ARENA_SHORTLIST.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        base_fields = list(reader.fieldnames)
        shortlist = list(reader)

    out_rows = []
    for item in shortlist:  # keep shortlist (score-ranked) order
        win = wins.get(item['id'])
        if win is not None:
            values = {k: ('' if win[k] is None else win[k]) for k in LENGTH_FIELDS}
            out_rows.append(dict(item, **values))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=base_fields + LENGTH_FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    reasons = collections.Counter(r['inclusion_reason'] for r in out_rows)
    print(f'shortlist rows: {len(shortlist):,}; kept: {len(out_rows):,} '
          f'(short_win {reasons["short_win"]:,}, tie {reasons["tie"]:,}, both_bad {reasons["both_bad"]:,}, '
          f'near_equal_win {reasons["near_equal_win"]:,})')
    print(f'wrote {args.output}')


if __name__ == '__main__':
    main()
