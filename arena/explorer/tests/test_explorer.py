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

    @staticmethod
    def expected_reason(r):
        if r['winner'] not in ('model_a', 'model_b', 'tie'):
            return None
        len_a, len_b = len(r['assistant_a']), len(r['assistant_b'])
        if r['winner'] == 'tie':
            return 'tie'
        win, lose = (len_a, len_b) if r['winner'] == 'model_a' else (len_b, len_a)
        if win < lose:
            return 'short_win'
        return 'near_equal_win' if (win - lose) / win < 0.05 else None

    def test_short_answer_wins_or_tie_subset(self):
        wins = self.data['short_wins']
        self.assertGreater(len(wins), 0)
        expected = [(r['id'], self.expected_reason(r)) for r in self.data['arena'] if self.expected_reason(r)]
        # Exactly the qualifying shortlist rows, in shortlist order, with the right reason.
        self.assertEqual([(r['id'], r['inclusion_reason']) for r in wins], expected)
        reasons = {r['inclusion_reason'] for r in wins}
        self.assertEqual(reasons, {'short_win', 'tie', 'near_equal_win'})
        for r in wins:
            self.assertNotEqual(r['winner'], 'both_bad')
            if r['inclusion_reason'] == 'near_equal_win':
                self.assertTrue(r['within_5pct'])
                self.assertGreaterEqual(r['winner_chars'], r['loser_chars'])
        result = explorer.query(self.data, 'short_wins', '', limit=5)
        self.assertEqual(result['total'], len(wins))
        self.assertIn('inclusion_reason', result['rows'][0])
        for reason in reasons:
            self.assertEqual(explorer.query(self.data, 'short_wins', 'reason:' + reason)['total'],
                             sum(r['inclusion_reason'] == reason for r in wins))

    def test_short_answer_win_rule(self):
        rule = lambda w, a, b: (explorer.short_answer_win({'winner': w, 'assistant_a': a, 'assistant_b': b}) or {}).get('inclusion_reason')
        self.assertEqual(rule('model_a', 'short', 'much longer'), 'short_win')
        self.assertEqual(rule('model_b', 'much longer', 'short'), 'short_win')
        self.assertIsNone(rule('model_a', 'much longer', 'short'))
        self.assertEqual(rule('tie', 'a', 'b' * 50), 'tie')
        self.assertIsNone(rule('both_bad', 'a', 'bbb'))
        self.assertIsNone(rule('model_a', '', 'bbb'))
        self.assertEqual(rule('model_a', 'x' * 100, 'x' * 100), 'near_equal_win')   # 0% diff
        self.assertEqual(rule('model_a', 'x' * 100, 'x' * 96), 'near_equal_win')    # 4% diff
        self.assertIsNone(rule('model_a', 'x' * 100, 'x' * 95))                     # 5% diff: not < 5%

    def test_short_answer_wins_or_tie_csv_matches_explorer(self):
        path = explorer.ARENA_SHORTLIST.parent / 'short_answer_wins_or_tie.csv'
        with path.open(encoding='utf-8', newline='') as f:
            rows = [(r['id'], r['inclusion_reason']) for r in csv.DictReader(f)]
        self.assertEqual(rows, [(r['id'], r['inclusion_reason']) for r in self.data['short_wins']])

    def test_french_search_and_pagination(self):
        row = self.data['french'][0]
        self.assertEqual(explorer.query(self.data, 'french', row['id'])['rows'][0]['id'], row['id'])
        self.assertEqual(len(explorer.query(self.data, 'french', '', offset=2, limit=3)['rows']), 3)
        with self.assertRaises(ValueError):
            explorer.query(self.data, 'unknown', '')


if __name__ == '__main__':
    unittest.main()
