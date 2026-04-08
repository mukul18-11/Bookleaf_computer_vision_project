"""
Webhook Server Module
Flask server that receives Google Drive push notifications (webhooks)
when new book cover files are uploaded.

Flow:
    1. Google Drive detects new file in watched folder
    2. Google sends HTTP POST to /webhook/drive
    3. Server downloads the file
    4. Triggers the full CV analysis pipeline

For development: also supports local folder watching via watchdog.
"""

import os
import uuid
import logging
import tempfile
from flask import Flask, request, jsonify

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

from config import (
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_APPLICATION_CREDENTIALS,
    FLASK_SECRET_KEY,
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Store processed file IDs to avoid duplicate processing
_processed_files = set()

# Pipeline callback - set by main.py
_pipeline_callback = None


def set_pipeline_callback(callback):
    """Register the function to call when a new file is detected.

    Args:
        callback: function(file_path, filename) -> analysis_result
    """
    global _pipeline_callback
    _pipeline_callback = callback


def _get_drive_service():
    """Build Google Drive API service using service account credentials."""
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_APPLICATION_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)


def download_file(file_id, filename):
    """Download a file from Google Drive to a local temp directory.

    Args:
        file_id: Google Drive file ID
        filename: original filename

    Returns:
        str: local path to downloaded file
    """
    service = _get_drive_service()

    download_dir = os.path.join(tempfile.gettempdir(), "bookleaf_uploads")
    os.makedirs(download_dir, exist_ok=True)
    local_path = os.path.join(download_dir, filename)

    request_body = service.files().get_media(fileId=file_id)
    with open(local_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request_body)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    logger.info(f"Downloaded: {filename} -> {local_path}")
    return local_path


def get_new_files():
    """Check Google Drive folder for files not yet processed.

    Returns:
        list of dicts: [{id, name, mimeType, createdTime}]
    """
    service = _get_drive_service()

    query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType, createdTime)",
        orderBy="createdTime desc",
        pageSize=20,
    ).execute()

    files = results.get("files", [])
    new_files = [f for f in files if f["id"] not in _processed_files]
    return new_files


def register_watch_channel(webhook_url, expiration_hours=24):
    """Register a watch channel on the Google Drive folder.

    This tells Google: "send a POST to webhook_url whenever something
    changes in this folder."

    Args:
        webhook_url: publicly accessible URL (e.g. ngrok URL)
        expiration_hours: how long the watch channel lasts

    Returns:
        dict: watch channel details
    """
    service = _get_drive_service()

    channel_id = str(uuid.uuid4())
    expiration = int(
        (__import__("time").time() + expiration_hours * 3600) * 1000
    )

    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": webhook_url,
        "expiration": expiration,
    }

    response = service.files().watch(
        fileId=GOOGLE_DRIVE_FOLDER_ID,
        body=body,
    ).execute()

    logger.info(f"Watch channel registered: {channel_id} -> {webhook_url}")
    return response


# =============================================================================
# Flask Routes
# =============================================================================

@app.route("/", methods=["GET"])
def home():
    """Health check endpoint."""
    return jsonify({
        "service": "BookLeaf Cover Validation",
        "status": "running",
        "endpoints": {
            "webhook": "POST /webhook/drive",
            "analyze": "POST /analyze",
            "health": "GET /health",
        }
    })


@app.route("/health", methods=["GET"])
def health():
    """Health check for monitoring."""
    return jsonify({"status": "healthy"}), 200


@app.route("/webhook/drive", methods=["POST"])
def webhook_drive():
    """Receive Google Drive push notifications.

    Google sends headers:
        X-Goog-Channel-ID: channel ID
        X-Goog-Resource-State: sync / change / update
        X-Goog-Resource-ID: resource being watched
    """
    resource_state = request.headers.get("X-Goog-Resource-State", "")

    # Initial sync notification - just acknowledge
    if resource_state == "sync":
        logger.info("Drive webhook: sync notification received")
        return jsonify({"status": "sync acknowledged"}), 200

    # Change notification - new file uploaded
    if resource_state in ("change", "update"):
        logger.info("Drive webhook: change detected, checking for new files")

        try:
            new_files = get_new_files()

            for file_info in new_files:
                file_id = file_info["id"]
                filename = file_info["name"]

                # Skip non-supported formats
                if not filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
                    continue

                logger.info(f"Processing new file: {filename}")
                _processed_files.add(file_id)

                # Download and process
                local_path = download_file(file_id, filename)

                if _pipeline_callback:
                    result = _pipeline_callback(local_path, filename)
                    logger.info(f"Pipeline result for {filename}: {result.get('status')}")

            return jsonify({"status": "processed", "files": len(new_files)}), 200

        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "ignored"}), 200


@app.route("/analyze", methods=["POST"])
def analyze_local():
    """Manually trigger analysis on a local file path.

    Expects JSON body: {"file_path": "/path/to/cover.png"}
    Useful for testing without Google Drive.
    """
    data = request.get_json()
    if not data or "file_path" not in data:
        return jsonify({"error": "file_path required in request body"}), 400

    file_path = data["file_path"]
    if not os.path.exists(file_path):
        return jsonify({"error": f"file not found: {file_path}"}), 404

    if _pipeline_callback:
        result = _pipeline_callback(file_path, os.path.basename(file_path))
        return jsonify(result), 200
    else:
        return jsonify({"error": "pipeline not initialized"}), 500


# =============================================================================
# Local Folder Watcher (Development Fallback)
# =============================================================================

def start_local_watcher(watch_dir, callback):
    """Watch a local folder for new files (development alternative to webhooks).

    Args:
        watch_dir: directory to watch
        callback: function(file_path, filename) to call on new files
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class CoverFileHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            filename = os.path.basename(event.src_path)
            if filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
                logger.info(f"Local watcher: new file detected: {filename}")
                try:
                    callback(event.src_path, filename)
                except Exception as e:
                    logger.error(f"Pipeline error for {filename}: {e}")

    observer = Observer()
    observer.schedule(CoverFileHandler(), watch_dir, recursive=False)
    observer.start()
    logger.info(f"Local folder watcher started on: {watch_dir}")
    return observer
