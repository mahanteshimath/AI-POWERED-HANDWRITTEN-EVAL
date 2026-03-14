import io
import re
import time

import streamlit as st

st.title("📋 Setup Exam")
st.caption("Upload the model answer PDF and define the marking rubric.")

# ── Snowflake session ─────────────────────────────────────────────────────────
session = st.session_state.get_snowflake_session()

DB, SCHEMA = "IITJ", "MH"
STAGE = f"@{DB}.{SCHEMA}.HW_EVAL_STAGE"


def safe_name(filename: str) -> str:
    """Sanitise filename — keep alphanumeric, dot, dash, underscore only."""
    stem = re.sub(r"[^a-zA-Z0-9_\-.]", "_", filename)
    return f"{int(time.time())}_{stem}"


def upload_to_stage(uploaded_file, subfolder: str) -> str:
    """Upload an in-memory file to a stage subfolder; return the relative path."""
    fname   = safe_name(uploaded_file.name)
    stage_path = f"{subfolder}/{fname}"
    session.file.put_stream(
        io.BytesIO(uploaded_file.getvalue()),
        f"{STAGE}/{stage_path}",
        overwrite=True,
        auto_compress=False,
    )
    return stage_path


# ── Form ──────────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("Exam Details")
    col1, col2 = st.columns(2)
    with col1:
        exam_name = st.text_input("Exam Name *", placeholder="e.g. Mid-Sem AI 2025")
    with col2:
        subject = st.text_input("Subject", placeholder="e.g. Artificial Intelligence")

st.markdown("---")

# ── Answer Key PDF ────────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("Model / Correct Answer")
    st.info(
        "Upload the answer key as a PDF (typed or scanned). "
        "Snowflake Cortex will perform OCR at evaluation time — "
        "no local text extraction needed."
    )
    answer_file = st.file_uploader(
        "Upload answer-key PDF *", type=["pdf"], key="answer_pdf"
    )
    if answer_file:
        st.success(f"Ready to upload: **{answer_file.name}**  ({answer_file.size / 1024:.1f} KB)")

st.markdown("---")

# ── Rubric PDF ────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("Rubric / Marking Scheme")
    total_marks = st.number_input("Total Marks", min_value=1, value=100, step=5)
    st.info(
        "Upload the rubric / marking scheme as a PDF. "
        "Snowflake Cortex will OCR it at evaluation time."
    )
    rubric_file = st.file_uploader(
        "Upload rubric PDF *", type=["pdf"], key="rubric_pdf"
    )
    if rubric_file:
        st.success(f"Ready to upload: **{rubric_file.name}**  ({rubric_file.size / 1024:.1f} KB)")

st.markdown("---")

# ── Save ──────────────────────────────────────────────────────────────────────
if st.button("💾 Save Exam", type="primary"):
    if not exam_name.strip():
        st.error("Exam name is required.")
        st.stop()
    if not answer_file:
        st.error("Answer key PDF is required.")
        st.stop()
    if not rubric_file:
        st.error("Rubric PDF is required.")
        st.stop()

    with st.spinner("Uploading answer key to Snowflake Stage..."):
        answer_stage_path = upload_to_stage(answer_file, "answer_keys")

    with st.spinner("Uploading rubric to Snowflake Stage..."):
        rubric_stage_path = upload_to_stage(rubric_file, "rubrics")

    with st.spinner("Saving exam to Snowflake..."):
        session.sql(
            f"""
            INSERT INTO {DB}.{SCHEMA}.HW_EXAMS
                (EXAM_NAME, SUBJECT, ANSWER_KEY_FILE, RUBRIC_FILE, TOTAL_MARKS)
            SELECT ?, ?, ?, ?, ?
            """,
            params=[
                exam_name.strip(),
                subject.strip(),
                answer_stage_path,
                rubric_stage_path,
                total_marks,
            ],
        ).collect()

    st.success(
        f"Exam **{exam_name}** saved!  "
        f"Answer key → `{answer_stage_path}`  |  Rubric → `{rubric_stage_path}`"
    )
    st.balloons()

# ── Existing Exams ────────────────────────────────────────────────────────────
st.markdown("---")
with st.container(border=True):
    st.subheader("Saved Exams")
    rows = session.sql(
        f"""
        SELECT EXAM_ID, EXAM_NAME, SUBJECT, TOTAL_MARKS, ANSWER_KEY_FILE, RUBRIC_FILE, CREATED_AT
        FROM {DB}.{SCHEMA}.HW_EXAMS
        ORDER BY CREATED_AT DESC
        LIMIT 20
        """
    ).collect()
    if rows:
        data = [r.as_dict() if hasattr(r, "as_dict") else dict(r) for r in rows]
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.info("No exams created yet.")
