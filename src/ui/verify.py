import logging
from tkinter import messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk
import httpx
from dotenv import set_key
from openai import OpenAI

from ai.model_type import ModelType

if TYPE_CHECKING:
    from ui.app import App


class verification:
    PROVIDERS = {
        "DeepSeek": (ModelType.DEEPSEEK, "DEEPSEEK_API_KEY"),
        "OpenAI": (ModelType.OPENAI, "OPENAI_API_KEY"),
        "Claude": (ModelType.ANTHROPIC, "ANTHROPIC_API_KEY"),
    }

    def __init__(self, app_instance: "App"):
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        self.key_frame = None

    def verify_key(self, provider: str, key: str):
        """Validate a provider key without generating billable card content."""
        try:
            if provider == "DeepSeek":
                OpenAI(api_key=key, base_url="https://api.deepseek.com").models.list()
            elif provider == "OpenAI":
                OpenAI(api_key=key).models.list()
            elif provider == "Claude":
                response = httpx.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=20,
                )
                response.raise_for_status()
            else:
                return False
            self.logger.info("Checked %s key: valid", provider)
            return True
        except Exception as error:
            self.logger.warning("Checked %s key: invalid (%s)", provider, type(error).__name__)
            return False

    def ask_for_key(self, provider="DeepSeek"):
        self.key_frame = ctk.CTkFrame(self.app_instance, fg_color="#111827")
        self.key_frame.pack(expand=True, fill="both")

        card = ctk.CTkFrame(self.key_frame, width=390, height=330, corner_radius=16,
                            fg_color="#1f2937", border_color="#374151", border_width=1)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        ctk.CTkLabel(card, text="Manage API key", font=ctk.CTkFont("Segoe UI", 24, "bold"),
                     text_color="#f3f4f6").pack(pady=(28, 5))
        ctk.CTkLabel(card, text="Keys are stored locally in the project .env file.",
                     font=ctk.CTkFont("Segoe UI", 12), text_color="#9ca3af").pack(pady=(0, 18))

        self.provider_menu = ctk.CTkOptionMenu(
            card, values=list(self.PROVIDERS), width=310, height=38,
            fg_color="#374151", button_color="#4b5563")
        self.provider_menu.set(provider if provider in self.PROVIDERS else "DeepSeek")
        self.provider_menu.pack(pady=6)

        self.key_entry = ctk.CTkEntry(
            card, placeholder_text="API key", width=310, height=40, show="*",
            fg_color="#111827", border_color="#4b5563")
        self.key_entry.pack(pady=8)

        ctk.CTkButton(card, text="Save and verify", width=310, height=42,
                      command=self.login_success, fg_color="#2563eb", hover_color="#1d4ed8").pack(pady=(10, 6))
        ctk.CTkButton(card, text="Cancel", width=310, height=36, command=self.cancel,
                      fg_color="transparent", hover_color="#374151").pack()

    def login_success(self):
        provider = self.provider_menu.get()
        key = self.key_entry.get().strip()
        if not key:
            messagebox.showerror("Missing key", "Enter an API key first.")
            return
        if not self.verify_key(provider, key):
            messagebox.showerror("Invalid API key", f"The {provider} key could not be verified.")
            return

        model_type, env_name = self.PROVIDERS[provider]
        self.app_instance.key_file.touch(exist_ok=True)
        set_key(str(self.app_instance.key_file), env_name, key)
        self.app_instance.api_keys[model_type] = key
        self.app_instance.key_valid = True
        self.app_instance.default_provider = provider
        self.key_frame.destroy()
        self.app_instance.start()

    def cancel(self):
        self.key_frame.destroy()
        self.app_instance.start()

    def addKey(self, provider=None):
        if self.app_instance.main_ui:
            self.app_instance.main_ui.destroy()
        self.ask_for_key(provider or self.app_instance.default_provider)
