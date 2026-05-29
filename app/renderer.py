import json
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from app.design_planner import build_design_plan
from app.schemas import CarouselOutput

CARD_WIDTH = 1080
CARD_HEIGHT = 1350


class CarouselRenderer:
    def __init__(self, templates_dir: Path, output_dir: Path) -> None:
        self.templates_dir = templates_dir
        self.output_dir = output_dir
        self.config_dir = templates_dir.parent / "config"
        self.last_output_dir = output_dir

        self.environment = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self.template = self.environment.get_template("card_v2.html")
        self.styles = (self.templates_dir / "style_v2.css").read_text(encoding="utf-8")
        self.brand = self._load_brand_config()

    def render_slides(self, carousel: CarouselOutput) -> list[Path]:
        run_dir = self._create_run_dir()
        self.last_output_dir = run_dir

        rendered_paths: list[Path] = []
        design_plan = build_design_plan(carousel.slides)
        self._save_manifest(run_dir, carousel, design_plan)

        print(f"\nDesign family: {design_plan.family}")

        with sync_playwright() as playwright:
            browser = self._launch_browser(playwright)
            page = browser.new_page(
                viewport={"width": CARD_WIDTH, "height": CARD_HEIGHT},
                device_scale_factor=1,
            )

            total_slides = len(carousel.slides)
            for slide in carousel.slides:
                slide_design = design_plan.slides[slide.number]
                html = self.template.render(
                    title=carousel.title,
                    slide=slide,
                    total_slides=total_slides,
                    styles=self.styles,
                    family=design_plan.family,
                    slide_design=slide_design,
                    brand=self.brand,
                )
                page.set_content(html, wait_until="load")

                image_path = run_dir / f"slide_{slide.number}.png"
                page.screenshot(path=str(image_path))
                rendered_paths.append(image_path)

            browser.close()

        return rendered_paths

    @staticmethod
    def _launch_browser(playwright):
        executable_path = os.getenv("CHROMIUM_EXECUTABLE_PATH", "").strip()
        launch_options = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        if executable_path:
            launch_options["executable_path"] = executable_path
            print(f"Using system Chromium: {executable_path}")
        return playwright.chromium.launch(**launch_options)

    def _create_run_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("run_%Y%m%d_%H%M%S")
        run_dir = self.output_dir / stamp
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _load_brand_config(self) -> dict[str, str]:
        config_path = self.config_dir / "brand.json"
        fallback = {
            "handle": "@carouselfactory",
            "footer_text": "Useful health content",
            "footer_username": "@carouselfactory",
            "default_mode": "random_family",
        }
        if not config_path.exists():
            return fallback

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return fallback

        return {**fallback, **data}

    def _save_manifest(self, run_dir: Path, carousel: CarouselOutput, design_plan) -> None:
        manifest = {
            "title": carousel.title,
            "design_family": design_plan.family,
            "slides": [
                {
                    "number": slide.number,
                    "layout": design_plan.slides[slide.number].layout,
                    "text_size": design_plan.slides[slide.number].text_size,
                    "headline": slide.headline,
                }
                for slide in carousel.slides
            ],
        }
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
