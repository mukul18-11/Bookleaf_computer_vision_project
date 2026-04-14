---
title: BookLeaf Cover Validator
emoji: 📘
colorFrom: orange
colorTo: red
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
---

# BookLeaf — Automated Book Cover Validator

An automated cover validation system built for **BookLeaf Publishing**. Upload
a front-cover image and the system runs a computer-vision pipeline that:

1. Uses **Google Cloud Vision OCR** to find every piece of text on the cover.
2. Calculates the **safe zone**, **badge zone** (bottom 9mm reserved for the
   "Winner of the 21st Century Emily Dickinson Award" emblem), and margin
   boundaries in pixels from the image DPI.
3. Flags any text that sits inside the badge zone or violates the cover's
   safe margins.
4. Returns a **PASS / REVIEW NEEDED** verdict with a specific fix for each
   issue (direction-based language — e.g. *"adjust the bottom margin"* —
   not unreliable OCR quotes).
5. Renders an annotated preview so the reviewer can see exactly where the
   problem is.

## How to use

1. Drag-drop or pick a book cover image (PNG or JPG, front cover, portrait).
2. Click **Validate cover**.
3. Read the status badge + issue list. Inspect the annotated cover for the
   coloured bounding boxes.

Three sample covers (clean / overlap / heavy-overlap) are wired in as
click-to-try examples.

## Stack

- **Gradio** — UI
- **OpenCV + NumPy + Pillow** — image handling and annotation
- **Google Cloud Vision API** — OCR (artistic fonts need high accuracy)
- **pdf2image** + `poppler-utils` — PDF support
- Pure-Python geometry for zone / overlap math

## Configuration

One secret is required at runtime:

| Secret | What | Why |
|---|---|---|
| `GOOGLE_CREDENTIALS_JSON` | Full JSON body of a Google Cloud service-account key with Vision API access | OCR backend |

On Hugging Face Spaces, set this under **Settings → Repository secrets**.
`app.py` writes the JSON to a temp file at startup and points
`GOOGLE_APPLICATION_CREDENTIALS` at it so the existing `modules/text_detector`
code works unchanged.

For local runs, either set `GOOGLE_CREDENTIALS_JSON` the same way, or put a
path-to-json in `GOOGLE_APPLICATION_CREDENTIALS` inside a `.env` file.

## Repo layout

```
app.py                      # Gradio UI — the demo entry point
main.py                     # Original CLI / Flask webhook entry (not used by the demo)
modules/
  cv_engine.py              # Pipeline orchestrator
  zone_mapper.py            # Safe zone + badge zone math
  text_detector.py          # Google Cloud Vision OCR
  overlap_checker.py        # Badge / margin / proximity checks
  classifier.py             # PASS vs REVIEW_NEEDED decision
  preprocessor.py           # PDF → image, ISBN parsing
  email_sender.py           # (unused in demo) production notification path
  airtable_client.py        # (unused in demo) production logging path
sample_covers/front/*.png   # 8 sample covers from BookLeaf
```

## Local dev

```
pip install -r requirements.txt
brew install poppler        # macOS; for Ubuntu: apt install poppler-utils
python app.py               # opens http://localhost:7860
```
