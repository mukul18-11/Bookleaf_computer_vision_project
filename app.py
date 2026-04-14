"""Gradio demo UI for the BookLeaf cover validator.

Wraps the existing CV pipeline (`modules.cv_engine.analyze_cover`) so a reviewer
can drag-drop a book cover image and see the analysis result — no email,
no Airtable, no Drive webhooks. Designed to run as a Hugging Face Space.
"""

import os
import json
import tempfile
import shutil
import uuid

# Bootstrap Google credentials from HF secret (JSON content) into a temp file
# BEFORE importing any modules/* code, since text_detector reads the env var
# at import / call time.
_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
if _creds_json and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    fd, _creds_path = tempfile.mkstemp(suffix=".json", prefix="gcp_")
    with os.fdopen(fd, "w") as f:
        f.write(_creds_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _creds_path

import gradio as gr

from modules.cv_engine import analyze_cover


SEVERITY_EMOJI = {"CRITICAL": "🔴", "WARNING": "🟠", "INFO": "🔵"}
STATUS_HEADLINE = {
    "PASS": "✅ PASS — cover meets all layout rules",
    "REVIEW_NEEDED": "⚠️ REVIEW NEEDED — issues detected",
}


def _format_issues_markdown(issues):
    if not issues:
        return "_No issues detected._"

    lines = [f"**{len(issues)} issue(s) found:**", ""]
    for idx, issue in enumerate(issues, 1):
        sev = issue.get("severity", "INFO")
        emoji = SEVERITY_EMOJI.get(sev, "•")
        issue_type = issue.get("type", "ISSUE").replace("_", " ")
        description = issue.get("description", "")
        correction = issue.get("correction", "")

        lines.append(f"### {idx}. {emoji} {sev} — {issue_type}")
        lines.append(description)
        if correction:
            lines.append(f"> 💡 **How to fix:** {correction}")
        lines.append("")
    return "\n".join(lines)


def validate_cover(image_path):
    if not image_path:
        return (
            "⚠️ Please upload a cover image first.",
            "",
            None,
            None,
        )

    # Give each run a unique ISBN so annotated files don't collide across clicks.
    demo_isbn = f"demo_{uuid.uuid4().hex[:8]}"

    try:
        result = analyze_cover(
            image_path=image_path,
            isbn=demo_isbn,
            use_google_vision=True,
            cover_type="front",
        )
    except Exception as e:
        return (
            f"❌ Analysis failed: {type(e).__name__}: {e}",
            "",
            None,
            None,
        )

    status = result.get("status", "UNKNOWN")
    confidence = result.get("confidence", 0)
    issues = result.get("issues", [])
    annotated_path = result.get("annotated_image_path")

    status_md = f"## {STATUS_HEADLINE.get(status, status)}\n**Confidence:** {confidence}%"
    issues_md = _format_issues_markdown(issues)

    return status_md, issues_md, annotated_path, result


def _example_list():
    samples_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "sample_covers", "front"
    )
    if not os.path.isdir(samples_dir):
        return []
    preferred = [
        "echoes_clean.png",
        "echoes_overlap.png",
        "tainted_emotion_overlap.png",
    ]
    examples = []
    for name in preferred:
        path = os.path.join(samples_dir, name)
        if os.path.exists(path):
            examples.append([path])
    return examples


with gr.Blocks(title="BookLeaf Cover Validator") as demo:
    gr.Markdown(
        """
        # 📘 BookLeaf — Automated Book Cover Validator

        Upload a front-cover image (PNG / JPG). The system detects layout
        violations — especially text sitting inside the bottom 9mm reserved
        for the "Winner of the 21st Century Emily Dickinson Award" badge —
        and returns a PASS / REVIEW NEEDED verdict with specific fixes.
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            image_in = gr.Image(type="filepath", label="Book cover image")
            run_btn = gr.Button("Validate cover", variant="primary")
            gr.Examples(
                examples=_example_list(),
                inputs=[image_in],
                label="Sample covers",
            )
        with gr.Column(scale=1):
            status_out = gr.Markdown(label="Status")
            issues_out = gr.Markdown(label="Issues")

    with gr.Row():
        annotated_out = gr.Image(type="filepath", label="Annotated cover")

    with gr.Accordion("Raw JSON result", open=False):
        raw_out = gr.JSON()

    run_btn.click(
        fn=validate_cover,
        inputs=[image_in],
        outputs=[status_out, issues_out, annotated_out, raw_out],
    )


if __name__ == "__main__":
    demo.launch()
