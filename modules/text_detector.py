"""
Text Detector Module
Detects all text on a book cover image and returns bounding box positions.

Primary: Google Cloud Vision API (best for stylized/artistic book fonts)
Fallback: EasyOCR (works offline, no API key needed)

Each detection returns: {text, bbox: {left, top, right, bottom}, confidence}
"""

import cv2
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)


def detect_text_google_vision(image_path):
    """Detect text using Google Cloud Vision API.

    Returns word-level and block-level text detections with bounding boxes.

    Args:
        image_path: Path to image file

    Returns:
        list of dicts: [{text, bbox: {left, top, right, bottom}, confidence, level}]
    """
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()

    with open(image_path, "rb") as f:
        content = f.read()

    image = vision.Image(content=content)
    response = client.text_detection(image=image)

    if response.error.message:
        raise Exception(f"Google Vision API error: {response.error.message}")

    detections = []
    annotations = response.text_annotations

    if not annotations:
        return detections

    # Skip first annotation (it's the full text block)
    for i, annotation in enumerate(annotations):
        vertices = annotation.bounding_poly.vertices

        # Get bounding box from polygon vertices
        xs = [v.x for v in vertices]
        ys = [v.y for v in vertices]

        bbox = {
            "left": min(xs),
            "top": min(ys),
            "right": max(xs),
            "bottom": max(ys),
        }

        detections.append({
            "text": annotation.description,
            "bbox": bbox,
            "confidence": 0.95 if i > 0 else 1.0,  # Vision API doesn't give per-word confidence
            "level": "full_text" if i == 0 else "word",
        })

    return detections


def detect_text_easyocr(image_path):
    """Detect text using EasyOCR (offline fallback).

    Args:
        image_path: Path to image file

    Returns:
        list of dicts: [{text, bbox: {left, top, right, bottom}, confidence, level}]
    """
    import easyocr

    reader = easyocr.Reader(["en"], gpu=False)
    results = reader.readtext(image_path)

    detections = []
    for bbox_points, text, confidence in results:
        # EasyOCR returns 4 corner points: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        xs = [point[0] for point in bbox_points]
        ys = [point[1] for point in bbox_points]

        bbox = {
            "left": int(min(xs)),
            "top": int(min(ys)),
            "right": int(max(xs)),
            "bottom": int(max(ys)),
        }

        detections.append({
            "text": text,
            "bbox": bbox,
            "confidence": round(float(confidence), 4),
            "level": "word",
        })

    return detections


def detect_text(image_path, use_google_vision=True):
    """Detect all text on a book cover image.

    Tries Google Cloud Vision first (if enabled and credentials available),
    falls back to EasyOCR.

    Args:
        image_path: Path to image file
        use_google_vision: Whether to try Google Vision API first

    Returns:
        dict with:
            detections: list of text detections with bounding boxes
            full_text: complete text found on the cover
            method: which OCR method was used
    """
    detections = []
    method = None

    # Try Google Cloud Vision first
    if use_google_vision and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            detections = detect_text_google_vision(image_path)
            method = "google_vision"
            logger.info(f"Google Vision detected {len(detections)} text elements")
        except Exception as e:
            logger.warning(f"Google Vision failed, falling back to EasyOCR: {e}")

    # Fallback to EasyOCR
    if not detections:
        try:
            detections = detect_text_easyocr(image_path)
            method = "easyocr"
            logger.info(f"EasyOCR detected {len(detections)} text elements")
        except Exception as e:
            logger.error(f"EasyOCR also failed: {e}")
            return {"detections": [], "full_text": "", "method": "none"}

    # Extract full text (join all word-level detections)
    full_text_parts = []
    word_detections = []
    for d in detections:
        if d["level"] == "full_text":
            full_text_parts.insert(0, d["text"])
        else:
            word_detections.append(d)
            full_text_parts.append(d["text"])

    full_text = " ".join(full_text_parts) if not any(
        d["level"] == "full_text" for d in detections
    ) else next(
        (d["text"] for d in detections if d["level"] == "full_text"), ""
    )

    return {
        "detections": word_detections if word_detections else detections,
        "full_text": full_text,
        "method": method,
    }


def group_text_into_lines(detections, line_threshold=15):
    """Group word-level detections into text lines based on vertical position.

    Words at similar Y positions are grouped into the same line.

    Args:
        detections: list of text detections
        line_threshold: max vertical pixel difference to consider same line

    Returns:
        list of line dicts: [{text, bbox: {left, top, right, bottom}, words: [...]}]
    """
    if not detections:
        return []

    # Sort by top position
    sorted_dets = sorted(detections, key=lambda d: d["bbox"]["top"])

    lines = []
    current_line = [sorted_dets[0]]

    for det in sorted_dets[1:]:
        # Check if this word is on the same line (similar Y position)
        current_center_y = np.mean([d["bbox"]["top"] + d["bbox"]["bottom"] for d in current_line]) / 2
        det_center_y = (det["bbox"]["top"] + det["bbox"]["bottom"]) / 2

        if abs(det_center_y - current_center_y) <= line_threshold:
            current_line.append(det)
        else:
            lines.append(_merge_line(current_line))
            current_line = [det]

    if current_line:
        lines.append(_merge_line(current_line))

    return lines


def _merge_line(words):
    """Merge a list of word detections into a single line detection."""
    # Sort words left-to-right
    words = sorted(words, key=lambda w: w["bbox"]["left"])

    text = " ".join(w["text"] for w in words)
    bbox = {
        "left": min(w["bbox"]["left"] for w in words),
        "top": min(w["bbox"]["top"] for w in words),
        "right": max(w["bbox"]["right"] for w in words),
        "bottom": max(w["bbox"]["bottom"] for w in words),
    }
    avg_confidence = np.mean([w["confidence"] for w in words])

    return {
        "text": text,
        "bbox": bbox,
        "confidence": round(float(avg_confidence), 4),
        "words": words,
    }


def draw_text_detections(image, detections, color=(255, 200, 0), thickness=2):
    """Draw bounding boxes around detected text on the image.

    Args:
        image: OpenCV image (BGR numpy array)
        detections: list of text detections with bbox
        color: BGR color tuple
        thickness: line thickness

    Returns:
        Annotated image copy
    """
    annotated = image.copy()

    for det in detections:
        bbox = det["bbox"]
        cv2.rectangle(
            annotated,
            (bbox["left"], bbox["top"]),
            (bbox["right"], bbox["bottom"]),
            color,
            thickness,
        )
        # Put text label above the box
        label = f"{det['text'][:30]} ({det['confidence']:.0%})"
        label_y = max(bbox["top"] - 5, 15)
        cv2.putText(
            annotated, label,
            (bbox["left"], label_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1,
        )

    return annotated


if __name__ == "__main__":
    """Quick test: detect text on sample covers."""
    from config import SAMPLE_FRONT_DIR, ANNOTATED_DIR

    test_image = os.path.join(SAMPLE_FRONT_DIR, "shabd_clean.png")

    if not os.path.exists(test_image):
        print(f"Test image not found: {test_image}")
        exit(1)

    print(f"Detecting text in: {test_image}")
    result = detect_text(test_image, use_google_vision=False)

    print(f"\nMethod: {result['method']}")
    print(f"Full text: {result['full_text'][:200]}")
    print(f"\nDetections ({len(result['detections'])}):")
    for det in result["detections"]:
        print(f"  '{det['text']}' at {det['bbox']} conf={det['confidence']:.2%}")

    # Group into lines
    lines = group_text_into_lines(result["detections"])
    print(f"\nGrouped into {len(lines)} lines:")
    for line in lines:
        print(f"  '{line['text']}' at y={line['bbox']['top']}-{line['bbox']['bottom']}")

    # Draw and save
    image = cv2.imread(test_image)
    annotated = draw_text_detections(image, result["detections"])
    output_path = os.path.join(ANNOTATED_DIR, "text_detection_test.png")
    cv2.imwrite(output_path, annotated)
    print(f"\nSaved annotated image to: {output_path}")
