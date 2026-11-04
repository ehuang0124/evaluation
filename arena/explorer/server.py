#!/usr/bin/env python3
"""Local conversation explorer for the Arena and Compar:IA shortlists."""
import argparse
import csv
import gzip
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
FRENCH = ROOT.parent.parent / 'french-arena/data/political_shortlist_provisional.csv'
FRENCH_FULL = ROOT.parent.parent / 'french-arena/data/full/political_shortlist_with_text.csv'
ARENA_SHORTLIST = ROOT.parent / 'results/shortlist.csv'


def load_data():
    csv.field_size_limit(100 * 1024 * 1024)
    with ARENA_SHORTLIST.open(encoding='utf-8', newline='') as f:
        shortlist = list(csv.DictReader(f))
    with gzip.open(ROOT / 'data/conversations.jsonl.gz', 'rt', encoding='utf-8') as f:
        full = {r['id']: r for r in (json.loads(line) for line in f if line.strip())}
    arena = []
    for item in shortlist:
        r = full.get(item['id'])
        if r is None:
            r = dict(item, prompt='', user_turns=[], assistant_a='', assistant_b='', text_status='missing_full_text')
        arena.append(r)
    with FRENCH.open(encoding='utf-8', newline='') as f:
        french = list(csv.DictReader(f))
    enriched = {}
    if FRENCH_FULL.exists():
        with FRENCH_FULL.open(encoding='utf-8', newline='') as f:
            enriched = {r['comparison_id']: r for r in csv.DictReader(f)}
    for row in arena:
        row['_search'] = '\n'.join(str(row.get(k) or '') for k in
                                   ('id', 'prompt', 'assistant_a', 'assistant_b', 'model_a', 'model_b')) .casefold()
        row['_search'] += '\n' + '\n'.join(row.get('user_turns') or []).casefold()
    for row in french:
        row['id'] = row['comparison_id']
        extra = enriched.get(row['id'])
        if extra:
            row['text_status'] = extra.get('text_status', 'review')
            row['text_warnings'] = extra.get('text_warnings', '')
            for name in ('user_turns_a', 'user_turns_b', 'assistant_turns_a', 'assistant_turns_b'):
                value = json.loads(extra.get(name + '_json') or '[]')
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise ValueError(f'Invalid {name} for {row["id"]}')
                row[name] = value
            row['user_turns'] = row['user_turns_a']
            row['prompt'] = row['user_turns_a'][-1] if row['user_turns_a'] else ''
            row['assistant_a'] = '\n\n'.join(row['assistant_turns_a'])
            row['assistant_b'] = '\n\n'.join(row['assistant_turns_b'])
        else:
            row['text_status'] = 'missing_source'
        row['_search'] = '\n'.join(str(v or '') for v in row.values()).casefold()
    return {'arena': arena, 'french': french}


def public(row):
    return {k: v for k, v in row.items() if not k.startswith('_')}


def query(data, dataset, text, offset=0, limit=20):
    if dataset not in data:
        raise ValueError('Unknown dataset')
    # All whitespace-separated keywords must occur; case-insensitive.
    terms = text.casefold().split()
    rows = [r for r in data[dataset] if all(term in r['_search'] for term in terms)]
    offset = max(0, offset)
    limit = max(1, min(100, limit))
    previews = []
    for r in rows[offset:offset + limit]:
        previews.append({k: r.get(k) for k in ('id', 'prompt', 'model_a', 'model_b', 'winner', 'timestamp', 'source_primary_topic', 'text_status')})
        if previews[-1]['prompt']:
            previews[-1]['prompt'] = previews[-1]['prompt'][:400]
    return {'total': len(rows), 'offset': offset, 'limit': limit, 'rows': previews}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def json_response(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if not url.path.startswith('/api/'):
            return super().do_GET()
        params = parse_qs(url.query)
        get = lambda key, default='': params.get(key, [default])[0]
        dataset = get('dataset', 'arena')
        try:
            if dataset not in self.server.data:
                raise ValueError('Unknown dataset')
            if url.path == '/api/query':
                self.json_response(query(self.server.data, dataset, get('q'), int(get('offset', '0')), int(get('limit', '20'))))
            elif url.path == '/api/row':
                row = self.server.by_id[dataset].get(get('id'))
                if row is None:
                    self.json_response({'error': 'Conversation not found'}, 404)
                else:
                    self.json_response(public(row))
            else:
                self.json_response({'error': 'Unknown endpoint'}, 404)
        except ValueError as exc:
            self.json_response({'error': str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.data = load_data()
    server.by_id = {name: {r['id']: r for r in rows} for name, rows in server.data.items()}
    print(f'Explorer listening on {args.host}:{args.port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
