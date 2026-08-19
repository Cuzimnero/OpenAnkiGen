import unittest
from pathlib import Path
from unittest.mock import patch

import genanki

from src.handler.anki_handler import anki_handler


class TestAnkiHandler(unittest.TestCase):

    def setUp(self):
        """Set up a new anki_handler for each test."""
        self.deck_name = "Test Deck"
        self.handler = anki_handler(self.deck_name)

    def test_initialization(self):
        """Test that the anki_handler is initialized correctly."""
        self.assertEqual(self.handler.deckname, self.deck_name)
        self.assertIsInstance(self.handler.model, genanki.Model)
        self.assertIsInstance(self.handler.deck, genanki.Deck)
        self.assertEqual(self.handler.deck.name, self.deck_name)

    def test_clean_field(self):
        """Test the clean_field method."""
        self.assertEqual(self.handler.clean_field("test string"), "test string")
        self.assertEqual(self.handler.clean_field(["item1", "item2"]), "item1, item2")
        self.assertEqual(self.handler.clean_field(123), "123")

    def test_normalize_mathjax_uses_anki_delimiters(self):
        value = self.handler.normalize_mathjax(r"Inline $x^2$ and display $$\frac{1}{2}$$")

        self.assertEqual(value, r"Inline \(x^2\) and display \[\frac{1}{2}\]")

    def test_add_fields_normalizes_mathjax_before_export(self):
        self.handler.add_fields([{
            "front": r"What is $x^2$?",
            "back": r"It is $$x \cdot x$$.",
            "topic": "Math",
        }])

        note = self.handler.deck.notes[0]
        self.assertIn(r"\(x^2\)", note.fields[0])
        self.assertIn(r"\[x \cdot x\]", note.fields[1])

    def test_add_fields(self):
        """Test the add_fields method."""
        cards = [
            {"front": "Question 1", "back": "Answer 1", "topic": "Topic 1"},
            {"front": "Question 2", "back": "Answer 2", "topic": "Topic 2"},
            {"front": "Question 3", "back": "Answer 3", "topic": "Topic 3"},
        ]
        self.handler.add_fields(cards)
        self.assertEqual(len(self.handler.deck.notes), 3)

        # Test with missing fields
        cards_with_missing_fields = [
            {"front": "Question 4", "topic": "Topic 4"},
            {"back": "Answer 5", "topic": "Topic 5"},
            {"front": "Question 6", "back": "Answer 6"},
        ]
        self.handler.add_fields(cards_with_missing_fields)
        self.assertEqual(len(self.handler.deck.notes), 6)

        # Check that the fields were correctly added
        note = self.handler.deck.notes[3]
        self.assertIn("Question 4", note.fields[0])
        self.assertIn("AI Error", note.fields[1])
        self.assertIn("Topic 4", note.fields[2])

    @patch('genanki.Package')
    @patch('os.startfile')
    def test_safe_tofile(self, mock_startfile, mock_package):
        """Test the safe_tofile method."""
        path = Path("test_output")
        self.handler.safe_tofile(path)

        expected_path = path / f"{self.deck_name.strip()}.apkg"

        # Check if genanki.Package was called correctly
        mock_package.assert_called_once_with(self.handler.deck)
        mock_package.return_value.write_to_file.assert_called_once_with(expected_path)

        # Check if os.startfile was called correctly
        mock_startfile.assert_called_once_with(expected_path)


if __name__ == '__main__':
    unittest.main()
