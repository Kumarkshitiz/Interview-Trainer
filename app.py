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
import os
from dotenv import load_dotenv

load_dotenv()
APP_SECRET = os.environ.get("APP_SECRET")
if not APP_SECRET:
    st.error("APP_SECRET not set — add APP_SECRET=<your password> to .env next to this file.")
    st.stop()

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Interview Trainer", page_icon="▣", layout="centered")

# ---------------- V3: single-user password gate ----------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("### ▣ interview_trainer")
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            if pw == APP_SECRET:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Wrong password.")
    st.stop()

AUTH_HEADERS = {"X-App-Secret": APP_SECRET}

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
DOMAIN_TAG = {  # short mono tag, like a file extension / module path
    "ml": "ml", "dl": "dl", "genai": "genai", "bigdata": "bigdata",
    "dbms": "dbms", "dsa": "dsa", "python": "py",
}

# ---- token system: "examiner's terminal" -- dark graphite console,
# phosphor-mint accent, monospace readouts for anything measured
# (scores, tags, progress) vs. serif for the actual question text you
# have to sit with and think about. Deliberately not the cream+serif
# or near-black+acid-green defaults. ----
BG = "#0F1115"
SURFACE = "#171A21"
SURFACE_BORDER = "#262B35"
INK = "#E7E5DE"
INK_SOFT = "#8B93A7"
ACCENT = "#6EE7C0"       # phosphor mint -- active / in-progress
TRACK = "#232833"        # remaining, in the donut
GOOD = "#6EE7C0"
WARN = "#E8A23D"
BAD = "#E2604F"
DOT_RED = "#4a3b3b"
DOT_AMBER = "#4a4234"
DOT_GREEN = "#324a3d"

DIFFICULTY_ICON = {"easy": "●", "medium": "●●", "hard": "●●●"}
SCORE_COLOR = {5: GOOD, 4: GOOD, 3: WARN, 2: BAD, 1: BAD, 0: INK_SOFT}

st.markdown(f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: {BG}; }}
    #MainMenu, footer {{ visibility: hidden; }}

    section[data-testid="stSidebar"] {{
        background-color: {SURFACE};
        border-right: 1px solid {SURFACE_BORDER};
    }}
    section[data-testid="stSidebar"] * {{ color: {INK}; }}

    .brand {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem;
        letter-spacing: 0.02em;
        color: {ACCENT};
        margin-bottom: 1.1rem;
    }}
    .brand span {{ color: {INK_SOFT}; }}

    .eyebrow {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: {INK_SOFT};
        margin-bottom: 0.6rem;
    }}

    /* terminal-window question card */
    .term-card {{
        background: {SURFACE};
        border: 1px solid {SURFACE_BORDER};
        border-radius: 10px;
        overflow: hidden;
        margin-bottom: 1.1rem;
    }}
    .term-titlebar {{
        display: flex;
        align-items: center;
        gap: 0.8rem;
        padding: 0.6rem 1rem;
        border-bottom: 1px solid {SURFACE_BORDER};
    }}
    .term-dots {{ display: flex; gap: 6px; flex-shrink: 0; }}
    .term-dots span {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
    .term-path {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        color: {INK_SOFT};
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }}
    .term-path b {{ color: {INK}; font-weight: 500; }}
    .term-diff {{
        margin-left: auto;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: {ACCENT};
        flex-shrink: 0;
    }}
    .term-body {{
        padding: 1.5rem 1.6rem 1.7rem;
        border-left: 3px solid {ACCENT};
    }}
    .term-prompt {{
        font-family: 'JetBrains Mono', monospace;
        color: {ACCENT};
        margin-right: 0.5rem;
    }}
    .term-question {{
        font-family: 'Source Serif 4', Georgia, serif;
        font-size: 1.2rem;
        line-height: 1.6;
        color: {INK};
        display: inline;
    }}

    /* feedback card */
    .feedback-card {{
        background: {SURFACE};
        border: 1px solid {SURFACE_BORDER};
        border-radius: 10px;
        padding: 1.4rem 1.6rem;
        margin-bottom: 1rem;
    }}
    .score-chip {{
        display: inline-block;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
        font-size: 0.95rem;
        padding: 0.25rem 0.65rem;
        border-radius: 6px;
        letter-spacing: 0.02em;
    }}
    .fb-label {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: {INK_SOFT};
        margin: 1rem 0 0.35rem;
    }}
    .fb-text {{ color: {INK}; line-height: 1.55; font-size: 0.98rem; }}

    /* buttons */
    .stButton > button {{
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        border-radius: 7px;
        border: 1px solid {SURFACE_BORDER};
        background: {SURFACE};
        color: {INK};
        transition: border-color 0.15s ease;
    }}
    .stButton > button:hover {{
        border-color: {ACCENT};
        color: {ACCENT};
    }}
    .stButton > button[kind="primary"] {{
        background: {ACCENT};
        color: {BG};
        border: none;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: {ACCENT};
        opacity: 0.88;
        color: {BG};
    }}

    textarea {{
        background-color: {SURFACE} !important;
        color: {INK} !important;
        border-color: {SURFACE_BORDER} !important;
        font-family: 'Inter', sans-serif !important;
    }}

    div[data-testid="stMetricValue"] {{ color: {INK}; font-family: 'JetBrains Mono', monospace; }}
    div[data-testid="stMetricLabel"] {{ color: {INK_SOFT}; }}

    h3 {{ color: {INK}; font-family: 'Inter', sans-serif; font-weight: 600; }}
</style>
""", unsafe_allow_html=True)


def fetch_next_question(domain: str, topic: str | None = None, exclude_id: int | None = None):
    params = {"domain": domain}
    if topic is not None:
        params["topic"] = topic
    if exclude_id is not None:
        params["exclude_id"] = exclude_id
    resp = requests.get(f"{API_BASE}/question/next", params=params, headers=AUTH_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_topics(domain: str):
    resp = requests.get(f"{API_BASE}/topics", params={"domain": domain}, headers=AUTH_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()["topics"]


def submit_answer(question_id: int, answer: str):
    resp = requests.post(
        f"{API_BASE}/answer/submit",
        json={"question_id": question_id, "answer": answer},
        headers=AUTH_HEADERS,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_summary(domain: str):
    resp = requests.get(f"{API_BASE}/stats/summary", params={"domain": domain}, headers=AUTH_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_attempt_history(question_id: int):
    resp = requests.get(f"{API_BASE}/questions/{question_id}/attempts", headers=AUTH_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()["attempts"]


def create_custom_question(domain: str, topic: str, subtopic: str, difficulty: str, source_text: str):
    resp = requests.post(
        f"{API_BASE}/questions/custom",
        json={
            "domain": domain, "topic": topic, "subtopic": subtopic or None,
            "difficulty": difficulty, "source_text": source_text,
        },
        headers=AUTH_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def transcribe_audio(audio_bytes: bytes):
    resp = requests.post(
        f"{API_BASE}/transcribe",
        files={"file": ("recording.wav", audio_bytes, "audio/wav")},
        headers=AUTH_HEADERS,
        timeout=60,  # local Whisper on CPU can take a while for longer recordings
    )
    resp.raise_for_status()
    return resp.json()["text"]


# ---------------- session state ----------------
if "domain" not in st.session_state:
    st.session_state.domain = DOMAINS[0]
if "current_question" not in st.session_state:
    st.session_state.current_question = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "locked_topic" not in st.session_state:
    st.session_state.locked_topic = None  # None = Auto (priority-driven)


def load_new_question(avoid_current: bool = False):
    """Fetch a new question. When avoid_current=True (Skip / Next), pass the
    currently-shown question's id so the backend doesn't just hand it right
    back. Respects a locked topic (Practice Mode) if one is set."""
    exclude_id = None
    if avoid_current and st.session_state.current_question:
        exclude_id = st.session_state.current_question["id"]
    st.session_state.current_question = fetch_next_question(
        st.session_state.domain, topic=st.session_state.locked_topic, exclude_id=exclude_id
    )
    st.session_state.last_result = None


# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown('<div class="brand">▣ interview<span>_</span>trainer</div>', unsafe_allow_html=True)

    selected_domain = st.selectbox(
        "Domain",
        DOMAINS,
        format_func=lambda d: DOMAIN_LABELS[d],
        index=DOMAINS.index(st.session_state.domain),
        label_visibility="collapsed",
    )

    if selected_domain != st.session_state.domain:
        st.session_state.domain = selected_domain
        st.session_state.locked_topic = None  # topic names don't carry across domains
        load_new_question()

    st.divider()
    st.markdown('<div class="eyebrow">Practice mode</div>', unsafe_allow_html=True)

    try:
        topics = fetch_topics(st.session_state.domain)
    except requests.exceptions.RequestException:
        topics = []

    topic_options = ["Auto (weakest first)"] + topics
    current_label = st.session_state.locked_topic or "Auto (weakest first)"
    selected_label = st.selectbox(
        "Topic", topic_options,
        index=topic_options.index(current_label) if current_label in topic_options else 0,
        label_visibility="collapsed",
    )
    new_locked_topic = None if selected_label == "Auto (weakest first)" else selected_label

    if new_locked_topic != st.session_state.locked_topic:
        st.session_state.locked_topic = new_locked_topic
        load_new_question()

    if st.session_state.locked_topic and topics:
        idx = topics.index(st.session_state.locked_topic)
        col_prev, col_next = st.columns(2)
        with col_prev:
            if st.button("← Prev", width="stretch", disabled=(idx == 0)):
                st.session_state.locked_topic = topics[idx - 1]
                load_new_question()
                st.rerun()
        with col_next:
            if st.button("Next →", width="stretch", disabled=(idx == len(topics) - 1)):
                st.session_state.locked_topic = topics[idx + 1]
                load_new_question()
                st.rerun()

    st.divider()
    st.markdown('<div class="eyebrow">Add your own question</div>', unsafe_allow_html=True)
    with st.expander("Add a question"):
        with st.form("custom_question_form", clear_on_submit=True):
            cq_topic = st.text_input("Topic", value=st.session_state.locked_topic or "")
            cq_subtopic = st.text_input("Subtopic (optional)")
            cq_difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"], index=1)
            cq_text = st.text_area("Question text", height=100)
            if st.form_submit_button("Add & practice now", width="stretch"):
                if not cq_topic.strip() or not cq_text.strip():
                    st.warning("Topic and question text are required.")
                else:
                    new_q = create_custom_question(
                        st.session_state.domain, cq_topic.strip(), cq_subtopic.strip(),
                        cq_difficulty, cq_text.strip()
                    )
                    st.session_state.current_question = new_q
                    st.session_state.last_result = None
                    st.rerun()

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
            hole=0.7,
            marker=dict(colors=[ACCENT, TRACK], line=dict(color=SURFACE, width=2)),
            textinfo="none",
            sort=False,
            showlegend=False,
        )])
        fig.add_annotation(
            text=f"<b>{pct}%</b><br><span style='font-size:11px;color:{INK_SOFT}'>done</span>",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=22, color=INK, family="JetBrains Mono"),
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
diff = q["difficulty"]

st.markdown(f"""
<div class="term-card">
    <div class="term-titlebar">
        <div class="term-dots">
            <span style="background:{DOT_RED}"></span>
            <span style="background:{DOT_AMBER}"></span>
            <span style="background:{DOT_GREEN}"></span>
        </div>
        <div class="term-path">{DOMAIN_TAG[q['domain']]} / <b>{q['topic']}</b>{' / ' + q['subtopic'] if q.get('subtopic') else ''}</div>
        <div class="term-diff">{DIFFICULTY_ICON.get(diff, '')} {diff}</div>
    </div>
    <div class="term-body">
        <span class="term-prompt">&gt;</span><span class="term-question">{q['question']}</span>
    </div>
</div>
""", unsafe_allow_html=True)

try:
    history = fetch_attempt_history(q["id"])
except requests.exceptions.RequestException:
    history = []

if history:
    with st.expander(f"Past attempts on this question ({len(history)})"):
        for h in history:
            st.markdown(f"**{h['timestamp']} · score {h['score']}/5**")
            st.caption(h["your_answer"])
            st.divider()

audio = st.audio_input("Or record your answer", key=f"audio_{q['id']}")
if audio is not None:
    audio_bytes = audio.getvalue()
    audio_fingerprint = (q["id"], len(audio_bytes), hash(audio_bytes))
    if st.session_state.get("last_transcribed") != audio_fingerprint:
        with st.spinner("Transcribing..."):
            try:
                text = transcribe_audio(audio_bytes)
                st.session_state[f"answer_{q['id']}"] = text
                st.session_state["last_transcribed"] = audio_fingerprint
                st.rerun()
            except requests.exceptions.RequestException as e:
                st.error(f"Transcription failed: {e}")

answer = st.text_area("Your answer", height=180, key=f"answer_{q['id']}", label_visibility="collapsed",
                       placeholder="Write your answer here, or record above...")

col1, col2 = st.columns(2)
with col1:
    submit_clicked = st.button("Submit answer", type="primary", width="stretch")
with col2:
    skip_clicked = st.button("Next", width="stretch")

if skip_clicked:
    load_new_question(avoid_current=True)
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
    <div class="feedback-card">
        <div class="eyebrow">Result</div>
        <span class="score-chip" style="background:{color}22; color:{color};">{score}/5</span>
        {f'<div class="fb-label">What&#39;s missing</div><div class="fb-text">{r["missing"]}</div>' if r["missing"] else ''}
        <div class="fb-label">Corrected explanation</div>
        <div class="fb-text">{r['corrected_explanation']}</div>
        {f'<div class="fb-label">Model answer</div><div class="fb-text">{r["model_answer"]}</div>' if r.get("model_answer") else ''}
        {f'<div class="fb-label">Vs. last attempt</div><div class="fb-text">{r["comparison"]}</div>' if r.get("comparison") else ''}
    </div>
    """, unsafe_allow_html=True)