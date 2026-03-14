import io
import json
import re
import textwrap
import time

import streamlit as st

st.title("🎯 Evaluate Student Answer")
st.caption("Upload a student's answer sheet — Snowflake Cortex will OCR and evaluate it.")

# ── Snowflake session ─────────────────────────────────────────────────────────
session = st.session_state.get_snowflake_session()

DB, SCHEMA = "IITJ", "MH"
STAGE = f"@{DB}.{SCHEMA}.HW_EVAL_STAGE"

DEFAULT_MODEL = "claude-sonnet-4-6"
LLM_MODELS = ["claude-sonnet-4-6", "claude-3-5-sonnet"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_name(filename: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_\-.]", "_", filename)
    return f"{int(time.time())}_{stem}"


def upload_to_stage(uploaded_file, subfolder: str) -> str:
    """Upload file to stage subfolder; return relative path."""
    fname = safe_name(uploaded_file.name)
    stage_path = f"{subfolder}/{fname}"
    session.file.put_stream(
        io.BytesIO(uploaded_file.getvalue()),
        f"{STAGE}/{stage_path}",
        overwrite=True,
        auto_compress=False,
    )
    return stage_path


def ocr_from_stage(stage_path: str) -> str:
    """
    Extract text using AI_PARSE_DOCUMENT (TO_FILE) with OCR mode.
    page_split=TRUE handles multi-page / large documents.
    Returns an array of page objects; we join all page content into one string.
    """
    safe_path = stage_path.replace("'", "")
    result = session.sql(
        f"""
        SELECT AI_PARSE_DOCUMENT(
            TO_FILE('{STAGE}', '{safe_path}'),
            {{'mode': 'OCR', 'page_split': TRUE}}
        ) AS parsed
        """
    ).collect()
    if not result:
        return ""

    parsed = result[0]["PARSED"]

    # page_split=TRUE → VARIANT is a list of per-page objects
    if isinstance(parsed, list):
        page_texts = []
        for page_obj in parsed:
            if isinstance(page_obj, dict):
                page_texts.append(str(page_obj.get("content", "")))
        return "\n".join(page_texts)

    # No page_split (or single page) → VARIANT is a single dict
    if isinstance(parsed, dict):
        content = parsed.get("content", "")
        if isinstance(content, list):
            return " ".join(
                b.get("text", str(b)) if isinstance(b, dict) else str(b)
                for b in content
            )
        return str(content)

    return str(parsed) if parsed else ""


def build_prompt(answer_key: str, rubric: str, total_marks: int, student_answer: str) -> str:
    return textwrap.dedent(f"""\
        You are an expert academic evaluator. Fairly evaluate the student's handwritten
        answer against the model answer and rubric provided below.

        <answer_key>
        {answer_key}
        </answer_key>

        <rubric>
        {rubric}
        Total marks: {total_marks}
        </rubric>

        <student_answer>
        {student_answer}
        </student_answer>

        Return ONLY valid JSON (no markdown fences, no extra text) in exactly this format:

        {{
            "questions": [
                {{
                    "question_number": 1,
                    "topic": "brief topic",
                    "marks_obtained": 0,
                    "max_marks": 0,
                    "correctness": "correct | partially_correct | incorrect",
                    "feedback": "specific feedback"
                }}
            ],
            "total_marks_obtained": 0,
            "total_marks_possible": {total_marks},
            "percentage": 0.0,
            "grade": "A+ | A | B+ | B | C | D | F",
            "overall_feedback": "comprehensive summary",
            "strengths": ["strength1"],
            "areas_for_improvement": ["area1"],
            "recommendations": ["recommendation1"]
        }}

        Rules:
        - Award partial marks where the approach is correct but final answer is wrong.
        - Be constructive and specific in feedback.
        - If OCR-transcribed handwriting is unclear, note it but do not penalise heavily.
        - Grade scale: A+(>=90), A(>=80), B+(>=70), B(>=60), C(>=50), D(>=40), F(<40).
    """)


def parse_response(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                return None
    return None


def assign_grade(pct: float) -> str:
    for threshold, grade in [(90, "A+"), (80, "A"), (70, "B+"), (60, "B"), (50, "C"), (40, "D")]:
        if pct >= threshold:
            return grade
    return "F"


# ── Load exams (only those with uploaded files) ──────────────────────────────
rows = session.sql(
    f"""SELECT EXAM_ID, EXAM_NAME, SUBJECT, TOTAL_MARKS
        FROM {DB}.{SCHEMA}.HW_EXAMS
        WHERE ANSWER_KEY_FILE IS NOT NULL AND RUBRIC_FILE IS NOT NULL
        ORDER BY CREATED_AT DESC"""
).collect()

if not rows:
    st.warning("No exams with uploaded files found. Please create one in **Setup Exam** first.")
    st.stop()

exam_options = {f"{r['EXAM_NAME']}  ({r['SUBJECT'] or 'N/A'})  [ID:{r['EXAM_ID']}]": r for r in rows}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    selected_model = st.selectbox("LLM Model", LLM_MODELS, index=0)

# ── 1. Select Exam ────────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("1. Select Exam")
    chosen = st.selectbox("Exam", list(exam_options.keys()))
    exam = exam_options[chosen]
    st.caption(f"Total marks: **{exam['TOTAL_MARKS']}**")

st.markdown("---")

# ── 2. Student Details ────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("2. Student Details")
    student_name = st.text_input("Student Name *", placeholder="e.g. Rahul Sharma")

st.markdown("---")

# ── 3. Student Answer PDF ─────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("3. Student Answer Sheet")
    st.info(
        "Upload the scanned / photographed answer sheet as a PDF. "
        "Snowflake Cortex OCR will extract the handwritten text directly."
    )
    student_file = st.file_uploader(
        "Upload student answer PDF *", type=["pdf"], key="student_pdf"
    )
    if student_file:
        st.success(f"Ready: **{student_file.name}**  ({student_file.size / 1024:.1f} KB)")

st.markdown("---")

# ── 4. Evaluate ───────────────────────────────────────────────────────────────
if st.button("🚀 Run AI Evaluation", type="primary", use_container_width=True):
    if not student_name.strip():
        st.error("Student name is required.")
        st.stop()
    if not student_file:
        st.error("Please upload the student's answer PDF.")
        st.stop()

    # Step 1 — Upload student answer to stage
    with st.spinner("Uploading student answer to Snowflake Stage..."):
        student_stage_path = upload_to_stage(student_file, "student_answers")

    # Step 2 — Fetch exam record (answer key + rubric file paths)
    exam_row = session.sql(
        f"SELECT ANSWER_KEY_FILE, RUBRIC_FILE, TOTAL_MARKS FROM {DB}.{SCHEMA}.HW_EXAMS WHERE EXAM_ID = ?",
        params=[exam["EXAM_ID"]],
    ).collect()[0]

    answer_key_file = exam_row["ANSWER_KEY_FILE"]
    rubric_file     = exam_row["RUBRIC_FILE"]
    total_marks     = int(exam_row["TOTAL_MARKS"])

    if not answer_key_file:
        st.error("This exam has no answer key file on record. Please re-create the exam.")
        st.stop()
    if not rubric_file:
        st.error("This exam has no rubric file on record. Please re-create the exam.")
        st.stop()

    # Step 3 — OCR the answer key (from stage)
    with st.spinner("Running OCR on answer key via Snowflake Cortex..."):
        answer_key_text = ocr_from_stage(answer_key_file)

    if not answer_key_text.strip():
        st.error("Could not extract text from the answer key PDF. Check the file in the stage.")
        st.stop()

    st.toast(f"Answer key: {len(answer_key_text)} characters extracted")

    # Step 4 — OCR the rubric (from stage)
    with st.spinner("Running OCR on rubric via Snowflake Cortex..."):
        rubric_text = ocr_from_stage(rubric_file)

    if not rubric_text.strip():
        st.error("Could not extract text from the rubric PDF. Check the file in the stage.")
        st.stop()

    st.toast(f"Rubric: {len(rubric_text)} characters extracted")

    # Step 5 — OCR the student answer (from stage)
    with st.spinner("Running OCR on student answer via Snowflake Cortex..."):
        student_answer_text = ocr_from_stage(student_stage_path)

    if not student_answer_text.strip():
        st.error("Could not extract text from the student answer PDF. The file may be blank or unreadable.")
        st.stop()

    st.toast(f"Student answer: {len(student_answer_text)} characters extracted")

    # Step 6 — AI evaluation
    prompt = build_prompt(answer_key_text, rubric_text, total_marks, student_answer_text)

    with st.spinner(f"AI ({selected_model}) evaluating... this may take a moment."):
        response = session.sql(
            "SELECT SNOWFLAKE.CORTEX.AI_COMPLETE(?, ?) AS response",
            params=[selected_model, prompt],
        ).collect()

    raw = response[0]["RESPONSE"]
    if isinstance(raw, str):
        raw = raw.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]

    evaluation = parse_response(raw)

    if evaluation is None:
        st.error("Could not parse the AI response as JSON. Raw output below.")
        st.code(raw)
        st.stop()

    # ── Display Results ───────────────────────────────────────────────────────
    marks_obtained = evaluation.get("total_marks_obtained", 0)
    marks_possible = evaluation.get("total_marks_possible", total_marks)
    percentage     = (marks_obtained / marks_possible * 100) if marks_possible else 0
    grade          = evaluation.get("grade") or assign_grade(percentage)

    st.markdown("---")
    st.subheader("📊 Evaluation Results")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Marks",      f"{marks_obtained} / {marks_possible}")
    c2.metric("Percentage", f"{percentage:.1f}%")
    c3.metric("Grade",      grade)
    c4.metric("Student",    student_name)

    questions = evaluation.get("questions", [])
    if questions:
        st.markdown("#### Question-wise Breakdown")
        for q in questions:
            badge = {"correct": "🟢", "partially_correct": "🟡", "incorrect": "🔴"}.get(
                q.get("correctness", ""), "⚪"
            )
            with st.expander(
                f"Q{q.get('question_number','?')}: {q.get('topic','')}  —  "
                f"{badge} {q.get('marks_obtained',0)}/{q.get('max_marks',0)} marks",
                expanded=False,
            ):
                st.write(f"**Status:** {q.get('correctness','').replace('_',' ').title()}")
                st.write(f"**Feedback:** {q.get('feedback','')}")

    st.markdown("#### Overall Feedback")
    st.info(evaluation.get("overall_feedback", "N/A"))

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Strengths**")
        for s in evaluation.get("strengths", []):
            st.write(f"- {s}")
    with cols[1]:
        st.markdown("**Areas for Improvement**")
        for a in evaluation.get("areas_for_improvement", []):
            st.write(f"- {a}")

    if evaluation.get("recommendations"):
        st.markdown("**Recommendations**")
        for r in evaluation["recommendations"]:
            st.write(f"- {r}")

    # ── Save to Snowflake ─────────────────────────────────────────────────────
    with st.spinner("Saving evaluation..."):
        session.sql(
            f"""
            INSERT INTO {DB}.{SCHEMA}.HW_EVALUATIONS
                (EXAM_ID, STUDENT_NAME, STUDENT_ANSWER_FILE, AI_EVALUATION,
                 TOTAL_MARKS_OBTAINED, TOTAL_MARKS_POSSIBLE, PERCENTAGE, GRADE)
            SELECT ?, ?, ?, ?, ?, ?, ?, ?
            """,
            params=[
                exam["EXAM_ID"],
                student_name.strip(),
                student_stage_path,
                json.dumps(evaluation),
                marks_obtained,
                marks_possible,
                round(percentage, 2),
                grade,
            ],
        ).collect()

    st.success("Evaluation saved!")
