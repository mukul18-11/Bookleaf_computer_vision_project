# 🤖 LLM CONTEXT FILE — READ THIS FIRST

> **INSTRUCTION TO ANY AI/LLM:** This file contains ALL the context you need to help the user (Mukul Kumar) complete his project. Read this file FIRST, then refer to the guide files in the `Guide/` folder (files 01-06) for detailed breakdowns. After reading, you should be able to immediately start helping with code, debugging, and architecture without asking for background.

---

## 📋 PROJECT SUMMARY (ONE PARAGRAPH)

Mukul is building an **Automated Book Cover Validation System** for **BookLeaf Publishing** (a real publishing company, India/USA/UK). The system uses **Computer Vision (OpenCV + Google Cloud Vision API for OCR)** to analyze book cover images, detect layout violations (especially author name overlapping with an award badge at the bottom), and then automatically **logs results to Airtable**, **sends personalized emails to authors**, and is triggered via **Google Drive webhooks** (push notifications, NOT polling). This is a **72-hour technical assignment** (Round 2 interview task). The deadline is ~April 9, 2026.

---

## 👤 USER PROFILE

- **Name:** Mukul Kumar
- **Skill Level:** Intermediate Python developer. Familiar with web development (React, Next.js, Vite). Has used n8n, Supabase, Brevo email API before. New to Computer Vision/OpenCV/OCR.
- **OS:** macOS
- **Previous Work:** Built a BookLeaf Customer Query Bot (chatbot) using n8n + Supabase for Round 1 of this interview process.
- **Learning Style:** Prefers simple, plain-English explanations. Asks "why" before "how." Wants to UNDERSTAND the code, not just copy-paste.
- **Time Constraint:** ~50 hours of concentrated work available. With AI help, estimated 25-30 hours of actual coding.

---

## 🎯 THE ASSIGNMENT REQUIREMENTS (FROM BOOKLEAF PUBLISHING)

### What BookLeaf Wants:
An automated system that processes 100-150 book covers monthly for their "Bestseller Breakthrough Package." Currently humans manually review covers — they want AI to do it.

### The #1 Most Critical Detection:
**Author names overlapping with the "21st Century Emily Dickinson Award" badge** at the bottom of book covers. This is the PRIMARY problem to solve. 95% accuracy required for this specific check.

### Complete System Requirements:

#### 1. Computer Vision Detection
- **CRITICAL (95% accuracy):** Text overlap with award badge area, Author name positioning conflicts
- **ADDITIONAL:** Text-to-border spacing violations, Back cover text alignment, Image resolution/quality

#### 2. Book Cover Specifications
- **Dimensions:** Front cover = 6 × 8 inches
- **Safe margins:** 3mm from sides, 3mm from top, 6mm from bottom
- **Badge zone:** Bottom 9mm of front cover — RESERVED for "Winner of 21st Century Emily Dickinson Award" emblem
- **Author name:** Can be anywhere on front cover BUT must stay in safe area AND cannot overlap badge zone
- **Quality:** No pixelation, text must be legible, elements must respect margins
- **Reference video:** https://www.youtube.com/watch?v=0DeuNeoIG4k (timestamp 4:20 for safe areas)

#### 3. Workflow Automation
- **Trigger:** Book cover uploaded to Google Drive folder
- **File naming:** `ISBN_text.extension` (e.g., `1234567890123_text.pdf`)
- **Formats:** PDF and PNG
- **Flow:** Upload → Analyze → Classify → Update Airtable → Send Email

#### 4. Status Classification (Two-tier)
- **PASS:** All validation rules met, no issues detected
- **REVIEW NEEDED:** Borderline cases (low confidence, minor spacing issues, potential overlaps)

#### 5. Airtable Integration
Required fields: Book ID (ISBN), Detection Timestamp, Issue Type & Severity, Status, Confidence Score (0-100%), Visual Annotations URL, Correction Instructions, Revision Tracking

#### 6. Email Notification System
- Personalized greeting with author name
- Clear status indication (✅ PASS or ❌ issues)
- Specific issues with text-based markers
- Step-by-step correction instructions
- Expected resubmission timeline
- Support contact info
- ISBN → author email mapping for personalization

### Performance Requirements:
- Processing accuracy: **90%+**
- Manual review reduction: **80%**
- Real-time processing upon upload
- Scalable to 100-150 covers/month

### Deliverables:
1. Fully functional workflow system (detection + Drive + Airtable + Email)
2. Documentation (architecture, API details, config, testing methodology)
3. Testing & Validation (demo with sample covers, accuracy report, edge cases)
4. Working demo + source code + test results + sample Airtable records + example emails
5. **Loom video walkthrough**

### Evaluation Criteria:
1. Detection accuracy (especially badge overlap) — **TOP PRIORITY**
2. Automation completeness
3. System reliability & error handling
4. Code quality & documentation
5. User interface clarity
6. Email communication effectiveness
7. Integration robustness

### Sample Materials:
- BookLeaf provided ~9 book cover images (front + back for each)
- Good cover example: badge at bottom, author name above, clear text, within margins
- Bad cover example: text overlaps badge area, spacing violations, author name conflicts

---

## 🔧 DECIDED TECH STACK

These decisions have already been made. Do NOT suggest alternatives unless the user asks.

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | **Python 3.10+** | Required for OpenCV, OCR |
| Computer Vision | **OpenCV (cv2)** | Image loading, zone drawing, annotations |
| OCR/Text Detection | **Google Cloud Vision API** | Best accuracy for artistic/stylized book cover fonts. Free tier: 1000 images/month. Fallback: EasyOCR |
| PDF Processing | **pdf2image + Pillow** | Convert PDF covers to images |
| File Trigger | **Google Drive Webhooks + Flask** | INSTANT push notifications when files uploaded. NOT polling. |
| Database | **Airtable API (pyairtable)** | Store analysis results |
| Email | **smtplib or Brevo API** | Send personalized notifications |
| Web Server | **Flask** | Receive webhook notifications from Google Drive |
| Dev Tunneling | **ngrok** | Expose local Flask server to internet during development |
| Config | **python-dotenv** | Manage API keys securely |
| Math/Arrays | **NumPy** | Image array operations |

### Key Architecture Decision: Webhooks, NOT Polling
The user specifically chose **Google Drive Push Notifications (webhooks)** over polling. The system works like this:
1. Flask server runs with endpoint `POST /webhook/drive`
2. Google Drive is configured to "watch" a folder and notify this endpoint
3. When a file is uploaded → Google sends HTTP POST to the Flask endpoint
4. Flask handler downloads the file and triggers the CV analysis pipeline
5. During development, ngrok exposes localhost to the internet

---

## 📁 PROJECT STRUCTURE

```
Bookleaf_computer_vision_project/
│
├── LLM_CONTEXT_README.md          ← THIS FILE (context for any LLM)
├── main.py                        ← Entry point — Flask server + pipeline
├── config.py                      ← Configuration (thresholds, paths)
├── .env                           ← API keys (never commit!)
├── requirements.txt               ← Python dependencies
├── README.md                      ← Project documentation for submission
│
├── Guide/                         ← Learning guides (reference only, not code)
│   ├── 01_PROJECT_OVERVIEW_EXPLAINED.txt
│   ├── 02_WHAT_YOU_NEED_TO_LEARN.txt
│   ├── 03_TECH_STACK_AND_ARCHITECTURE.txt
│   ├── 04_TIMELINE_AND_PLAN.txt
│   ├── 05_KEY_CONCEPTS_CHEATSHEET.txt
│   └── 06_STEP_BY_STEP_EXECUTION_GUIDE.txt
│
├── modules/                       ← Core Python modules
│   ├── __init__.py
│   ├── webhook_server.py          ← Flask server for Google Drive webhooks
│   ├── preprocessor.py            ← PDF→Image, ISBN extraction
│   ├── cv_engine.py               ← Main CV analysis (ties all CV modules)
│   ├── text_detector.py           ← OCR text detection (Google Cloud Vision)
│   ├── zone_mapper.py             ← Calculate safe zones, badge zones in pixels
│   ├── overlap_checker.py         ← Check text vs zones, calculate overlap
│   ├── quality_checker.py         ← Image resolution, blur detection
│   ├── classifier.py              ← PASS / REVIEW_NEEDED decision logic
│   ├── airtable_client.py         ← Airtable API CRUD operations
│   └── email_sender.py            ← Email notification system
│
├── templates/                     ← HTML email templates
│   ├── pass_email.html
│   └── review_email.html
│
├── sample_covers/                 ← The 9 sample book covers from BookLeaf
│   ├── front/
│   └── back/
│
├── tests/                         ← Test scripts
│   ├── test_detection.py
│   ├── test_overlap.py
│   └── test_pipeline.py
│
├── output/                        ← Analysis results
│   ├── annotated/                 ← Images with visual annotations
│   └── reports/                   ← JSON/text reports
│
└── docs/                          ← Submission documentation
    ├── architecture.md
    ├── api_integration.md
    └── testing_results.md
```

---

## 🔑 KEY CONFIGURATION VALUES

```python
# Cover Specifications
COVER_WIDTH_INCHES = 6
COVER_HEIGHT_INCHES = 8

# Safe Area Margins (convert to pixels using DPI)
MARGIN_SIDES_MM = 3        # 3mm from left and right edges
MARGIN_TOP_MM = 3          # 3mm from top
MARGIN_BOTTOM_MM = 6       # 6mm from bottom

# Award Badge Reserved Zone
BADGE_ZONE_HEIGHT_MM = 9   # Bottom 9mm reserved for badge

# Detection Thresholds
CRITICAL_CONFIDENCE_THRESHOLD = 0.95
OVERALL_CONFIDENCE_THRESHOLD = 0.90
OVERLAP_TOLERANCE_PIXELS = 5

# Quality Thresholds
MIN_DPI = 150
BLUR_THRESHOLD = 100  # Laplacian variance

# Conversion Formula
# pixels = mm_value * (DPI / 25.4)
# DPI = image_width_pixels / 6  (cover is 6 inches wide)
```

---

## 🧠 KEY ALGORITHMS

### 1. MM to Pixels Conversion
```python
def mm_to_pixels(mm, dpi):
    return int(mm * (dpi / 25.4))

# DPI calculated from image: DPI = image_width / 6
```

### 2. Rectangle Overlap Detection (THE CORE ALGORITHM)
```python
def rectangles_overlap(a, b):
    """Check if rectangle a overlaps rectangle b.
    Each rect is dict with keys: left, top, right, bottom"""
    return (a['left'] < b['right'] and
            a['right'] > b['left'] and
            a['top'] < b['bottom'] and
            a['bottom'] > b['top'])
```

### 3. Badge Zone Calculation
```python
# Badge zone is the bottom 9mm of the cover
badge_zone = {
    'left': 0,
    'top': image_height - mm_to_pixels(9, dpi),
    'right': image_width,
    'bottom': image_height
}
```

### 4. Classification Logic
```python
def classify(issues, overall_confidence):
    if len(issues) == 0:
        return "PASS"
    if any(i['severity'] == 'CRITICAL' for i in issues):
        return "REVIEW_NEEDED"
    if overall_confidence < 85:
        return "REVIEW_NEEDED"
    return "PASS"
```

---

## 📊 EXPECTED OUTPUT FORMAT

```json
{
  "isbn": "9780134685991",
  "status": "PASS or REVIEW_NEEDED",
  "confidence": 95.5,
  "issues": [
    {
      "type": "BADGE_OVERLAP",
      "severity": "CRITICAL",
      "description": "Author name overlaps with award badge zone",
      "text": "John Smith",
      "overlap_percentage": 45.2,
      "correction": "Move author name at least 15mm above the bottom edge"
    }
  ],
  "annotated_image_path": "output/annotated/9780134685991_annotated.png",
  "timestamp": "2026-04-08T17:30:00"
}
```

---

## 📦 DEPENDENCIES

```
# requirements.txt
opencv-python
numpy
Pillow
pdf2image
google-cloud-vision
google-api-python-client
google-auth
google-auth-httplib2
google-auth-oauthlib
flask
pyairtable
python-dotenv
requests
watchdog  # for local development fallback
```

### System Dependencies (macOS):
```bash
brew install poppler     # Required for pdf2image
brew install ngrok       # For exposing local Flask server
```

---

## ✅ PROGRESS TRACKER

> **UPDATE THIS SECTION AS YOU COMPLETE TASKS**

- [ ] Environment setup (venv, packages installed)
- [ ] Sample covers added to project
- [ ] Zone mapper module built
- [ ] Text detector module built (Google Cloud Vision OCR)
- [ ] Overlap checker module built
- [ ] Quality checker module built
- [ ] CV engine module built (ties all CV modules together)
- [ ] Classifier module built
- [ ] Preprocessor module built (PDF handling, ISBN extraction)
- [ ] Tested on sample covers — accuracy verified
- [ ] Airtable account created and table set up
- [ ] Airtable client module built
- [ ] Email templates created (PASS + REVIEW)
- [ ] Email sender module built
- [ ] Google Cloud project set up (Drive API + Vision API)
- [ ] Flask webhook server built
- [ ] Full pipeline wired in main.py
- [ ] End-to-end test passed
- [ ] Documentation written
- [ ] Loom video recorded
- [ ] Submitted

---

## 🚨 IMPORTANT NOTES FOR ANY LLM HELPING

1. **WEBHOOK NOT POLLING** — The user explicitly chose webhook approach for Google Drive. Do not suggest polling or watchdog as the primary approach (watchdog is only for local development fallback).

2. **GOOGLE CLOUD VISION for OCR** — The user chose this over EasyOCR and Tesseract because book covers use artistic/stylized fonts that need high accuracy. Free tier is sufficient (1000 images/month, user has ~18 images).

3. **THE USER WANTS TO UNDERSTAND** — Don't just dump code. Explain what each part does and why. The user is learning CV for the first time.

4. **BADGE OVERLAP IS #1 PRIORITY** — If time is short, focus on getting badge overlap detection working perfectly before adding other features. This is what BookLeaf cares about most.

5. **COVER SPECS:** 6×8 inches, 3mm side margins, 6mm bottom margin, bottom 9mm is badge zone. All measurements need converting to pixels using DPI.

6. **FILE NAMING:** `ISBN_text.pdf` — extract ISBN by splitting on underscore: `filename.split("_")[0]`

7. **TWO STATUSES ONLY:** PASS or REVIEW_NEEDED. Nothing else.

8. **THE USER HAS ~9 SAMPLE COVERS** — front and back of each book. These are provided by BookLeaf for testing.

9. **PREVIOUS CONTEXT:** The user completed Round 1 (BookLeaf chatbot with n8n + Supabase). This is Round 2. Different project, same company.

10. **SUBMISSION INCLUDES:** Working demo, source code, documentation, test results, sample Airtable records, sample emails, Loom video.

---

## 📚 REFERENCE FILES

For deeper detail on any topic, read these files in the `Guide/` folder:

| File | Contents |
|------|----------|
| `01_PROJECT_OVERVIEW_EXPLAINED.txt` | Full assignment explained in plain English |
| `02_WHAT_YOU_NEED_TO_LEARN.txt` | Technologies to learn, prioritized with resources |
| `03_TECH_STACK_AND_ARCHITECTURE.txt` | System architecture diagram, folder structure, config values |
| `04_TIMELINE_AND_PLAN.txt` | Hour-by-hour plan broken into 11 blocks |
| `05_KEY_CONCEPTS_CHEATSHEET.txt` | CV, OCR, coordinates, overlap math, confidence scoring explained |
| `06_STEP_BY_STEP_EXECUTION_GUIDE.txt` | Step-by-step coding guide — what to build in what order |

---

## 🔗 EXTERNAL RESOURCES

- BookLeaf Assignment Doc: Private Google Doc (screenshots available in Guide/)
- Safe Area Reference Video: https://www.youtube.com/watch?v=0DeuNeoIG4k (4:20 timestamp)
- OpenCV Docs: https://docs.opencv.org/4.x/
- Google Cloud Vision: https://cloud.google.com/vision/docs
- Google Drive Push Notifications: https://developers.google.com/drive/api/guides/push
- Airtable API: https://airtable.com/developers/web/api/introduction
- pyairtable: https://pyairtable.readthedocs.io/
- Flask: https://flask.palletsprojects.com/
- ngrok: https://ngrok.com/docs

---

*Last updated: April 8, 2026*
*Created by: AI assistant (Antigravity/Claude) to provide full project context*
