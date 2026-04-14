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
import re
from config import (
    OVERLAP_TOLERANCE_PIXELS,
    ISSUE_BADGE_OVERLAP,
    ISSUE_BADGE_BUFFER_CONFLICT,
    ISSUE_BADGE_MISSING,
    ISSUE_BADGE_ZONE_TEXT,
    ISSUE_AUTHOR_BADGE_CONFLICT,
    ISSUE_MARGIN_VIOLATION,
    ISSUE_BORDER_PROXIMITY,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    COLOR_OVERLAP,
    COLOR_WARNING,
    BORDER_PROXIMITY_FRAC_X,
    BORDER_PROXIMITY_FRAC_Y,
)

_BADGE_ALLOW_KEYWORDS_PRIMARY = {"emily", "dickinson"}
_BADGE_ALLOW_KEYWORDS_SECONDARY = {"winner", "21st", "century"}
_BADGE_COMPONENT_TOKENS = {
    "winner",
    "of",
    "the",
    "21st",
    "century",
    "emily",
    "dickinson",
    "award",
}


def _normalize_tokens(text):
    text = (text or "").lower()
    # Keep letters/numbers so tokens like "21st" survive.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [t for t in text.split() if t]


def is_allowed_badge_text(text):
    """Return True if this detection looks like the badge phrase itself.

    The badge zone is reserved, but the badge's own text should not be flagged
    as an overlap. We keep this conservative to avoid letting unrelated text pass.
    """
    tokens = set(_normalize_tokens(text))
    if not tokens:
        return False

    # In practice OCR often detects only the last line "Award".
    # Treat "award" as the required anchor token for the badge text.
    if "award" not in tokens:
        return False

    if tokens == {"award"}:
        return True

    has_primary = bool(tokens & _BADGE_ALLOW_KEYWORDS_PRIMARY)
    has_secondary = bool(tokens & _BADGE_ALLOW_KEYWORDS_SECONDARY)

    return has_primary or has_secondary


def is_badge_component_text(text):
    """True if this text looks like it belongs to the badge phrase (any token match).

    This is broader than is_allowed_badge_text() so we can build a badge bounding
    box even when OCR splits the phrase into separate words/lines.
    """
    tokens = set(_normalize_tokens(text))
    return bool(tokens & _BADGE_COMPONENT_TOKENS)


def _merge_bboxes(bboxes):
    left = min(b["left"] for b in bboxes)
    top = min(b["top"] for b in bboxes)
    right = max(b["right"] for b in bboxes)
    bottom = max(b["bottom"] for b in bboxes)
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def find_badge_phrase_bbox(word_detections, image_width, image_height):
    """Locate the badge phrase bbox using OCR word boxes.

    Strategy:
    - Look for an 'award' token near the bottom (anchor).
    - Expand to include nearby badge-component tokens above it.
    - Return merged bbox, or None if we can't find an anchor.
    """
    if not word_detections:
        return None

    # Anchor must contain "award" (helps avoid false positives).
    award_candidates = []
    for det in word_detections:
        tokens = set(_normalize_tokens(det.get("text", "")))
        if "award" not in tokens:
            continue
        bbox = det.get("bbox")
        if not bbox:
            continue
        cy = (bbox["top"] + bbox["bottom"]) / 2.0
        # Badge is expected in the lower half.
        if cy < image_height * 0.45:
            continue
        award_candidates.append(det)

    if not award_candidates:
        return None

    # Pick the lowest 'award' token as anchor (usually the final line).
    anchor = max(award_candidates, key=lambda d: d["bbox"]["bottom"])
    anchor_bbox = anchor["bbox"]
    anchor_cx = (anchor_bbox["left"] + anchor_bbox["right"]) / 2.0

    # Include other badge-component tokens in a vertical band above the anchor.
    # Keep this proportional to the image height.
    max_up_span = int(round(image_height * 0.18))  # generous but still "bottom-ish"
    band_top = max(0, anchor_bbox["top"] - max_up_span)
    band_bottom = min(image_height, anchor_bbox["bottom"] + int(round(image_height * 0.02)))

    components = []
    for det in word_detections:
        bbox = det.get("bbox")
        if not bbox:
            continue
        if not is_badge_component_text(det.get("text", "")):
            continue
        # Must overlap the vertical band around the anchor.
        if bbox["bottom"] < band_top or bbox["top"] > band_bottom:
            continue
        # Must be reasonably close to the anchor horizontally (badge is centered).
        cx = (bbox["left"] + bbox["right"]) / 2.0
        if abs(cx - anchor_cx) > image_width * 0.35:
            continue
        components.append(bbox)

    # Always include the anchor box even if OCR didn't pick up other tokens.
    if not components:
        components = [anchor_bbox]

    return _merge_bboxes(components)


def make_badge_buffer_zone(badge_bbox, image_width, image_height, buffer_multiplier=1.5):
    """Return a rectangle above the badge bbox with height = multiplier * badge height."""
    badge_h = max(1, int(badge_bbox["bottom"] - badge_bbox["top"]))
    buffer_h = int(round(badge_h * float(buffer_multiplier)))
    return {
        "left": badge_bbox["left"],
        "top": max(0, badge_bbox["top"] - buffer_h),
        "right": badge_bbox["right"],
        "bottom": badge_bbox["top"],
    }


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


def check_badge_overlap(detections, badge_zone, image_height):
    """Check if any detected text overlaps with the badge zone.

    THIS IS THE #1 CRITICAL CHECK.

    Args:
        detections: list of text detections with bbox
        badge_zone: badge zone rectangle {left, top, right, bottom}
        image_height: image height in pixels (for % reporting)

    Returns:
        list of overlap issues found
    """
    issues = []
    # For the badge zone we want to be strict. If text even slightly enters the
    # reserved bottom strip, it should be flagged. We therefore expand the zone
    # upward by the tolerance rather than shrinking the text bbox.
    tolerance = max(0, int(OVERLAP_TOLERANCE_PIXELS))
    strict_badge_zone = dict(badge_zone)
    strict_badge_zone["top"] = max(0, strict_badge_zone["top"] - tolerance)

    for det in detections:
        # Allow the badge phrase itself inside the reserved zone.
        if is_allowed_badge_text(det.get("text", "")):
            continue

        text_bbox = det["bbox"]
        if rectangles_overlap(text_bbox, strict_badge_zone):
            overlap = calculate_overlap_area(text_bbox, strict_badge_zone)

            # Determine how far into badge zone the text goes
            badge_zone_height = strict_badge_zone["bottom"] - strict_badge_zone["top"]
            penetration_pixels = text_bbox["bottom"] - strict_badge_zone["top"]
            penetration_pct = (
                (penetration_pixels / float(image_height) * 100.0) if image_height else 0.0
            )

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
                "penetration_px": int(round(penetration_pixels)),
                "penetration_pct_of_image": round(penetration_pct, 2),
                "confidence": round(confidence, 1),
                "correction": (
                    f"Move text '{det['text']}' at least "
                    f"{max(0, penetration_pixels)}px upward "
                    f"to clear the reserved bottom zone ({badge_zone_height}px)."
                ),
            }
            issues.append(issue)

    return issues


def list_text_in_badge_zone(detections, badge_zone):
    """List all OCR detections that intersect the badge zone (for debug / reporting)."""
    hits = []
    for det in detections:
        bbox = det.get("bbox")
        if not bbox:
            continue
        if rectangles_overlap(bbox, badge_zone):
            hits.append({
                "text": det.get("text", ""),
                "bbox": bbox,
                "allowed": bool(is_allowed_badge_text(det.get("text", ""))),
            })
    return hits


def check_reserved_badge_zone_only(word_detections, badge_zone):
    """Enforce bottom badge zone rules:

    - Bottom 9mm (4.43% height) is reserved for the badge phrase only.
    - Any other text inside the zone => CRITICAL.
    - If badge phrase is not found at all inside/near the zone => CRITICAL.
    """
    tol = max(0, int(OVERLAP_TOLERANCE_PIXELS))
    strict_zone = dict(badge_zone)
    strict_zone["top"] = max(0, strict_zone["top"] - tol)

    # Use a wider search area for the badge phrase itself.
    # OCR bounding boxes often place the badge text slightly above the
    # computed zone, so we look up to 2× the badge zone height above it.
    badge_zone_height = badge_zone["bottom"] - badge_zone["top"]
    badge_search_zone = dict(strict_zone)
    badge_search_zone["top"] = max(0, strict_zone["top"] - badge_zone_height * 2)

    hits = []
    other_hits = []
    badge_award_found = False

    for det in word_detections or []:
        bbox = det.get("bbox")
        if not bbox:
            continue

        text = det.get("text", "")
        in_strict = rectangles_overlap(bbox, strict_zone)
        in_search = rectangles_overlap(bbox, badge_search_zone)

        if not in_strict and not in_search:
            continue

        allowed = is_badge_component_text(text) or is_allowed_badge_text(text)

        if in_strict:
            hits.append({"text": text, "bbox": bbox, "allowed": bool(allowed)})

        if allowed:
            # Consider the badge "present" if OCR saw the anchor token "award"
            # anywhere in the badge search area (strict zone + region above).
            if in_search and (is_allowed_badge_text(text) or ("award" in set(_normalize_tokens(text)))):
                badge_award_found = True
        else:
            if in_strict:
                other_hits.append({"text": text, "bbox": bbox})

    issues = []

    for h in other_hits:
        overlap = calculate_overlap_area(h["bbox"], strict_zone)
        issues.append({
            "type": ISSUE_BADGE_ZONE_TEXT,
            "severity": SEVERITY_CRITICAL,
            "description": f"Text '{h['text']}' is present inside the reserved badge zone",
            "text": h["text"],
            "text_bbox": h["bbox"],
            "overlap_percentage": overlap["overlap_percentage"],
            "overlap_rect": overlap["overlap_rect"],
            "confidence": 99.0,
            "correction": "Remove/move this text out of the bottom badge zone.",
        })

    if not badge_award_found:
        issues.append({
            "type": ISSUE_BADGE_MISSING,
            "severity": SEVERITY_CRITICAL,
            "description": "Badge phrase not found inside the reserved bottom badge zone",
            "text": "",
            "text_bbox": strict_zone,
            "overlap_percentage": 0,
            "overlap_rect": None,
            "confidence": 95.0,
            "correction": (
                "Place the badge phrase 'Winner of the 21st Century Emily Dickinson Award' "
                "inside the bottom badge zone."
            ),
        })

    return {"issues": issues, "hits": hits, "zone": strict_zone}


def check_badge_phrase_and_buffer(word_detections, image_width, image_height):
    """Dynamic badge rule:
    1. Find the badge phrase bounding box (anchored by token 'award').
    2. Compute its height.
    3. Create a buffer zone directly above it with height = 1.5x badge height.
    4. If ANY other text overlaps the badge bbox or the buffer zone => CRITICAL.

    Returns:
        dict with: issues, badge_bbox, buffer_zone, hits
    """
    badge_bbox = find_badge_phrase_bbox(word_detections, image_width, image_height)
    if not badge_bbox:
        return {"issues": [], "badge_bbox": None, "buffer_zone": None, "hits": []}

    buffer_zone = make_badge_buffer_zone(badge_bbox, image_width, image_height, 1.5)

    # Union region for "what's inside the reserved area" debugging.
    reserved_union = {
        "left": min(badge_bbox["left"], buffer_zone["left"]),
        "top": min(badge_bbox["top"], buffer_zone["top"]),
        "right": max(badge_bbox["right"], buffer_zone["right"]),
        "bottom": max(badge_bbox["bottom"], buffer_zone["bottom"]),
    }

    hits = []
    issues = []

    for det in word_detections:
        bbox = det.get("bbox")
        if not bbox:
            continue

        if not rectangles_overlap(bbox, reserved_union):
            continue

        text = det.get("text", "")
        allowed = is_badge_component_text(text) or is_allowed_badge_text(text)
        hits.append({"text": text, "bbox": bbox, "allowed": bool(allowed)})

        if allowed:
            continue

        in_badge = rectangles_overlap(bbox, badge_bbox)
        in_buffer = rectangles_overlap(bbox, buffer_zone)
        if not (in_badge or in_buffer):
            continue

        overlap = calculate_overlap_area(bbox, reserved_union)
        issues.append({
            "type": ISSUE_BADGE_BUFFER_CONFLICT,
            "severity": SEVERITY_CRITICAL,
            "description": (
                f"Text '{text}' appears in reserved badge area "
                f"({'badge' if in_badge else 'buffer'})"
            ),
            "text": text,
            "text_bbox": bbox,
            "overlap_percentage": overlap["overlap_percentage"],
            "overlap_rect": overlap["overlap_rect"],
            "confidence": 99.0,
            "correction": "Remove/move this text out of the badge and buffer zones.",
        })

    return {
        "issues": issues,
        "badge_bbox": badge_bbox,
        "buffer_zone": buffer_zone,
        "hits": hits,
    }


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
        # Don't flag the badge phrase itself for margin violations.
        if is_allowed_badge_text(det.get("text", "")):
            continue

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


def check_border_proximity(
    detections,
    image_width,
    image_height,
    min_distance_frac_x=BORDER_PROXIMITY_FRAC_X,
    min_distance_frac_y=BORDER_PROXIMITY_FRAC_Y,
):
    """Check if any text is dangerously close to the image borders.

    Args:
        detections: list of text detections
        image_width: image width in pixels
        image_height: image height in pixels
        min_distance_frac_x: minimum safe distance from left/right as a fraction of width
        min_distance_frac_y: minimum safe distance from top/bottom as a fraction of height

    Returns:
        list of proximity warning issues
    """
    issues = []
    min_dist_x = int(round(image_width * float(min_distance_frac_x)))
    min_dist_y = int(round(image_height * float(min_distance_frac_y)))

    for det in detections:
        bbox = det["bbox"]
        too_close = []

        if bbox["left"] < min_dist_x:
            too_close.append("left edge")
        if bbox["right"] > image_width - min_dist_x:
            too_close.append("right edge")
        if bbox["top"] < min_dist_y:
            too_close.append("top edge")
        if bbox["bottom"] > image_height - min_dist_y:
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
                "correction": "Move text further away from the edges.",
            })

    return issues


def check_all_overlaps(word_detections, zones, line_detections=None):
    """Run all overlap and margin checks.

    Args:
        word_detections: word-level detections from OCR
        zones: output from zone_mapper.get_zones()
        line_detections: optional grouped line detections (better for margin checks)

    Returns:
        dict with:
            issues: list of all issues found
            badge_overlaps: count of badge zone overlaps
            margin_violations: count of margin violations
            proximity_warnings: count of border proximity warnings
    """
    w = zones["image_width"]
    h = zones["image_height"]

    all_issues = []

    # 1. CRITICAL: Reserved bottom badge zone rule (front covers only).
    badge_zone = zones.get("badge_zone") or {}
    badge_zone_height = (badge_zone.get("bottom", 0) - badge_zone.get("top", 0)) if badge_zone else 0

    if badge_zone_height > 0:
        badge_rule = check_reserved_badge_zone_only(word_detections, zones["badge_zone"])
        badge_issues = badge_rule["issues"]
        badge_zone_hits = badge_rule["hits"]
    else:
        # Back covers: no badge zone, so no badge checks.
        badge_issues = []
        badge_zone_hits = []

    all_issues.extend(badge_issues)

    margin_targets = line_detections if line_detections else word_detections

    # 2. WARNING: Check margin violations
    margin_issues = check_margin_violations(margin_targets, zones["safe_area"], w, h)
    all_issues.extend(margin_issues)

    # 3. WARNING: Check border proximity
    proximity_issues = check_border_proximity(margin_targets, w, h)
    all_issues.extend(proximity_issues)

    return {
        "issues": all_issues,
        "badge_overlaps": len(badge_issues),
        "margin_violations": len(margin_issues),
        "proximity_warnings": len(proximity_issues),
        "badge_zone_hits": badge_zone_hits,
        "badge_bbox": None,
        "badge_buffer_zone": None,
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
        if issue["type"] in (
            ISSUE_BADGE_OVERLAP,
            ISSUE_BADGE_BUFFER_CONFLICT,
            ISSUE_AUTHOR_BADGE_CONFLICT,
        ):
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
