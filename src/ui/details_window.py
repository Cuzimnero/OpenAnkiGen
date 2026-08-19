import logging
import math
import os
import sys
import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk
from PIL import Image

if TYPE_CHECKING:
    from ui.app import App


class details_window(ctk.CTkToplevel):
    CARD_STYLE = {"fg_color": "#1f2937", "border_color": "#374151", "border_width": 1, "corner_radius": 14}

    def __init__(self, app_instance: "App"):
        super().__init__(app_instance)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        self.title("Create Anki deck")
        self.geometry("500x840")
        self.resizable(False, False)
        self.configure(fg_color="#111827")
        self.attributes("-topmost", True)
        self.after(200, lambda: self.iconbitmap(str(self.app_instance.icon_path)))
        self.app_instance.generator.set_pdf_handler(self.app_instance.selected_file)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_label = ctk.CTkLabel(self.content_frame, text="Create your deck", anchor="w",
                                         font=ctk.CTkFont("Segoe UI", 26, "bold"), text_color="#f3f4f6")
        self.header_info = ctk.CTkLabel(
            self.content_frame, text="Review the source and choose how your cards should be generated.", anchor="w",
            font=ctk.CTkFont("Segoe UI", 12), text_color="#9ca3af")
        self._create_file_section()
        self._create_exclude_section()
        self._create_deck_section()
        self._create_language_section()
        self._create_filter_section()
        self._create_audiobook_section()
        self._create_start_button()

    def _create_file_section(self):
        self.file_frame = ctk.CTkFrame(self.content_frame, width=440, height=105, **self.CARD_STYLE)
        self.file_label = ctk.CTkLabel(self.file_frame, text="Source PDF", anchor="w",
                                       font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color="#f3f4f6")
        file_name = os.path.basename(self.app_instance.selected_file)
        file_name = file_name[:31] + "..." if len(file_name) > 34 else file_name
        prefix = "ui" if getattr(sys, "frozen", False) else "src/ui"
        icon_path = self.app_instance.temp_path / prefix / "assets" / "reload_icon_v2.png"
        reload_source = Image.open(icon_path)
        reload_icon = ctk.CTkImage(reload_source, reload_source, size=(20, 20))
        self.file_button = ctk.CTkButton(
            self.file_frame, text=file_name, command=lambda: self.app_instance.main_ui.select_file(False),
            anchor="w", width=330, height=38, corner_radius=9, fg_color="#374151", hover_color="#4b5563")
        self.reload_file_button = ctk.CTkButton(
            self.file_frame, width=38, height=38, text="", command=self.execute_reload,
            corner_radius=9, border_width=1, border_color="#4b5563",
            fg_color="#263244", hover_color="#374151", image=reload_icon)

    def _create_exclude_section(self):
        self.exclude_frame = ctk.CTkFrame(self.content_frame, width=440, height=65, **self.CARD_STYLE)
        self.exclude_button = ctk.CTkButton(
            self.exclude_frame, text="Exclude pages", command=self.app_instance.create_exclude_window,
            width=145, height=36, corner_radius=9, fg_color="#374151", hover_color="#4b5563")
        self.exclude_textbox = ctk.CTkTextbox(
            self.exclude_frame, width=225, height=34, state="disabled", corner_radius=8,
            border_width=0, fg_color="#111827")

    def _create_deck_section(self):
        self.context_frame = ctk.CTkFrame(self.content_frame, width=440, height=115, **self.CARD_STYLE)
        self.context_label = ctk.CTkLabel(self.context_frame, text="Deck name", anchor="w",
                                          font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color="#f3f4f6")
        self.context_text = ctk.CTkTextbox(
            self.context_frame, width=400, height=48, corner_radius=8, border_width=1,
            border_color="#4b5563", fg_color="#111827")

    def _create_language_section(self):
        self.language_frame = ctk.CTkFrame(self.content_frame, width=440, height=65, **self.CARD_STYLE)
        self.language_info = ctk.CTkLabel(self.language_frame, text="Card language", anchor="w",
                                          font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color="#f3f4f6")
        self.language_switch = ctk.CTkOptionMenu(
            self.language_frame, values=["Default", "English", "Spanish", "German"], width=180, height=36,
            corner_radius=9, fg_color="#374151", button_color="#4b5563", button_hover_color="#6b7280")

    def _create_filter_section(self):
        self.embedding_frame = ctk.CTkFrame(self.content_frame, width=440, height=105, **self.CARD_STYLE)
        self.embedding_info = ctk.CTkLabel(self.embedding_frame, text="Duplicate filtering", anchor="w",
                                            font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color="#f3f4f6")
        self.embedding_hint = ctk.CTkLabel(
            self.embedding_frame, text="Higher values keep more similar cards.", anchor="w",
            font=ctk.CTkFont("Segoe UI", 11), text_color="#9ca3af")
        self.threshold_slider_frame = ctk.CTkFrame(self.embedding_frame, fg_color="transparent", width=400, height=42)
        self.threshold_slider = ctk.CTkSlider(
            self.threshold_slider_frame, from_=50, to=100, number_of_steps=50, width=330, height=18,
            command=self.threshold_slider_execute, progress_color="#2563eb", button_color="#60a5fa",
            button_hover_color="#93c5fd")
        self.threshold_slider.set(80)
        self.threshold_value_label = ctk.CTkLabel(
            self.threshold_slider_frame, text="0.80", width=45, font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color="#93c5fd")

    def _create_audiobook_section(self):
        self.audiobook_frame = ctk.CTkFrame(self.content_frame, width=440, height=70, **self.CARD_STYLE)
        self.audiobook_enabled = ctk.BooleanVar(value=False)
        self.audiobook_checkbox = ctk.CTkCheckBox(
            self.audiobook_frame, text="Create local audiobook", variable=self.audiobook_enabled,
            font=ctk.CTkFont("Segoe UI", 14, "bold"), checkbox_width=23, checkbox_height=23,
            fg_color="#2563eb", hover_color="#1d4ed8", border_color="#60a5fa")
        self.audiobook_hint = ctk.CTkLabel(
            self.audiobook_frame, text="Local Piper voice · downloaded once · WAV output", anchor="w",
            font=ctk.CTkFont("Segoe UI", 11), text_color="#9ca3af")

    def _create_start_button(self):
        prefix = "ui" if getattr(sys, "frozen", False) else "src/ui"
        icon_path = self.app_instance.temp_path / prefix / "assets" / "generate_icon_v2.png"
        icon_source = Image.open(icon_path)
        generate_icon = ctk.CTkImage(icon_source, icon_source, size=(27, 27))
        self.start_btn = ctk.CTkButton(
            self.content_frame, text="Generate Anki deck", command=self.app_instance.start_generation,
            width=440, height=56, corner_radius=12, fg_color="#2563eb", hover_color="#1d4ed8",
            border_width=1, border_color="#3b82f6",
            font=ctk.CTkFont("Segoe UI", 15, "bold"), image=generate_icon, compound="left")
        self.info_label = ctk.CTkLabel(self.content_frame, text="", text_color="#93c5fd")

    def show(self):
        self.content_frame.pack(fill="both", expand=True, padx=30, pady=24)
        self.header_label.pack(fill="x")
        self.header_info.pack(fill="x", pady=(2, 18))
        self.file_frame.pack(pady=(0, 10))
        self.file_label.pack(fill="x", padx=20, pady=(14, 7))
        self.file_button.pack(side="left", padx=(20, 8), pady=(0, 15))
        self.reload_file_button.pack(side="right", padx=(0, 20), pady=(0, 15))
        self.exclude_frame.pack(pady=(0, 10))
        self.exclude_button.pack(side="left", padx=(20, 8), pady=14)
        self.exclude_textbox.pack(side="right", padx=(0, 20), pady=14)
        self.context_frame.pack(pady=(0, 10))
        self.context_label.pack(fill="x", padx=20, pady=(14, 7))
        self.context_text.pack(padx=20, pady=(0, 14))
        self.language_frame.pack(pady=(0, 10))
        self.language_info.pack(side="left", padx=20, pady=14)
        self.language_switch.pack(side="right", padx=20, pady=14)
        self.embedding_frame.pack(pady=(0, 14))
        self.embedding_info.pack(fill="x", padx=20, pady=(12, 0))
        self.embedding_hint.pack(fill="x", padx=20)
        self.threshold_slider_frame.pack(padx=20, pady=(2, 8))
        self.threshold_slider.pack(side="left", padx=(0, 10), pady=8)
        self.threshold_value_label.pack(side="right", pady=8)
        self.audiobook_frame.pack(pady=(0, 14))
        self.audiobook_checkbox.pack(anchor="w", padx=20, pady=(12, 0))
        self.audiobook_hint.pack(anchor="w", padx=52, pady=(0, 10))
        self.start_btn.pack()
        for frame in (self.file_frame, self.exclude_frame, self.context_frame,
                      self.language_frame, self.embedding_frame, self.audiobook_frame):
            frame.pack_propagate(False)

    def execute_reload(self):
        self.app_instance.generator.handler.doc_reload()
        self.reload_excludes_textbox()
        self.clear_deleted_pages()

    def clear_deleted_pages(self):
        exclude_window = getattr(self.app_instance, "exclude_window", None)
        self.app_instance.pages_to_delete_sorted.clear()
        if exclude_window:
            exclude_window.deleted_pages.clear()

    def threshold_slider_execute(self, value):
        threshold = value / 100
        self.threshold_value_label.configure(text=f"{threshold:.2f}")
        if hasattr(self.app_instance, "generator"):
            self.app_instance.generator.set_threshold_value(threshold)

    def reload_excludes_textbox(self):
        self.deleted_pages = []
        self.exclude_textbox.configure(state="normal")
        self.exclude_textbox.delete("1.0", "end")
        self.exclude_textbox.configure(state="disabled")

    def start_progress_bar(self):
        self.start_btn.pack_forget()
        self._create_card_animation()
        self.bar = ctk.CTkProgressBar(
            self.content_frame, orientation="horizontal", progress_color="#2563eb",
            mode="determinate", fg_color="#374151", width=440)
        self.bar.pack(pady=(5, 2))
        self.bar.set(0)
        self.info_label.configure(text="Generating cards …")
        self.info_label.pack(pady=(2, 0))

    @staticmethod
    def _rotated_points(center_x, center_y, width, height, angle):
        cosine, sine = math.cos(angle), math.sin(angle)
        points = []
        for offset_x, offset_y in ((-width / 2, -height / 2), (width / 2, -height / 2),
                                   (width / 2, height / 2), (-width / 2, height / 2)):
            points.extend((center_x + offset_x * cosine - offset_y * sine,
                           center_y + offset_x * sine + offset_y * cosine))
        return points

    def _create_card_animation(self):
        if hasattr(self, "animation_canvas") and self.animation_canvas.winfo_exists():
            return
        self.animation_canvas = tk.Canvas(
            self.content_frame, width=440, height=62, background="#111827",
            borderwidth=0, highlightthickness=0)
        self.animation_canvas.pack(pady=(7, 0))
        self._animation_phase = 0.0
        self._animation_cards = []
        for index, (center_x, color) in enumerate(((176, "#1d4ed8"), (220, "#2563eb"), (264, "#3b82f6"))):
            card = self.animation_canvas.create_polygon(
                self._rotated_points(center_x, 31, 35, 45, 0), fill=color,
                outline="#93c5fd", width=1, smooth=True)
            line_one = self.animation_canvas.create_line(center_x - 10, 26, center_x + 10, 26,
                                                         fill="#dbeafe", width=2)
            line_two = self.animation_canvas.create_line(center_x - 10, 34, center_x + 6, 34,
                                                         fill="#bfdbfe", width=2)
            self._animation_cards.append((card, line_one, line_two, center_x, index * 1.7))
        self._animate_cards()

    def _animate_cards(self):
        if not hasattr(self, "animation_canvas") or not self.animation_canvas.winfo_exists():
            return
        self._animation_phase += 0.13
        for card, line_one, line_two, base_x, offset in self._animation_cards:
            center_x = base_x + math.sin(self._animation_phase * 0.65 + offset) * 4
            center_y = 31 + math.sin(self._animation_phase + offset) * 7
            angle = math.sin(self._animation_phase * 0.8 + offset) * 0.13
            self.animation_canvas.coords(card, *self._rotated_points(center_x, center_y, 35, 45, angle))
            cosine, sine = math.cos(angle), math.sin(angle)
            for item, y_offset, right in ((line_one, -5, 10), (line_two, 3, 6)):
                left_x, right_x = -10, right
                self.animation_canvas.coords(
                    item,
                    center_x + left_x * cosine - y_offset * sine,
                    center_y + left_x * sine + y_offset * cosine,
                    center_x + right_x * cosine - y_offset * sine,
                    center_y + right_x * sine + y_offset * cosine,
                )
        self._animation_after_id = self.after(45, self._animate_cards)

    def update_progress_bar(self, value):
        if hasattr(self, "bar"):
            self.bar.set(value)

    def reset_progress_bar(self):
        if hasattr(self, "bar"):
            self.bar.set(0)

    def on_closing(self):
        self.logger.info("Closing details_window...")
        if hasattr(self, "_animation_after_id"):
            self.after_cancel(self._animation_after_id)
        self.app_instance.main_ui.change_buttons_case_1()
        self.app_instance.generator.window_active = False
        self.app_instance.details_window = None
        self.destroy()

    def change_button_states(self, state: str):
        self.threshold_slider.configure(state=state)
        self.language_switch.configure(state=state)
        self.context_text.configure(state=state)
        self.exclude_button.configure(state=state)
        self.file_button.configure(state=state)
        self.reload_file_button.configure(state=state)
        self.audiobook_checkbox.configure(state=state)
