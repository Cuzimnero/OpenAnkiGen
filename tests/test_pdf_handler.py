import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from src.handler.pdf_handler import pdf_handler


class TestPdfHandler(unittest.TestCase):

    def setUp(self):
        # Create a dummy PDF for testing
        self.test_pdf_path = Path("test.pdf")
        self.doc = fitz.open()
        for i in range(3):
            page = self.doc.new_page()
            page.insert_text((50, 50), f"Section {i + 1}", fontsize=20)
            page.insert_text((50, 82), f"This is page {i + 1}.", fontsize=11)
        self.doc.save(str(self.test_pdf_path))
        self.doc.close()
        # Initialize the handler for each test
        self.handler = pdf_handler(self.test_pdf_path)

    def tearDown(self):
        # Clean up the dummy PDF
        if hasattr(self, 'handler') and self.handler:
            if hasattr(self.handler, 'doc') and self.handler.doc:
                try:
                    self.handler.doc.close()
                except ValueError:
                    pass
        if self.test_pdf_path.exists():
            self.test_pdf_path.unlink()

    def test_01_initialization(self):
        """Test if the PDF handler is initialized correctly."""
        self.assertEqual(self.handler.pages, 3)
        self.assertEqual(self.handler.current_page, 0)

    def test_02_get_pdf_page(self):
        """Test if get_pdf_page returns the correct text content."""
        text = self.handler.get_pdf_page()
        self.assertIn("This is page 1.", text)
        self.assertEqual(self.handler.current_page, 1)

        text = self.handler.get_pdf_page()
        self.assertIn("This is page 2.", text)
        self.assertEqual(self.handler.current_page, 2)

        text = self.handler.get_pdf_page()
        self.assertIn("This is page 3.", text)
        self.assertEqual(self.handler.current_page, 3)

        # Test end of document
        text = self.handler.get_pdf_page()
        self.assertIsNone(text)
        self.assertEqual(self.handler.current_page, 3)

    def test_03_convert_to_pic(self):
        """Test if convert_to_pic yields the correct number of images."""
        images = list(self.handler.convert_to_pic())
        self.assertEqual(len(images), 3)
        for img in images:
            self.assertIsInstance(img, Image.Image)

    def test_04_delete_page(self):
        """Test if delete_page correctly deletes a page."""
        self.handler.delete_page(1)  # Delete the second page
        self.assertEqual(self.handler.pages, 2)

        # After deleting page 1 (0-indexed), the new page 1 should be the original page 2
        self.handler.current_page = 1
        text = self.handler.get_pdf_page()
        self.assertIn("This is page 3.", text)

        # Reload the document to verify that the page is not deleted from the file
        self.handler.doc_reload()
        self.assertEqual(self.handler.pages, 3)
        self.assertEqual(self.handler.current_page, 0)

    def test_05_doc_reload(self):
        """Test if doc_reload correctly reloads the document."""
        self.handler.delete_page(0)
        self.assertEqual(self.handler.pages, 2)

        # Reload the original document
        self.handler.doc_reload()
        self.assertEqual(self.handler.pages, 3)
        self.handler.current_page = 0
        text = self.handler.get_pdf_page()
        self.assertIn("This is page 1", text)

    def test_06_render_page_is_size_bounded(self):
        """Preview rendering keeps image memory independent of total page count."""
        image = self.handler.render_page(0, max_width=320, max_height=240)
        self.assertIsInstance(image, Image.Image)
        self.assertLessEqual(image.width, 320)
        self.assertLessEqual(image.height, 240)

        with self.assertRaises(ValueError):
            self.handler.render_page(99)

        with self.assertRaises(ValueError):
            self.handler.render_page(-1)

    def test_07_concurrent_previews_are_safe_and_bounded(self):
        """Concurrent preview requests do not corrupt the shared PDF document."""
        with ThreadPoolExecutor(max_workers=3) as executor:
            images = list(executor.map(
                lambda page: self.handler.render_page(page, max_width=200, max_height=160),
                range(self.handler.pages),
            ))

        self.assertEqual(len(images), self.handler.pages)
        for image in images:
            self.assertLessEqual(image.width, 200)
            self.assertLessEqual(image.height, 160)

    def test_08_extracts_layout_and_detects_slide_deck(self):
        blocks = self.handler.extract_blocks()

        self.assertEqual(len(blocks), 6)
        self.assertTrue(all({"text", "page", "font_size", "is_bold", "bbox"} <= block.keys()
                            for block in blocks))
        self.assertEqual(self.handler.detect_document_type(blocks), "slides")

    def test_09_detects_sections_across_pdf_pages(self):
        sections = self.handler.detect_sections()

        self.assertEqual([section["title"] for section in sections],
                         ["Section 1", "Section 2", "Section 3"])
        self.assertIn("This is page 2.", sections[1]["paragraphs"][0]["text"])
        self.assertEqual(sections[1]["paragraphs"][0]["page"], 2)

    def test_10_chunks_are_bounded_and_overlap(self):
        self.handler.detect_sections = lambda: [{
            "title": "Large section",
            "paragraphs": [
                {"text": " ".join(f"alpha{i}" for i in range(220)), "page": 1},
                {"text": " ".join(f"bridge{i}" for i in range(80)), "page": 2},
                {"text": " ".join(f"omega{i}" for i in range(220)), "page": 3},
            ],
        }]

        chunks = self.handler.create_chunks(max_tokens=400, overlap_tokens=80)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk["text"].split()) <= int(400 / 1.3) for chunk in chunks))
        self.assertIn("bridge0", chunks[0]["text"])
        self.assertIn("bridge0", chunks[1]["text"])
        self.assertEqual(chunks[0]["section_title"], "Large section")


if __name__ == '__main__':
    unittest.main()
