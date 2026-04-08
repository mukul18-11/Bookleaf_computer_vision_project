"""
Airtable Client Module
Handles creating, reading, and updating records in Airtable
for storing book cover analysis results.

Table: "Cover Analysis" with fields:
    - Book ID (ISBN), Detection Timestamp, Issue Type, Severity,
      Status, Confidence Score, Correction Instructions,
      Annotated Image URL, Revision Count, Author Email
"""

import logging
from datetime import datetime
from pyairtable import Api
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME

logger = logging.getLogger(__name__)


def _get_table():
    """Get the Airtable table object."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        raise ValueError(
            "Airtable credentials not configured. "
            "Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in .env"
        )
    api = Api(AIRTABLE_API_KEY)
    return api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)


def create_record(analysis_result):
    """Create a new record in Airtable from analysis results.

    Args:
        analysis_result: output dict from cv_engine.analyze_cover()

    Returns:
        dict: created Airtable record
    """
    table = _get_table()

    # Build issue type list
    issue_types = list(set(
        issue["type"] for issue in analysis_result.get("issues", [])
    ))

    # Get the highest severity
    severities = [issue["severity"] for issue in analysis_result.get("issues", [])]
    top_severity = "Critical" if "CRITICAL" in severities else (
        "Warning" if "WARNING" in severities else "Info"
    )

    # Build correction instructions text
    corrections = "\n".join(
        f"- {issue['correction']}"
        for issue in analysis_result.get("issues", [])
        if issue.get("correction")
    )

    fields = {
        "Book ID": analysis_result.get("isbn", "unknown"),
        "Detection Timestamp": datetime.now().isoformat(),
        "Issue Type": issue_types if issue_types else ["None"],
        "Severity": top_severity if analysis_result.get("issues") else "Info",
        "Status": "Pass" if analysis_result["status"] == "PASS" else "Review Needed",
        "Confidence Score": analysis_result.get("confidence", 0),
        "Correction Instructions": corrections or "No corrections needed.",
        "Annotated Image URL": analysis_result.get("annotated_image_path", ""),
        "Revision Count": 1,
    }

    record = table.create(fields)
    logger.info(f"Airtable record created: {record['id']} for ISBN {fields['Book ID']}")
    return record


def update_record(record_id, updates):
    """Update an existing Airtable record.

    Args:
        record_id: Airtable record ID
        updates: dict of field names to new values

    Returns:
        dict: updated Airtable record
    """
    table = _get_table()
    record = table.update(record_id, updates)
    logger.info(f"Airtable record updated: {record_id}")
    return record


def find_record_by_isbn(isbn):
    """Find an existing record by ISBN to check for resubmissions.

    Args:
        isbn: book ISBN string

    Returns:
        dict or None: matching Airtable record, or None if not found
    """
    table = _get_table()
    formula = f"{{Book ID}} = '{isbn}'"
    records = table.all(formula=formula)

    if records:
        logger.info(f"Found existing record for ISBN {isbn}: {records[0]['id']}")
        return records[0]
    return None


def upsert_record(analysis_result):
    """Create or update a record based on ISBN.

    If a record already exists for this ISBN, update it and increment
    the revision count. Otherwise create a new record.

    Args:
        analysis_result: output dict from cv_engine.analyze_cover()

    Returns:
        dict: created or updated Airtable record
    """
    isbn = analysis_result.get("isbn", "unknown")
    existing = find_record_by_isbn(isbn)

    if existing:
        revision = existing["fields"].get("Revision Count", 1) + 1

        issue_types = list(set(
            issue["type"] for issue in analysis_result.get("issues", [])
        ))
        severities = [issue["severity"] for issue in analysis_result.get("issues", [])]
        top_severity = "Critical" if "CRITICAL" in severities else (
            "Warning" if "WARNING" in severities else "Info"
        )
        corrections = "\n".join(
            f"- {issue['correction']}"
            for issue in analysis_result.get("issues", [])
            if issue.get("correction")
        )

        updates = {
            "Detection Timestamp": datetime.now().isoformat(),
            "Issue Type": issue_types if issue_types else ["None"],
            "Severity": top_severity if analysis_result.get("issues") else "Info",
            "Status": "Pass" if analysis_result["status"] == "PASS" else "Review Needed",
            "Confidence Score": analysis_result.get("confidence", 0),
            "Correction Instructions": corrections or "No corrections needed.",
            "Annotated Image URL": analysis_result.get("annotated_image_path", ""),
            "Revision Count": revision,
        }

        record = update_record(existing["id"], updates)
        logger.info(f"Updated existing record for ISBN {isbn} (revision {revision})")
        return record
    else:
        return create_record(analysis_result)


def get_all_records():
    """Retrieve all records from the Cover Analysis table.

    Returns:
        list of Airtable records
    """
    table = _get_table()
    return table.all()
