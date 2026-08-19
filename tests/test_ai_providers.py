import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai.anki_gen import AnkiGen
from ai.model_type import CallType, ModelType
from ui.verify import verification


class TestAIProviders(unittest.TestCase):

    def test_cloud_providers_have_separate_key_names(self):
        self.assertEqual(
            {name: config[1] for name, config in verification.PROVIDERS.items()},
            {
                "DeepSeek": "DEEPSEEK_API_KEY",
                "OpenAI": "OPENAI_API_KEY",
                "Claude": "ANTHROPIC_API_KEY",
            },
        )
        self.assertEqual(len({ModelType.DEEPSEEK, ModelType.OPENAI, ModelType.ANTHROPIC}), 3)

    def test_json_parser_accepts_plain_and_fenced_json(self):
        generator = AnkiGen.__new__(AnkiGen)

        self.assertEqual(generator._parse_json_text('{"cards": []}'), {"cards": []})
        self.assertEqual(generator._parse_json_text('```json\n{"cards": []}\n```'), {"cards": []})

    def test_generation_response_returns_cards_without_ui(self):
        generator = AnkiGen.__new__(AnkiGen)
        generator.progress = 0
        generator.generation_units = 2
        generator.app_instance = SimpleNamespace()
        cards = [{"front": "What?", "back": "Answer", "topic": "Test"}]

        result = generator._cards_from_response({"cards": cards}, CallType.CARD_GENERATION)

        self.assertEqual(result, cards)
        self.assertEqual(generator.progress, 1)


if __name__ == "__main__":
    unittest.main()
