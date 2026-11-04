import importlib.util
from pathlib import Path
import unittest
import csv
import json
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('explorer', Path(__file__).resolve().parents[1] / 'server.py')
explorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(explorer)


class ExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = explorer.load_data()

    def test_data_and_french_missing_text(self):
        self.assertGreater(len(self.data['arena']), 0)
        self.assertGreater(len(self.data['french']), 0)
        self.assertNotIn('prompt', self.data['french'][0])
        self.assertNotIn('assistant_a', self.data['french'][0])

    def test_search_all_terms_case_insensitive_and_responses(self):
        row = self.data['arena'][0]
        terms = row['assistant_a'].split()[:2]
        result = explorer.query(self.data, 'arena', ' '.join(terms).upper(), limit=100)
        self.assertGreater(result['total'], 0)
        self.assertEqual(explorer.query(self.data, 'arena', row['id'] + ' nonexistentkeywordzzzz')['total'], 0)
        self.assertEqual(explorer.query(self.data, 'arena', row['id'])['rows'][0]['id'], row['id'])

    def test_exact_arena_shortlist_and_french_text_join(self):
        with explorer.ARENA_SHORTLIST.open(encoding='utf-8', newline='') as f:
            ids = {r['id'] for r in csv.DictReader(f)}
        self.assertEqual(ids, {r['id'] for r in self.data['arena']})
        french_id = self.data['french'][0]['id']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'enriched.csv'
            record = {'comparison_id': french_id, 'text_status': 'complete', 'text_warnings': '',
                      'user_turns_a_json': json.dumps(['question uniquexyz']), 'user_turns_b_json': json.dumps(['question uniquexyz']),
                      'assistant_turns_a_json': json.dumps(['réponse A']), 'assistant_turns_b_json': json.dumps(['réponse B'])}
            with path.open('w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=record.keys())
                writer.writeheader()
                writer.writerow(record)
            with patch.object(explorer, 'FRENCH_FULL', path):
                data = explorer.load_data()
            self.assertEqual(explorer.query(data, 'french', 'uniquexyz')['rows'][0]['id'], french_id)
            self.assertEqual(data['french'][0]['assistant_b'], 'réponse B')
            self.assertEqual(len(data['french']), len(self.data['french']))

    def test_short_answer_wins_subset(self):
        wins = self.data['short_wins']
        arena_ids = [r['id'] for r in self.data['arena']]
        self.assertGreater(len(wins), 0)
        # Strict subset of the shortlist, in shortlist order.
        positions = [arena_ids.index(r['id']) for r in wins]
        self.assertEqual(positions, sorted(positions))
        for r in wins:
            self.assertIn(r['winner'], ('model_a', 'model_b'))
            len_a, len_b = len(r['assistant_a']), len(r['assistant_b'])
            win, lose = (len_a, len_b) if r['winner'] == 'model_a' else (len_b, len_a)
            self.assertLess(win, lose)
            self.assertEqual((r['winner_chars'], r['loser_chars']), (win, lose))
        # Every excluded decisive row really has the longer (or equal) answer winning.
        win_ids = {r['id'] for r in wins}
        for r in self.data['arena']:
            if r['id'] not in win_ids and r['winner'] in ('model_a', 'model_b') and r['assistant_a'].strip() and r['assistant_b'].strip():
                len_a, len_b = len(r['assistant_a']), len(r['assistant_b'])
                self.assertGreaterEqual(len_a if r['winner'] == 'model_a' else len_b, len_b if r['winner'] == 'model_a' else len_a)
        result = explorer.query(self.data, 'short_wins', '', limit=5)
        self.assertEqual(result['total'], len(wins))
        self.assertIn('winner_chars', result['rows'][0])

    def test_short_answer_win_rule(self):
        rule = explorer.short_answer_win
        self.assertIsNotNone(rule({'winner': 'model_a', 'assistant_a': 'short', 'assistant_b': 'much longer'}))
        self.assertIsNotNone(rule({'winner': 'model_b', 'assistant_a': 'much longer', 'assistant_b': 'short'}))
        self.assertIsNone(rule({'winner': 'model_a', 'assistant_a': 'much longer', 'assistant_b': 'short'}))
        self.assertIsNone(rule({'winner': 'model_a', 'assistant_a': 'same', 'assistant_b': 'four'}))
        self.assertIsNone(rule({'winner': 'tie', 'assistant_a': 'a', 'assistant_b': 'bbb'}))
        self.assertIsNone(rule({'winner': 'both_bad', 'assistant_a': 'a', 'assistant_b': 'bbb'}))
        self.assertIsNone(rule({'winner': 'model_a', 'assistant_a': '', 'assistant_b': 'bbb'}))

    def test_short_answer_wins_csv_matches_explorer(self):
        path = explorer.ARENA_SHORTLIST.parent / 'short_answer_wins.csv'
        with path.open(encoding='utf-8', newline='') as f:
            ids = [r['id'] for r in csv.DictReader(f)]
        self.assertEqual(ids, [r['id'] for r in self.data['short_wins']])

    def test_french_search_and_pagination(self):
        row = self.data['french'][0]
        self.assertEqual(explorer.query(self.data, 'french', row['id'])['rows'][0]['id'], row['id'])
        self.assertEqual(len(explorer.query(self.data, 'french', '', offset=2, limit=3)['rows']), 3)
        with self.assertRaises(ValueError):
            explorer.query(self.data, 'unknown', '')


if __name__ == '__main__':
    unittest.main()
