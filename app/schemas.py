from pydantic import BaseModel, Field, field_validator


class Slide(BaseModel):
    number: int = Field(..., ge=1)
    headline: str = Field(..., min_length=1, max_length=140)
    text: str = Field(..., min_length=1, max_length=400)


class CarouselOutput(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    slides: list[Slide] = Field(..., min_length=1)
    caption: str = Field(..., min_length=1)
    cta: str = Field(..., min_length=1)
    hashtags: list[str] = Field(..., min_length=1)

    @field_validator("slides")
    @classmethod
    def validate_slide_sequence(cls, slides: list[Slide]) -> list[Slide]:
        sorted_slides = sorted(slides, key=lambda slide: slide.number)
        expected_numbers = list(range(1, len(sorted_slides) + 1))
        actual_numbers = [slide.number for slide in sorted_slides]
        if actual_numbers != expected_numbers:
            raise ValueError("Slide numbers must be sequential and start at 1.")
        return sorted_slides

    @field_validator("hashtags")
    @classmethod
    def normalize_hashtags(cls, hashtags: list[str]) -> list[str]:
        normalized: list[str] = []
        for hashtag in hashtags:
            cleaned = hashtag.strip()
            if not cleaned:
                continue
            if not cleaned.startswith("#"):
                cleaned = f"#{cleaned}"
            normalized.append(cleaned)

        if not normalized:
            raise ValueError("At least one hashtag is required.")
        return normalized


class GenerationRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    niche: str = Field(..., min_length=1)
    language: str = Field(..., min_length=1)
    slides_count: int = Field(..., ge=1, le=20)
    tone_of_voice: str = Field(..., min_length=1)
