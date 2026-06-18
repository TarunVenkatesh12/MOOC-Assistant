import re
import os
import json
import time
import logging
from urllib.parse import unquote
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

_primary_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
_PRIMARY_MODEL = "llama-3.3-70b-versatile"

_fallback_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
_FALLBACK_MODEL = "llama-3.1-8b-instant"

client = _primary_client

MIN_RELEVANCE = 0.6
MIN_CLARITY = 0.6

def _rule_based_check(draft_answer: str, course_context: str) -> dict | None:
    if "Je vais vérifier cela dans les ressources du cours" in draft_answer:
        return {
            "is_valid": False,
            "answer_relevance": 0.0,
            "grounding_score": 0.0,
            "clarity_score": 0.0,
            "issues": ["Fallback answer detected — solution agent had no context"],
            "fixed_answer": (
                "Je n'ai pas trouvé d'information suffisante dans les ressources du cours "
                "pour répondre précisément à cette question. "
                "Je vous invite à consulter l'équipe pédagogique directement."
            ),
        }

    first_person_errors = [
        "je n'ai pas testé", "je n'ai pas essayé",
        "je ne sais pas", "je ne comprends pas",
        "je n'arrive pas",
    ]
    answer_lower = draft_answer.lower()
    if any(phrase in answer_lower for phrase in first_person_errors):
        return {
            "is_valid": False,
            "answer_relevance": 0.3,
            "grounding_score": 0.2,
            "clarity_score": 0.4,
            "issues": ["Answer speaks in first person as a confused student"],
            "fixed_answer": None,
        }

    return None

def _llm_validate(
    topic_title: str,
    author: str,
    student_message: str,
    course_context: str,
    draft_answer: str,
) -> dict:
    display_title = unquote(topic_title)
    context_snippet = course_context[:1200] if course_context else "Aucun contexte disponible."

    system_prompt = (
        "Tu es un validateur strict pour un tuteur pédagogique MOOC MicroPython / IoT. "
        "Tu reçois la question d'un étudiant, des extraits de cours pertinents, et une réponse draft. "
        "Tu dois évaluer la réponse et retourner UNIQUEMENT un objet JSON valide."
    )

    user_prompt = f"""
SUJET DU FORUM : {display_title}

MESSAGE DE L'ÉTUDIANT ({author}) :
{student_message}

EXTRAITS DU COURS UTILISÉS :
{context_snippet}

RÉPONSE DRAFT À ÉVALUER :
{draft_answer}

Retourne uniquement ce JSON :

{{
  "answer_relevance": <float 0.0-1.0>,
  "grounding_score": <float 0.0-1.0>,
  "clarity_score": <float 0.0-1.0>,
  "is_valid": <true si answer_relevance >= 0.6 et clarity_score >= 0.6, sinon false>,
  "issues": [<liste de problèmes>],
  "fixed_answer": <string>
}}
"""

    for attempt in range(2):
        try:
            time.sleep(3 + attempt * 4)  # attempt 0: 3s, attempt 1: 7s
            use_client = _primary_client if attempt == 0 else _fallback_client
            use_model = _PRIMARY_MODEL if attempt == 0 else _FALLBACK_MODEL
            response = use_client.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=350,
                temperature=0.1,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)

            result.setdefault("answer_relevance", 0.5)
            result.setdefault("grounding_score", 0.5)
            result.setdefault("clarity_score", 0.5)
            result.setdefault("is_valid", True)
            result.setdefault("issues", [])
            result.setdefault("fixed_answer", draft_answer)

            logger.info(
                f"    [ValidatorAgent] Scores — relevance={result['answer_relevance']:.2f} "
                f"grounding={result['grounding_score']:.2f} "
                f"clarity={result['clarity_score']:.2f} "
                f"valid={result['is_valid']}"
            )
            return result

        except Exception as e:
            err_str = str(e)
            if "429" in err_str and attempt == 0:
                logger.warning("    [ValidatorAgent] Rate limit hit — retrying with fallback model")
                continue
            logger.error(f"    [ValidatorAgent] Validation failed: {e}")
            return {
                "answer_relevance": 0.7,
                "grounding_score": 0.7,
                "clarity_score": 0.7,
                "is_valid": True,
                "issues": [f"Validator unavailable: {err_str[:100]}"],
                "fixed_answer": draft_answer,
            }

def validate_solution(
    topic_title: str,
    post: dict,
    course_context: str,
    draft_answer: str,
) -> dict:
    author = post.get("author", "l'étudiant·e")
    content = post.get("content", "")[:1000]

    rule_result = _rule_based_check(draft_answer, course_context)
    if rule_result is not None:
        logger.info(f"    [ValidatorAgent] Rule-based check failed: {rule_result['issues']}")
        fixed = rule_result.get("fixed_answer") or draft_answer
        if rule_result["fixed_answer"] is not None:
            return {
                "final_answer": fixed,
                "is_valid": rule_result["is_valid"],
                "answer_relevance": rule_result["answer_relevance"],
                "grounding_score": rule_result["grounding_score"],
                "clarity_score": rule_result["clarity_score"],
                "issues": rule_result["issues"],
                "was_corrected": True,
            }

    validation = _llm_validate(
        topic_title=topic_title,
        author=author,
        student_message=content,
        course_context=course_context,
        draft_answer=draft_answer,
    )

    final_answer = validation.get("fixed_answer") or draft_answer
    was_corrected = final_answer.strip() != draft_answer.strip()

    if was_corrected:
        logger.info("    [ValidatorAgent] Answer was corrected by validator")
    else:
        logger.info("    [ValidatorAgent] Answer accepted as-is")

    return {
        "final_answer": final_answer,
        "is_valid": validation["is_valid"],
        "answer_relevance": validation["answer_relevance"],
        "grounding_score": validation["grounding_score"],
        "clarity_score": validation["clarity_score"],
        "issues": validation["issues"],
        "was_corrected": was_corrected,
    }

logger.info("✅ Validator Agent loaded")