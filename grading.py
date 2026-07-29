import json
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, validate_domain, DOMAIN_LABELS

_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT_TEMPLATE = """You are grading a student's answer to a {label} interview question.

Grade strictly but fairly on a 1-5 scale:
1 = answer is wrong or shows no understanding
2 = major gaps or misconceptions
3 = partially correct, missing key points
4 = mostly correct, minor gaps
5 = complete and correct

Use the provided reference context (excerpts from {label} reference material) to check
factual accuracy, but do not penalize the student for not using the reference's exact
phrasing — grade the underlying understanding, not the wording.

Respond ONLY with a JSON object in this exact shape, no markdown fences, no extra text:
{{
  "score": <integer 1-5>,
  "missing": "<1-3 sentences on what's missing or wrong, empty string if score is 5>",
  "corrected_explanation": "<a concise, correct explanation of the concept, 2-5 sentences>"
}}"""


def grade_answer(question_text: str, student_answer: str, context_chunks: list, domain: str) -> dict:
    validate_domain(domain)
    label = DOMAIN_LABELS.get(domain, domain)

    context_block = "\n\n".join(
        f"[{c['source_book']}, p.{c['page']}]: {c['text']}" for c in context_chunks
    ) or "(no reference context retrieved)"

    user_prompt = f"""Question: {question_text}

Reference context (may be partial/imperfect, use your own {label} knowledge alongside it):
{context_block}

Student's answer:
{student_answer}

Grade this answer now."""

    response = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(label=label)},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    raw = response.choices[0].message.content.strip()

    # models occasionally wrap JSON in markdown fences despite instructions — strip defensively
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # fail safe: don't crash the request, surface something usable
        parsed = {
            "score": 0,
            "missing": "Grading response could not be parsed — please retry.",
            "corrected_explanation": raw[:500],
        }

    parsed["score"] = int(parsed.get("score", 0))
    return parsed