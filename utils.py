"""
Shared utilities for the AI Handwritten Eval Streamlit app.
All pages import constants, helpers, and UI components from here.
"""
import io
import re
import time

import streamlit as st

# ── Database / stage coordinates ──────────────────────────────────────────────
DB     = "IITJ"
SCHEMA = "MH"
STAGE  = f"@{DB}.{SCHEMA}.HW_EVAL_STAGE"

# ── Document size limits (per Snowflake Cortex docs) ──────────────────────────
MAX_SIZE_GEMINI_MB = 10.0   # gemini-3-pro
MAX_SIZE_CLAUDE_MB =  4.5   # All Claude document-input models

# ── Grade scale ───────────────────────────────────────────────────────────────
GRADE_ORDER      = ["A+", "A", "B+", "B", "C", "D", "F"]
GRADE_THRESHOLDS = [(90, "A+"), (80, "A"), (70, "B+"), (60, "B"), (50, "C"), (40, "D")]


def show_footer() -> None:
    """Inject a fixed branding footer at the bottom of every page."""
    st.markdown(
        """
<style>
.footer {
    position: fixed;
    left: 0;
    bottom: 0;
    width: 100%;
    background-color: #2C1E5B;
    color: white;
    text-align: center;
    z-index: 9999;
    padding: 10px 0;
    box-shadow: 0 -2px 10px rgba(0,0,0,0.3);
}
.footer p { margin: 0; }
.footer a { color: white; text-decoration; }
.footer a:hover { text-decoration: underline; }
</style>
<div class="footer">
<p>Developed with ❤️ by <a href="https://bit.ly/atozaboutdata" target="_blank">MAHANTESH HIREMATH (M25AI2134@IITJ.AC.IN)</a></p>
</div>
""",
        unsafe_allow_html=True,
    )


def assign_grade(pct: float) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if pct >= threshold:
            return grade
    return "F"


# ── File helpers ──────────────────────────────────────────────────────────────

def safe_name(filename: str) -> str:
    """Sanitise filename — keep alphanumeric, dot, dash, underscore; prepend timestamp."""
    stem = re.sub(r"[^a-zA-Z0-9_\-.]", "_", filename)
    return f"{int(time.time())}_{stem}"


def upload_to_stage(uploaded_file, subfolder: str) -> str:
    """Upload an in-memory PDF to the shared stage; return the relative path."""
    session    = st.session_state.get_snowflake_session()
    fname      = safe_name(uploaded_file.name)
    stage_path = f"{subfolder}/{fname}"
    session.file.put_stream(
        io.BytesIO(uploaded_file.getvalue()),
        f"{STAGE}/{stage_path}",
        overwrite=True,
        auto_compress=False,
    )
    return stage_path


def show_file_size(uploaded_file, selected_model: str | None = None) -> float:
    """
    Show a success/warning/error message based on file size vs model limits.
    Returns the file size in MB.
    """
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > MAX_SIZE_GEMINI_MB:
        st.error(
            f"File is {size_mb:.2f} MB — exceeds the {MAX_SIZE_GEMINI_MB:.0f} MB limit. "
            "Please compress the PDF."
        )
    elif size_mb > MAX_SIZE_CLAUDE_MB and selected_model != "gemini-3-pro":
        st.warning(
            f"File is {size_mb:.2f} MB — exceeds the {MAX_SIZE_CLAUDE_MB} MB limit for Claude models. "
            "Switch to **gemini-3-pro** in the sidebar, or reduce file size."
        )
    else:
        st.success(f"Ready: **{uploaded_file.name}**  ({size_mb:.2f} MB)")
    return size_mb


def validate_file_for_upload(uploaded_file, selected_model: str) -> None:
    """
    Hard-stop via st.stop() if the file exceeds the chosen model's document size limit.
    Call this at the start of the evaluation button handler.
    """
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > MAX_SIZE_GEMINI_MB:
        st.error(
            f"File is {size_mb:.2f} MB — exceeds the {MAX_SIZE_GEMINI_MB:.0f} MB limit. "
            "Please compress the PDF and re-upload."
        )
        st.stop()
    if size_mb > MAX_SIZE_CLAUDE_MB and selected_model != "gemini-3-pro":
        st.error(
            f"File is {size_mb:.2f} MB — exceeds the {MAX_SIZE_CLAUDE_MB} MB limit for {selected_model}. "
            "Switch to **gemini-3-pro** or compress the PDF."
        )
        st.stop()


# ── Evaluation result renderer ────────────────────────────────────────────────

def render_evaluation_detail(evaluation: dict) -> None:
    """Render a rich, human-readable evaluation report."""

    # ── Question-wise breakdown ──────────────────────────────────────────────
    questions = evaluation.get("questions", [])
    if questions:
        st.markdown("### Question-wise Breakdown")
        for q in questions:
            correctness  = q.get("correctness", "")
            marks_obt    = float(q.get("marks_obtained", 0) or 0)
            max_marks    = float(q.get("max_marks",     1) or 1)
            score_ratio  = marks_obt / max_marks if max_marks else 0

            icon  = {"correct": "🟢", "partially_correct": "🟡", "incorrect": "🔴"}.get(correctness, "⚪")
            label = {"correct": "Correct", "partially_correct": "Partially Correct",
                     "incorrect": "Incorrect"}.get(correctness, "Unknown")

            title = (
                f"{icon} **Q{q.get('question_number', '?')}: {q.get('topic', '')}**"
                f"  —  {marks_obt:.1g}/{max_marks:.4g} marks  *({label})*"
            )
            with st.expander(title, expanded=True):
                st.progress(score_ratio, text=f"{marks_obt:.1g} / {max_marks:.4g} marks scored")
                st.markdown(f"> {q.get('feedback', 'No feedback available.')}")

        st.markdown("---")

    # ── Overall feedback ─────────────────────────────────────────────────────
    overall = evaluation.get("overall_feedback", "")
    if overall:
        st.markdown("### Overall Feedback")
        st.info(overall, icon="📝")
        st.markdown("---")

    # ── Strengths / Areas for Improvement / Recommendations ─────────────────
    strengths    = evaluation.get("strengths",             [])
    improvements = evaluation.get("areas_for_improvement", [])
    recs         = evaluation.get("recommendations",        [])

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### ✅ Strengths")
        if strengths:
            for s in strengths:
                st.success(s)
        else:
            st.caption("—")

    with col2:
        st.markdown("#### ⚠️ Areas for Improvement")
        if improvements:
            for a in improvements:
                st.warning(a)
        else:
            st.caption("—")

    with col3:
        st.markdown("#### 💡 Recommendations")
        if recs:
            for r in recs:
                st.info(r)
        else:
            st.caption("—")
