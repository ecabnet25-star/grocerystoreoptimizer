import unittest
from unittest.mock import patch

from grocery_optimizer.assistant import build_meal_assistant_response


class TestAssistant(unittest.TestCase):
    def test_fallback_response_without_ollama(self):
        def _getenv(key: str, default: str | None = None) -> str | None:
            return "fallback" if key == "GROCERY_ASSISTANT_MODE" else default

        with patch("os.getenv", side_effect=_getenv):
            result = build_meal_assistant_response(
                user_message="Meal ideas?",
                plan_items=[{"name": "Brown Rice"}, {"name": "Black Beans"}, {"name": "Broccoli"}],
                likes=["rice"],
                dislikes=[],
                health_goals=["muscle"],
            )

        self.assertIn("response", result)
        self.assertEqual(result["response_source"], "rule_fallback")
        self.assertTrue(len(result["suggestions"]) > 0)
        self.assertIn("Plan tip", result["response"])
        self.assertIn("plan_tip", result)

    def test_fallback_detects_meal_prep_intent(self):
        def _getenv(key: str, default: str | None = None) -> str | None:
            return "fallback" if key == "GROCERY_ASSISTANT_MODE" else default

        with patch("os.getenv", side_effect=_getenv):
            result = build_meal_assistant_response(
                user_message="Make a meal prep schedule",
                plan_items=[{"name": "Oats"}, {"name": "Yogurt"}, {"name": "Berries"}],
                likes=[],
                dislikes=[],
                health_goals=[],
            )

        self.assertIn("Batch cook", result["plan_tip"])

    def test_hybrid_uses_ollama_when_available(self):
        def _getenv(key: str, default: str | None = None) -> str | None:
            if key == "GROCERY_ASSISTANT_MODE":
                return "hybrid"
            if key == "GROCERY_ASSISTANT_OLLAMA_MODEL":
                return "llama3.2:3b"
            return default

        with patch("os.getenv", side_effect=_getenv):
            with patch("grocery_optimizer.assistant._ollama_generate_response", return_value=("LLM response", "llama3.2:3b")):
                result = build_meal_assistant_response(
                    user_message="Dinner ideas",
                    plan_items=[{"name": "Chicken Breast"}, {"name": "Brown Rice"}],
                    likes=["chicken"],
                    dislikes=["yogurt"],
                    health_goals=["energy"],
                )

        self.assertEqual(result["response"], "LLM response")
        self.assertEqual(result["response_source"], "ollama")
        self.assertEqual(result["model"], "llama3.2:3b")


if __name__ == "__main__":
    unittest.main()
