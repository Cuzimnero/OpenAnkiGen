import concurrent.futures
import json
import logging
import math
import os
import pathlib
import re
import sys
from typing import TYPE_CHECKING

import customtkinter as ctk
import httpx
import ollama
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer

from ai import embedding
from ai.model_type import ModelType, CallType
from handler.pdf_handler import pdf_handler

if TYPE_CHECKING:
    from ui.app import App


class AnkiGen:
    def __init__(self, model_type: ModelType, model: str, app_instance: App):
        self.app_instance = app_instance
        self.window_active = True
        self.threshold_value = 0.8
        self.progress = 0
        self.model = model
        self.model_type = model_type
        self.logger = logging.getLogger(__name__)
        load_dotenv()
        if self.model_type is not ModelType.LOCALE:
            self.workers = 30
            self.rework_size = 50
        else:
            self.workers = 3
            self.rework_size = 30

    def set_pdf_handler(self, path: pathlib.Path):
        self.handler = pdf_handler(path)

    def set_threshold_value(self, threshold_value: float):
        self.threshold_value = threshold_value

    def load_embedding_model(self):
        if getattr(sys, 'frozen', False):
            model_path = os.path.join(sys._MEIPASS, "ai", "model_data")
            self.embedding_model = SentenceTransformer(model_path, local_files_only=True)
        else:
            model_path = self.app_instance.temp_path / "src" / "ai" / "model_data"
            if not os.path.exists(model_path):
                self.logger.warning("Model not found. Downloading for the first time...")
                temp_model = SentenceTransformer('all-MiniLM-L6-v2')
                temp_model.save(model_path)
                self.logger.warning(f"Model got saved in  {model_path}")
            self.embedding_model = SentenceTransformer(str(model_path))

    def set_model(self, model: str):
        self.model = model

    def rework_part(self, cards: list[dict]):
        system_prompt = r"""You are an expert Anki Content Optimizer. Your task is to filter, categorize, and refine a list of flashcards.

        ### DECISION MATRIX:
        You MUST return a valid JSON object with the following structure:
        {
          "keep": [
            {"front": "...", "back": "...", "topic": "..."}
          ],
          "rework": [
           {
              "front": "...", 
              "back": "...", 
              "topic": "...", 
              "reason": "Why it needs rework"
            }
          ],
          "delete_count": 5
        }
        1. KEEP (Direct JSON Output):
           - Use this for cards that are factually correct, concise, and exam-ready.
           - Criteria: The answer (back) must be shorter than 3 sentences and formatted clearly (e.g., bullet points).
        
        2. DELETE (Ignore):
           - Organizational data (dates, room numbers, job offers, professor contact info).
           - Cards where the front is a single generic word (e.g., "Note", "Context") that is not a technical term.
           - Exact duplicates or redundant information already covered in better cards.
        
        3. REWORK :
           - WHEN: The content is exam-relevant, but the formatting or phrasing is poor.
           - WHY (Specific Criteria):
             * 'Wall of Text': The answer is a long, unstructured paragraph.
             * 'Vague Question': The question is too broad (e.g., "What about Ethics?").
             * 'Single-Word Issue': The front is an important technical term (e.g., "Cosine Similarity"), but the back is incomplete, messy, or lacks a clear definition.
             * 'Incomplete Answer': The back provides fewer items than requested (e.g., list of 5 instead of 6).
             * 'Generation Cut-off': The answer ends abruptly mid-sentence or mid-structure.
             * 'Context Leak': Mentions slide numbers,not given examples, page numbers, or "previous sections".
             * 'Formatting Glitch': Broken Anki MathJax (\(...\) or \[...\]) or Markdown syntax.
             * 'Answer Mismatch': The back of the card does not provide a direct or accurate answer to the question asked
            - MANDATORY: For every card in the 'rework' list, you MUST provide a 'reason' field 
                explaining exactly what is wrong (e.g., 'Wall of Text', 'No Question Mark').
           - HOW: Add them in the "rework" section.
        
        IMPORTANT: 
        - Every input card must be assigned to exactly ONE category (keep, rework, or delete).
        - The "rework" section contains the original fields plus the "reason".
        """

        user_prompt = f"""
                Filter and condense the following list of cards. Ensure the result is manageable and focuses on the most important exam-relevant knowledge.

                INPUT_CARDS:
                {json.dumps(cards)}
                """
        self.logger.info(f"Checking {len(cards)} cards")
        return self.run_prompt(system_prompt, user_prompt, "Rework error", CallType.FILTER_AND_SPLIT)

    def rework_flashcard(self, flashcard: list[dict]):
        """Improves flashcards
        Input: A worse Flashcard to improve
        Output: Reworked Flashcard"""
        rework_system_prompt = r"""You are an Anki Refinement Specialist. Your task is to take a list of sub-optimal flashcards and transform them into high-quality, atomic learning units.

        ### OBJECTIVES:
        - 'Wall of Text': The answer is a long, unstructured paragraph. -> Fix by using clear bullet points (max 3 per card).
        - 'Vague Question': The question is too broad (e.g., "What about Ethics?"). -> Clarify by making the front specific and targeted.
        - 'Single-Word Issue': The front is an important technical term (e.g., "Cosine Similarity"), but the back is incomplete, messy, or lacks a clear definition. -> Expand into clear, comprehensive definitions.
        - 'Incomplete Answer': The back provides fewer items than requested (e.g., list of 5 instead of 6). -> Ensure the back matches the requested number of items.
        - 'Generation Cut-off': The answer ends abruptly mid-sentence or mid-structure. -> Complete the sentence and restore the full logical structure.
        - 'Context Leak': Mentions slide numbers, page numbers, examples or "previous sections". -> Remove all external references to make the card self-contained.
        - 'Formatting Glitch': Broken Anki MathJax (\(...\) or \[...\]) or Markdown syntax. -> Repair the syntax to ensure all elements render correctly.
        - 'Answer Mismatch': Problem: The back of the card does not provide a direct, precise, or complete answer to the specific question asked on the front. Revision Approach: Rewrite the answer so it addresses the front exactly. Eliminate irrelevant information and ensure the response leads directly to the core of the question.
        - 'MANDATORY': Every 'front' must be a grammatically correct, self-contained question ending with a question mark; if the input is a statement or a noun, you MUST rephrase it into a 'How', 'What', 'Why', or 'Which' question.

        ### OUTPUT FORMAT:
        You MUST return a valid JSON object with a single list called 'cards':
        {
          "cards": [
            {"front": "...", "back": "...", "topic": "..."},
            {"front": "...", "back": "...", "topic": "..."}
          ]
        }
        """
        rework_user_prompt = f"""
        Improve the following flashcards. Use the provided 'reason' to guide your refinement for each card.

        INPUT_CARDS_TO_FIX:
        {json.dumps(flashcard)}
        """
        self.logger.info(f"Reworking {len(flashcard)} flashcards.")
        self.logger.debug(f"Flashcards to rework: {flashcard}")
        return self.run_prompt(rework_system_prompt, rework_user_prompt, "Rework error", CallType.CARD_IMPROVEMENT)

    def rework(self, cards: list[dict]):
        """reworks created anki cards deletes unnecessary and bad cards"""
        self.logger.info("Reworking anki cards...")
        if hasattr(self.app_instance, "details_window"):
            self.app_instance.details_window.reset_progress_bar()
        self.progress = 0

        self.rework_iterations = math.ceil(len(cards) / self.rework_size)
        rework_cards = []
        pending_tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            for i in range(0, self.rework_iterations):
                task = executor.submit(self.rework_part, cards[i * self.rework_size:(i + 1) * self.rework_size])
                pending_tasks.append(task)
            for future in concurrent.futures.as_completed(pending_tasks):
                if not self.window_active:
                    self.logger.warning("Window closed generation stopped")
                    return
                try:
                    rework_cards.extend(future.result())
                except Exception as e:
                    self.logger.error(f"Error: {e}")
        self.logger.info(f"Reworked cards: {len(rework_cards)}")
        embeddet = embedding.delete_dupes(rework_cards, self.embedding_model, self.logger, self.threshold_value)
        self.logger.info(f"Cards after duplicate deletion: {len(embeddet)}")
        return embeddet

    def createCards(self, language: str, info_label: ctk.CTkLabel):
        """Generate cards from layout-aware, overlapping document sections."""
        cards = []
        all_cards = []
        chunks = self.handler.create_chunks()
        self.generation_units = len(chunks)

        if not chunks:
            self.logger.warning("No readable document sections found.")
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            for chunk in chunks:
                page_cards = executor.submit(self._createCard_part, chunk, language)
                cards.append(page_cards)
            for future in concurrent.futures.as_completed(cards):
                if not self.window_active:
                    self.logger.warning("Window closed generation stopped")
                    return
                try:
                    page_cards = future.result()
                    all_cards.extend(page_cards)
                except Exception as e:
                    self.logger.error(f"Error: {e}")
        info_label.configure(text="execute card rework ...")
        self.logger.info(f"Created {len(all_cards)} cards.")
        final_cards = self.rework(all_cards)
        return final_cards

    def _createCard_part(self, chunk: dict, language: str):
        input_text = chunk["text"]
        section_title = chunk["section_title"]
        page_range = (str(chunk["page_start"]) if chunk["page_start"] == chunk["page_end"]
                      else f"{chunk['page_start']}-{chunk['page_end']}")
        self.logger.info(
            f"Creating {language} cards for section '{section_title}' (pages {page_range})"
        )
        system_prompt = r"""
        You are a professional Flashcard creator. 
        Analyze the provided text and extract the core concepts into flashcards.
        Output MUST be a valid JSON object containing a list called 'cards'.
        Each card must have 'front' and 'back' fields.
        Example:
                {
        "cards": [
            {
        "front": "What is a apple?",
              "back": "A fruit",
              "topic": "Fruits"
            }
          ]
        }
        TECHNICAL FORMATTING:
        - Use Anki MathJax delimiters for ALL math/technical variables: \(...\) inline and \[...\] for display math.
        - Never use dollar-sign delimiters for formulas.
        - Ensure valid JSON output. Double-escape backslashes in JSON (e.g., \\frac{1}{2}).
        - Topic field must be a high-level category 
        STRICT FRONT-SIDE RULE:
        - Every 'front' MUST start with a question word (What, How, Why, Which, etc.).
        - A 'front' that is only a noun or a phrase (e.g., "DNS Purpose") is a CRITICAL ERROR.
        - Imagine the user is being tested: The 'front' must provide enough context to give a precise answer.
        PEDAGOGICAL RULES:
        - Use Active Recall: Ask specific questions.
        - Atomic Cards: One concept per card. 
        - No "Yes/No" questions.
        - If the input text is just an organizational slide or lacks technical substance, return {"cards": []}.
        Keep the answers concise and focused on one concept per card. Also add a field with 'topic' this should store 
        the core topic which the card is about only 1-4 words. 
        'Example Embedding': If you refer to a specific calculation or scenario from the text, you MUST include the relevant data points (numbers, addresses, conditions) within the 'Front' of the card.
        """

        user_prompt = f"""
        Convert the following lecture notes into necessary high-quality Anki cards use all important things.
        SECTION CONTEXT:
        - Section title: {section_title}
        - Internal source pages: {page_range}
        - Use the section title to resolve context, but NEVER mention page numbers or the source document in a card.
        LANGUAGE RULE:
        - All content (front, back, topic) MUST be in {language}. If {language} is "default", use the primary language found in the provided text. Do not translate technical terms that are commonly used in their original form.
        STRICT RULES:
        1. IGNORE all organizational data: Do not create cards about professor names, university names, course IDs, dates, slide numbers, or bibliography.
        2. FOCUS on: Definitions, technical concepts, algorithms, code logic, and factual relationships.
        3. SKIP meta-information: No cards about "Lecture 1", "Introduction", or "Thank you for your attention" slides.
        4. Q&A STYLE: The 'front' must be a specific question. The 'back' must be the direct answer.
        5.  Every 'front' MUST be a complete, self-contained question. Never use single words or sentence fragments as a question. 
        6. Ignore Example calculations and examples in general
         
        ---
        {input_text}
        
        ---
        """
        return self.run_prompt(system_prompt, user_prompt, "generation error", CallType.CARD_GENERATION)

    def _parse_json_text(self, content: str):
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
        return json.loads(content)

    def _advance_progress(self, mode: CallType):
        self.progress += 1
        window = getattr(self.app_instance, "details_window", None)
        if not window or not hasattr(window, "bar"):
            return
        denominator = (max(1, self.generation_units) if mode is CallType.CARD_GENERATION
                       else max(1, self.rework_iterations))
        value = self.progress / denominator
        window.after(0, lambda: window.bar.set(value))

    def _cards_from_response(self, data: dict, mode: CallType):
        if mode in (CallType.CARD_GENERATION, CallType.CARD_IMPROVEMENT):
            self._advance_progress(mode)
            return data.get("cards", [])

        final_cards = list(data.get("keep", []))
        cards_to_improve = data.get("rework", [])
        if cards_to_improve:
            final_cards.extend(self.rework_flashcard(cards_to_improve))
        return final_cards

    def run_prompt(self, system_prompt: str, user_prompt: str, error_message: str, mode: CallType):
        if not self.window_active:
            return []
        try:
            if self.model_type in (ModelType.DEEPSEEK, ModelType.OPENAI):
                key = self.app_instance.api_keys[self.model_type]
                client_kwargs = {"api_key": key}
                if self.model_type is ModelType.DEEPSEEK:
                    client_kwargs["base_url"] = "https://api.deepseek.com"
                client = OpenAI(**client_kwargs)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=False,
                    response_format={"type": "json_object"},
                )
                data = self._parse_json_text(response.choices[0].message.content)

            elif self.model_type is ModelType.ANTHROPIC:
                response = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.app_instance.api_keys[ModelType.ANTHROPIC],
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 4096,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_prompt}],
                    },
                    timeout=180,
                )
                response.raise_for_status()
                response_data = response.json()
                text_content = "".join(
                    block.get("text", "") for block in response_data.get("content", [])
                    if block.get("type") == "text"
                )
                data = self._parse_json_text(text_content)

            elif self.model_type is ModelType.LOCALE:
                response = ollama.chat(
                    model=self.model,
                    format="json",
                    options={"num_ctx": 4096},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                data = self._parse_json_text(response.message.content)
            else:
                raise ValueError(f"Unsupported model provider: {self.model_type}")

            return self._cards_from_response(data, mode)
        except Exception as error:
            self.logger.error("%s (%s): %s", error_message, self.model_type.name, error)
            return []
