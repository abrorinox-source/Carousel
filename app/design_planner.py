from __future__ import annotations

import random
from dataclasses import dataclass

from app.theme_registry_simple import FAMILIES, LAYOUTS, TOKENS


@dataclass(frozen=True)
class SlideDesign:
    slide_number: int
    layout: str
    text_size: str


@dataclass(frozen=True)
class DesignPlan:
    family: str
    tokens: dict[str, str]
    slides: dict[int, SlideDesign]


def _text_size(headline: str, text: str) -> str:
    total = len(headline) + len(text)
    if total > 260:
        return "long"
    if total > 160:
        return "medium"
    return "short"


def build_design_plan(slides: list) -> DesignPlan:
    family = random.choice(FAMILIES)
    tokens = TOKENS[family]
    total = len(slides)
    previous_layout = ""
    planned: dict[int, SlideDesign] = {}

    for slide in slides:
        if slide.number == 1:
            choices = LAYOUTS["hero"]
        elif slide.number == total:
            choices = LAYOUTS["final"]
        else:
            choices = [item for item in LAYOUTS["body"] if item != previous_layout]
            if not choices:
                choices = LAYOUTS["body"]

        layout = random.choice(choices)
        previous_layout = layout
        planned[slide.number] = SlideDesign(
            slide_number=slide.number,
            layout=layout,
            text_size=_text_size(slide.headline, slide.text),
        )

    return DesignPlan(family=family, tokens=tokens, slides=planned)
