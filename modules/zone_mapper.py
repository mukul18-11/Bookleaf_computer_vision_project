"""
Zone Mapper Module
Calculates safe areas, badge zones, and margins in pixel coordinates
based on image dimensions and DPI.

Every zone is a rectangle: {left, top, right, bottom}
"""

import cv2
import numpy as np
from config import (
    COVER_WIDTH_INCHES,
    MARGIN_SIDES_MM,
    MARGIN_TOP_MM,
    MARGIN_BOTTOM_MM,
    BADGE_ZONE_HEIGHT_MM,
    mm_to_pixels,
    calculate_dpi,
    COLOR_SAFE_ZONE,
    COLOR_BADGE_ZONE,
    COLOR_MARGIN,
)


def get_zones(image_width, image_height, dpi=None):
    """Calculate all zone boundaries in pixels for a given image.

    Args:
        image_width: Image width in pixels
        image_height: Image height in pixels
        dpi: Dots per inch. If None, calculated from image width assuming 6-inch cover.

    Returns:
        dict with keys: margins, safe_area, badge_zone, dpi
        Each zone is {left, top, right, bottom}
    """
    if dpi is None:
        dpi = calculate_dpi(image_width)

    # Convert mm margins to pixels
    margin_left = mm_to_pixels(MARGIN_SIDES_MM, dpi)
    margin_right = mm_to_pixels(MARGIN_SIDES_MM, dpi)
    margin_top = mm_to_pixels(MARGIN_TOP_MM, dpi)
    margin_bottom = mm_to_pixels(MARGIN_BOTTOM_MM, dpi)
    badge_height = mm_to_pixels(BADGE_ZONE_HEIGHT_MM, dpi)

    # Margins define the unsafe border strip around the cover
    margins = {
        "left": margin_left,
        "top": margin_top,
        "right": margin_right,
        "bottom": margin_bottom,
    }

    # Safe area = inside all margins AND above badge zone
    safe_area = {
        "left": margin_left,
        "top": margin_top,
        "right": image_width - margin_right,
        "bottom": image_height - margin_bottom - badge_height,
    }

    # Badge zone = bottom strip of the cover (9mm tall, full width)
    badge_zone = {
        "left": 0,
        "top": image_height - badge_height,
        "right": image_width,
        "bottom": image_height,
    }

    return {
        "margins": margins,
        "safe_area": safe_area,
        "badge_zone": badge_zone,
        "dpi": dpi,
        "image_width": image_width,
        "image_height": image_height,
    }


def draw_zones(image, zones):
    """Draw zone boundaries on image for visualization.

    Args:
        image: OpenCV image (BGR numpy array)
        zones: Output from get_zones()

    Returns:
        Annotated image copy with zone rectangles drawn
    """
    annotated = image.copy()
    safe = zones["safe_area"]
    badge = zones["badge_zone"]
    margins = zones["margins"]
    h, w = annotated.shape[:2]

    # Draw safe area boundary (green, dashed effect with thicker line)
    cv2.rectangle(
        annotated,
        (safe["left"], safe["top"]),
        (safe["right"], safe["bottom"]),
        COLOR_SAFE_ZONE,
        2,
    )
    cv2.putText(
        annotated, "SAFE AREA",
        (safe["left"] + 10, safe["top"] + 25),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_SAFE_ZONE, 2,
    )

    # Draw badge zone (red, filled with transparency)
    overlay = annotated.copy()
    cv2.rectangle(
        overlay,
        (badge["left"], badge["top"]),
        (badge["right"], badge["bottom"]),
        COLOR_BADGE_ZONE,
        -1,  # filled
    )
    cv2.addWeighted(overlay, 0.3, annotated, 0.7, 0, annotated)

    # Draw badge zone border
    cv2.rectangle(
        annotated,
        (badge["left"], badge["top"]),
        (badge["right"], badge["bottom"]),
        COLOR_BADGE_ZONE,
        2,
    )
    cv2.putText(
        annotated, "BADGE ZONE (9mm) - NO TEXT HERE",
        (badge["left"] + 10, badge["top"] + 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2,
    )

    # Draw margin lines (cyan)
    # Top margin
    cv2.line(annotated, (0, margins["top"]), (w, margins["top"]), COLOR_MARGIN, 1)
    # Bottom margin
    cv2.line(
        annotated,
        (0, h - margins["bottom"]),
        (w, h - margins["bottom"]),
        COLOR_MARGIN, 1,
    )
    # Left margin
    cv2.line(annotated, (margins["left"], 0), (margins["left"], h), COLOR_MARGIN, 1)
    # Right margin
    cv2.line(
        annotated,
        (w - margins["right"], 0),
        (w - margins["right"], h),
        COLOR_MARGIN, 1,
    )

    return annotated


if __name__ == "__main__":
    """Quick test: load a sample cover and visualize zones."""
    import os
    from config import SAMPLE_FRONT_DIR, ANNOTATED_DIR

    test_image_path = os.path.join(SAMPLE_FRONT_DIR, "shabd_clean.png")

    if not os.path.exists(test_image_path):
        print(f"Test image not found: {test_image_path}")
        exit(1)

    image = cv2.imread(test_image_path)
    h, w = image.shape[:2]
    print(f"Image size: {w} x {h} pixels")

    zones = get_zones(w, h)
    print(f"DPI: {zones['dpi']:.0f}")
    print(f"Safe area: {zones['safe_area']}")
    print(f"Badge zone: {zones['badge_zone']}")
    print(f"Margins: {zones['margins']}")

    annotated = draw_zones(image, zones)
    output_path = os.path.join(ANNOTATED_DIR, "zones_visualization.png")
    cv2.imwrite(output_path, annotated)
    print(f"Saved zones visualization to: {output_path}")
