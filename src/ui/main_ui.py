import logging
import os
import sys
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk
from PIL import Image

if TYPE_CHECKING:
    from ui.app import App


class main_ui:

    def __init__(self, app_instance: App):
        self.localMod = None
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)

        self.main_frame = ctk.CTkFrame(self.app_instance, fg_color="#111827", corner_radius=0)
        self.content_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")

        if getattr(sys, 'frozen', False):
            logo_path = self.app_instance.temp_path / "ui" / "assets" / "logo_v2.png"
        else:
            logo_path = self.app_instance.temp_path / "src" / "ui" / "assets" / "logo_v2.png"
        logo_source = Image.open(logo_path)
        self.logo_image = ctk.CTkImage(light_image=logo_source, dark_image=logo_source, size=(72, 72))
        self.logo_label = ctk.CTkLabel(self.content_frame, text="", image=self.logo_image)

        self.title_label = ctk.CTkLabel(
            self.content_frame,
            text="OpenAnkiGen",
            font=ctk.CTkFont(family="Segoe UI", size=38, weight="bold"),
            text_color="#60a5fa"
        )
        self.subtitle_label = ctk.CTkLabel(
            self.content_frame,
            text="Turn your PDF notes into focused Anki cards.",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color="#9ca3af"
        )

        self.modelFrame = ctk.CTkFrame(
            self.content_frame,
            fg_color="#1f2937",
            border_color="#374151",
            border_width=1,
            corner_radius=16,
            width=380,
            height=160
        )
        self.Modelabel = ctk.CTkLabel(
            self.modelFrame,
            text="AI model",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#f3f4f6"
        )
        self.chooseMod = ctk.CTkOptionMenu(self.modelFrame,
                                           values=["DeepSeek", "OpenAI", "Claude", "Local Model (Ollama)"],
                                           command=self.app_instance.select_model,
                                           state=self.app_instance.chooseMod_state,
                                           height=38,
                                           corner_radius=9,
                                           fg_color="#2563eb",
                                           button_color="#1d4ed8",
                                           button_hover_color="#1e40af")
        if getattr(sys, 'frozen', False):
            file_icon_path = self.app_instance.temp_path / "ui" / "assets" / "file_select_icon.png"
        else:
            file_icon_path = self.app_instance.temp_path / "src" / "ui" / "assets" / "file_select_icon.png"
        try:
            file_icon = ctk.CTkImage(light_image=Image.open(file_icon_path),
                                     dark_image=Image.open(file_icon_path),
                                     size=(40, 40))
        except FileNotFoundError:
            messagebox.showerror("File Not Found", "file_icon_path doesn't exist")

        self.file_btn = ctk.CTkButton(
            self.content_frame,
            text="  Select a PDF",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            height=58,
            width=380,
            corner_radius=12,
            command=lambda: self.select_file(True),
            image=file_icon,
            compound="left",
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        self.hint_label = ctk.CTkLabel(
            self.content_frame,
            text="PDF files only  •  You can review pages before generation",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#6b7280"
        )
        self.addKey_button = ctk.CTkButton(
            self.content_frame,
            text=self._key_button_text(),
            fg_color="transparent",
            hover_color="#1f2937",
            command=self.app_instance.verification.addKey,
            text_color="#9ca3af",
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )

    def _key_button_text(self):
        if self.app_instance.key_valid:
            return "Manage API keys"
        return "Add an API key"

    def show(self):
        self.main_frame.pack(expand=True, fill="both")
        self.content_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.logo_label.pack(pady=(0, 5))
        self.title_label.pack(pady=(0, 2))
        self.subtitle_label.pack(pady=(0, 24))
        self.modelFrame.pack_propagate(False)
        self.modelFrame.pack(pady=(0, 18))
        self.Modelabel.pack(fill="x", padx=22, pady=(20, 10))
        self.chooseMod.pack(fill="x", padx=22, pady=(0, 20))
        self.file_btn.pack()
        self.hint_label.pack(pady=(8, 18))
        self.addKey_button.pack()

        self.chooseMod.set(self.app_instance.default_provider)
        self.app_instance.after(10, lambda: self.app_instance.select_model(self.app_instance.default_provider))

    def set_choose_mod(self, mod: str):
        if mod in self.chooseMod.cget("values"):
            self.chooseMod.set(mod)
        else:
            raise ValueError("Can not modify choose mod: mod dont exist")

    def select_file(self, kind: bool):
        """ Starts file selection dialog. In context to two different cases 1. called  by the main page and 2. called by the details window"""
        self.change_button_states("disabled")
        if not kind:
            path = filedialog.askopenfilename(filetypes=[("PDF-files", "*.pdf")],
                                              parent=self.app_instance)
            self.app_instance.details_window.reload_excludes_textbox()
            self.app_instance.details_window.clear_deleted_pages()
        else:
            path = filedialog.askopenfilename(filetypes=[("PDF-files", "*.pdf")], parent=self.main_frame)

        if path:
            self.app_instance.generator.set_pdf_handler(Path(path))
            self.app_instance.selected_file = path
            if (kind == True):
                self.app_instance.create_details_window()
                return
            file_name = os.path.basename(self.app_instance.selected_file)[0:20]
            if len(os.path.basename(self.app_instance.selected_file)) > 20:
                file_name = file_name + "..."
            self.app_instance.details_window.file_button.configure(text=file_name)
            self.app_instance.generator.set_pdf_handler(self.app_instance.selected_file)
        else:
            self.change_buttons_case_1()

    def select_model(self, installed_models):
        """ Initializes chosen Model. If Ollama is selected, it fetches installed local models and displays a selection menu."""
        self.destroy_local_mod()
        self.localMod = ctk.CTkOptionMenu(self.modelFrame, values=installed_models,
                                          command=self.app_instance.set_model, )
        self.localMod.pack(pady=20)

    def destroy_local_mod(self):
        if hasattr(self, "localMod"):
            try:
                self.localMod.destroy()
                self.localMod = None
            except Exception:
                pass

    def destroy(self):
        self.main_frame.destroy()

    def change_button_states(self, state: str):
        self.file_btn.configure(state=state)
        self.chooseMod.configure(state=state)
        self.addKey_button.configure(state=state)
        if hasattr(self, "localMod") and self.localMod:
            self.localMod.configure(state=state)

    def change_buttons_case_1(self):
        if not self.app_instance.key_valid or self.app_instance.ollama_available:
            self.change_button_states("normal")
        else:
            self.file_btn.configure(state="normal")
            self.addKey_button.configure(state="normal")
            if hasattr(self, "localMod") and self.localMod:
                self.localMod.configure(state="normal")
