# Carousel Factory

A local Python MVP that generates AI carousel content with Gemini and renders every slide into PNG images.

## Tech stack

- Python
- Google AI Studio / Gemini API
- python-dotenv
- pydantic
- jinja2
- playwright
- simple keyword RAG over local `.txt` and `.md` files

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
    rag.py
    renderer.py
    schemas.py
    utils.py
  assets/
    doctor.jpg
  knowledge/
    medical_rules.md
    source_material.example.txt
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

1. Searches local files in `knowledge/` using simple keyword RAG.
2. Adds the best matching chunks to the Gemini prompt.
3. Generates structured carousel content with Gemini.
4. Validates and parses the response using Pydantic.
5. Renders each slide into PNG using Jinja2 + Playwright.
6. Saves slide images in `output/slide_1.png`, `output/slide_2.png`, etc.
7. Saves `caption`, `cta`, and `hashtags` in `output/caption.txt`.

## Instagram publish setup

Instagram publishing needs public image URLs. This repo now supports a local VM folder served through a temporary public tunnel.

1. Start the bot:

```bash
python bot.py
```

The bot will automatically start the public tunnel helper if `PUBLIC_BASE_URL` is not already set.

If you want to run the tunnel manually, use:

```bash
python scripts/public_tunnel.py
```

2. The script serves the project root locally and exposes it with a public URL.
3. It writes the public base URL to `.public_base_url`.
4. `app/instagram_publisher.py` uses that URL to build the `image_url` values for Meta Graph API.

Optional environment settings:

```env
PUBLIC_BASE_URL_FILE=.public_base_url
PUBLIC_UPLOAD_DIR=output
```

If you already have a public host or CDN, you can set `PUBLIC_BASE_URL` directly instead of using the tunnel file.

## Simple RAG workflow

The app currently supports local knowledge files with these extensions:

```text
.txt
.md
```

To use client materials:

1. Convert `.docx` or `.pdf` files to `.txt` first.
2. Put the converted files into the `knowledge/` folder.
3. Use clear file names, for example:

```text
knowledge/thyroid_voc_phrases.txt
knowledge/thyroid_lecture_notes.txt
knowledge/brand_profile.md
```

When you run `python main.py`, the app will print which knowledge chunks were used:

```text
RAG context used:
- thyroid_voc_phrases.txt | score=8
- medical_rules.md | score=3
```

This is not vector search yet. It is a lightweight MVP search that scores chunks by keyword matches from topic, niche, and tone of voice.

## Medical safety note

For medical topics, keep the content educational. The prompt tells the model not to diagnose, prescribe medication, recommend dosages, or tell people to stop/change medication.

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
