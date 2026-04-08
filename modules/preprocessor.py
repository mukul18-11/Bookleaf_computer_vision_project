"""
Preprocessor Module
Handles file input: PDF to image conversion, ISBN extraction from filename,
and preparing images for the CV pipeline.

File naming convention: ISBN_text.extension
    Example: 9780134685991_text.pdf -> ISBN = 9780134685991

Also supports "combined" images that contain back+front covers side-by-side
in a single landscape image. In that case, the image is split into two halves:
    left half  -> back cover
    right half -> front cover
"""

import os
import re
import cv2
import numpy as np
import logging
import tempfile
from PIL import Image

logger = logging.getLogger(__name__)


def extract_isbn(filename):
    """Extract ISBN from filename following the ISBN_text.extension convention.

    Args:
        filename: file name like "9780134685991_text.pdf"

    Returns:
        str: ISBN string, or "unknown" if not found
    """
    basename = os.path.splitext(os.path.basename(filename))[0]

    # Try splitting on underscore first (expected format: ISBN_text)
    parts = basename.split("_")
    if parts and re.match(r"^\d{10,13}$", parts[0]):
        return parts[0]

    # Try extracting any 13 or 10 digit number from the filename
    isbn_match = re.search(r"\b(\d{13}|\d{10})\b", basename)
    if isbn_match:
        return isbn_match.group(1)

    return "unknown"


def _safe_stem(file_path):
    """Create a filesystem-friendly stem from a path's basename."""
    stem = os.path.splitext(os.path.basename(file_path))[0]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_") or "cover"


def is_side_by_side_cover_image(image, min_aspect_ratio=1.15):
    """Heuristic: detect a combined back+front image (side-by-side).

    Most single covers are portrait (height > width). The combined image is
    typically landscape (width > height).
    """
    h, w = image.shape[:2]
    if h <= 0:
        return False
    aspect = w / float(h)
    return w > h and aspect >= float(min_aspect_ratio)


def split_side_by_side_covers(image, original_path, seam_trim_px=2):
    """Split a combined side-by-side cover image into back and front halves.

    Assumes: left half is back cover, right half is front cover.

    Returns:
        list of dicts: [{image, page, path, type}]
    """
    h, w = image.shape[:2]
    mid = w // 2
    trim = max(0, int(seam_trim_px))

    # Trim a few pixels around the seam to avoid slicing the divider line.
    left_end = max(1, mid - trim)
    right_start = min(w - 1, mid + trim)

    back_img = image[:, :left_end]
    front_img = image[:, right_start:]

    split_dir = os.path.join(tempfile.gettempdir(), "bookleaf_splits")
    os.makedirs(split_dir, exist_ok=True)

    stem = _safe_stem(original_path)
    back_path = os.path.join(split_dir, f"{stem}_back.png")
    front_path = os.path.join(split_dir, f"{stem}_front.png")

    cv2.imwrite(back_path, back_img)
    cv2.imwrite(front_path, front_img)

    return [
        {"image": back_img, "page": 1, "path": back_path, "type": "back"},
        {"image": front_img, "page": 2, "path": front_path, "type": "front"},
    ]


def convert_pdf_to_images(pdf_path, dpi=300):
    """Convert a PDF file to a list of images.

    Page 1 = front cover, Page 2 = back cover (if multi-page).

    Args:
        pdf_path: path to the PDF file
        dpi: resolution for conversion (300 DPI recommended for print)

    Returns:
        list of dicts: [{image: numpy array, page: int, path: str}]
    """
    from pdf2image import convert_from_path

    pages = convert_from_path(pdf_path, dpi=dpi)
    results = []

    for i, page in enumerate(pages):
        # Convert PIL Image to OpenCV numpy array (BGR)
        image_rgb = np.array(page)
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)

        # Save as temporary PNG
        temp_path = pdf_path.replace(".pdf", f"_page{i + 1}.png")
        cv2.imwrite(temp_path, image_bgr)

        results.append({
            "image": image_bgr,
            "page": i + 1,
            "path": temp_path,
            "type": "front" if i == 0 else "back",
        })

    logger.info(f"Converted PDF to {len(results)} image(s)")
    return results


def load_image(file_path, *, split_combined=True):
    """Load an image file (PNG, JPG, etc.) for analysis.

    Args:
        file_path: path to image file

    Returns:
        list of dicts: [{image: numpy array, path: str, type: str, page?: int}]
    """
    image = cv2.imread(file_path)
    if image is None:
        raise FileNotFoundError(f"Could not load image: {file_path}")

    if split_combined and is_side_by_side_cover_image(image):
        logger.info("Detected side-by-side cover image; splitting into back/front halves")
        return split_side_by_side_covers(image, file_path)

    return [{
        "image": image,
        "path": file_path,
        "type": "front",  # Default to front cover for single images
    }]


def preprocess(file_path, *, split_combined=True):
    """Preprocess an uploaded file for analysis.

    Handles both PDF and image files. Extracts ISBN from filename.

    Args:
        file_path: path to the uploaded file
        split_combined: whether to auto-split side-by-side back+front images

    Returns:
        dict with:
            isbn: extracted ISBN
            images: list of {image, path, type, page}
            original_path: original file path
            format: file format (pdf/png/jpg)
    """
    filename = os.path.basename(file_path)
    isbn = extract_isbn(filename)
    ext = os.path.splitext(filename)[1].lower()

    logger.info(f"Preprocessing: {filename} (ISBN: {isbn}, format: {ext})")

    images = []

    if ext == ".pdf":
        images = convert_pdf_to_images(file_path)
    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff"):
        images = load_image(file_path, split_combined=split_combined)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    return {
        "isbn": isbn,
        "images": images,
        "original_path": file_path,
        "format": ext.lstrip("."),
    }


if __name__ == "__main__":
    """Quick test: extract ISBNs from sample filenames."""
    test_filenames = [
        "9780134685991_text.pdf",
        "9789372158725_cover.png",
        "my_book_cover.png",
        "1234567890123_text.pdf",
        "image (29) (1).png",
    ]

    print("ISBN Extraction Tests:")
    for fn in test_filenames:
        isbn = extract_isbn(fn)
        print(f"  {fn:40} -> ISBN: {isbn}")
