import streamlit as st
from snowflake.snowpark.context import get_active_session
from utils import show_footer

st.set_page_config(
    page_title="AI Handwritten Eval",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_snowflake_session():
    if "snowflake_session" in st.session_state:
        try:
            st.session_state.snowflake_session.sql("SELECT 1").collect()
            return st.session_state.snowflake_session
        except Exception:
            pass

    try:
        session = get_active_session()
    except Exception:
        from snowflake.snowpark import Session
        cfg = st.secrets["connections"]["snowflake"]
        session = Session.builder.configs(cfg).create()

    st.session_state.snowflake_session = session
    return session


# ── Connect & initialise ──────────────────────────────────────────────────────
if "initialized" not in st.session_state:
    with st.spinner("Connecting to Snowflake..."):
        session = get_snowflake_session()

        # Stage for all file uploads (answer keys + student answers)
        session.sql(
            """
            CREATE STAGE IF NOT EXISTS IITJ.MH.HW_EVAL_STAGE
            ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
            DIRECTORY = (ENABLE = true)
            """
        ).collect()

        # Exams table — stores stage file paths for answer key + rubric PDFs
        session.sql(
            """
            CREATE TABLE IF NOT EXISTS IITJ.MH.HW_EXAMS (
                EXAM_ID          NUMBER AUTOINCREMENT,
                EXAM_NAME        VARCHAR,
                SUBJECT          VARCHAR,
                ANSWER_KEY_FILE  VARCHAR,
                RUBRIC_FILE      VARCHAR,
                TOTAL_MARKS      NUMBER,
                CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )
            """
        ).collect()

        # Evaluations table — stores stage file path for student answer PDF
        session.sql(
            """
            CREATE TABLE IF NOT EXISTS IITJ.MH.HW_EVALUATIONS (
                EVAL_ID              NUMBER AUTOINCREMENT,
                EXAM_ID              NUMBER,
                STUDENT_NAME         VARCHAR,
                STUDENT_ANSWER_FILE  VARCHAR,
                AI_EVALUATION        VARCHAR(16777216),
                TOTAL_MARKS_OBTAINED FLOAT,
                TOTAL_MARKS_POSSIBLE FLOAT,
                PERCENTAGE           FLOAT,
                GRADE                VARCHAR,
                EVALUATED_AT         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )
            """
        ).collect()

    st.session_state.initialized = True
    st.toast("Connected to Snowflake!")

# ── Schema migration (runs once per session, independent of initialized) ──────
if "schema_v3" not in st.session_state:
    session = get_snowflake_session()
    for sql in [
        "ALTER TABLE IF EXISTS IITJ.MH.HW_EXAMS ADD COLUMN IF NOT EXISTS ANSWER_KEY_FILE VARCHAR",
        "ALTER TABLE IF EXISTS IITJ.MH.HW_EXAMS ADD COLUMN IF NOT EXISTS RUBRIC_FILE VARCHAR",
        "ALTER TABLE IF EXISTS IITJ.MH.HW_EVALUATIONS ADD COLUMN IF NOT EXISTS STUDENT_ANSWER_FILE VARCHAR",
    ]:
        try:
            session.sql(sql).collect()
        except Exception:
            pass
    st.session_state.schema_v3 = True

st.session_state.get_snowflake_session = get_snowflake_session

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    try:
        get_snowflake_session().sql("SELECT 1").collect()
        st.success("☁️connected")
    except Exception as e:
        st.error(f"Connection lost: {e}")

    st.markdown("---")
    st.markdown("### How to use")
    st.markdown(
        """
**1. 📋 Setup Exam**
- Enter exam name & subject
- Upload answer key PDF
- Upload marking rubric PDF
- Set total marks → **Save Exam**

**2. 🎯 Evaluate**
- Select exam
- Enter student name
- Upload student answer PDF
- Choose AI model *(sidebar)*
- Click **Run AI Evaluation**

**3. 📊 Results**
- Filter by exam / student / grade
- View per-question breakdown
- Check grade distribution chart
"""
    )
    st.markdown("---")
    st.caption("💡 Use **gemini-3-pro** for large scans (up to 10 MB). Switch to **claude-sonnet-4-5** for smaller PDFs (up to 4.5 MB).")

# ── Navigation ────────────────────────────────────────────────────────────────
pg = st.navigation(
    {
        "Menu": [
            st.Page("pages/01_Setup_Exam.py", title="Setup Exam", icon="📋", default=True),
            st.Page("pages/02_Evaluate.py",   title="Evaluate",   icon="🎯"),
            st.Page("pages/03_Results.py",    title="Results",    icon="📊"),
        ]
    }
)
pg.run()
show_footer()
