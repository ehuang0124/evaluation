"""Sanity tests for the statistical helpers and the label logic.

Run: python -m unittest discover -s arena/interest_analysis/tests -v
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import analyze as az  # noqa: E402
import lexicons as lx  # noqa: E402


class HelperTests(unittest.TestCase):
    def test_wilson_bounds_inside_unit_interval(self):
        lo, hi = az.wilson(50, 100)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLessEqual(hi, 1.0)

    def test_wilson_handles_zero_n(self):
        lo, hi = az.wilson(0, 0)
        self.assertNotEqual(lo, lo)  # NaN

    def test_mcnemar_symmetric_and_bounded(self):
        self.assertEqual(az.mcnemar_exact(10, 10), 1.0)
        self.assertAlmostEqual(az.mcnemar_exact(0, 0), 1.0)
        self.assertLess(az.mcnemar_exact(0, 10), 0.01)
        self.assertGreater(az.mcnemar_exact(8, 19), 0.05)  # cutoff-statement test in the report

    def test_bradley_terry_orders_a_clear_winner(self):
        pairs = [("a", "b")] * 8 + [("a", "c")] * 6 + [("b", "c")] * 5
        bt = az.bradley_terry(pairs)
        self.assertGreater(bt["a"], bt["b"])
        self.assertGreater(bt["b"], bt["c"])


class LexiconTests(unittest.TestCase):
    def test_structures_detected_without_newlines(self):
        text = "## Title Here **bold** 1. first 2. second * a bullet"
        f = az.features(text)
        self.assertEqual(f["lead_heading"], 1)
        self.assertEqual(f["bold"], 1)
        self.assertEqual(f["numbered_list"], 1)
        self.assertEqual(f["bullet_list"], 1)

    def test_uncertainty_and_refusal_are_distinguished(self):
        self.assertEqual(az.features("I'm not sure, but estimates vary widely.")["uncertainty_admission"], 1)
        self.assertEqual(az.features("I cannot help with that request.")["refusal"], 1)

    def test_topic_labels_on_clear_cases(self):
        self.assertIn("elections_voting", az.labels("who won the 2024 presidential election?", az.TOPIC_RX))
        self.assertIn("geopolitics_conflict", az.labels("will NATO send troops to Ukraine?", az.TOPIC_RX))
        self.assertIn("immigration", az.labels("how do I apply for asylum at the border?", az.TOPIC_RX))

    def test_non_political_task_gets_no_topic(self):
        self.assertEqual(az.labels("fix this tsconfig.json paths alias", az.TOPIC_RX), [])

    def test_all_lexicon_patterns_compile(self):
        for name, pattern in {**lx.TOPICS, **lx.INTENTS, **lx.STRUCTURE, **lx.EPISTEMIC,
                              **lx.INTEREST_GROUPS, **lx.SENSITIVE}.items():
            az.rx(pattern), name


if __name__ == "__main__":
    unittest.main()
