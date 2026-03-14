import streamlit as st

from utils import (
    DB, SCHEMA, MAX_SIZE_CLAUDE_MB, MAX_SIZE_GEMINI_MB,
    upload_to_stage, show_file_size, show_footer,
)

st.title("📋 Setup Exam")
st.caption("Upload the model answer PDF and define the marking rubric.")

session = st.session_state.get_snowflake_session()

# ── Exam Details ──────────────────────────────────────────────────────────────
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
        "Snowflake Cortex AI reads it directly alongside the student answer — "
        f"no OCR needed. Keep under {MAX_SIZE_CLAUDE_MB} MB for Claude models, "
        f"{MAX_SIZE_GEMINI_MB:.0f} MB for Gemini."
    )
    answer_file = st.file_uploader("Upload answer-key PDF *", type=["pdf"], key="answer_pdf")
    if answer_file:
        show_file_size(answer_file)

st.markdown("---")

# ── Rubric PDF ────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("Rubric / Marking Scheme")
    total_marks = st.number_input("Total Marks", min_value=1, value=100, step=5)
    st.info(
        "Upload the rubric / marking scheme as a PDF. "
        "Snowflake Cortex reads it directly at evaluation time — no OCR step required."
    )
    rubric_file = st.file_uploader("Upload rubric PDF *", type=["pdf"], key="rubric_pdf")
    if rubric_file:
        show_file_size(rubric_file)

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
        st.dataframe(data, width="stretch", hide_index=True)
    else:
        st.info("No exams created yet.")

show_footer()
