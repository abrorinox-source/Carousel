from pathlib import Path

from app.schemas import CarouselOutput


def save_caption_file(carousel: CarouselOutput, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    content = "\n".join(
        [
            f"Caption: {carousel.caption}",
            "",
            f"CTA: {carousel.cta}",
            "",
            "Hashtags:",
            " ".join(carousel.hashtags),
        ]
    )

    caption_path = output_dir / "caption.txt"
    caption_path.write_text(content, encoding="utf-8")
    return caption_path
