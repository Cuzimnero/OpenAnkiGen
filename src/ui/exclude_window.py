import queue
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from ui.app import App


class ExcludeWindow(ctk.CTkToplevel):
    """Memory-bounded, on-demand PDF page selector."""

    CACHE_SIZE = 5

    def __init__(self, app_instance: "App"):
        super().__init__(app_instance)
        self.app = app_instance
        self.handler = self.app.generator.handler
        self.total_pages = self.handler.pages
        self.current_page = 0
        self.deleted_pages = list(self.app.deleted_pages)
        self.selected_pages = set(self.deleted_pages)
        self.page_states = {}
        self._image_cache = OrderedDict()
        self._request_queue = queue.Queue(maxsize=1)
        self._result_queue = queue.Queue()
        self._request_token = 0
        self._closed = False

        self.title("Exclude PDF pages")
        self.geometry("980x820")
        self.minsize(760, 650)
        self.configure(fg_color="#111827")
        self.focus_force()
        self.grab_set()
        self.lift()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.iconbitmap(str(self.app.icon_path)))
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build_ui()
        self.selection_label.configure(text=f"{len(self.selected_pages):,} selected")
        threading.Thread(target=self._render_worker, daemon=True).start()
        self.after(50, self._poll_results)

    def _build_ui(self):
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.title_label = ctk.CTkLabel(
            self.header, text="Exclude pages", anchor="w",
            font=ctk.CTkFont("Segoe UI", 28, "bold"), text_color="#f3f4f6")
        self.subtitle_label = ctk.CTkLabel(
            self.header, text="Preview one page at a time. Only a few previews are kept in memory.", anchor="w",
            font=ctk.CTkFont("Segoe UI", 12), text_color="#9ca3af")
        self.selection_label = ctk.CTkLabel(
            self.header, text="0 selected", anchor="e", font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color="#93c5fd")

        self.preview_card = ctk.CTkFrame(
            self, fg_color="#1f2937", border_color="#374151", border_width=1, corner_radius=16)
        self.preview_area = ctk.CTkFrame(self.preview_card, fg_color="#0b1220", corner_radius=12)
        self.image_label = ctk.CTkLabel(self.preview_area, text="")

        self.loading_frame = ctk.CTkFrame(self.preview_area, fg_color="transparent")
        self.loading_label = ctk.CTkLabel(
            self.loading_frame, text="Preparing preview…", font=ctk.CTkFont("Segoe UI", 16, "bold"),
            text_color="#dbeafe")
        self.loading_hint = ctk.CTkLabel(
            self.loading_frame, text="Rendering only the page you need", font=ctk.CTkFont("Segoe UI", 12),
            text_color="#6b7280")
        self.loading_bar = ctk.CTkProgressBar(
            self.loading_frame, width=260, height=7, mode="indeterminate", fg_color="#374151",
            progress_color="#3b82f6", corner_radius=5)

        self.controls = ctk.CTkFrame(self, fg_color="#1f2937", corner_radius=14)
        self.previous_button = ctk.CTkButton(
            self.controls, text="‹  Previous", command=lambda: self._move_page(-1), width=125, height=40,
            fg_color="#374151", hover_color="#4b5563", corner_radius=9)
        self.page_entry = ctk.CTkEntry(
            self.controls, width=72, height=40, justify="center", fg_color="#111827",
            border_color="#4b5563", corner_radius=9)
        self.page_entry.bind("<Return>", self._jump_to_page)
        self.page_count_label = ctk.CTkLabel(
            self.controls, text=f"of {self.total_pages:,}", font=ctk.CTkFont("Segoe UI", 13),
            text_color="#9ca3af")
        self.next_button = ctk.CTkButton(
            self.controls, text="Next  ›", command=lambda: self._move_page(1), width=125, height=40,
            fg_color="#374151", hover_color="#4b5563", corner_radius=9)
        self.exclude_checkbox = ctk.CTkCheckBox(
            self.controls, text="Exclude this page", command=self._toggle_current_page,
            checkbox_width=24, checkbox_height=24, border_color="#60a5fa", hover_color="#2563eb",
            fg_color="#2563eb", font=ctk.CTkFont("Segoe UI", 14, "bold"))

        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer_actions = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.cancel_button = ctk.CTkButton(
            self.footer_actions, text="Cancel", command=self._cancel, width=130, height=44,
            fg_color="#374151", hover_color="#4b5563", corner_radius=10)
        self.finish_button = ctk.CTkButton(
            self.footer_actions, text="Apply selection", command=self.exclude_window_finish, width=210, height=44,
            fg_color="#2563eb", hover_color="#1d4ed8", corner_radius=10,
            font=ctk.CTkFont("Segoe UI", 14, "bold"))

        self.header.pack(fill="x", padx=32, pady=(25, 16))
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.selection_label.grid(row=0, column=1, rowspan=2, sticky="e")
        self.header.grid_columnconfigure(0, weight=1)

        self.preview_card.pack(fill="both", expand=True, padx=32)
        self.preview_area.pack(fill="both", expand=True, padx=14, pady=14)
        self.loading_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.loading_label.pack()
        self.loading_hint.pack(pady=(3, 14))
        self.loading_bar.pack()

        self.controls.pack(fill="x", padx=32, pady=14)
        self.previous_button.grid(row=0, column=1, padx=8, pady=(14, 8))
        self.page_entry.grid(row=0, column=2, padx=(8, 5), pady=(14, 8))
        self.page_count_label.grid(row=0, column=3, sticky="w", pady=(14, 8))
        self.next_button.grid(row=0, column=4, padx=8, pady=(14, 8))
        self.exclude_checkbox.grid(row=1, column=1, columnspan=4, pady=(4, 14))
        self.controls.grid_columnconfigure(0, weight=1)
        self.controls.grid_columnconfigure(5, weight=1)

        self.footer.pack(fill="x", padx=32, pady=(0, 22))
        self.footer_actions.pack(anchor="center")
        self.cancel_button.pack(side="left", padx=6)
        self.finish_button.pack(side="left", padx=6)

    def show(self):
        if self.total_pages:
            self._show_page(0)
        else:
            self._show_empty_document()

    def _show_page(self, page_index):
        self.current_page = max(0, min(page_index, self.total_pages - 1))
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, str(self.current_page + 1))
        self.previous_button.configure(state="normal" if self.current_page else "disabled")
        self.next_button.configure(state="normal" if self.current_page < self.total_pages - 1 else "disabled")
        if self.current_page + 1 in self.selected_pages:
            self.exclude_checkbox.select()
        else:
            self.exclude_checkbox.deselect()

        cached = self._image_cache.get(self.current_page)
        if cached is not None:
            self._image_cache.move_to_end(self.current_page)
            self._display_image(cached)
            return

        self._start_loading()
        self._request_token += 1
        while True:
            try:
                self._request_queue.get_nowait()
            except queue.Empty:
                break
        self._request_queue.put((self.current_page, self._request_token))

    def _render_worker(self):
        while not self._closed:
            try:
                page_index, token = self._request_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                image = self.handler.render_page(page_index, max_width=780, max_height=500)
                self._result_queue.put((page_index, token, image, None))
            except Exception as error:
                self._result_queue.put((page_index, token, None, str(error)))

    def _poll_results(self):
        if self._closed or not self.winfo_exists():
            return
        try:
            while True:
                page_index, token, image, error = self._result_queue.get_nowait()
                if image is not None:
                    self._cache_image(page_index, image)
                if token == self._request_token and page_index == self.current_page:
                    if error:
                        self._show_error(error)
                    else:
                        self._display_image(image)
        except queue.Empty:
            pass
        self.after(50, self._poll_results)

    def _cache_image(self, page_index, image):
        self._image_cache[page_index] = image
        self._image_cache.move_to_end(page_index)
        while len(self._image_cache) > self.CACHE_SIZE:
            self._image_cache.popitem(last=False)

    def _display_image(self, image):
        self.loading_bar.stop()
        self.loading_frame.place_forget()
        available_w = max(300, self.preview_area.winfo_width() - 50)
        available_h = max(250, self.preview_area.winfo_height() - 40)
        ratio = min(available_w / image.width, available_h / image.height)
        size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=size)
        self.image_label.configure(image=ctk_image, text="")
        self.image_label._safe_image_reference = ctk_image
        self.image_label.place(relx=0.5, rely=0.5, anchor="center")

    def _start_loading(self):
        self.image_label.place_forget()
        self.loading_label.configure(text=f"Loading page {self.current_page + 1:,}…")
        self.loading_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.loading_bar.start()

    def _show_error(self, error):
        self.loading_bar.stop()
        self.loading_label.configure(text="Preview unavailable")
        self.loading_hint.configure(text=error)

    def _show_empty_document(self):
        self.loading_label.configure(text="This PDF contains no pages")
        self.loading_hint.configure(text="Choose another PDF to continue.")
        self.previous_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        self.exclude_checkbox.configure(state="disabled")

    def _move_page(self, offset):
        self._show_page(self.current_page + offset)

    def _jump_to_page(self, _event=None):
        try:
            page_number = int(self.page_entry.get())
        except ValueError:
            page_number = self.current_page + 1
        self._show_page(page_number - 1)

    def _toggle_current_page(self):
        page_number = self.current_page + 1
        if self.exclude_checkbox.get():
            self.selected_pages.add(page_number)
        else:
            self.selected_pages.discard(page_number)
        self.selection_label.configure(text=f"{len(self.selected_pages):,} selected")

    def exclude_window_finish(self):
        self.deleted_pages = sorted(self.selected_pages)
        self.app.deleted_pages = self.deleted_pages.copy()
        self.app.pages_to_delete_sorted = sorted(self.selected_pages, reverse=True)
        output_str = ",".join(map(str, self.deleted_pages))
        textbox = self.app.details_window.exclude_textbox
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("end", output_str)
        textbox.configure(state="disabled")
        self._close()

    def _cancel(self):
        self._close()

    def _close(self):
        self._closed = True
        self.loading_bar.stop()
        self.grab_release()
        self.destroy()
