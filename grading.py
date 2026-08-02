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

Also write a model answer: a strong, concise answer to the question as a top
candidate would actually give it in an interview -- not a textbook excerpt,
not padded, just what a great answer sounds like out loud.
{comparison_instruction}

Respond ONLY with a JSON object in this exact shape, no markdown fences, no extra text:
{{
  "score": <integer 1-5>,
  "missing": "<1-3 sentences on what's missing or wrong, empty string if score is 5>",
  "corrected_explanation": "<a concise, correct explanation of the concept, 2-5 sentences>",
  "model_answer": "<a strong exemplar answer to the original question, 2-5 sentences, interview-spoken register not textbook register>"{comparison_field}
}}"""

COMPARISON_INSTRUCTION = """
The student has attempted this question before. You are also given their most
recent previous answer and its score. Compare the NEW answer to the PREVIOUS
one directly -- don't just compare the numeric scores. A same-score answer
can still show real improvement (or regression) in reasoning, completeness,
or clarity. Say plainly whether they did better, worse, or about the same,
and why, in 1-2 sentences."""

COMPARISON_FIELD = """,
  "comparison": "<1-2 sentences: better/worse/about the same than their previous attempt, and why>\""""


def grade_answer(
    question_text: str,
    student_answer: str,
    context_chunks: list,
    domain: str,
    previous_attempt: dict | None = None,
) -> dict:
    validate_domain(domain)
    label = DOMAIN_LABELS.get(domain, domain)

    context_block = "\n\n".join(
        f"[{c['source_book']}, p.{c['page']}]: {c['text']}" for c in context_chunks
    ) or "(no reference context retrieved)"

    comparison_instruction = COMPARISON_INSTRUCTION if previous_attempt else ""
    comparison_field = COMPARISON_FIELD if previous_attempt else ""

    previous_block = ""
    if previous_attempt:
        previous_block = f"""

Student's most recent PREVIOUS answer to this same question (scored {previous_attempt['score']}/5):
{previous_attempt['your_answer']}"""

    user_prompt = f"""Question: {question_text}

Reference context (may be partial/imperfect, use your own {label} knowledge alongside it):
{context_block}
{previous_block}

Student's NEW answer:
{student_answer}

Grade this answer now."""

    response = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(
                label=label, comparison_instruction=comparison_instruction, comparison_field=comparison_field
            )},
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
            "model_answer": "",
        }

    parsed["score"] = int(parsed.get("score", 0))
    parsed.setdefault("model_answer", "")
    parsed.setdefault("comparison", "")
    return parsed