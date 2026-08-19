import html
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox

import genanki


class anki_handler:

    def __init__(self, deck_name: str):
        """initialization of cards style"""
        self.deckname = deck_name
        style = """
            .card {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 20px;
                text-align: center;
                color: #2c3e50;
                background-color: #f9f9f9;
                padding: 20px;
            }

            .topic-box {
                display: inline-block;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                background-color: #3498db;
                color: white;
                padding: 4px 12px;
                border-radius: 15px;
                margin-bottom: 20px;
                font-weight: bold;
            }

            .question {
                font-weight: 600;
                line-height: 1.4;
                margin-top: 10px;
            }

            .answer {
                color: #2980b9;
                margin-top: 20px;
                font-weight: 400;
            }

            hr#answer {
                border: 0;
                height: 1px;
                background-image: linear-gradient(to right, rgba(0, 0, 0, 0), rgba(52, 152, 219, 0.75), rgba(0, 0, 0, 0));
                margin-top: 30px;
            }
            """
        id_m = random.randrange(1 << 30, 1 << 31)
        id_d = random.randrange(1 << 30, 1 << 31)
        self.model = genanki.Model(
            id_m, "default", fields=[{'name': 'Question'},
                                     {'name': 'Answer'}, {'name': 'Topic'},
                                     ],
            templates=[
                {
                    'name': 'Card 1',
                    'qfmt': """
                    <div class="topic-box">{{Topic}}</div>
                    <div class="question">{{Question}}</div>
                    """,
                    'afmt': """
                    {{FrontSide}}
                    <hr id="answer">
                    <div class="answer">{{Answer}}</div>
                    """,
                },
            ],
            css=style
        )
        self.deck = genanki.Deck(id_d, deck_name)

    def clean_field(self, data):
        if isinstance(data, list):
            return ", ".join(map(str, data))
        return str(data)

    def normalize_mathjax(self, data):
        """Convert common dollar-delimited model output to Anki MathJax markup."""
        text = self.clean_field(data)
        text = re.sub(r"\$\$(.+?)\$\$", r"\\[\1\\]", text, flags=re.DOTALL)
        text = re.sub(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", r"\\(\1\\)", text, flags=re.DOTALL)
        return text

    def add_fields(self, cards: list[dict]):
        """adding cards to deck"""
        for card in cards:
            front = card.get("front") if card.get("front") is not None else "AI Error"
            topic = card.get("topic") if card.get("topic") is not None else "AI Error"
            back = card.get("back") if card.get("back") is not None else "AI Error"
            node = genanki.Note(
                model=self.model,
                fields=[
                    html.escape(self.normalize_mathjax(front)),
                    html.escape(self.normalize_mathjax(back)),
                    html.escape(self.clean_field(topic))
                ]
            )
            self.deck.add_note(node)

    def safe_tofile(self, path: Path):
        genanki.Package(self.deck).write_to_file(path / f"{self.deckname.strip()}.apkg")
        try:
            open_path = path / f"{self.deckname.strip()}.apkg"
            self.open_file(open_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open deck in Anki: {e}")

    def open_file(self, path: Path):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":  # macOS
            subprocess.run(["open", str(path)])
        else:  # Linux
            subprocess.run(["xdg-open", str(path)])

    def fix_format(self, cards: list[dict]):
        return
