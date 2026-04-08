"""
Overlap Checker Module
THE MOST CRITICAL MODULE - Checks if any detected text overlaps with
the badge zone or violates safe margins.

Core algorithm: Rectangle intersection detection.
Two rectangles overlap if:
    a.left < b.right AND a.right > b.left AND a.top < b.bottom AND a.bottom > b.top
"""

import cv2
import numpy as np
from config import (
    OVERLAP_TOLERANCE_PIXELS,
    ISSUE_BADGE_OVERLAP,
    ISSUE_AUTHOR_BADGE_CONFLICT,
    ISSUE_MARGIN_VIOLATION,
    ISSUE_BORDER_PROXIMITY,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    COLOR_OVERLAP,
    COLOR_WARNING,
    mm_to_pixels,
)


def rectangles_overlap(a, b):
    """Check if rectangle a overlaps rectangle b.

    Args:
        a: dict with keys {left, top, right, bottom}
        b: dict with keys {left, top, right, bottom}

    Returns:
        bool: True if rectangles overlap
    """
    return (
        a["left"] < b["right"]
        and a["right"] > b["left"]
        and a["top"] < b["bottom"]
        and a["bottom"] > b["top"]
    )


def calculate_overlap_area(a, b):
    """Calculate the intersection area between two rectangles.

    Args:
        a: dict with keys {left, top, right, bottom}
        b: dict with keys {left, top, right, bottom}

    Returns:
        dict with: overlap_area (pixels^2), overlap_percentage (% of rect a),
                   overlap_rect ({left, top, right, bottom} of intersection)
    """
    # Calculate intersection rectangle
    inter_left = max(a["left"], b["left"])
    inter_top = max(a["top"], b["top"])
    inter_right = min(a["right"], b["right"])
    inter_bottom = min(a["bottom"], b["bottom"])

    # Calculate widths/heights
    inter_width = max(0, inter_right - inter_left)
    inter_height = max(0, inter_bottom - inter_top)
    overlap_area = inter_width * inter_height

    # Calculate overlap as percentage of rectangle a
    a_area = (a["right"] - a["left"]) * (a["bottom"] - a["top"])
    overlap_percentage = (overlap_area / a_area * 100) if a_area > 0 else 0

    overlap_rect = None
    if overlap_area > 0:
        overlap_rect = {
            "left": inter_left,
            "top": inter_top,
            "right": inter_right,
            "bottom": inter_bottom,
        }

    return {
        "overlap_area": overlap_area,
        "overlap_percentage": round(overlap_percentage, 1),
        "overlap_rect": overlap_rect,
    }


def distance_to_zone(text_bbox, zone_bbox):
    """Calculate minimum distance from a text box to a zone boundary.

    Negative distance means overlap.

    Args:
        text_bbox: text bounding box {left, top, right, bottom}
        zone_bbox: zone boundary {left, top, right, bottom}

    Returns:
        float: minimum pixel distance (negative = overlap)
    """
    # Distance from text bottom to zone top (for badge zone below text)
    dist_bottom_to_top = zone_bbox["top"] - text_bbox["bottom"]

    return dist_bottom_to_top


def check_badge_overlap(detections, badge_zone, dpi):
    """Check if any detected text overlaps with the badge zone.

    THIS IS THE #1 CRITICAL CHECK.

    Args:
        detections: list of text detections with bbox
        badge_zone: badge zone rectangle {left, top, right, bottom}
        dpi: image DPI for mm conversion

    Returns:
        list of overlap issues found
    """
    issues = []
    tolerance = OVERLAP_TOLERANCE_PIXELS

    for det in detections:
        text_bbox = det["bbox"]

        # Apply tolerance: shrink text box slightly to avoid false positives on edges
        adjusted_bbox = {
            "left": text_bbox["left"] + tolerance,
            "top": text_bbox["top"] + tolerance,
            "right": text_bbox["right"] - tolerance,
            "bottom": text_bbox["bottom"] - tolerance,
        }

        if rectangles_overlap(adjusted_bbox, badge_zone):
            overlap = calculate_overlap_area(text_bbox, badge_zone)

            # Determine how far into badge zone the text goes
            badge_zone_height = badge_zone["bottom"] - badge_zone["top"]
            penetration_pixels = text_bbox["bottom"] - badge_zone["top"]
            penetration_mm = penetration_pixels / (dpi / 25.4) if dpi > 0 else 0

            # Higher overlap % = higher confidence that this is a real problem
            confidence = min(99, 70 + overlap["overlap_percentage"] * 0.3)

            issue = {
                "type": ISSUE_BADGE_OVERLAP,
                "severity": SEVERITY_CRITICAL,
                "description": (
                    f"Text '{det['text']}' overlaps with award badge zone "
                    f"by {overlap['overlap_percentage']:.1f}%"
                ),
                "text": det["text"],
                "text_bbox": text_bbox,
                "overlap_percentage": overlap["overlap_percentage"],
                "overlap_rect": overlap["overlap_rect"],
                "penetration_mm": round(penetration_mm, 1),
                "confidence": round(confidence, 1),
                "correction": (
                    f"Move text '{det['text']}' at least {penetration_mm + 3:.0f}mm "
                    f"above the bottom edge to clear the badge zone."
                ),
            }
            issues.append(issue)

    return issues


def check_margin_violations(detections, safe_area, image_width, image_height):
    """Check if any text extends outside the safe area margins.

    Args:
        detections: list of text detections with bbox
        safe_area: safe area rectangle {left, top, right, bottom}
        image_width: image width in pixels
        image_height: image height in pixels

    Returns:
        list of margin violation issues
    """
    issues = []
    tolerance = OVERLAP_TOLERANCE_PIXELS

    for det in detections:
        bbox = det["bbox"]
        violations = []

        # Check each margin
        if bbox["left"] < safe_area["left"] - tolerance:
            violations.append(f"left margin by {safe_area['left'] - bbox['left']}px")
        if bbox["right"] > safe_area["right"] + tolerance:
            violations.append(f"right margin by {bbox['right'] - safe_area['right']}px")
        if bbox["top"] < safe_area["top"] - tolerance:
            violations.append(f"top margin by {safe_area['top'] - bbox['top']}px")
        if bbox["bottom"] > safe_area["bottom"] + tolerance:
            violations.append(f"bottom margin by {bbox['bottom'] - safe_area['bottom']}px")

        if violations:
            issues.append({
                "type": ISSUE_MARGIN_VIOLATION,
                "severity": SEVERITY_WARNING,
                "description": (
                    f"Text '{det['text']}' extends beyond {', '.join(violations)}"
                ),
                "text": det["text"],
                "text_bbox": bbox,
                "violations": violations,
                "confidence": 85.0,
                "correction": "Reposition text to stay within the safe margins.",
            })

    return issues


def check_border_proximity(detections, image_width, image_height, dpi, min_distance_mm=2):
    """Check if any text is dangerously close to the image borders.

    Args:
        detections: list of text detections
        image_width: image width in pixels
        image_height: image height in pixels
        dpi: image DPI
        min_distance_mm: minimum safe distance from border in mm

    Returns:
        list of proximity warning issues
    """
    issues = []
    min_dist_px = mm_to_pixels(min_distance_mm, dpi)

    for det in detections:
        bbox = det["bbox"]
        too_close = []

        if bbox["left"] < min_dist_px:
            too_close.append("left edge")
        if bbox["right"] > image_width - min_dist_px:
            too_close.append("right edge")
        if bbox["top"] < min_dist_px:
            too_close.append("top edge")
        if bbox["bottom"] > image_height - min_dist_px:
            too_close.append("bottom edge")

        if too_close:
            issues.append({
                "type": ISSUE_BORDER_PROXIMITY,
                "severity": SEVERITY_WARNING,
                "description": (
                    f"Text '{det['text']}' is too close to {', '.join(too_close)}"
                ),
                "text": det["text"],
                "text_bbox": bbox,
                "edges": too_close,
                "confidence": 80.0,
                "correction": f"Move text at least {min_distance_mm}mm away from edges.",
            })

    return issues


def check_all_overlaps(detections, zones):
    """Run all overlap and margin checks.

    Args:
        detections: list of text detections from text_detector
        zones: output from zone_mapper.get_zones()

    Returns:
        dict with:
            issues: list of all issues found
            badge_overlaps: count of badge zone overlaps
            margin_violations: count of margin violations
            proximity_warnings: count of border proximity warnings
    """
    dpi = zones["dpi"]
    w = zones["image_width"]
    h = zones["image_height"]

    all_issues = []

    # 1. CRITICAL: Check badge zone overlaps
    badge_issues = check_badge_overlap(detections, zones["badge_zone"], dpi)
    all_issues.extend(badge_issues)

    # 2. WARNING: Check margin violations
    margin_issues = check_margin_violations(detections, zones["safe_area"], w, h)
    all_issues.extend(margin_issues)

    # 3. WARNING: Check border proximity
    proximity_issues = check_border_proximity(detections, w, h, dpi)
    all_issues.extend(proximity_issues)

    return {
        "issues": all_issues,
        "badge_overlaps": len(badge_issues),
        "margin_violations": len(margin_issues),
        "proximity_warnings": len(proximity_issues),
    }


def draw_overlaps(image, issues):
    """Draw overlap visualizations on the image.

    Args:
        image: OpenCV image (BGR numpy array)
        issues: list of issues from check_all_overlaps

    Returns:
        Annotated image copy
    """
    annotated = image.copy()

    for issue in issues:
        if issue["type"] in (ISSUE_BADGE_OVERLAP, ISSUE_AUTHOR_BADGE_CONFLICT):
            # Draw red highlight on overlap area
            if "overlap_rect" in issue and issue["overlap_rect"]:
                rect = issue["overlap_rect"]
                overlay = annotated.copy()
                cv2.rectangle(
                    overlay,
                    (rect["left"], rect["top"]),
                    (rect["right"], rect["bottom"]),
                    COLOR_OVERLAP,
                    -1,
                )
                cv2.addWeighted(overlay, 0.4, annotated, 0.6, 0, annotated)

            # Draw red border around the offending text
            bbox = issue["text_bbox"]
            cv2.rectangle(
                annotated,
                (bbox["left"], bbox["top"]),
                (bbox["right"], bbox["bottom"]),
                COLOR_OVERLAP,
                3,
            )
            cv2.putText(
                annotated,
                f"OVERLAP: {issue['overlap_percentage']:.0f}%",
                (bbox["left"], bbox["top"] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                COLOR_OVERLAP,
                2,
            )

        elif issue["type"] in (ISSUE_MARGIN_VIOLATION, ISSUE_BORDER_PROXIMITY):
            bbox = issue["text_bbox"]
            cv2.rectangle(
                annotated,
                (bbox["left"], bbox["top"]),
                (bbox["right"], bbox["bottom"]),
                COLOR_WARNING,
                2,
            )

    return annotated


if __name__ == "__main__":
    """Quick test: check overlaps on a sample cover."""
    import os
    from config import SAMPLE_FRONT_DIR, ANNOTATED_DIR
    from modules.zone_mapper import get_zones

    # Test with the overlap cover
    test_image_path = os.path.join(SAMPLE_FRONT_DIR, "tainted_emotion_overlap.png")
    image = cv2.imread(test_image_path)
    h, w = image.shape[:2]

    zones = get_zones(w, h)

    # Create some fake detections for testing the overlap logic
    # (In real usage, these come from text_detector)
    fake_detections = [
        {
            "text": "For those who feel more than they can express",
            "bbox": {"left": 400, "top": h - 60, "right": 750, "bottom": h - 5},
            "confidence": 0.92,
        },
        {
            "text": "Ojal Jain",
            "bbox": {"left": 500, "top": 400, "right": 700, "bottom": 450},
            "confidence": 0.95,
        },
    ]

    result = check_all_overlaps(fake_detections, zones)
    print(f"Badge overlaps: {result['badge_overlaps']}")
    print(f"Margin violations: {result['margin_violations']}")
    print(f"Proximity warnings: {result['proximity_warnings']}")
    for issue in result["issues"]:
        print(f"  [{issue['severity']}] {issue['description']}")
