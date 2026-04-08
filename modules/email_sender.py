"""
Email Sender Module
Sends personalized HTML emails to authors based on analysis results.

Uses smtplib with Gmail SMTP by default.
Templates are Jinja2-style HTML files in templates/ folder.
"""

import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from config import (
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_EMAIL,
    SMTP_PASSWORD,
    STATUS_PASS,
)

logger = logging.getLogger(__name__)

# ISBN -> author info lookup table
# In production this would come from Airtable or a database
AUTHOR_LOOKUP = {
    "9789372158725": {"name": "Parisha Shobhan", "email": "parisha@example.com"},
    "9789372158726": {"name": "Pulak Das", "email": "pulak@example.com"},
    "9780137247094": {"name": "Benny James SDB", "email": "benny@example.com"},
    "9789898652364": {"name": "Benny James SDB", "email": "benny@example.com"},
    "9789371547765": {"name": "Pratik Kolekar", "email": "pratik@example.com"},
    "9789371245868": {"name": "Ojal Jain", "email": "ojal@example.com"},
}

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def get_author_info(isbn):
    """Look up author name and email from ISBN.

    Args:
        isbn: book ISBN string

    Returns:
        dict with name and email, or defaults if not found
    """
    if isbn in AUTHOR_LOOKUP:
        return AUTHOR_LOOKUP[isbn]
    return {"name": "Author", "email": None}


def _render_template(template_name, context):
    """Render an HTML template with the given context variables.

    Uses simple string replacement ({{ variable }}) for basic templates.
    For the issues loop, does manual expansion.

    Args:
        template_name: filename in templates/ folder
        context: dict of template variables

    Returns:
        str: rendered HTML
    """
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    with open(template_path, "r") as f:
        html = f.read()

    # Replace simple variables
    for key, value in context.items():
        if isinstance(value, (str, int, float)):
            html = html.replace("{{ " + key + " }}", str(value))

    # Handle issues loop for review template
    if "issues" in context and "{% for issue in issues %}" in html:
        loop_start = html.index("{% for issue in issues %}")
        loop_end = html.index("{% endfor %}") + len("{% endfor %}")
        loop_template = html[loop_start:loop_end]

        # Extract the inner template (between for and endfor)
        inner_start = loop_template.index("%}") + 2
        inner_end = loop_template.index("{% endfor %}")
        inner_template = loop_template[inner_start:inner_end]

        # Render each issue
        rendered_issues = ""
        for issue in context["issues"]:
            issue_html = inner_template
            issue_html = issue_html.replace("{{ issue.severity }}", issue.get("severity", ""))
            issue_html = issue_html.replace(
                "{{ issue.severity | lower }}", issue.get("severity", "").lower()
            )
            issue_html = issue_html.replace(
                "{{ issue.type | replace('_', ' ') }}",
                issue.get("type", "").replace("_", " ")
            )
            issue_html = issue_html.replace("{{ issue.description }}", issue.get("description", ""))

            # Handle correction if/endif
            correction = issue.get("correction", "")
            if correction and "{% if issue.correction %}" in issue_html:
                if_start = issue_html.index("{% if issue.correction %}")
                if_end = issue_html.index("{% endif %}") + len("{% endif %}")
                if_block = issue_html[if_start:if_end]
                inner_if = if_block.replace("{% if issue.correction %}", "").replace("{% endif %}", "")
                inner_if = inner_if.replace("{{ issue.correction }}", correction)
                issue_html = issue_html[:if_start] + inner_if + issue_html[if_end:]
            elif "{% if issue.correction %}" in issue_html:
                if_start = issue_html.index("{% if issue.correction %}")
                if_end = issue_html.index("{% endif %}") + len("{% endif %}")
                issue_html = issue_html[:if_start] + issue_html[if_end:]

            rendered_issues += issue_html

        html = html[:loop_start] + rendered_issues + html[loop_end:]

    return html


def send_email(to_email, subject, html_body):
    """Send an HTML email via SMTP.

    Args:
        to_email: recipient email address
        subject: email subject line
        html_body: rendered HTML content

    Returns:
        bool: True if sent successfully
    """
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured, skipping email send")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email

    # Plain text fallback
    plain_text = "Please view this email in an HTML-compatible email client."
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_notification(analysis_result):
    """Send the appropriate email notification based on analysis results.

    Picks PASS or REVIEW template, fills in details, sends to author.

    Args:
        analysis_result: output dict from cv_engine.analyze_cover()

    Returns:
        dict: {sent: bool, to: str, subject: str}
    """
    isbn = analysis_result.get("isbn", "unknown")
    author = get_author_info(isbn)
    status = analysis_result.get("status", "REVIEW_NEEDED")

    if not author["email"]:
        logger.warning(f"No email found for ISBN {isbn}, skipping notification")
        return {"sent": False, "to": None, "subject": None, "reason": "no email on file"}

    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    context = {
        "author_name": author["name"],
        "isbn": isbn,
        "confidence": analysis_result.get("confidence", 0),
        "timestamp": timestamp,
    }

    if status == STATUS_PASS:
        template = "pass_email.html"
        subject = f"Your BookLeaf Cover Has Been Approved - ISBN {isbn}"
    else:
        template = "review_email.html"
        subject = f"Action Required: Your BookLeaf Cover Needs Revision - ISBN {isbn}"
        context["issue_count"] = analysis_result.get("total_issues", 0)
        context["issues"] = analysis_result.get("issues", [])

    html_body = _render_template(template, context)
    sent = send_email(author["email"], subject, html_body)

    return {
        "sent": sent,
        "to": author["email"],
        "subject": subject,
        "author_name": author["name"],
    }
