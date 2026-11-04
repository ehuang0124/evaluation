import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import screen_political as sp


def msg(role, content, reasoning=None):
    d = {"role": role, "content": content}
    if reasoning is not None:
        d["reasoning_content"] = reasoning
    return d


def turn(response_id, comparison_id, turn, prompt, answer_a, answer_b, categories=None, languages=None, choice=None, full_a=None, full_b=None):
    return {
        "response_id": response_id,
        "comparison_id": comparison_id,
        "timestamp": "2026-01-01T00:00:00",
        "turn": turn,
        "model_a": "model-a",
        "model_b": "model-b",
        "response_a": [msg("user", prompt), msg("assistant", answer_a, reasoning="hidden election reasoning")],
        "response_b": [msg("user", prompt), msg("assistant", answer_b)],
        "choice": choice,
        "metadata": {"categories": categories or [], "languages": languages or ["fr"], "mode": "random"},
        "full_conversation_a": full_a if full_a is not None else [msg("system", "system secret"), msg("user", prompt), msg("assistant", answer_a, reasoning="hidden election reasoning")],
        "full_conversation_b": full_b if full_b is not None else [msg("user", prompt), msg("assistant", answer_b)],
    }


class RulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = sp.PoliticalRules()

    def test_french_accents_and_elections(self):
        ev = self.rules.screen("Quelle est la position des candidats à l'élection présidentielle ?")
        self.assertIn("elections_voting", ev)

    def test_generic_vote_without_civic_context_not_matched(self):
        ev = self.rules.screen("Vote for your favorite singer in this talent show.")
        self.assertNotIn("elections_voting", ev)

    def test_generic_policy_without_public_context_not_matched(self):
        ev = self.rules.screen("My insurance policy expires tomorrow.")
        self.assertNotIn("public_policy_governance", ev)

    def test_immigration(self):
        ev = self.rules.screen("Peux-tu expliquer la politique migratoire et le droit d'asile ?")
        self.assertIn("immigration_asylum", ev)
        self.assertIn("public_policy_governance", ev)

    def test_political_figure(self):
        ev = self.rules.screen("Compare Emmanuel Macron et Marine Le Pen.")
        self.assertIn("political_figures_parties", ev)

    def test_reasoning_and_system_not_screened(self):
        row = turn("r1", "c1", 0, "Bonjour", "Bonjour !", "Salut !", categories=["Other"])
        row["response_a"][1]["reasoning_content"] = "election présidentielle immigration Macron"
        row["full_conversation_a"].insert(0, msg("system", "election présidentielle immigration Macron"))
        screened = sp.screen_turn(row, self.rules)
        self.assertFalse(screened["political"])
        self.assertEqual(screened["conversation_topics"], [])

    def test_metadata_politics_shortlists(self):
        row = turn("r2", "c2", 0, "Bonjour", "Bonjour !", "Salut !", categories=["Politics & Government"])
        screened = sp.screen_turn(row, self.rules)
        self.assertTrue(screened["political"])
        self.assertTrue(screened["metadata_political"])
        self.assertIn("source_topic", screened["shortlist_reason"])

    def test_adjacent_metadata_alone_does_not_shortlist(self):
        row = turn("r3", "c3", 0, "Bonjour", "Bonjour !", "Salut !", categories=["Environment"])
        screened = sp.screen_turn(row, self.rules)
        self.assertFalse(screened["political"])
        self.assertTrue(screened["adjacent_metadata"])


class PipelineTest(unittest.TestCase):
    def _fixture(self, path):
        rows = [
            turn(
                "r1", "c-pol", 0, "Parle-moi de l'élection présidentielle.",
                "Voici un résumé.", "Un autre résumé.", categories=["Education"],
                choice="a_better",
                full_a=[msg("system", "system secret"), msg("user", "Parle-moi de l'élection présidentielle."), msg("assistant", "Voici un résumé.")],
                full_b=[msg("user", "Parle-moi de l'élection présidentielle."), msg("assistant", "Un autre résumé.")],
            ),
            turn(
                "r2", "c-pol", 1, "Et le programme ?", "Le programme A.",
                "Le programme B.", categories=["Education"],
                full_a=[msg("system", "system secret"), msg("user", "Parle-moi de l'élection présidentielle."), msg("assistant", "Voici un résumé."), msg("user", "Et le programme ?"), msg("assistant", "Le programme A.")],
                full_b=[msg("user", "Parle-moi de l'élection présidentielle."), msg("assistant", "Un autre résumé."), msg("user", "Et le programme ?"), msg("assistant", "Le programme B.")],
            ),
            turn("r3", "c-meta", 0, "Bonjour", "Bonjour !", "Salut !", categories=["Politics & Government"]),
            turn(
                "r7", "c-meta", 1, "Et ensuite ?", "Encore bonjour.", "Encore salut.",
                categories=["Politics & Government"],
                full_a=[msg("system", "system secret"), msg("user", "Bonjour"), msg("assistant", "Bonjour !"), msg("user", "Et ensuite ?"), msg("assistant", "Encore bonjour.")],
                full_b=[msg("user", "Bonjour"), msg("assistant", "Salut !"), msg("user", "Et ensuite ?"), msg("assistant", "Encore salut.")],
            ),
            turn("r4", "c-resp", 0, "Raconte une histoire.", "Cette histoire parle d'Emmanuel Macron.", "Une histoire neutre."),
            turn("r5", "c-adj", 0, "Comment recycler ?", "Recyclez le papier.", "Triez les déchets.", categories=["Environment"]),
            turn("r6", "c-neu", 0, "Quelle est la capitale du Japon ?", "Tokyo.", "Tokyo."),
            turn("r6", "c-neu", 0, "duplicate", "duplicate", "duplicate"),
        ]
        pd.DataFrame(rows).to_parquet(path, index=False)

    def _args(self, input_path, output, direct=False, french_only=False):
        return argparse.Namespace(
            input=str(input_path), output_dir=str(output), revision=None,
            rules=str(sp.RULES_PATH), batch_size=2, limit_rows=None,
            french_only=french_only, direct_pandas=direct,
        )

    def test_end_to_end_streaming_and_direct_pandas(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "fixture.parquet"
            self._fixture(src)
            for name, direct in [("stream", False), ("direct", True)]:
                out = root / name
                summary = sp.run(self._args(src, out, direct=direct))
                self.assertEqual(summary["counts"]["source_rows_read"], 8)
                self.assertEqual(summary["counts"]["duplicate_response_id_rows"], 1)
                self.assertEqual(summary["counts"]["shortlisted_conversations"], 3)
                conv = pd.read_parquet(out / "political_conversations.parquet")
                self.assertEqual(set(conv.comparison_id), {"c-pol", "c-meta", "c-resp"})
                self.assertTrue(conv.comparison_id.is_unique)
                prompts = pd.read_parquet(out / "political_prompts.parquet")
                self.assertEqual(len(prompts), 5)  # all turns in shortlisted conversations
                responses = pd.read_parquet(out / "political_responses.parquet")
                self.assertEqual(len(responses), 10)
                self.assertEqual(summary["counts"]["prompt_turns_with_political_text"], 1)
                self.assertEqual(summary["counts"]["assistant_responses_with_political_text"], 1)
                pol = conv.set_index("comparison_id").loc["c-pol"]
                self.assertEqual(pol["n_source_turns"], 2)
                self.assertEqual(pol["max_turn"], 1)
                self.assertEqual(pol["model_a"], "model-a")
                self.assertEqual(pol["model_b"], "model-b")
                self.assertTrue(pol["conversation_export_complete"])
                self.assertEqual(pol["conversation_export_status"], "complete")
                transcript_a = json.dumps(pol["full_conversation_a"].tolist(), ensure_ascii=False)
                transcript_b = json.dumps(pol["full_conversation_b"].tolist(), ensure_ascii=False)
                self.assertIn("Et le programme ?", transcript_a)
                self.assertIn("Le programme A.", transcript_a)
                self.assertIn("Et le programme ?", transcript_b)
                self.assertIn("Le programme B.", transcript_b)
                self.assertNotIn("system secret", transcript_a)
                self.assertNotIn("hidden election reasoning", transcript_a)
                self.assertEqual(summary["counts"]["conversations_with_complete_transcripts"], 3)
                self.assertEqual(
                    summary["full_conversation_dataset"]["transcript_status_counts"]["complete"], 3
                )
                topic_counts = pd.read_csv(out / "topic_counts.csv").set_index("topic")
                self.assertEqual(topic_counts.loc["politics_government_metadata", "conversations"], 1)
                self.assertTrue((out / "summary.json").exists())
                self.assertTrue((out / "manifest.json").exists())

    def test_requires_full_conversation_columns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "annotation_only.parquet"
            rows = [turn("r1", "c1", 0, "élection présidentielle", "Réponse A", "Réponse B")]
            pd.DataFrame(rows).drop(columns=["full_conversation_a", "full_conversation_b"]).to_parquet(src, index=False)
            out = root / "out"
            with self.assertRaisesRegex(ValueError, "Full-text export requires"):
                sp.run(self._args(src, out))
            self.assertFalse(out.exists())

    def test_french_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "fixture.parquet"
            rows = [
                turn("r1", "c-fr", 0, "élection présidentielle", "A", "B", languages=["fr"]),
                turn("r2", "c-en", 0, "presidential election", "A", "B", languages=["en"]),
            ]
            pd.DataFrame(rows).to_parquet(src, index=False)
            out = root / "out"
            summary = sp.run(self._args(src, out, french_only=True))
            self.assertEqual(summary["counts"]["shortlisted_conversations"], 1)
            conv = pd.read_parquet(out / "political_conversations.parquet")
            self.assertEqual(set(conv.comparison_id), {"c-fr"})


if __name__ == "__main__":
    unittest.main()
