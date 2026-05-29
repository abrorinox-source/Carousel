import os
import re

from dotenv import load_dotenv
from google import genai

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

    def generate(self, request: GenerationRequest) -> CarouselOutput:
        prompt = self._build_prompt(request)
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
    def _build_prompt(request: GenerationRequest) -> str:
        return (
            "You are an expert social media strategist. "
            "Create a concise Instagram carousel in valid JSON format only. "
            "Do not add markdown fences, comments, or extra text. "
            "\n\n"
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
            "- Number slides sequentially starting from 1."
        )
