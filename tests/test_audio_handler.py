import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.handler.audio_handler import AudiobookGenerator


class TestAudiobookGenerator(unittest.TestCase):

    def test_clean_for_speech_removes_markup(self):
        cleaned = AudiobookGenerator.clean_for_speech("<b>Value</b> is $x$ **important**")
        self.assertEqual(cleaned, "Value is important")

    def test_clean_for_speech_removes_all_supported_formula_styles(self):
        text = (r"Keep this. $x^2$ \(y = 3\) \[\frac{1}{2}\] "
                r"[latex]\sum_i x_i[/latex] End.")
        cleaned = AudiobookGenerator.clean_for_speech(text)

        self.assertEqual(cleaned, "Keep this. End.")
        self.assertNotIn("frac", cleaned)
        self.assertNotIn("sum", cleaned)

    def test_cards_to_script_uses_selected_language(self):
        cards = [{"front": "Was ist DNS?", "back": "Ein Namensdienst", "topic": "Netzwerk"}]
        script = AudiobookGenerator.cards_to_script(cards, "Routing", "German")

        self.assertIn("Unser nächstes Thema ist Netzwerk.", script)
        self.assertIn("Was ist DNS?", script)
        self.assertIn("Die Antwort lautet: Ein Namensdienst", script)
        self.assertNotIn("Frage:", script)

    def test_formula_only_cards_are_not_narrated(self):
        cards = [
            {"front": "$x^2$", "back": "$x \\cdot x$", "topic": "Math"},
            {"front": "Was ist DNS?", "back": "Ein Namensdienst", "topic": "Netzwerk"},
        ]
        script = AudiobookGenerator.cards_to_script(cards, "Routing", "German")

        self.assertIn("1 Lernkarten", script)
        self.assertNotIn("cdot", script)

    def test_safe_filename_replaces_windows_characters(self):
        self.assertEqual(AudiobookGenerator._safe_filename('Deck: A/B?'), "Deck_ A_B_")

    def test_thinking_pause_is_exactly_ten_seconds_and_contains_ticks(self):
        frames = AudiobookGenerator.thinking_pause_frames(1000, channels=1, sample_width=2, duration=10)

        self.assertEqual(len(frames), 1000 * 2 * 10)
        self.assertTrue(any(frames))

    def test_answer_follows_question_as_a_separate_segment(self):
        cards = [{"front": "Question?", "back": "Answer", "topic": "Test"}]

        segments = AudiobookGenerator.narration_segments(cards, "Demo", "English")

        self.assertEqual([kind for kind, _text in segments], ["intro", "topic", "question", "answer"])
        self.assertEqual(segments[-1][1], "The answer is: Answer")

    @patch("src.handler.audio_handler.PiperVoice.load")
    def test_create_writes_a_wav_file(self, load_mock):
        with tempfile.TemporaryDirectory() as directory:
            generator = AudiobookGenerator(Path(directory) / "models")
            voice = MagicMock()

            def synthesize(_text, wav_file, **_kwargs):
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(22050)
                wav_file.writeframes(b"\x00\x00" * 100)

            voice.synthesize_wav.side_effect = synthesize
            load_mock.return_value = voice
            with patch.object(generator, "ensure_voice", return_value=(Path("voice.onnx"), Path("voice.onnx.json"))):
                result = generator.create(
                    [{"front": "Question?", "back": "Answer", "topic": "Test"}],
                    Path(directory),
                    "Demo",
                    "English",
                )

            self.assertTrue(result.exists())
            self.assertEqual(result.name, "Demo_audiobook.wav")
            self.assertEqual(voice.synthesize_wav.call_count, 4)
            with wave.open(str(result), "rb") as wav_file:
                self.assertEqual(wav_file.getnframes(), 4 * 100 + 10 * 22050)

    @patch("src.handler.audio_handler.download_voice")
    def test_missing_voice_is_downloaded_to_separate_language_folder(self, download_mock):
        with tempfile.TemporaryDirectory() as directory:
            generator = AudiobookGenerator(Path(directory))

            def create_voice_files(voice_name, target):
                (target / f"{voice_name}.onnx").write_bytes(b"model")
                (target / f"{voice_name}.onnx.json").write_text("{}", encoding="utf-8")

            download_mock.side_effect = create_voice_files
            model_path, config_path = generator.ensure_voice("German")

            self.assertEqual(model_path.parent.name, "German")
            self.assertEqual(model_path.name, "de_DE-thorsten-medium.onnx")
            self.assertTrue(config_path.exists())


if __name__ == "__main__":
    unittest.main()
