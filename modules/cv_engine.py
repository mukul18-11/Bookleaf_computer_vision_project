"""
CV Engine Module
The main computer vision analysis module that ties together:
    - zone_mapper: calculates safe areas and badge zones
    - text_detector: finds all text and positions via OCR
    - overlap_checker: checks text vs zones for violations
    - quality_checker: checks blur, pixelation, resolution
    - classifier: makes PASS / REVIEW_NEEDED decision

This is the "brain" of the system.
"""

import cv2
import os
import json
import logging
from datetime import datetime

from modules.zone_mapper import get_zones, draw_zones
from modules.text_detector import detect_text, draw_text_detections, group_text_into_lines
from modules.overlap_checker import check_all_overlaps, draw_overlaps
from modules.quality_checker import check_quality
from modules.classifier import build_classification_result
from config import ANNOTATED_DIR, REPORTS_DIR

logger = logging.getLogger(__name__)


def analyze_cover(image_path, isbn="unknown", use_google_vision=True, cover_type="front"):
    """Run the complete CV analysis pipeline on a book cover image.

    Steps:
        1. Load image and determine dimensions/DPI
        2. Calculate zones (safe area, badge zone, margins)
        3. Detect all text with OCR (bounding boxes + content)
        4. Check for overlaps (text vs badge zone, text vs margins)
        5. Check image quality (blur, pixelation, resolution)
        6. Classify result (PASS or REVIEW_NEEDED)
        7. Create annotated image showing all findings
        8. Save report

    Args:
        image_path: path to the book cover image
        isbn: book ISBN for the report
        use_google_vision: whether to try Google Cloud Vision API

    Returns:
        Complete analysis result dict
    """
    logger.info(f"Starting analysis for: {image_path} (ISBN: {isbn})")

    # Step 1: Load image
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not load image: {image_path}")

    h, w = image.shape[:2]
    logger.info(f"Image loaded: {w}x{h} pixels")

    # Step 2: Calculate zones
    zones = get_zones(w, h, cover_type=cover_type)
    logger.info(f"Zones calculated (DPI: {zones['dpi']:.0f})")

    # Step 3: Detect text via OCR
    text_result = detect_text(image_path, use_google_vision=use_google_vision)
    detections = text_result["detections"]
    logger.info(f"OCR detected {len(detections)} text elements via {text_result['method']}")

    # Group text into lines for better analysis
    text_lines = group_text_into_lines(detections)
    logger.info(f"Grouped into {len(text_lines)} text lines")

    # Step 4: Check overlaps - use both individual words and grouped lines
    # Lines give better context for overlap detection
    overlap_targets = text_lines if text_lines else detections
    overlap_result = check_all_overlaps(overlap_targets, zones)
    logger.info(
        f"Overlap check: {overlap_result['badge_overlaps']} badge overlaps, "
        f"{overlap_result['margin_violations']} margin violations"
    )

    # Step 5: Check image quality
    quality_result = check_quality(image)
    logger.info(
        f"Quality check: blur={quality_result['blur']['is_blurry']}, "
        f"pixelated={quality_result['pixelation']['is_pixelated']}, "
        f"low_res={quality_result['resolution']['is_low_res']}"
    )

    # Combine all issues
    all_issues = overlap_result["issues"] + quality_result["issues"]

    # Step 6: Create annotated image
    annotated = image.copy()
    annotated = draw_zones(annotated, zones)
    annotated = draw_text_detections(annotated, detections)
    annotated = draw_overlaps(annotated, overlap_result["issues"])

    # Add status text at the top
    status_text = f"ISBN: {isbn} | Texts: {len(detections)} | Issues: {len(all_issues)}"
    cv2.putText(
        annotated, status_text,
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
    )

    # Save annotated image
    os.makedirs(ANNOTATED_DIR, exist_ok=True)
    annotated_filename = f"{isbn}_annotated.png"
    annotated_path = os.path.join(ANNOTATED_DIR, annotated_filename)
    cv2.imwrite(annotated_path, annotated)
    logger.info(f"Annotated image saved: {annotated_path}")

    # Step 7: Build classification result
    result = build_classification_result(
        isbn=isbn,
        issues=all_issues,
        quality_result=quality_result,
        ocr_detections=detections,
        annotated_image_path=annotated_path,
    )

    # Add extra metadata
    result["image_path"] = image_path
    result["image_dimensions"] = {"width": w, "height": h}
    result["dpi"] = zones["dpi"]
    result["ocr_method"] = text_result["method"]
    result["text_detected"] = len(detections)
    result["full_text"] = text_result["full_text"][:500]
    result["text_lines"] = [
        {"text": line["text"], "bbox": line["bbox"]}
        for line in text_lines
    ]

    # Save report as JSON
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_filename = f"{isbn}_report.json"
    report_path = os.path.join(REPORTS_DIR, report_filename)
    with open(report_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"Report saved: {report_path}")

    logger.info(f"Analysis complete: {result['status']} (confidence: {result['confidence']}%)")
    return result


def analyze_batch(image_dir, use_google_vision=True):
    """Analyze all cover images in a directory.

    Args:
        image_dir: path to directory containing cover images
        use_google_vision: whether to try Google Cloud Vision API

    Returns:
        list of analysis results
    """
    results = []
    supported_extensions = (".png", ".jpg", ".jpeg", ".bmp", ".tiff")

    for filename in sorted(os.listdir(image_dir)):
        if not filename.lower().endswith(supported_extensions):
            continue

        image_path = os.path.join(image_dir, filename)
        isbn = filename.split("_")[0] if "_" in filename else os.path.splitext(filename)[0]

        try:
            result = analyze_cover(image_path, isbn=isbn, use_google_vision=use_google_vision)
            results.append(result)
            print(f"  {result['status']:15} | {result['confidence']:5.1f}% | {filename}")
        except Exception as e:
            logger.error(f"Failed to analyze {filename}: {e}")
            results.append({
                "isbn": isbn,
                "status": "ERROR",
                "error": str(e),
                "image_path": image_path,
            })
            print(f"  {'ERROR':15} | {'N/A':>5} | {filename}: {e}")

    return results


if __name__ == "__main__":
    """Test: analyze all sample front covers."""
    from config import SAMPLE_FRONT_DIR

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 70)
    print("BookLeaf Cover Validation - Batch Analysis")
    print("=" * 70)
    print(f"\nAnalyzing covers in: {SAMPLE_FRONT_DIR}\n")
    print(f"  {'STATUS':15} | {'CONF':>5} | FILENAME")
    print(f"  {'-'*15} | {'-'*5} | {'-'*30}")

    results = analyze_batch(SAMPLE_FRONT_DIR, use_google_vision=False)

    print(f"\n{'=' * 70}")
    print(f"Total: {len(results)} covers analyzed")
    passed = sum(1 for r in results if r.get("status") == "PASS")
    review = sum(1 for r in results if r.get("status") == "REVIEW_NEEDED")
    errors = sum(1 for r in results if r.get("status") == "ERROR")
    print(f"  PASS: {passed} | REVIEW_NEEDED: {review} | ERRORS: {errors}")
