# Carousel Factory

A local Python MVP that generates AI carousel content with Gemini and renders every slide into PNG images.

## Tech stack

- Python
- Google AI Studio / Gemini API
- python-dotenv
- pydantic
- jinja2
- playwright

## Project structure

```text
carousel-factory/
  .env
  .env.example
  README.md
  requirements.txt
  main.py
  app/
    __init__.py
    ai_generator.py
    renderer.py
    schemas.py
    utils.py
  assets/
    doctor.jpg
  templates/
    card.html
    style.css
  output/
```

## Setup

1. Create virtual environment:

```bash
python -m venv .venv
```

2. Activate virtual environment:

Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Install Playwright Chromium:

```bash
playwright install chromium
```

5. Add your key to `.env`:

```env
GEMINI_API_KEY=your_real_google_ai_studio_key
GEMINI_MODEL=gemini-3.5-flash
```

6. Run the app:

```bash
python main.py
```

## Run flow

When running `python main.py`, the terminal will ask:

- `Topic:`
- `Niche:`
- `Language:`
- `Slides count:`
- `Tone of voice:`

The app then:

1. Generates structured carousel content with Gemini.
2. Validates and parses the response using Pydantic.
3. Renders each slide into PNG using Jinja2 + Playwright.
4. Saves slide images in `output/slide_1.png`, `output/slide_2.png`, etc.
5. Saves `caption`, `cta`, and `hashtags` in `output/caption.txt`.

## Output JSON shape

```json
{
  "title": "string",
  "slides": [
    {
      "number": 1,
      "headline": "string",
      "text": "string"
    }
  ],
  "caption": "string",
  "cta": "string",
  "hashtags": ["string"]
}
```
