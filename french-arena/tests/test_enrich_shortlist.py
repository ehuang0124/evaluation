import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('enrich_shortlist', ROOT / 'analysis/enrich_shortlist.py')
enrich = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enrich)


def message(role, text):
    return {'role': role, 'content': text, 'reasoning_content': 'secret'}


class EnrichmentTest(unittest.TestCase):
    def test_join_highest_turn_and_statuses(self):
        metadata = [{'comparison_id': '1', 'final_turn': '1', 'model_a': 'A', 'model_b': 'B'},
                    {'comparison_id': 'missing', 'final_turn': '0'}]
        def row(turn, a, b):
            return {'comparison_id': '1', 'turn': turn, 'model_a': 'A', 'model_b': 'B', 'full_conversation_a': a, 'full_conversation_b': b}
        first = [message('user', 'Bonjour'), message('assistant', 'A0')]
        a = first + [message('user', 'Question,\nlongue'), message('assistant', 'A1\nfull'), message('system', 'private')]
        b = [message('user', 'Bonjour'), message('assistant', 'B0'), message('user', 'Question,\nlongue'), message('assistant', 'B1')]
        result = enrich.enrich(metadata, [row(1, a, b), row(0, first, first)])
        self.assertEqual(result[0]['text_status'], 'complete')
        self.assertEqual(json.loads(result[0]['assistant_turns_a_json']), ['A0', 'A1\nfull'])
        self.assertEqual(json.loads(result[0]['user_turns_a_json']), ['Bonjour', 'Question,\nlongue'])
        self.assertNotIn('secret', str(result))
        self.assertEqual(result[1]['text_status'], 'missing_source')
        b[-2] = message('user', 'different')
        result = enrich.enrich(metadata[:1], [row(1, a, b), row(1, a, b)])
        self.assertEqual(result[0]['text_status'], 'review')
        self.assertIn('prompts differ', result[0]['text_warnings'])
        self.assertIn('multiple source rows', result[0]['text_warnings'])

    def test_actual_parquet_to_csv(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shortlist, source, output = root/'ids.csv', root/'source.parquet', root/'full.csv'
            shortlist.write_text('comparison_id,final_turn,model_a,model_b\n1,0,A,B\n', encoding='utf-8')
            rows = [{'comparison_id': '1', 'turn': 0, 'model_a': 'A', 'model_b': 'B',
                     'full_conversation_a': [message('user', 'Une question'), message('assistant', 'Réponse A')],
                     'full_conversation_b': [message('user', 'Une question'), message('assistant', 'Réponse B')]}]
            pq.write_table(pa.Table.from_pylist(rows), source)
            subprocess.run([sys.executable, str(ROOT/'analysis/enrich_shortlist.py'), '--input', str(source), '--shortlist', str(shortlist), '--output', str(output)], check=True)
            with output.open(encoding='utf-8', newline='') as f:
                r = next(csv.DictReader(f))
            self.assertEqual(r['text_status'], 'complete')
            self.assertEqual(json.loads(r['assistant_turns_b_json']), ['Réponse B'])


if __name__ == '__main__':
    unittest.main()
