#!/usr/bin/env python3
"""Build the "short answer wins" subset of the Arena ranked shortlist.

Starts from exactly the 1,500 IDs in ``arena/results/shortlist.csv``, joins the
full final answers from ``arena/explorer/data/conversations.jsonl.gz`` and keeps
only the votes where the human picked the strictly shorter answer:

* decisive votes only (``winner`` is ``model_a`` or ``model_b``; ``tie`` and
  ``both_bad`` have no winner);
* length = character count of each side's final (judged) answer;
* rows with identical lengths, an empty answer, or no full text are dropped.

The selection rule lives in ``arena/explorer/server.py`` (``short_answer_win``)
so the explorer's "Short answer wins" dataset and this CSV can never diverge.

Output: ``arena/results/short_answer_wins.csv`` — the shortlist.csv columns
(metadata + existing 420-char excerpts, no full text) plus length columns.
"""
import argparse
import csv
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
LENGTH_FIELDS = ['answer_a_chars', 'answer_b_chars', 'winner_chars', 'loser_chars', 'chars_saved', 'length_ratio']


def load_explorer():
    spec = importlib.util.spec_from_file_location('explorer_server', HERE / 'explorer/server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=HERE / 'results/short_answer_wins.csv')
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
            out_rows.append(dict(item, **{k: win[k] for k in LENGTH_FIELDS}))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=base_fields + LENGTH_FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    decisive = sum(r['winner'] in ('model_a', 'model_b') for r in data['arena'])
    print(f'shortlist rows: {len(shortlist):,}; decisive votes: {decisive:,}; '
          f'short answer wins: {len(out_rows):,} ({len(out_rows) / decisive:.1%} of decisive)')
    print(f'wrote {args.output}')


if __name__ == '__main__':
    main()
