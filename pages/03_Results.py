import streamlit as st
import json

st.title("📊 Evaluation Results")
st.caption("View and analyse all student evaluations.")

# ── Snowflake session ────────────────────────────────────────────────────────
session = st.session_state.get_snowflake_session()

DB, SCHEMA = "IITJ", "MH"

# ── Filters ──────────────────────────────────────────────────────────────────
with st.container(border=True):
    col1, col2, col3 = st.columns(3)

    with col1:
        exams = session.sql(
            f"SELECT DISTINCT EXAM_ID, EXAM_NAME FROM {DB}.{SCHEMA}.HW_EXAMS ORDER BY EXAM_NAME"
        ).collect()
        exam_map = {r["EXAM_NAME"]: r["EXAM_ID"] for r in exams}
        exam_filter = st.selectbox("Exam", ["All"] + list(exam_map.keys()))

    with col2:
        student_filter = st.text_input("Student name contains", placeholder="e.g. Rahul")

    with col3:
        grade_filter = st.selectbox("Grade", ["All", "A+", "A", "B+", "B", "C", "D", "F"])

# ── Build query ──────────────────────────────────────────────────────────────
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
        e.AI_EVALUATION,
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

# ── Summary metrics ──────────────────────────────────────────────────────────
data = [r.as_dict() if hasattr(r, "as_dict") else dict(r) for r in rows]

total_evals = len(data)
avg_pct = sum(d["PERCENTAGE"] for d in data) / total_evals if total_evals else 0
avg_marks = sum(d["TOTAL_MARKS_OBTAINED"] for d in data) / total_evals if total_evals else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Evaluations", total_evals)
m2.metric("Avg Marks", f"{avg_marks:.1f}")
m3.metric("Avg %", f"{avg_pct:.1f}%")
m4.metric("Top Grade", data[0]["GRADE"] if data else "N/A")

st.markdown("---")

# ── Results table ────────────────────────────────────────────────────────────
st.subheader("All Evaluations")
table_data = [
    {
        "Student": d["STUDENT_NAME"],
        "Exam": d["EXAM_NAME"],
        "Subject": d["SUBJECT"] or "",
        "Marks": f"{d['TOTAL_MARKS_OBTAINED']}/{d['TOTAL_MARKS_POSSIBLE']}",
        "Percentage": f"{d['PERCENTAGE']:.1f}%",
        "Grade": d["GRADE"],
        "Evaluated At": str(d["EVALUATED_AT"]),
    }
    for d in data
]
st.dataframe(table_data, use_container_width=True, hide_index=True)

st.markdown("---")

# ── Detailed view ────────────────────────────────────────────────────────────
st.subheader("Detailed Evaluation")

eval_options = {
    f"{d['STUDENT_NAME']} — {d['EXAM_NAME']} ({d['GRADE']})": d for d in data
}
chosen = st.selectbox("Select an evaluation", list(eval_options.keys()))
record = eval_options[chosen]

try:
    evaluation = json.loads(record["AI_EVALUATION"]) if isinstance(record["AI_EVALUATION"], str) else record["AI_EVALUATION"]
except (json.JSONDecodeError, TypeError):
    evaluation = None

if evaluation is None:
    st.warning("Could not parse evaluation data.")
    st.stop()

# Metrics
c1, c2, c3 = st.columns(3)
c1.metric("Marks", f"{record['TOTAL_MARKS_OBTAINED']} / {record['TOTAL_MARKS_POSSIBLE']}")
c2.metric("Percentage", f"{record['PERCENTAGE']:.1f}%")
c3.metric("Grade", record["GRADE"])

# Questions
questions = evaluation.get("questions", [])
if questions:
    st.markdown("#### Question-wise Breakdown")
    for q in questions:
        qnum = q.get("question_number", "?")
        topic = q.get("topic", "")
        m_obt = q.get("marks_obtained", 0)
        m_max = q.get("max_marks", 0)
        correctness = q.get("correctness", "")
        feedback = q.get("feedback", "")

        badge = {"correct": "🟢", "partially_correct": "🟡", "incorrect": "🔴"}.get(correctness, "⚪")

        with st.expander(f"Q{qnum}: {topic}  —  {badge} {m_obt}/{m_max} marks"):
            st.write(f"**Status:** {correctness.replace('_', ' ').title()}")
            st.write(f"**Feedback:** {feedback}")

# Overall
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

# ── Grade distribution ───────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Grade Distribution")
grade_counts = {}
for d in data:
    g = d["GRADE"]
    grade_counts[g] = grade_counts.get(g, 0) + 1

grade_order = ["A+", "A", "B+", "B", "C", "D", "F"]
chart_data = {g: grade_counts.get(g, 0) for g in grade_order if g in grade_counts}

if chart_data:
    st.bar_chart(chart_data)
