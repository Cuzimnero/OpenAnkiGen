from pathlib import Path
import re
import statistics
import threading

import fitz
from PIL import Image


class pdf_handler:

    def __init__(self, path: Path):
        "Initalize the handler and opens the PDF file"
        self.path = path
        self.current_page = 0
        self.doc = fitz.open(self.path)
        self.pages = len(self.doc)
        self._doc_lock = threading.Lock()

    def doc_reload(self):
        """reload doc from PDF file"""
        with self._doc_lock:
            self.doc.close()
            self.doc = fitz.open(self.path)
            self.pages = len(self.doc)
            self.current_page = 0

    def get_pdf_page(self):
        """returns next page of the PDF file"""
        if self.current_page >= self.pages:
            return
        with self._doc_lock:
            output = self.doc[self.current_page]
            self.current_page = self.current_page + 1
            return output.get_text()

    def extract_blocks(self):
        """Extract ordered text blocks together with basic layout metadata."""
        extracted = []
        with self._doc_lock:
            for page_index in range(self.pages):
                page = self.doc.load_page(page_index)
                page_blocks = []
                for block in page.get_text("dict", sort=True).get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    lines = []
                    sizes = []
                    bold = False
                    for line in block.get("lines", []):
                        spans = line.get("spans", [])
                        line_text = "".join(span.get("text", "") for span in spans).strip()
                        if line_text:
                            lines.append(line_text)
                        for span in spans:
                            if span.get("text", "").strip():
                                sizes.append(float(span.get("size", 0)))
                                bold = bold or bool(span.get("flags", 0) & 16)
                    text = "\n".join(lines).strip()
                    if text:
                        page_blocks.append({
                            "text": text,
                            "page": page_index + 1,
                            "font_size": max(sizes, default=0),
                            "is_bold": bold,
                            "bbox": tuple(block.get("bbox", (0, 0, 0, 0))),
                        })
                extracted.extend(page_blocks)
        return extracted

    @staticmethod
    def _body_font_size(blocks):
        sizes = []
        for block in blocks:
            sizes.extend([block["font_size"]] * max(1, min(len(block["text"]) // 20, 20)))
        return statistics.median(sizes) if sizes else 11.0

    @staticmethod
    def _is_heading(block, body_font_size):
        text = " ".join(block["text"].split())
        if not text or len(text) > 140 or len(text.split()) > 16:
            return False
        numbered = bool(re.match(r"^(?:chapter|section|kapitel|abschnitt)?\s*\d+(?:\.\d+)*[.:]?\s+\S+", text, re.I))
        large = block["font_size"] >= max(body_font_size * 1.18, body_font_size + 1.5)
        bold_heading = block["is_bold"] and block["font_size"] >= body_font_size and len(text) <= 90
        return numbered or large or bold_heading

    def detect_document_type(self, blocks=None):
        """Estimate whether the PDF is a slide deck or a continuous document."""
        blocks = blocks if blocks is not None else self.extract_blocks()
        if not blocks or not self.pages:
            return "document"
        body_size = self._body_font_size(blocks)
        page_words = [0] * self.pages
        pages_with_heading = set()
        for block in blocks:
            page_words[block["page"] - 1] += len(block["text"].split())
            if self._is_heading(block, body_size):
                pages_with_heading.add(block["page"])
        average_words = sum(page_words) / self.pages
        heading_ratio = len(pages_with_heading) / self.pages
        return "slides" if average_words < 220 and heading_ratio >= 0.5 else "document"

    def detect_sections(self, blocks=None):
        """Group text blocks into logical sections that may span page boundaries."""
        blocks = blocks if blocks is not None else self.extract_blocks()
        if not blocks:
            return []
        body_size = self._body_font_size(blocks)
        sections = []
        current = {"title": "Document", "paragraphs": []}

        for block in blocks:
            if self._is_heading(block, body_size):
                if current["paragraphs"]:
                    sections.append(current)
                current = {
                    "title": " ".join(block["text"].split()),
                    "paragraphs": [],
                }
            else:
                current["paragraphs"].append({"text": block["text"], "page": block["page"]})

        if current["paragraphs"]:
            sections.append(current)
        return sections

    @staticmethod
    def _split_long_paragraph(paragraph, max_words):
        words = paragraph["text"].split()
        if len(words) <= max_words:
            return [paragraph]
        return [
            {"text": " ".join(words[start:start + max_words]), "page": paragraph["page"]}
            for start in range(0, len(words), max_words)
        ]

    def create_chunks(self, max_tokens=1500, overlap_tokens=150):
        """Create bounded section chunks with paragraph-level overlap."""
        max_words = max(50, int(max_tokens / 1.3))
        overlap_words = max(0, int(overlap_tokens / 1.3))
        chunks = []

        for section in self.detect_sections():
            paragraphs = []
            for paragraph in section["paragraphs"]:
                paragraphs.extend(self._split_long_paragraph(paragraph, max_words))

            current = []
            current_words = 0
            for paragraph in paragraphs:
                paragraph_words = len(paragraph["text"].split())
                if current and current_words + paragraph_words > max_words:
                    self._append_chunk(chunks, section["title"], current)
                    overlap = []
                    overlap_count = 0
                    for prior in reversed(current):
                        if overlap_count >= overlap_words:
                            break
                        overlap.insert(0, prior)
                        overlap_count += len(prior["text"].split())
                    while overlap and overlap_count + paragraph_words > max_words:
                        removed = overlap.pop(0)
                        overlap_count -= len(removed["text"].split())
                    current = overlap
                    current_words = overlap_count
                current.append(paragraph)
                current_words += paragraph_words
            if current:
                self._append_chunk(chunks, section["title"], current)

        for index, chunk in enumerate(chunks, start=1):
            chunk["chunk_index"] = index
        return chunks

    @staticmethod
    def _append_chunk(chunks, title, paragraphs):
        text = "\n\n".join(paragraph["text"] for paragraph in paragraphs).strip()
        if not text:
            return
        pages = [paragraph["page"] for paragraph in paragraphs]
        chunks.append({
            "section_title": title,
            "text": text,
            "page_start": min(pages),
            "page_end": max(pages),
        })

    def convert_to_pic(self):
        """Yields a PIL Image for each page in the PDF.
        Uses a scale matrix to reduce memory footprint and increase speed."""
        for page in self.doc:
            mat = fitz.Matrix(0.35, 0.35)
            map = page.get_pixmap(matrix=mat)
            yield Image.frombytes("RGB", (map.width, map.height), map.samples)

    def render_page(self, page_index: int, max_width: int = 780, max_height: int = 500):
        """Render one preview page on demand with a bounded pixel size."""
        if page_index < 0 or page_index >= self.pages:
            raise ValueError("Page does not exist")
        with self._doc_lock:
            page = self.doc.load_page(page_index)
            scale = min(max_width / page.rect.width, max_height / page.rect.height)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    def delete_page(self, page: int):
        """Deletes a specific page by index and updates the total page count."""
        try:
            with self._doc_lock:
                self.doc.delete_page(page)
                self.pages = len(self.doc)
            return
        except Exception as e:
            raise ValueError("Page does not exist")
