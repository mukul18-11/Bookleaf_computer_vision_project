"""
Quality Checker Module
Checks image quality: blur detection (Laplacian variance),
pixelation detection, and resolution/DPI validation.
"""

import cv2
import numpy as np
from config import (
    MIN_DPI,
    MIN_WIDTH_PIXELS,
    BLUR_THRESHOLD,
    PIXELATION_BLOCK_SIZE,
    ISSUE_LOW_RESOLUTION,
    ISSUE_BLURRY_IMAGE,
    ISSUE_PIXELATED_IMAGE,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
    calculate_dpi,
)


def check_blur(image):
    """Detect if image is blurry using Laplacian variance.

    The Laplacian operator highlights regions of rapid intensity change (edges).
    A sharp image has many strong edges -> high variance.
    A blurry image has weak/no edges -> low variance.

    Args:
        image: OpenCV image (BGR numpy array)

    Returns:
        dict with: is_blurry (bool), variance (float), threshold (float)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = laplacian.var()

    return {
        "is_blurry": variance < BLUR_THRESHOLD,
        "variance": round(variance, 2),
        "threshold": BLUR_THRESHOLD,
    }


def check_pixelation(image):
    """Detect if image is pixelated by comparing block-level vs pixel-level detail.

    Pixelated images have uniform color blocks. We downsample and upsample
    the image, then compare with original. If the difference is small,
    the image was already blocky (pixelated).

    Args:
        image: OpenCV image (BGR numpy array)

    Returns:
        dict with: is_pixelated (bool), score (float)
    """
    h, w = image.shape[:2]
    block = PIXELATION_BLOCK_SIZE

    # Downsample then upsample to simulate pixelation
    small = cv2.resize(image, (w // block, h // block), interpolation=cv2.INTER_LINEAR)
    reconstructed = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)

    # Compare original vs reconstructed
    diff = cv2.absdiff(image, reconstructed)
    score = np.mean(diff)

    # Low difference = image was already blocky = pixelated
    # Threshold: if score < 10, image looks same after block-averaging -> pixelated
    is_pixelated = score < 10.0

    return {
        "is_pixelated": is_pixelated,
        "score": round(float(score), 2),
    }


def check_resolution(image_width, image_height):
    """Check if image meets minimum resolution requirements.

    Args:
        image_width: Image width in pixels
        image_height: Image height in pixels

    Returns:
        dict with: is_low_res (bool), dpi (float), min_dpi (int), width (int)
    """
    dpi = calculate_dpi(image_width)

    return {
        "is_low_res": dpi < MIN_DPI or image_width < MIN_WIDTH_PIXELS,
        "dpi": round(dpi, 1),
        "min_dpi": MIN_DPI,
        "width": image_width,
        "min_width": MIN_WIDTH_PIXELS,
    }


def check_quality(image):
    """Run all quality checks on an image.

    Args:
        image: OpenCV image (BGR numpy array)

    Returns:
        dict with:
            issues: list of issue dicts (type, severity, description, details)
            blur: blur check results
            pixelation: pixelation check results
            resolution: resolution check results
    """
    h, w = image.shape[:2]
    issues = []

    # 1. Blur detection
    blur = check_blur(image)
    if blur["is_blurry"]:
        issues.append({
            "type": ISSUE_BLURRY_IMAGE,
            "severity": SEVERITY_WARNING,
            "description": (
                f"Image appears blurry (Laplacian variance: {blur['variance']}, "
                f"threshold: {blur['threshold']})"
            ),
            "details": blur,
            "correction": "Re-upload a sharper, higher-quality image. Avoid camera shake during capture.",
        })

    # 2. Pixelation detection
    pixelation = check_pixelation(image)
    if pixelation["is_pixelated"]:
        issues.append({
            "type": ISSUE_PIXELATED_IMAGE,
            "severity": SEVERITY_WARNING,
            "description": (
                f"Image appears pixelated (block similarity score: {pixelation['score']})"
            ),
            "details": pixelation,
            "correction": "Re-upload a higher resolution image. Do not zoom/crop low-resolution source files.",
        })

    # 3. Resolution check
    resolution = check_resolution(w, h)
    if resolution["is_low_res"]:
        severity = SEVERITY_CRITICAL if resolution["dpi"] < 100 else SEVERITY_WARNING
        issues.append({
            "type": ISSUE_LOW_RESOLUTION,
            "severity": severity,
            "description": (
                f"Image resolution too low (DPI: {resolution['dpi']}, "
                f"width: {resolution['width']}px, "
                f"minimum: {resolution['min_dpi']} DPI / {resolution['min_width']}px)"
            ),
            "details": resolution,
            "correction": f"Re-export the cover at minimum {MIN_DPI} DPI ({MIN_WIDTH_PIXELS}px wide).",
        })

    return {
        "issues": issues,
        "blur": blur,
        "pixelation": pixelation,
        "resolution": resolution,
    }


if __name__ == "__main__":
    """Quick test: check quality of sample covers."""
    import os
    from config import SAMPLE_FRONT_DIR

    for filename in sorted(os.listdir(SAMPLE_FRONT_DIR)):
        if not filename.endswith(".png"):
            continue
        path = os.path.join(SAMPLE_FRONT_DIR, filename)
        image = cv2.imread(path)
        if image is None:
            continue

        print(f"\n--- {filename} ---")
        result = check_quality(image)
        print(f"  Blur: variance={result['blur']['variance']}, blurry={result['blur']['is_blurry']}")
        print(f"  Pixelation: score={result['pixelation']['score']}, pixelated={result['pixelation']['is_pixelated']}")
        print(f"  Resolution: DPI={result['resolution']['dpi']}, low_res={result['resolution']['is_low_res']}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"  ISSUE: [{issue['severity']}] {issue['description']}")
        else:
            print("  Quality: OK")
