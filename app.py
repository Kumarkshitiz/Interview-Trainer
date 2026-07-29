"""
Streamlit frontend for the Interview Trainer.

Flow: pick domain -> question shown -> answer -> submit -> score/feedback
-> progress (donut: attempted vs remaining, center-labeled, + avg score).

Usage:
    streamlit run app.py

Expects the FastAPI backend running separately:
    uvicorn main:app --reload
"""

import streamlit as st
import requests
import plotly.graph_objects as go

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Interview Trainer", page_icon="◆", layout="centered")

DOMAINS = ["ml", "dl", "genai", "bigdata", "dbms", "dsa", "python"]
DOMAIN_LABELS = {
    "ml": "Machine Learning",
    "dl": "Deep Learning",
    "genai": "Generative AI / LLMs",
    "bigdata": "Big Data / Data Engineering",
    "dbms": "Databases / SQL",
    "dsa": "Data Structures & Algorithms",
    "python": "Python",
}

# ---- signature palette: deep slate + amber accent, not the default
# Streamlit blue and not the cream/terracotta AI-design cliche ----
INK = "#1B1F2A"
INK_SOFT = "#4A5266"
PAPER = "#F7F6F3"
ACCENT = "#E0A458"       # amber -- "in progress" / attempted
TRACK = "#DDD9D0"        # warm gray -- remaining
GOOD = "#4C9A6A"
WARN = "#D9A441"
BAD = "#C2543F"

DIFFICULTY_ICON = {"easy": "●", "medium": "●●", "hard": "●●●"}
SCORE_COLOR = {5: GOOD, 4: GOOD, 3: WARN, 2: BAD, 1: BAD, 0: INK_SOFT}

st.markdown(f"""
<style>
    .stApp {{ background-color: {PAPER}; }}
    h1, h2, h3 {{ font-family: 'Georgia', 'Times New Roman', serif; color: {INK}; }}
    .question-card {{
        background: white;
        border: 1px solid #E6E2D8;
        border-radius: 10px;
        padding: 1.6rem 1.8rem;
        margin-bottom: 1rem;
    }}
    .eyebrow {{
        font-family: 'Georgia', serif;
        font-size: 0.78rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {INK_SOFT};
        margin-bottom: 0.3rem;
    }}
    div[data-testid="stMetricValue"] {{ color: {INK}; }}
</style>
""", unsafe_allow_html=True)


def fetch_next_question(domain: str):
    resp = requests.get(f"{API_BASE}/question/next", params={"domain": domain}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def submit_answer(question_id: int, answer: str):
    resp = requests.post(
        f"{API_BASE}/answer/submit",
        json={"question_id": question_id, "answer": answer},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_summary(domain: str):
    resp = requests.get(f"{API_BASE}/stats/summary", params={"domain": domain}, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------- session state ----------------
if "domain" not in st.session_state:
    st.session_state.domain = DOMAINS[0]
if "current_question" not in st.session_state:
    st.session_state.current_question = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None


def load_new_question():
    st.session_state.current_question = fetch_next_question(st.session_state.domain)
    st.session_state.last_result = None


# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown("### Interview Trainer")
    selected_domain = st.selectbox(
        "Domain",
        DOMAINS,
        format_func=lambda d: DOMAIN_LABELS[d],
        index=DOMAINS.index(st.session_state.domain),
        label_visibility="collapsed",
    )

    if selected_domain != st.session_state.domain:
        st.session_state.domain = selected_domain
        load_new_question()

    if st.button("New question", width="stretch"):
        load_new_question()

    st.divider()
    st.markdown('<div class="eyebrow">Progress</div>', unsafe_allow_html=True)

    try:
        summary = fetch_summary(st.session_state.domain)
    except requests.exceptions.RequestException:
        summary = None

    if summary and summary["total_questions"] > 0:
        attempted = summary["attempted_questions"]
        total = summary["total_questions"]
        remaining = summary["remaining_questions"]
        pct = round(100 * attempted / total) if total else 0

        fig = go.Figure(data=[go.Pie(
            values=[attempted, remaining],
            hole=0.68,
            marker=dict(colors=[ACCENT, TRACK], line=dict(color=PAPER, width=2)),
            textinfo="none",
            sort=False,
            showlegend=False,
        )])
        # center label lives INSIDE the donut hole -- no legend, nothing to overlap
        fig.add_annotation(
            text=f"<b>{pct}%</b><br><span style='font-size:11px;color:{INK_SOFT}'>done</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(size=22, color=INK),
        )
        fig.update_layout(
            margin=dict(t=6, b=6, l=6, r=6),
            height=170,
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        col_a, col_b = st.columns(2)
        col_a.metric("Attempted", f"{attempted}/{total}")
        avg = summary["average_score"]
        col_b.metric("Avg score", f"{avg}/5" if avg is not None else "—")
    else:
        st.caption("No questions loaded for this domain yet.")

# ---------------- main: question + answer ----------------
st.markdown(f"### {DOMAIN_LABELS[st.session_state.domain]}")

if st.session_state.current_question is None:
    try:
        load_new_question()
    except requests.exceptions.RequestException as e:
        st.error(f"Couldn't reach the backend at {API_BASE}. Is `uvicorn main:app --reload` running?\n\n{e}")
        st.stop()

q = st.session_state.current_question

st.markdown(f"""
<div class="question-card">
    <div class="eyebrow">{q['topic']} · {q.get('subtopic') or ''} · {DIFFICULTY_ICON.get(q['difficulty'], '')} {q['difficulty']}</div>
    <div style="font-size:1.15rem; line-height:1.5; color:{INK};">{q['question']}</div>
</div>
""", unsafe_allow_html=True)

answer = st.text_area("Your answer", height=180, key=f"answer_{q['id']}", label_visibility="collapsed",
                       placeholder="Write your answer here...")

col1, col2 = st.columns(2)
with col1:
    submit_clicked = st.button("Submit answer", type="primary", width="stretch")
with col2:
    skip_clicked = st.button("Skip", width="stretch")

if skip_clicked:
    load_new_question()
    st.rerun()

if submit_clicked:
    if not answer.strip():
        st.warning("Write an answer before submitting.")
    else:
        with st.spinner("Grading..."):
            try:
                result = submit_answer(q["id"], answer)
                st.session_state.last_result = result
            except requests.exceptions.RequestException as e:
                st.error(f"Grading request failed: {e}")

# ---------------- feedback ----------------
if st.session_state.last_result:
    r = st.session_state.last_result
    score = r["score"]
    color = SCORE_COLOR.get(score, INK_SOFT)

    st.markdown(f"""
    <div class="question-card" style="border-left: 4px solid {color};">
        <div class="eyebrow">Score</div>
        <div style="font-size:1.6rem; font-weight:bold; color:{color};">{score}/5</div>
    """, unsafe_allow_html=True)

    if r["missing"]:
        st.markdown(f"**What's missing:** {r['missing']}")
    st.markdown(f"**Corrected explanation:** {r['corrected_explanation']}")
    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("Next question", width="stretch"):
        load_new_question()
        st.rerun()