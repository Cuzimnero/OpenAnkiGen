import html
import io
import math
import re
import struct
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig
from piper.download_voices import download_voice


class AudiobookGenerator:
    """Generate a WAV audiobook using project-local neural Piper voices."""

    VOICES = {
        "Default": "en_US-lessac-medium",
        "English": "en_US-lessac-medium",
        "German": "de_DE-thorsten-medium",
        "Spanish": "es_ES-davefx-medium",
    }
    NARRATION = {
        "English": {
            "intro": "Welcome to {deck}. This audiobook contains {count} study cards. Let's begin.",
            "topics": ("Our next topic is {topic}.", "Let's continue with {topic}.", "Now consider {topic}."),
            "pause": "Take a moment to think. The answer is: {answer}",
        },
        "German": {
            "intro": "Willkommen zu {deck}. Dieses Hörbuch enthält {count} Lernkarten. Beginnen wir.",
            "topics": ("Unser nächstes Thema ist {topic}.", "Weiter geht es mit {topic}.",
                       "Schauen wir uns nun {topic} an."),
            "pause": "Nimm dir einen Moment zum Nachdenken. Die Antwort lautet: {answer}",
        },
        "Spanish": {
            "intro": "Bienvenido a {deck}. Este audiolibro contiene {count} tarjetas de estudio. Empecemos.",
            "topics": ("El siguiente tema es {topic}.", "Continuamos con {topic}.", "Veamos ahora {topic}."),
            "pause": "Tómate un momento para pensar. La respuesta es: {answer}",
        },
    }

    @staticmethod
    def clean_for_speech(value):
        text = html.unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"\[latex\].*?\[/latex\]", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"\[\$\].*?\[/\$\]", " ", text, flags=re.DOTALL)
        text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)
        text = re.sub(r"(?<!\\)\$(?!\$).*?(?<!\\)\$", " ", text, flags=re.DOTALL)
        text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.DOTALL)
        text = re.sub(r"\\\(.*?\\\)", " ", text, flags=re.DOTALL)
        text = re.sub(r"[^.!?\n]*[=<>∑√∞^][^.!?\n]*[.!?]?", " ", text)
        text = re.sub(r"\\[A-Za-z]+(?:\{[^{}]*\})*", " ", text)
        text = re.sub(r"[`*_#]", "", text)
        text = re.sub(r"[{}$]", " ", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def narration_segments(cls, cards, deck_name, language="Default"):
        narration = cls.NARRATION.get(language, cls.NARRATION["English"])
        spoken_cards = []
        for card in cards:
            front = cls.clean_for_speech(card.get("front"))
            back = cls.clean_for_speech(card.get("back"))
            topic = cls.clean_for_speech(card.get("topic"))
            if front and back:
                spoken_cards.append((front, back, topic))

        deck = cls.clean_for_speech(deck_name) or "OpenAnkiGen"
        segments = [("intro", narration["intro"].format(deck=deck, count=len(spoken_cards)))]
        previous_topic = None
        topic_index = 0
        for front, back, topic in spoken_cards:
            if topic and topic != previous_topic:
                template = narration["topics"][topic_index % len(narration["topics"])]
                segments.append(("topic", template.format(topic=topic)))
                topic_index += 1
                previous_topic = topic
            segments.append(("question", front))
            answer_text = narration["pause"].replace(
                "Take a moment to think. ", ""
            ).replace(
                "Nimm dir einen Moment zum Nachdenken. ", ""
            ).replace(
                "Tómate un momento para pensar. ", ""
            ).format(answer=back)
            segments.append(("answer", answer_text))
        return segments

    @classmethod
    def cards_to_script(cls, cards, deck_name, language="Default"):
        return "\n\n".join(text for _kind, text in cls.narration_segments(cards, deck_name, language))

    @staticmethod
    def thinking_pause_frames(sample_rate, channels=1, sample_width=2, duration=10):
        """Create a ten-second silent pause with a soft clock tick every second."""
        if sample_width != 2:
            return b"\x00" * sample_rate * duration * channels * sample_width
        total_samples = sample_rate * duration
        tick_samples = max(1, int(sample_rate * 0.045))
        frames = bytearray(total_samples * channels * sample_width)
        for second in range(duration):
            start = second * sample_rate
            for offset in range(tick_samples):
                envelope = 1 - (offset / tick_samples)
                sample = int(3800 * envelope * math.sin(2 * math.pi * 1050 * offset / sample_rate))
                packed = struct.pack("<h", sample)
                for channel in range(channels):
                    position = ((start + offset) * channels + channel) * sample_width
                    frames[position:position + sample_width] = packed
        return bytes(frames)

    @staticmethod
    def _synthesize_segment(voice, text, synthesis_config):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as segment_file:
            voice.synthesize_wav(text, segment_file, syn_config=synthesis_config)
        buffer.seek(0)
        with wave.open(buffer, "rb") as segment_file:
            params = segment_file.getparams()
            frames = segment_file.readframes(segment_file.getnframes())
        return params, frames

    @staticmethod
    def _safe_filename(name):
        cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip().rstrip(".")
        return cleaned or "OpenAnkiGen"

    def __init__(self, model_root: Path):
        self.model_root = Path(model_root)

    def ensure_voice(self, language):
        language = language if language in self.VOICES else "Default"
        voice_name = self.VOICES[language]
        voice_directory = self.model_root / language
        model_path = voice_directory / f"{voice_name}.onnx"
        config_path = voice_directory / f"{voice_name}.onnx.json"
        if not model_path.exists() or not config_path.exists():
            voice_directory.mkdir(exist_ok=True, parents=True)
            download_voice(voice_name, voice_directory)
        if not model_path.exists() or not config_path.exists():
            raise RuntimeError(f"Piper voice download incomplete: {voice_name}")
        return model_path, config_path

    def create(self, cards, output_directory: Path, deck_name: str, language="Default"):
        if not cards:
            raise ValueError("Cannot create an audiobook without cards")
        output_directory.mkdir(exist_ok=True, parents=True)
        output_path = output_directory / f"{self._safe_filename(deck_name)}_audiobook.wav"
        segments = self.narration_segments(cards, deck_name, language)
        model_path, config_path = self.ensure_voice(language)
        voice = PiperVoice.load(str(model_path), config_path=str(config_path))
        synthesis_config = SynthesisConfig(length_scale=1.08, noise_scale=0.55, noise_w_scale=0.7)
        segment_iterator = iter(
            (kind, *self._synthesize_segment(voice, text, synthesis_config))
            for kind, text in segments if text
        )
        try:
            first_segment = next(segment_iterator)
        except StopIteration:
            raise RuntimeError("No speakable card content remained after formula filtering")

        with wave.open(str(output_path), "wb") as wav_file:
            first_params = first_segment[1]
            wav_file.setparams(first_params)
            pending_segment = first_segment
            while pending_segment is not None:
                kind, params, frames = pending_segment
                if (params.nchannels, params.sampwidth, params.framerate) != (
                        first_params.nchannels, first_params.sampwidth, first_params.framerate):
                    raise RuntimeError("Piper returned inconsistent audio formats")
                wav_file.writeframesraw(frames)
                if kind == "question":
                    wav_file.writeframesraw(self.thinking_pause_frames(
                        first_params.framerate,
                        first_params.nchannels,
                        first_params.sampwidth,
                        duration=10,
                    ))
                pending_segment = next(segment_iterator, None)

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("The local TTS engine did not create an audio file")
        return output_path
