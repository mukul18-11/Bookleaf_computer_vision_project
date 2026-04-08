"""
BookLeaf Automated Book Cover Validation System
================================================
Entry point that wires the full pipeline together.

Modes:
    1. SERVER mode  - Flask webhook server (production)
    2. LOCAL mode   - Watch a local folder for new files (development)
    3. BATCH mode   - Analyze all sample covers at once (testing)
    4. SINGLE mode  - Analyze a single file (debugging)

Usage:
    python main.py                          # starts Flask server
    python main.py --mode local             # watch local folder
    python main.py --mode batch             # analyze all sample covers
    python main.py --mode single cover.png  # analyze one file
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bookleaf")

# Import modules
from modules.preprocessor import preprocess, extract_isbn
from modules.cv_engine import analyze_cover, analyze_batch
from modules.classifier import build_classification_result
from config import SAMPLE_FRONT_DIR, ANNOTATED_DIR, REPORTS_DIR


def run_pipeline(file_path, filename=None):
    """Run the full analysis pipeline on a single file.

    Steps:
        1. Preprocess (extract ISBN, convert PDF if needed)
        2. Analyze with CV engine (text detection, overlap check, quality)
        3. Log results to Airtable
        4. Send email notification to author

    Args:
        file_path: path to the cover image/PDF
        filename: original filename (for ISBN extraction)

    Returns:
        dict: complete analysis result
    """
    if filename is None:
        filename = os.path.basename(file_path)

    logger.info(f"{'='*60}")
    logger.info(f"PIPELINE START: {filename}")
    logger.info(f"{'='*60}")

    # Step 1: Preprocess
    isbn = extract_isbn(filename)
    logger.info(f"ISBN: {isbn}")

    # Step 2: Handle PDF or image
    preprocessed = preprocess(file_path)
    isbn = preprocessed["isbn"]

    results = []
    for img_data in preprocessed["images"]:
        image_path = img_data["path"]
        cover_type = img_data["type"]

        logger.info(f"Analyzing {cover_type} cover: {image_path}")

        # Step 3: Run CV analysis
        result = analyze_cover(
            image_path,
            isbn=f"{isbn}_{cover_type}" if len(preprocessed["images"]) > 1 else isbn,
            use_google_vision=True,
        )
        results.append(result)

        # Log result summary
        logger.info(f"  Status: {result['status']}")
        logger.info(f"  Confidence: {result['confidence']}%")
        logger.info(f"  Issues: {result['total_issues']}")
        if result["issues"]:
            for issue in result["issues"]:
                logger.info(f"    [{issue['severity']}] {issue['description']}")

    # Use the front cover result as the primary result
    primary_result = results[0] if results else {"status": "ERROR", "isbn": isbn}

    # Step 4: Log to Airtable (if configured)
    try:
        from modules.airtable_client import upsert_record
        airtable_record = upsert_record(primary_result)
        logger.info(f"Airtable record: {airtable_record.get('id', 'N/A')}")
    except Exception as e:
        logger.warning(f"Airtable logging skipped: {e}")

    # Step 5: Send email notification (if configured)
    try:
        from modules.email_sender import send_notification
        email_result = send_notification(primary_result)
        if email_result["sent"]:
            logger.info(f"Email sent to: {email_result['to']}")
        else:
            logger.info(f"Email not sent: {email_result.get('reason', 'SMTP not configured')}")
    except Exception as e:
        logger.warning(f"Email notification skipped: {e}")

    logger.info(f"PIPELINE COMPLETE: {primary_result['status']}")
    logger.info(f"{'='*60}\n")

    return primary_result


def mode_server():
    """Start the Flask webhook server (production mode)."""
    from modules.webhook_server import app, set_pipeline_callback, register_watch_channel
    from config import WEBHOOK_URL

    set_pipeline_callback(run_pipeline)

    # Register watch channel if webhook URL is configured
    if WEBHOOK_URL:
        try:
            register_watch_channel(WEBHOOK_URL)
            logger.info(f"Watch channel registered: {WEBHOOK_URL}")
        except Exception as e:
            logger.warning(f"Could not register watch channel: {e}")
            logger.info("Server will still run - use POST /analyze for manual testing")

    logger.info("Starting BookLeaf Cover Validation Server...")
    logger.info("Endpoints:")
    logger.info("  GET  /          - Service info")
    logger.info("  GET  /health    - Health check")
    logger.info("  POST /webhook/drive  - Google Drive webhook")
    logger.info("  POST /analyze   - Manual file analysis")
    app.run(host="0.0.0.0", port=5000, debug=True)


def mode_local(watch_dir=None):
    """Start local folder watcher (development mode)."""
    from modules.webhook_server import app, set_pipeline_callback, start_local_watcher
    import threading

    if watch_dir is None:
        watch_dir = os.path.join(os.path.dirname(__file__), "uploads")
        os.makedirs(watch_dir, exist_ok=True)

    set_pipeline_callback(run_pipeline)

    logger.info(f"Watching folder: {watch_dir}")
    logger.info("Drop a book cover image into this folder to trigger analysis")

    observer = start_local_watcher(watch_dir, run_pipeline)

    # Also start Flask server for manual /analyze endpoint
    def run_flask():
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    logger.info("Flask server running on http://localhost:5000")
    logger.info("Press Ctrl+C to stop")

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
        logger.info("Stopped.")


def mode_batch():
    """Analyze all sample covers (testing mode)."""
    logger.info("=" * 70)
    logger.info("BATCH ANALYSIS - All Sample Covers")
    logger.info("=" * 70)

    if not os.path.exists(SAMPLE_FRONT_DIR):
        logger.error(f"Sample covers directory not found: {SAMPLE_FRONT_DIR}")
        return

    files = sorted([
        f for f in os.listdir(SAMPLE_FRONT_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ])

    if not files:
        logger.error("No image files found in sample_covers/front/")
        return

    logger.info(f"Found {len(files)} cover images\n")
    print(f"  {'STATUS':15} | {'CONF':>6} | {'ISSUES':>6} | FILENAME")
    print(f"  {'-'*15} | {'-'*6} | {'-'*6} | {'-'*35}")

    all_results = []
    for filename in files:
        file_path = os.path.join(SAMPLE_FRONT_DIR, filename)
        try:
            result = analyze_cover(file_path, isbn=filename.split(".")[0], use_google_vision=True)
            all_results.append(result)
            print(
                f"  {result['status']:15} | {result['confidence']:5.1f}% | "
                f"{result['total_issues']:6} | {filename}"
            )
        except Exception as e:
            logger.error(f"Failed: {filename}: {e}")
            print(f"  {'ERROR':15} | {'N/A':>6} | {'N/A':>6} | {filename}")

    # Summary
    passed = sum(1 for r in all_results if r["status"] == "PASS")
    review = sum(1 for r in all_results if r["status"] == "REVIEW_NEEDED")
    print(f"\n{'='*70}")
    print(f"  Total: {len(all_results)} | PASS: {passed} | REVIEW_NEEDED: {review}")
    print(f"  Accuracy: {(passed + review) / len(all_results) * 100:.0f}% processed successfully")
    print(f"{'='*70}")

    # Save batch report
    os.makedirs(REPORTS_DIR, exist_ok=True)
    batch_report = {
        "timestamp": datetime.now().isoformat(),
        "total": len(all_results),
        "passed": passed,
        "review_needed": review,
        "results": all_results,
    }
    report_path = os.path.join(REPORTS_DIR, "batch_report.json")
    with open(report_path, "w") as f:
        json.dump(batch_report, f, indent=2, default=str)
    print(f"\n  Batch report saved: {report_path}")


def mode_single(file_path):
    """Analyze a single cover file (debugging mode)."""
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return

    result = run_pipeline(file_path)

    print(f"\n{'='*60}")
    print(f"  RESULT: {result['status']}")
    print(f"  Confidence: {result.get('confidence', 'N/A')}%")
    print(f"  Issues: {result.get('total_issues', 0)}")
    if result.get("issues"):
        for issue in result["issues"]:
            print(f"    [{issue['severity']}] {issue['description']}")
    print(f"  Annotated: {result.get('annotated_image_path', 'N/A')}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="BookLeaf Automated Book Cover Validation System"
    )
    parser.add_argument(
        "--mode",
        choices=["server", "local", "batch", "single"],
        default="server",
        help="Run mode (default: server)",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="File path for single mode",
    )
    parser.add_argument(
        "--watch-dir",
        help="Directory to watch in local mode",
    )

    args = parser.parse_args()

    if args.mode == "server":
        mode_server()
    elif args.mode == "local":
        mode_local(args.watch_dir)
    elif args.mode == "batch":
        mode_batch()
    elif args.mode == "single":
        if not args.file:
            print("Error: single mode requires a file path")
            print("Usage: python main.py --mode single /path/to/cover.png")
            sys.exit(1)
        mode_single(args.file)
