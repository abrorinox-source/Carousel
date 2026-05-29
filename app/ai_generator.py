import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from app.rag import KeywordRag
from app.schemas import CarouselOutput, GenerationRequest


class AIGenerator:
    def __init__(self, model: str | None = None) -> None:
        load_dotenv()

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. Add your Google AI Studio API key to your .env file."
            )

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.client = genai.Client(api_key=api_key)

        project_root = Path(__file__).resolve().parents[1]
        self.rag = KeywordRag(knowledge_dir=project_root / "knowledge")

    def generate(self, request: GenerationRequest) -> CarouselOutput:
        rag_context = self.rag.build_context(
            query=f"{request.topic} {request.niche} {request.tone_of_voice}",
            top_k=5,
        )
        prompt = self._build_prompt(request, knowledge_context=rag_context.text)

        if rag_context.has_context:
            print("\nRAG context used:")
            for chunk in rag_context.chunks:
                print(f"- {chunk.source} | score={chunk.score}")
        else:
            print("\nRAG context used: no relevant chunks found")

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": CarouselOutput,
            },
        )

        raw_text = (response.text or "").strip()
        if not raw_text:
            raise ValueError("The model returned an empty response.")

        json_payload = self._extract_json(raw_text)
        carousel = CarouselOutput.model_validate_json(json_payload)

        if len(carousel.slides) != request.slides_count:
            raise ValueError(
                f"Expected {request.slides_count} slides, but got {len(carousel.slides)}."
            )

        return carousel

    @staticmethod
    def _extract_json(text: str) -> str:
        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("No JSON object found in the model response.")

        return text[start : end + 1].strip()

    @staticmethod
    def _build_prompt(request: GenerationRequest, knowledge_context: str = "") -> str:
        if knowledge_context.strip():
            knowledge_block = (
                "Knowledge context from local files:\n"
                "Use this context as the primary source for audience language, pains, hooks, and topic details.\n"
                "Do not invent medical claims that are not supported by this context.\n"
                "If a medical detail is not present in the context, write in a general educational way and recommend consulting a specialist.\n\n"
                f"{knowledge_context}\n\n"
            )
        else:
            knowledge_block = (
                "No relevant local knowledge context was found for this topic.\n"
                "Keep the carousel general, educational, and safe. Do not invent specific medical claims.\n\n"
            )

        return (
            "You are an expert social media strategist and careful health-content editor. "
            "Create a concise Instagram carousel in valid JSON format only. "
            "Do not add markdown fences, comments, or extra text. "
            "This is educational content, not personal medical advice. "
            "Do not diagnose, prescribe medication, recommend dosages, or tell people to stop/change medication. "
            "Use soft wording like 'может быть связано', 'стоит обсудить со специалистом', 'важно проверить'. "
            "Avoid fearmongering and fake guarantees. "
            "\n\n"
            f"{knowledge_block}"
            f"Topic: {request.topic}\n"
            f"Niche: {request.niche}\n"
            f"Language: {request.language}\n"
            f"Slides count: {request.slides_count}\n"
            f"Tone of voice: {request.tone_of_voice}\n\n"
            "Return JSON with this exact shape:\n"
            "{\n"
            '  "title": "string",\n'
            '  "slides": [\n'
            "    {\n"
            '      "number": 1,\n'
            '      "headline": "string",\n'
            '      "text": "string"\n'
            "    }\n"
            "  ],\n"
            '  "caption": "string",\n'
            '  "cta": "string",\n'
            '  "hashtags": ["string"]\n'
            "}\n\n"
            "Requirements:\n"
            "- Use exactly the requested number of slides.\n"
            "- Do not put slide numbers in headlines.\n"
            "- Keep each slide text short and readable.\n"
            "- Write slide text as 1 to 3 compact sentences.\n"
            "- Make hashtags relevant to the niche and topic.\n"
            "- Number slides sequentially starting from 1.\n"
            "- For medical topics, always keep the content educational and include a soft doctor-consultation CTA."
        )
