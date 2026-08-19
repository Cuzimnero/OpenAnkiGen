import ctypes
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
import ollama
from dotenv import load_dotenv
from tkinterdnd2 import TkinterDnD

from ai.anki_gen import AnkiGen
from ai.model_type import ModelType
from handler.anki_handler import anki_handler
from handler.audio_handler import AudiobookGenerator
from ui.details_window import details_window
from ui.exclude_window import ExcludeWindow
from ui.main_ui import main_ui
from ui.verify import verification

# Set a unique AppUserModelID to ensure the app has its own taskbar icon on Windows
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenAnkiGen")
except Exception:
    pass

# Determine base path for resources (handles both standard script and PyInstaller .exe)
if getattr(sys, 'frozen', False):
    temp_path = Path(sys._MEIPASS)
    base_path = Path(sys.executable).parent
else:
    temp_path = Path(__file__).parent.parent.parent
    base_path = Path(__file__).parent.parent.parent

# Add the project root to sys.path to ensure internal modules can be imported correctly
if str(temp_path) not in sys.path:
    sys.path.insert(0, str(temp_path))


# Application interface
class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        """Initializes the main application, window settings, and authentication state."""
        self.base_path = base_path
        self.temp_path = temp_path
        self.ollama_available = True
        self.pages_to_delete_sorted = []
        self.main_ui = None
        log_filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".log"
        logging_path = base_path / "logs"
        logging_path.mkdir(exist_ok=True, parents=True)
        log_file = logging_path / log_filename
        logging.basicConfig(
            filename=str(log_file),
            filemode='a',
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO,
            force=True
        )

        self.verification = verification(self)
        self.localMod = None
        self.deleted_pages = []

        if getattr(sys, 'frozen', False):
            self.icon_path = temp_path / "ui" / "logo_v2.ico"
        else:
            self.icon_path = temp_path / "src" / "ui" / "logo_v2.ico"

        super().__init__()
        self.iconbitmap(str(self.icon_path))

        self.title("OpenAnkiGen")
        self.geometry("620x620")
        ctk.set_appearance_mode("dark")
        self.key_file = base_path / ".env"
        self.selected_file = None
        load_dotenv(self.key_file)
        self.api_keys = {
            ModelType.DEEPSEEK: os.getenv("DEEPSEEK_API_KEY", ""),
            ModelType.OPENAI: os.getenv("OPENAI_API_KEY", ""),
            ModelType.ANTHROPIC: os.getenv("ANTHROPIC_API_KEY", ""),
        }
        self.key_valid = any(self.api_keys.values())
        self.chooseMod_state = "normal"
        self.default_provider = self._default_provider()
        self.generator = AnkiGen(ModelType.DEEPSEEK, "deepseek-chat", self)

        self.logger = logging.getLogger(__name__)
        self.logger.info("Logger started")

        self.start()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start(self):
        self.main_ui = main_ui(self)
        self.main_ui.show()
        self.update_idletasks()

    def _default_provider(self):
        if self.api_keys[ModelType.DEEPSEEK]:
            return "DeepSeek"
        if self.api_keys[ModelType.OPENAI]:
            return "OpenAI"
        if self.api_keys[ModelType.ANTHROPIC]:
            return "Claude"
        return "Local Model (Ollama)"

    def select_model(self, choice):
        """ Initializes chosen Model. If Ollama is selected, it fetches installed local models and displays a selection menu."""
        values = {
            "DeepSeek": (ModelType.DEEPSEEK, "deepseek-chat"),
            "OpenAI": (ModelType.OPENAI, "gpt-5.6-luna"),
            "Claude": (ModelType.ANTHROPIC, "claude-haiku-4-5-20251001"),
            "Local Model (Ollama)": (ModelType.LOCALE, ""),
        }
        provider = values.get(choice)
        if not provider:
            return
        model, default_model = provider
        if model is not ModelType.LOCALE and not self.api_keys.get(model):
            messagebox.showwarning("API key required", f"Add a {choice} API key first.")
            self.verification.addKey(choice)
            return
        if model == ModelType.LOCALE:
            try:
                response = ollama.list()
                installed_models = [m.model for m in response.models]
                if self.main_ui and self.main_ui.main_frame.winfo_exists():
                    self.main_ui.select_model(installed_models)
                if installed_models:
                    default_model = installed_models[0]
                else:
                    self.main_ui.file_btn.configure(state="disabled")
                    if hasattr(self.main_ui, "localMod"):
                        self.main_ui.localMod.configure(values=["You have no models installed!"])
                        self.main_ui.localMod.set("You have no models installed!")
                    default_model = "no models installed"
                    messagebox.showwarning("Warning", "You have no models installed!")

                self.generator = AnkiGen(model, default_model, self)
                self.ollama_available = True
            except Exception as e:
                messagebox.showerror("Error", str(e))
                if self.main_ui and hasattr(self.main_ui, "file_btn"):
                    try:
                        if self.main_ui.file_btn.winfo_exists():
                            self.main_ui.file_btn.configure(state="disabled")
                    except Exception:
                        pass
                self.ollama_available = False
        else:
            if self.main_ui and hasattr(self.main_ui, "file_btn"):
                if self.main_ui.file_btn.winfo_exists():
                    self.main_ui.file_btn.configure(state="normal")
                    self.main_ui.destroy_local_mod()
            self.generator = AnkiGen(model, default_model, self)

    def set_model(self, model: str):
        self.generator.set_model(model)

    def create_details_window(self):
        self.details_window = details_window(self)
        self.details_window.show()
        self.deleted_pages.clear()

    def create_exclude_window(self):
        self.exclude_window = ExcludeWindow(self)
        self.exclude_window.show()

    def handle_pdf_error(self):
        self.details_window.withdraw()
        self.details_window.destroy()
        messagebox.showerror("Error", f"PDF Error Try again !")
        self.main_ui.file_btn.configure(state="normal")

    def start_generation(self):
        """updates detail page for generation of cards, initialize generation"""

        provider_names = {
            ModelType.DEEPSEEK: "DeepSeek",
            ModelType.OPENAI: "OpenAI",
            ModelType.ANTHROPIC: "Claude",
            ModelType.LOCALE: f"Ollama using {self.generator.model}",
        }
        modeltype = provider_names[self.generator.model_type]
        self.logger.info(f"generating starts with {self.generator.threshold_value} Threshold: {modeltype}")
        if self.generator.threshold_value > 0.8:
            self.logger.warning(
                f" High threshold {self.generator.threshold_value}: More cards, but higher chance of duplicates.")
        elif self.generator.threshold_value < 0.7:
            self.logger.warning(
                f" Low threshold {self.generator.threshold_value}: Strict filtering. Many cards might be skipped.")

        self.details_window.start_btn.configure(state="disabled", text="Generating cards...")
        self.details_window.change_button_states("disabled")
        self.create_audiobook = self.details_window.audiobook_enabled.get()
        self.audiobook_language = self.details_window.language_switch.get()
        self.audiobook_path = None

        thread = threading.Thread(target=self.run_gen)
        self.details_window.start_progress_bar()
        self.generator.load_embedding_model()
        self.generator.window_active = True
        thread.start()

    def run_gen(self):
        """generates cards"""
        if self.generator.model == "no models installed" and self.generator.model_type is ModelType.LOCALE:
            messagebox.showerror("Error", "Please install a model first (e.g., 'ollama pull llama3')")
            return
        for page in self.pages_to_delete_sorted:
            try:
                self.generator.handler.delete_page(page - 1)
            except Exception as e:
                self.after(0, self.handle_pdf_error)
                return
        deck_name = self.details_window.context_text.get("1.0", "end-1c").strip()
        cards = self.generator.createCards(self.details_window.language_switch.get(), self.details_window.info_label)
        if not cards:
            messagebox.showerror("Error", "No cards generated.")
            if self.details_window:
                self.details_window.after(10, self.details_window.destroy)
            self.main_ui.change_button_states("normal")
            return

        handler = anki_handler(deck_name)
        handler.add_fields(cards)
        output_path = base_path / "output"
        output_path.mkdir(exist_ok=True)

        if self.create_audiobook:
            self.after(0, lambda: self.details_window.info_label.configure(text="Creating local audiobook …"))
            try:
                tts_model_root = (self.temp_path / "ai" / "tts_models" if getattr(sys, "frozen", False)
                                  else self.temp_path / "src" / "ai" / "tts_models")
                self.audiobook_path = AudiobookGenerator(tts_model_root).create(
                    cards,
                    output_path,
                    deck_name,
                    self.audiobook_language,
                )
                self.logger.info("Audiobook created: %s", self.audiobook_path)
            except Exception as error:
                self.logger.error("Audiobook generation failed: %s", error)
                self.after(0, lambda: messagebox.showwarning(
                    "Audiobook unavailable",
                    "The Anki deck was created, but the local audiobook could not be generated. "
                    "See the log for details.",
                ))
        handler.safe_tofile(output_path)
        self.after(0, self.finish)

    def finish(self):
        """finishes generating cards"""
        if self.details_window.winfo_exists():
            self.details_window.destroy()
        self.main_ui.change_button_states("normal")
        message = "Generation successful!"
        if self.audiobook_path:
            message += f"\n\nAudiobook:\n{self.audiobook_path}"
        messagebox.showinfo("AnkiGen", message)

    def on_closing(self):
        self.logger.info("Application closed")
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
