import os
import time
import streamlit as st
from snowflake.snowpark.context import get_active_session
from utils import show_footer


def _ensure_logo_png(path="assets/logo_icon.png"):
    if os.path.exists(path):
        return path
    os.makedirs("assets", exist_ok=True)
    try:
        from PIL import Image, ImageDraw
        W, H = 64, 64
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Purple rounded background
        draw.rounded_rectangle([(0, 0), (W-1, H-1)], radius=14, fill=(44, 30, 91))
        # White page
        draw.rounded_rectangle([(12, 8), (50, 56)], radius=4, fill=(255, 255, 255))
        # Handwriting lines
        draw.line([(18, 20), (44, 20)], fill=(44, 30, 91), width=2)
        draw.line([(18, 28), (44, 28)], fill=(44, 30, 91), width=2)
        draw.line([(18, 36), (36, 36)], fill=(44, 30, 91), width=2)
        # Green checkmark
        draw.line([(28, 47), (33, 53)], fill=(34, 197, 94), width=3)
        draw.line([(33, 53), (48, 40)], fill=(34, 197, 94), width=3)
        img.save(path)
        return path
    except Exception:
        return None

st.set_page_config(
    page_title="AI Handwritten Eval | IITJ",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)


SESSION_HEALTHCHECK_SECS = 300


@st.cache_resource(show_spinner=False)
def _create_local_session(cfg_items: tuple[tuple[str, str], ...]):
    from snowflake.snowpark import Session

    cfg = dict(cfg_items)
    return Session.builder.configs(cfg).create()


def _build_session():
    try:
        return get_active_session()
    except Exception:
        cfg = st.secrets["connections"]["snowflake"]
        cfg_items = tuple(sorted(dict(cfg).items()))
        return _create_local_session(cfg_items)


def get_snowflake_session(force_refresh: bool = False):
    if force_refresh:
        st.session_state.pop("snowflake_session", None)
        st.session_state.pop("snowflake_last_healthcheck", None)
        _create_local_session.clear()

    session = st.session_state.get("snowflake_session")
    if session is None:
        session = _build_session()
        st.session_state.snowflake_session = session
        st.session_state.snowflake_last_healthcheck = time.time()
        return session

    last_check = st.session_state.get("snowflake_last_healthcheck", 0.0)
    now = time.time()
    if now - last_check > SESSION_HEALTHCHECK_SECS:
        try:
            session.sql("SELECT 1").collect()
        except Exception:
            session = _build_session()
            st.session_state.snowflake_session = session
        finally:
            st.session_state.snowflake_last_healthcheck = now

    return st.session_state.snowflake_session


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

_logo = _ensure_logo_png()
if _logo:
    st.logo(_logo, link="https://bit.ly/atozaboutdata")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    try:
        get_snowflake_session()
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
