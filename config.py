"""
BookLeaf Cover Validation - Configuration
All thresholds, specifications, and paths for the CV pipeline.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# BOOK COVER PHYSICAL SPECIFICATIONS
# =============================================================================
COVER_WIDTH_INCHES = 6
COVER_HEIGHT_INCHES = 8

# Safe Area Margins (millimeters)
MARGIN_SIDES_MM = 3       # 3mm from left and right edges
MARGIN_TOP_MM = 3         # 3mm from top edge
MARGIN_BOTTOM_MM = 6      # 6mm from bottom edge

# Award Badge Reserved Zone
BADGE_ZONE_HEIGHT_MM = 9  # Bottom 9mm reserved for "Winner of 21st Century Emily Dickinson Award"

# -----------------------------------------------------------------------------
# Percentage-based zone sizing (resolution independent)
# -----------------------------------------------------------------------------
# We treat every cover as 6x8 inches physically, but we avoid DPI/mm->px conversion.
# Instead, we convert physical distances into *fractions* of the image dimensions.
#
# Key fact: 9mm out of an 8-inch tall cover is always ~4.43% of the cover height.
# 8 inches = 203.2mm, so 9 / 203.2 ≈ 0.04429.
BADGE_ZONE_HEIGHT_FRAC = 0.0443

# Fractions for margins based on the 6x8in cover spec.
# (Computed once here so zone mapping can be purely percentage-based.)
_COVER_WIDTH_MM = COVER_WIDTH_INCHES * 25.4
_COVER_HEIGHT_MM = COVER_HEIGHT_INCHES * 25.4
MARGIN_SIDES_FRAC = MARGIN_SIDES_MM / _COVER_WIDTH_MM
MARGIN_TOP_FRAC = MARGIN_TOP_MM / _COVER_HEIGHT_MM
MARGIN_BOTTOM_FRAC = MARGIN_BOTTOM_MM / _COVER_HEIGHT_MM

# Border proximity warning (default was 2mm). Expressed as fractions of width/height.
BORDER_PROXIMITY_FRAC_X = 2.0 / _COVER_WIDTH_MM
BORDER_PROXIMITY_FRAC_Y = 2.0 / _COVER_HEIGHT_MM

# =============================================================================
# DETECTION THRESHOLDS
# =============================================================================
CRITICAL_CONFIDENCE_THRESHOLD = 0.95   # 95% for critical detections (badge overlap)
OVERALL_CONFIDENCE_THRESHOLD = 0.90    # 90% overall processing accuracy
OVERLAP_TOLERANCE_PIXELS = 5           # Small tolerance for edge cases

# =============================================================================
# IMAGE QUALITY THRESHOLDS
# =============================================================================
# Toggle: if False, blur/pixelation/resolution issues are not produced.
# (You can still enable it later if BookLeaf wants quality validation.)
ENABLE_QUALITY_CHECKS = False
MIN_DPI = 150                          # Minimum acceptable DPI
MIN_WIDTH_PIXELS = 1200                # Minimum image width
BLUR_THRESHOLD = 100.0                 # Laplacian variance below this = blurry
PIXELATION_BLOCK_SIZE = 8             # Block size for pixelation detection


# =============================================================================
# CLASSIFICATION THRESHOLDS
# =============================================================================
REVIEW_CONFIDENCE_THRESHOLD = 85       # Below this confidence -> REVIEW_NEEDED

# =============================================================================
# FILE PATHS
# =============================================================================
SAMPLE_COVERS_DIR = os.path.join(os.path.dirname(__file__), "sample_covers")
SAMPLE_FRONT_DIR = os.path.join(SAMPLE_COVERS_DIR, "front")
SAMPLE_BACK_DIR = os.path.join(SAMPLE_COVERS_DIR, "back")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
ANNOTATED_DIR = os.path.join(OUTPUT_DIR, "annotated")
REPORTS_DIR = os.path.join(OUTPUT_DIR, "reports")

# =============================================================================
# ANNOTATION COLORS (BGR format for OpenCV)
# =============================================================================
COLOR_SAFE_ZONE = (0, 255, 0)          # Green - safe area boundary
COLOR_BADGE_ZONE = (0, 0, 255)         # Red - badge zone (danger)
COLOR_TEXT_BOX = (255, 200, 0)         # Cyan-ish - detected text
COLOR_OVERLAP = (0, 0, 255)            # Red - overlap detected
COLOR_MARGIN = (255, 255, 0)           # Cyan - margin lines
COLOR_WARNING = (0, 165, 255)          # Orange - warnings

# =============================================================================
# ISSUE TYPES AND SEVERITIES
# =============================================================================
ISSUE_BADGE_OVERLAP = "BADGE_OVERLAP"
ISSUE_BADGE_BUFFER_CONFLICT = "BADGE_BUFFER_CONFLICT"
ISSUE_BADGE_MISSING = "BADGE_MISSING"
ISSUE_BADGE_ZONE_TEXT = "BADGE_ZONE_TEXT"
ISSUE_AUTHOR_BADGE_CONFLICT = "AUTHOR_BADGE_CONFLICT"
ISSUE_MARGIN_VIOLATION = "MARGIN_VIOLATION"
ISSUE_BORDER_PROXIMITY = "BORDER_PROXIMITY"
ISSUE_LOW_RESOLUTION = "LOW_RESOLUTION"
ISSUE_BLURRY_IMAGE = "BLURRY_IMAGE"
ISSUE_PIXELATED_IMAGE = "PIXELATED_IMAGE"

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

# =============================================================================
# STATUS VALUES
# =============================================================================
STATUS_PASS = "PASS"
STATUS_REVIEW = "REVIEW_NEEDED"

# =============================================================================
# API CREDENTIALS (loaded from .env)
# =============================================================================
GOOGLE_APPLICATION_CREDENTIALS = os.path.expanduser(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
).strip()
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Cover Analysis")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "bookleaf-cv-secret")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


def mm_to_pixels(mm_value, dpi):
    """Convert millimeters to pixels based on DPI.

    Formula: pixels = mm * (DPI / 25.4)
    Since 1 inch = 25.4mm
    """
    return int(mm_value * (dpi / 25.4))


def calculate_dpi(image_width_pixels):
    """Calculate DPI from image width, knowing the cover is 6 inches wide."""
    return image_width_pixels / COVER_WIDTH_INCHES
