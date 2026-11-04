#!/usr/bin/env python3
"""Join the provisional shortlist to visible full transcripts from the gated source.

Writes a separate CSV; never overwrites the metadata-only shortlist. The source
must be an authorized local or hf:// Parquet file with full_conversation_a/b.
"""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = 'hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet'
DEFAULT_SHORTLIST = ROOT / 'data/political_shortlist_provisional.csv'
DEFAULT_OUTPUT = ROOT / 'data/full/political_shortlist_with_text.csv'
COLUMNS = ['comparison_id', 'turn', 'model_a', 'model_b', 'full_conversation_a', 'full_conversation_b']
EXTRA = ['source_max_turn', 'text_status', 'text_warnings', 'user_turns_a_json', 'user_turns_b_json', 'assistant_turns_a_json', 'assistant_turns_b_json']


def visible_messages(value, role):
    """Preserve visible text verbatim, excluding system, tool and reasoning fields."""
    result = []
    for message in value or []:
        if not isinstance(message, dict) or message.get('role') != role:
            continue
        content = message.get('content')
        if isinstance(content, str):
            result.append(content)
        elif isinstance(content, list):
            parts = [block if isinstance(block, str) else block.get('text', block.get('content', ''))
                     for block in content if isinstance(block, (str, dict))]
            result.append('\n'.join(p for p in parts if isinstance(p, str)))
    return result


def enrich(shortlist, source_rows):
    """Join on comparison_id, choosing the highest source turn irrespective of order."""
    ids = {r['comparison_id'] for r in shortlist}
    if len(ids) != len(shortlist) or '' in ids:
        raise ValueError('Shortlist comparison_id values must be nonempty and unique')
    selected, duplicates = {}, set()
    for row in source_rows:
        cid = row.get('comparison_id')
        if cid not in ids or row.get('turn') is None:
            continue
        turn = int(row['turn'])
        old = selected.get(cid)
        if old is None or turn > int(old['turn']):
            selected[cid] = row
            duplicates.discard(cid)
        elif turn == int(old['turn']):
            duplicates.add(cid)
    result = []
    for metadata in shortlist:
        cid = metadata['comparison_id']
        row = selected.get(cid)
        out = dict(metadata)
        if row is None:
            out.update(source_max_turn='', text_status='missing_source', text_warnings='ID not found in source')
            out.update({k: '[]' for k in EXTRA if k.endswith('_json')})
        else:
            a_users = visible_messages(row.get('full_conversation_a'), 'user')
            b_users = visible_messages(row.get('full_conversation_b'), 'user')
            a_answers = visible_messages(row.get('full_conversation_a'), 'assistant')
            b_answers = visible_messages(row.get('full_conversation_b'), 'assistant')
            warnings = []
            # Source turns are zero-based; metadata captures the final turn including post-vote turns.
            try:
                expected = int(metadata['final_turn']) + 1
                if int(row['turn']) != int(metadata['final_turn']):
                    warnings.append('source final turn differs from shortlist')
                if any(len(v) < expected or any(not x for x in v) for v in (a_users, b_users, a_answers, b_answers)):
                    warnings.append('missing or empty visible messages')
            except (KeyError, ValueError, TypeError):
                warnings.append('shortlist final turn unavailable')
            if a_users != b_users:
                warnings.append('model A and B user prompts differ')
            if cid in duplicates:
                warnings.append('multiple source rows at highest turn; first retained')
            if any(metadata.get(f'model_{side}') and row.get(f'model_{side}') and metadata[f'model_{side}'] != row[f'model_{side}'] for side in ('a', 'b')):
                warnings.append('source model names differ from shortlist')
            out.update(source_max_turn=row['turn'], text_status='review' if warnings else 'complete', text_warnings='; '.join(warnings))
            for key, value in [('user_turns_a_json', a_users), ('user_turns_b_json', b_users), ('assistant_turns_a_json', a_answers), ('assistant_turns_b_json', b_answers)]:
                out[key] = json.dumps(value, ensure_ascii=False)
        result.append(out)
    return result


def source_rows(path, batch_size):
    import fsspec
    import pyarrow.parquet as pq
    with fsspec.open(path, 'rb') as f:
        parquet = pq.ParquetFile(f)
        missing = set(COLUMNS) - set(parquet.schema_arrow.names)
        if missing:
            raise ValueError(f'Source missing columns: {sorted(missing)}')
        for batch in parquet.iter_batches(batch_size=batch_size, columns=COLUMNS):
            yield from batch.to_pylist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default=DEFAULT_SOURCE, help='Authorized local Parquet path or hf:// URI')
    parser.add_argument('--shortlist', type=Path, default=DEFAULT_SHORTLIST)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--batch-size', type=int, default=1024)
    args = parser.parse_args()
    if args.output.resolve() == args.shortlist.resolve():
        parser.error('Output must not overwrite the provisional shortlist')
    with args.shortlist.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        shortlist = list(reader)
    if not fields or 'comparison_id' not in fields or set(fields) & set(EXTRA):
        parser.error('Invalid shortlist columns')
    rows = enrich(shortlist, source_rows(args.input, args.batch_size))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields + EXTRA)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows)} rows to {args.output}; ' + ', '.join(f"{status}: {sum(r['text_status'] == status for r in rows)}" for status in ('complete', 'review', 'missing_source')))


if __name__ == '__main__':
    main()
