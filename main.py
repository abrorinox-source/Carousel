from pathlib import Path

from dotenv import load_dotenv
from google.genai import errors

from app.ai_generator import AIGenerator
from app.renderer import CarouselRenderer
from app.schemas import GenerationRequest
from app.utils import save_caption_file


def ask_non_empty(prompt_label: str) -> str:
    while True:
        value = input(f"{prompt_label}: ").strip()
        if value:
            return value
        print("Please enter a value.")


def ask_slides_count() -> int:
    while True:
        raw_value = input("Slides count: ").strip()
        if not raw_value:
            print("Please enter a number.")
            continue

        if not raw_value.isdigit():
            print("Slides count must be a number.")
            continue

        count = int(raw_value)
        if count < 1 or count > 20:
            print("Slides count must be between 1 and 20.")
            continue
        return count


def build_request() -> GenerationRequest:
    topic = ask_non_empty("Topic")
    niche = ask_non_empty("Niche")
    language = ask_non_empty("Language")
    slides_count = ask_slides_count()
    tone_of_voice = ask_non_empty("Tone of voice")

    return GenerationRequest(
        topic=topic,
        niche=niche,
        language=language,
        slides_count=slides_count,
        tone_of_voice=tone_of_voice,
    )


def main() -> None:
    load_dotenv()

    project_root = Path(__file__).resolve().parent
    output_dir = project_root / "output"
    templates_dir = project_root / "templates"

    try:
        request = build_request()
        generator = AIGenerator()
        carousel = generator.generate(request)

        renderer = CarouselRenderer(templates_dir=templates_dir, output_dir=output_dir)
        image_paths = renderer.render_slides(carousel)

        caption_path = save_caption_file(carousel, output_dir)

        print("\nGenerated carousel JSON:")
        print(carousel.model_dump_json(indent=2))

        print("\nSaved files:")
        for image_path in image_paths:
            print(f"- {image_path}")
        print(f"- {caption_path}")

    except (ValueError, RuntimeError, errors.APIError) as exc:
        print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
