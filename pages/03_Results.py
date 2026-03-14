import json

import pandas as pd
import streamlit as st

from utils import DB, SCHEMA, GRADE_ORDER, render_evaluation_detail, show_footer

st.title("📊 Evaluation Results")
st.caption("View and analyse all student evaluations.")

session = st.session_state.get_snowflake_session()


# ── Cached loaders ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def load_exam_list(_session):
    return [
        r.as_dict() if hasattr(r, "as_dict") else dict(r)
        for r in _session.sql(
            f"SELECT DISTINCT EXAM_ID, EXAM_NAME FROM {DB}.{SCHEMA}.HW_EXAMS ORDER BY EXAM_NAME"
        ).collect()
    ]


@st.cache_data(ttl=300, show_spinner=False)
def load_evaluation(_session, eval_id: int) -> dict | None:
    """Fetch the AI_EVALUATION JSON for a single record — called only when user selects it."""
    rows = _session.sql(
        f"SELECT AI_EVALUATION FROM {DB}.{SCHEMA}.HW_EVALUATIONS WHERE EVAL_ID = ?",
        params=[eval_id],
    ).collect()
    if not rows:
        return None
    raw = rows[0]["AI_EVALUATION"]
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if isinstance(raw, str) else None
    except (json.JSONDecodeError, TypeError):
        return None


# ── Filters ───────────────────────────────────────────────────────────────────
with st.container(border=True):
    col1, col2, col3 = st.columns(3)

    with col1:
        exams    = load_exam_list(session)
        exam_map = {f"{r['EXAM_NAME']} [#{r['EXAM_ID']}]": r["EXAM_ID"] for r in exams}
        exam_filter = st.selectbox("Exam", ["All"] + list(exam_map.keys()))

    with col2:
        student_filter = st.text_input("Student name contains", placeholder="e.g. Rahul")

    with col3:
        # Uses GRADE_ORDER — single source of truth for the grade list
        grade_filter = st.selectbox("Grade", ["All"] + GRADE_ORDER)

# ── Build query — AI_EVALUATION intentionally excluded; fetched on-demand ─────
where, params = [], []

if exam_filter != "All":
    where.append("e.EXAM_ID = ?")
    params.append(exam_map[exam_filter])

if student_filter.strip():
    where.append("e.STUDENT_NAME ILIKE ?")
    params.append(f"%{student_filter.strip()}%")

if grade_filter != "All":
    where.append("e.GRADE = ?")
    params.append(grade_filter)

where_sql = f"WHERE {' AND '.join(where)}" if where else ""

query = f"""
    SELECT
        e.EVAL_ID,
        x.EXAM_NAME,
        x.SUBJECT,
        e.STUDENT_NAME,
        e.TOTAL_MARKS_OBTAINED,
        e.TOTAL_MARKS_POSSIBLE,
        e.PERCENTAGE,
        e.GRADE,
        e.EVALUATED_AT
    FROM {DB}.{SCHEMA}.HW_EVALUATIONS e
    JOIN {DB}.{SCHEMA}.HW_EXAMS x ON e.EXAM_ID = x.EXAM_ID
    {where_sql}
    ORDER BY e.EVALUATED_AT DESC
    LIMIT 100
"""

rows = session.sql(query, params=params).collect()

if not rows:
    st.info("No evaluations found. Evaluate a student on the **Evaluate** page first.")
    st.stop()

# ── Single-pass: build all aggregates, table rows, and dropdown options ───────
total_evals  = 0
sum_pct      = 0.0
sum_marks    = 0.0
pass_count   = 0
grade_counts = {g: 0 for g in GRADE_ORDER}
table_data   = []
eval_options = {}   # label → EVAL_ID
eval_records = {}   # EVAL_ID → record dict (for detail metrics)

for r in rows:
    d   = r.as_dict() if hasattr(r, "as_dict") else dict(r)
    pct = d["PERCENTAGE"] or 0.0
    g   = d.get("GRADE", "")

    total_evals += 1
    sum_pct     += pct
    sum_marks   += (d["TOTAL_MARKS_OBTAINED"] or 0.0)
    if pct >= 50:
        pass_count += 1
    if g in grade_counts:
        grade_counts[g] += 1

    table_data.append({
        "Student":      d["STUDENT_NAME"],
        "Exam":         d["EXAM_NAME"],
        "Subject":      d["SUBJECT"] or "",
        "Marks":        f"{int(d['TOTAL_MARKS_OBTAINED'] or 0)}/{int(d['TOTAL_MARKS_POSSIBLE'] or 0)}",
        "Percentage":   f"{pct:.1f}%",
        "Grade":        g,
        "Evaluated At": str(d["EVALUATED_AT"]),
    })

    label             = f"[#{d['EVAL_ID']}] {d['STUDENT_NAME']} — {d['EXAM_NAME']} ({g})"
    eval_options[label] = d["EVAL_ID"]
    eval_records[d["EVAL_ID"]] = d

avg_pct   = sum_pct   / total_evals
avg_marks = sum_marks / total_evals
pass_rate = pass_count / total_evals * 100

# ── Summary metrics ───────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Evaluations", total_evals)
m2.metric("Avg Marks",         f"{avg_marks:.1f}")
m3.metric("Avg %",             f"{avg_pct:.1f}%")
m4.metric("Pass Rate (≥50%)",  f"{pass_rate:.0f}%")

st.markdown("---")

# ── Results table ─────────────────────────────────────────────────────────────
st.subheader("All Evaluations")
st.dataframe(table_data, width="stretch", hide_index=True)

st.markdown("---")

# ── Detailed view — loads AI_EVALUATION only for the selected record ──────────
st.subheader("Detailed Evaluation")

chosen     = st.selectbox("Select an evaluation", list(eval_options.keys()))
eval_id    = eval_options[chosen]
record     = eval_records[eval_id]
evaluation = load_evaluation(session, eval_id)

if evaluation is None:
    st.warning("Could not load evaluation data.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Marks",      f"{int(record['TOTAL_MARKS_OBTAINED'] or 0)} / {int(record['TOTAL_MARKS_POSSIBLE'] or 0)}")
c2.metric("Percentage", f"{(record['PERCENTAGE'] or 0.0):.1f}%")
c3.metric("Grade",      record["GRADE"])

render_evaluation_detail(evaluation)

# ── Grade distribution ────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Grade Distribution")

if any(v > 0 for v in grade_counts.values()):
    col_bar, col_line = st.columns(2)

    with col_bar:
        st.caption("Grade breakdown (count per grade)")
        st.bar_chart(grade_counts, color="#2C1E5B")

    with col_line:
        st.caption("Student scores — sorted by % (hover to see name & grade)")
        sorted_rows = sorted(
            table_data,
            key=lambda x: float(x["Percentage"].rstrip("%")),
            reverse=True,
        )
        scores_df = pd.DataFrame(
            [
                {
                    "Student": f"{d['Student']} ({d['Grade']})",
                    "Score (%)": float(d["Percentage"].rstrip("%")),
                }
                for d in sorted_rows
            ]
        ).set_index("Student")
        st.line_chart(scores_df, y="Score (%)")

show_footer()
