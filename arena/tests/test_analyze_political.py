import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze_political as ap


class EnglishPoliticalCoverageTests(unittest.TestCase):
    def assert_topic(self, prompt, topic):
        result = ap.classify(prompt)
        self.assertEqual(result["tier"], "strict", prompt)
        self.assertIn(topic, result["categories"], prompt)

    def test_election_and_voting(self):
        self.assert_topic("How do I register to vote in the midterm election?", "elections")

    def test_elected_public_figures_and_officials(self):
        self.assert_topic("What powers do elected city council members have?", "political_figures")
        self.assert_topic("Compare the governor and the state legislature", "public_policy")

    def test_civic_engagement_and_discourse(self):
        self.assert_topic("How can residents speak during a public hearing?", "civic_engagement")
        self.assert_topic("Explain the debate over political disinformation", "public_discourse")
        self.assert_topic("What is the role of a grassroots organizing campaign?", "civic_engagement")

    def test_contentious_public_interest_issues(self):
        self.assert_topic("Summarize arguments about reproductive rights", "public_discourse")
        self.assert_topic("What are the arguments for and against school choice?", "public_discourse")

    def test_nonpolitical_technical_vote_stays_downgraded(self):
        result = ap.classify("Implement a majority vote classifier in Python")
        self.assertEqual(result["tier"], "broad")

    def test_weak_civic_terms_need_context_for_probable(self):
        self.assertEqual(ap.classify("Write a petition for my fantasy guild")["tier"], "broad")


if __name__ == "__main__":
    unittest.main()
