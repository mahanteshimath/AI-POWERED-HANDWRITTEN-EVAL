# AI-Powered Handwritten Answer Evaluation System

An end-to-end Streamlit application that uses **Snowflake Cortex AI** to automatically evaluate handwritten student answer sheets against an answer key and marking rubric — providing marks, grades, question-wise feedback, and recommendations.

---

## Overview

| Layer | Technology |
|---|---|
| Frontend | Streamlit (multi-page) |
| Database & Storage | Snowflake (`IITJ.MH`) |
| File Storage | Snowflake Stage (`HW_EVAL_STAGE`, SSE-encrypted) |
| OCR | Snowflake Cortex `AI_PARSE_DOCUMENT` |
| LLM Evaluation | Snowflake Cortex `AI_COMPLETE` (`claude-sonnet-4-6`) |

All OCR and AI inference happens **inside Snowflake** — no external APIs, no local text extraction.

---

## Architecture

```
┌────────────────────────────────────────────────────┐
│                  Streamlit App                     │
│                                                    │
│  📋 Setup Exam  │  🎯 Evaluate  │  📊 Results      │
└────────┬───────────────┬──────────────────────────-┘
         │               │
         ▼               ▼
┌─────────────────────────────────────────────────-──┐
│                  Snowflake                         │
│                                                    │
│  HW_EVAL_STAGE/                                    │
│  ├── answer_keys/   (answer key PDFs)              │
│  ├── rubrics/       (rubric PDFs)                  │
│  └── student_answers/ (student answer PDFs)        │
│                                                    │
│  AI_PARSE_DOCUMENT(TO_FILE(...), {mode:'OCR'})     │
│       ↓ extracted text                             │
│  AI_COMPLETE('claude-sonnet-4-6', prompt)          │
│       ↓ JSON evaluation                            │
│  HW_EVALUATIONS  (results stored)                  │
└────────────────────────────────────────────────────┘
```

---

## Evaluation Pipeline

```
Teacher sets up exam:
  answer_key.pdf  ──► Snowflake Stage (answer_keys/)
  rubric.pdf      ──► Snowflake Stage (rubrics/)

Student evaluation:
  student_answer.pdf ──► Snowflake Stage (student_answers/)
                              │
               ┌──────────────┼──────────────┐
               ▼              ▼              ▼
        OCR answer key   OCR rubric   OCR student answer
        (AI_PARSE_DOC)  (AI_PARSE_DOC) (AI_PARSE_DOC)
               └──────────────┼──────────────┘
                               ▼
                   AI_COMPLETE (claude-sonnet-4-6)
                               ▼
              Structured JSON evaluation result
                               ▼
              Display + Save to HW_EVALUATIONS
```

---

## Features

- **PDF-native** — upload scanned handwritten answer sheets directly; no manual transcription
- **OCR in Snowflake** — `AI_PARSE_DOCUMENT` with `page_split: TRUE` handles multi-page documents and large PDFs
- **Structured AI grading** — per-question marks, correctness status, and feedback
- **Question-wise breakdown** — 🟢 Correct / 🟡 Partial / 🔴 Incorrect badges per question
- **Strengths & recommendations** — actionable improvement suggestions per student
- **Results dashboard** — filter by exam, student name, and grade; grade distribution chart
- **Dual-environment auth** — runs locally (via `secrets.toml`) or natively inside Streamlit in Snowflake

---

## Grading Scale

| Grade | Percentage |
|---|---|
| A+ | ≥ 90% |
| A  | ≥ 80% |
| B+ | ≥ 70% |
| B  | ≥ 60% |
| C  | ≥ 50% |
| D  | ≥ 40% |
| F  | < 40% |

---

## Snowflake Objects Created (auto on first run)

| Object | Type | Purpose |
|---|---|---|
| `IITJ.MH.HW_EVAL_STAGE` | Stage (SSE) | Stores all uploaded PDFs |
| `IITJ.MH.HW_EXAMS` | Table | Exam metadata + stage file paths |
| `IITJ.MH.HW_EVALUATIONS` | Table | AI evaluation results per student |

### `HW_EXAMS` schema

| Column | Type | Description |
|---|---|---|
| `EXAM_ID` | NUMBER (autoincrement) | Primary key |
| `EXAM_NAME` | VARCHAR | Name of the exam |
| `SUBJECT` | VARCHAR | Subject / course name |
| `ANSWER_KEY_FILE` | VARCHAR | Stage path to answer key PDF |
| `RUBRIC_FILE` | VARCHAR | Stage path to rubric PDF |
| `TOTAL_MARKS` | NUMBER | Maximum marks for the exam |
| `CREATED_AT` | TIMESTAMP_NTZ | Creation timestamp |

### `HW_EVALUATIONS` schema

| Column | Type | Description |
|---|---|---|
| `EVAL_ID` | NUMBER (autoincrement) | Primary key |
| `EXAM_ID` | NUMBER | Foreign key → `HW_EXAMS` |
| `STUDENT_NAME` | VARCHAR | Student's name |
| `STUDENT_ANSWER_FILE` | VARCHAR | Stage path to student's answer PDF |
| `AI_EVALUATION` | VARCHAR(16M) | Full JSON evaluation from Claude |
| `TOTAL_MARKS_OBTAINED` | FLOAT | Marks awarded |
| `TOTAL_MARKS_POSSIBLE` | FLOAT | Maximum marks |
| `PERCENTAGE` | FLOAT | Score percentage |
| `GRADE` | VARCHAR | Letter grade |
| `EVALUATED_AT` | TIMESTAMP_NTZ | Evaluation timestamp |

---

## Project Structure

```
AI POWERED HANDWRITTEN EVAL/
├── Home.py                    # Entry point: Snowflake connection, DB/stage setup, navigation
├── pages/
│   ├── 01_Setup_Exam.py       # Upload answer key PDF + rubric PDF, define total marks
│   ├── 02_Evaluate.py         # Upload student PDF, run OCR + AI evaluation
│   └── 03_Results.py          # Results dashboard with filters and grade distribution
├── .streamlit/
│   └── secrets.toml           # Snowflake credentials (local only, gitignored)
├── requirements.txt
└── .gitignore
```

---

## Setup

### Prerequisites

- Python 3.9+
- Conda (recommended) or pip
- Snowflake account with Cortex AI enabled
- `ACCOUNTADMIN` role (or role with `CREATE STAGE`, `CREATE TABLE`, and Cortex grants)

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd "AI POWERED HANDWRITTEN EVAL"
conda activate monty_streamlit   # or your preferred env
pip install -r requirements.txt
```

### 2. Configure Snowflake credentials

Create `.streamlit/secrets.toml`:

```toml
[connections.snowflake]
account   = "YOUR_ACCOUNT_IDENTIFIER"
user      = "YOUR_USERNAME"
password  = "YOUR_PASSWORD"
role      = "ACCOUNTADMIN"
warehouse = "COMPUTE_WH"
database  = "iitj"
schema    = "mh"
```

> **Note:** This file is listed in `.gitignore` and must never be committed.

### 3. Run the app

```bash
streamlit run Home.py
```

Open **http://localhost:8501** in your browser.

On first launch, the app will automatically create the Snowflake stage and tables.

---

## Usage

### Step 1 — Setup Exam (`📋 Setup Exam`)

1. Enter the exam name and subject
2. Upload the **answer key PDF** (typed or scanned)
3. Upload the **rubric / marking scheme PDF**
4. Set the total marks
5. Click **Save Exam** — both PDFs are stored securely in Snowflake Stage

### Step 2 — Evaluate Student (`🎯 Evaluate`)

1. Select the exam from the dropdown
2. Enter the student's name
3. Upload the **student's handwritten answer sheet** as a PDF
4. Click **Run AI Evaluation**

The system will:
- Upload the answer sheet to Snowflake Stage
- Run `AI_PARSE_DOCUMENT` OCR on all three PDFs (answer key, rubric, student answer)
- Send the extracted texts to `claude-sonnet-4-6` via `AI_COMPLETE`
- Display marks, grade, per-question breakdown, strengths, and recommendations
- Save the full evaluation to `HW_EVALUATIONS`

### Step 3 — View Results (`📊 Results`)

- Filter evaluations by exam, student name, or grade
- View summary metrics: total evaluations, average marks, average percentage
- Drill into any evaluation for the full question-wise breakdown
- Grade distribution bar chart

---

## Supported LLM Models

| Model | Description |
|---|---|
| `claude-sonnet-4-6` | Default — latest, highest accuracy |
| `claude-3-5-sonnet` | Fallback option |

Model can be switched from the sidebar on the Evaluate page.

---

## Requirements

```
streamlit
snowflake-snowpark-python
```

---

## Notes

- **Handwritten PDFs**: Scanned PDFs work best when scanned at ≥ 300 DPI
- **Large documents**: `page_split: TRUE` in `AI_PARSE_DOCUMENT` automatically handles multi-page PDFs that would otherwise exceed Cortex token limits
- **Snowflake Native App**: The app is compatible with Streamlit in Snowflake — `get_active_session()` is used when available, with local `secrets.toml` as fallback
- **File naming**: All uploaded files are prefixed with a Unix timestamp to prevent name collisions in the stage
