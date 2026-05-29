import base64
import mimetypes
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from app.schemas import CarouselOutput

CARD_WIDTH = 1080
CARD_HEIGHT = 1350


class CarouselRenderer:
    def __init__(self, templates_dir: Path, output_dir: Path) -> None:
        self.templates_dir = templates_dir
        self.output_dir = output_dir
        self.assets_dir = templates_dir.parent / "assets"
        self.background_image_path = self.assets_dir / "doctor.jpg"

        self.environment = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self.template = self.environment.get_template("card.html")
        self.styles = (self.templates_dir / "style.css").read_text(encoding="utf-8")

    def render_slides(self, carousel: CarouselOutput) -> list[Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._clear_old_slide_images()

        rendered_paths: list[Path] = []

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(
                viewport={"width": CARD_WIDTH, "height": CARD_HEIGHT},
                device_scale_factor=1,
            )

            total_slides = len(carousel.slides)
            background_image_uri = self._background_image_data_uri()
            for slide in carousel.slides:
                html = self.template.render(
                    title=carousel.title,
                    slide=slide,
                    total_slides=total_slides,
                    styles=self.styles,
                    background_image_uri=background_image_uri,
                )
                page.set_content(html, wait_until="load")

                image_path = self.output_dir / f"slide_{slide.number}.png"
                page.screenshot(path=str(image_path))
                rendered_paths.append(image_path)

            browser.close()

        return rendered_paths

    def _clear_old_slide_images(self) -> None:
        for image_file in self.output_dir.glob("slide_*.png"):
            image_file.unlink(missing_ok=True)

    def _background_image_data_uri(self) -> str:
        if not self.background_image_path.exists():
            return ""

        mime_type = mimetypes.guess_type(self.background_image_path.name)[0] or "image/jpeg"
        encoded_image = base64.b64encode(self.background_image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded_image}"
