"""
Classifier Module
Takes analysis results and classifies the cover as PASS or REVIEW_NEEDED.

Two statuses only:
    PASS          - All checks passed, no issues detected
    REVIEW_NEEDED - Issues found or confidence too low, needs human review
"""

from config import (
    REVIEW_CONFIDENCE_THRESHOLD,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    STATUS_PASS,
    STATUS_REVIEW,
)


def calculate_overall_confidence(issues, quality_result, ocr_detections):
    """Calculate an overall confidence score for the analysis.

    The score reflects how confident we are in the analysis results.
    Higher = more confident in the verdict (whether pass or fail).

    Factors:
        - OCR detection confidence (how well we could read the text)
        - Number and severity of issues found
        - Image quality metrics

    Args:
        issues: list of all issues found
        quality_result: output from quality_checker.check_quality()
        ocr_detections: list of text detections from OCR

    Returns:
        float: confidence score 0-100
    """
    score = 100.0

    # Factor 1: OCR confidence - if OCR was not confident, neither are we
    if ocr_detections:
        avg_ocr_conf = sum(d["confidence"] for d in ocr_detections) / len(ocr_detections)
        # Scale: 0.9+ OCR conf = no penalty, below that = penalty
        if avg_ocr_conf < 0.9:
            score -= (0.9 - avg_ocr_conf) * 50  # Up to -45 points
    else:
        # No text detected at all - very low confidence
        score -= 30

    # Factor 2: Image quality
    if quality_result:
        if quality_result.get("blur", {}).get("is_blurry"):
            score -= 15  # Blurry = harder to trust OCR results
        if quality_result.get("resolution", {}).get("is_low_res"):
            score -= 10  # Low res = less reliable detection

    # Factor 3: Issue clarity
    # If issues have high overlap percentages, we're more confident in them
    for issue in issues:
        if issue.get("overlap_percentage", 0) > 50:
            # Large overlaps are clear-cut - actually increases confidence in verdict
            score = max(score, 90)
        elif issue.get("overlap_percentage", 0) < 10:
            # Tiny overlaps are ambiguous
            score -= 5

    return round(max(0, min(100, score)), 1)


def classify(issues, overall_confidence):
    """Classify the cover based on issues found and confidence.

    Decision rules:
        1. No issues at all -> PASS
        2. Any CRITICAL issue -> REVIEW_NEEDED
        3. Confidence below threshold -> REVIEW_NEEDED
        4. Only minor warnings with high confidence -> PASS

    Args:
        issues: list of all detected issues
        overall_confidence: confidence score 0-100

    Returns:
        dict with: status, reason, summary
    """
    if not issues:
        return {
            "status": STATUS_PASS,
            "reason": "No layout issues detected",
            "summary": "Cover passed all validation checks.",
        }

    # Check for critical issues
    critical_issues = [i for i in issues if i.get("severity") == SEVERITY_CRITICAL]
    warning_issues = [i for i in issues if i.get("severity") == SEVERITY_WARNING]

    if critical_issues:
        descriptions = "; ".join(i["description"] for i in critical_issues[:3])
        return {
            "status": STATUS_REVIEW,
            "reason": f"{len(critical_issues)} critical issue(s) found",
            "summary": f"Critical: {descriptions}",
        }

    # Low confidence even without critical issues = needs human eyes
    if overall_confidence < REVIEW_CONFIDENCE_THRESHOLD:
        return {
            "status": STATUS_REVIEW,
            "reason": f"Low analysis confidence ({overall_confidence}%)",
            "summary": "Analysis confidence is too low to auto-approve. Human review recommended.",
        }

    # Only warnings with high confidence - these are minor
    if warning_issues and overall_confidence >= REVIEW_CONFIDENCE_THRESHOLD:
        return {
            "status": STATUS_REVIEW,
            "reason": f"{len(warning_issues)} warning(s) detected",
            "summary": "; ".join(i["description"] for i in warning_issues[:3]),
        }

    return {
        "status": STATUS_PASS,
        "reason": "All checks passed",
        "summary": "Cover meets all layout requirements.",
    }


def build_classification_result(isbn, issues, quality_result, ocr_detections, annotated_image_path=None):
    """Build the complete classification result dict.

    This is the final output format for the entire pipeline.

    Args:
        isbn: book ISBN string
        issues: all issues from overlap_checker + quality_checker
        quality_result: output from quality_checker
        ocr_detections: text detections from text_detector
        annotated_image_path: path to the annotated output image

    Returns:
        Complete result dict matching the expected output format
    """
    from datetime import datetime

    confidence = calculate_overall_confidence(issues, quality_result, ocr_detections)
    classification = classify(issues, confidence)

    return {
        "isbn": isbn,
        "status": classification["status"],
        "confidence": confidence,
        "classification_reason": classification["reason"],
        "summary": classification["summary"],
        "issues": [
            {
                "type": i.get("type", "UNKNOWN"),
                "severity": i.get("severity", "INFO"),
                "description": i.get("description", ""),
                "text": i.get("text", ""),
                "overlap_percentage": i.get("overlap_percentage", 0),
                "correction": i.get("correction", ""),
            }
            for i in issues
        ],
        "total_issues": len(issues),
        "critical_count": sum(1 for i in issues if i.get("severity") == SEVERITY_CRITICAL),
        "warning_count": sum(1 for i in issues if i.get("severity") == SEVERITY_WARNING),
        "annotated_image_path": annotated_image_path or "",
        "timestamp": datetime.now().isoformat(),
    }
