import re
import os
import time
import logging
from urllib.parse import unquote
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

try:
    from rag.retriever import retrieve_as_context
    RAG_AVAILABLE = True
    logger.info("✅ Solution Agent: RAG retriever loaded")
except (ImportError, ModuleNotFoundError) as e:
    RAG_AVAILABLE = False
    logger.warning(f"⚠️  Solution Agent: RAG unavailable ({e}) — generic answers only")
    def retrieve_as_context(query: str, **kwargs) -> str:
        return ""

INSTRUCTOR_NAMES = {"bgaultier", "baptiste", "equipe pédagogique", "staff"}

LOW_VALUE_PHRASES = [
    "merci",
    "merci beaucoup",
    "merci pour votre réponse",
    "merci pour ta réponse",
    "merci à tous",
    "bonjour",
    "bonsoir",
    "salut",
    "bonne journée",
    "bonne soirée",
    "bonne continuation",
    "cordialement",
    "à bientôt",
    "ok merci",
    "parfait merci",
    "super merci",
    "c'est clair",
    "c'est bon",
    "ça va",
    "ca va",
    "je comprends",
    "je suis d'accord",
    "je suis ok",
]

COMMENTARY_PHRASES = [
    "je suis déçu",
    "je ne suis pas content",
    "je ne suis pas très content",
    "j'arrête",
    "j'abandonne",
    "je quitte",
    "je me plains",
    "ça m'énerve",
    "ca m'enerve",
    "c'est nul",
]

ADMIN_KEYWORDS = [
    "inscrire",
    "inscription",
    "certificat",
    "attestation",
    "validation du cours",
    "note finale",
    "quand seront les notes",
    "quand sera publié",
    "quand sera corrigé",
    "quand sera disponible",
    "date limite",
    "accès au mooc",
    "réouverture du cours",
    "pouvez-vous m'inscrire",
    "pouvez-vous nous inscrire",
]

QUESTION_HINTS = ["?", "comment", "pourquoi", "quand", "où", "quel", "quelle", "quelles", "comment faire", "serait-il possible", "pourrait-on", "pouvez-vous", "peut-on", "est-ce que"]

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()

def _is_instructor_post(author: str) -> bool:
    author_n = _normalize(author)
    return any(name in author_n for name in INSTRUCTOR_NAMES)

def _is_question_like(content: str) -> bool:
    text = _normalize(content)
    return any(h in text for h in QUESTION_HINTS)

def _is_short_polite_only(content: str) -> bool:
    text = _normalize(content)
    if not text:
        return True
    if len(text) > 140:
        return False
    has_question = _is_question_like(text)
    has_request = any(k in text for k in ["serait-il possible", "pourrait-on", "pouvez-vous", "peut-on", "je voudrais", "j'aimerais", "je souhaite", "j'ai besoin"])
    has_actionable_issue = any(k in text for k in ["erreur", "problème", "probléme", "plant", "reboot", "https", "wifi", "get", "post", "flux", "barrière", "barriere", "tp", "exercice", "module", "fonction"])
    polite_only = any(kw in text for kw in LOW_VALUE_PHRASES) and not (has_question or has_request or has_actionable_issue)
    return polite_only

def _is_low_value_post(content: str) -> bool:
    text = _normalize(content)
    if not text:
        return True
    if _is_short_polite_only(text):
        return True
    if len(text) < 50 and not _is_question_like(text):
        return True
    if len(text) < 80 and any(kw in text for kw in LOW_VALUE_PHRASES) and not any(k in text for k in ["serait-il possible", "pourrait-on", "pouvez-vous", "peut-on", "je voudrais", "j'aimerais", "je souhaite", "j'ai besoin", "erreur", "problème", "wifi", "get", "post", "flux", "tp", "exercice"]):
        return True
    return False

def _is_commentary_post(content: str) -> bool:
    text = _normalize(content)
    if _is_question_like(text):
        return False
    if any(k in text for k in ["merci", "bonjour", "bonsoir", "salut"]) and len(text) < 120 and not any(k in text for k in ["erreur", "problème", "wifi", "get", "post", "flux", "tp", "exercice", "question", "comment", "pourquoi"]):
        return True
    return any(kw in text for kw in COMMENTARY_PHRASES)

def _needs_professor_only(content: str) -> bool:
    text = _normalize(content)
    return any(kw in text for kw in ADMIN_KEYWORDS)

def _needs_professor_review(course_context: str, answer_relevance: float) -> bool:
    if answer_relevance <= 0.4:
        return True
    no_rag_context = (
        not course_context
        or "Aucun contenu" in course_context
        or len(course_context.strip()) < 100
    )
    if no_rag_context and answer_relevance < 0.6:
        return True
    return False

def _build_rag_query(topic_title: str, content: str) -> str:
    clean_content = content.strip()[:400]
    clean_title = unquote(topic_title).strip()
    query = f"{clean_content} {clean_title}" if clean_content else clean_title
    query = re.sub(r'%[0-9A-Fa-f]{2}', ' ', query)
    query = re.sub(r'\s+', ' ', query).strip()
    logger.info(f"    RAG query ({len(query)} chars): {query[:80]}…")
    return query

def generate_solution(topic_title: str, post: dict) -> dict:
    author = post.get("author", "l'étudiant·e")
    content = post.get("content", "")[:1000]
    content_norm = _normalize(content)

    if _is_instructor_post(author):
        logger.info(f"    [SolutionAgent] Skipping instructor post from '{author}'")
        return {
            "answer": None,
            "skipped": True,
            "skip_reason": "instructor",
            "needs_professor": False,
            "course_context": "",
            "rag_used": False,
            "draft_relevance": 0.0,
        }

    if _needs_professor_only(content_norm):
        logger.info(f"    [SolutionAgent] Routing admin/grading post from '{author}' to professor")
        return {
            "answer": None,
            "skipped": True,
            "skip_reason": "admin_grading",
            "needs_professor": True,
            "course_context": "",
            "rag_used": False,
            "draft_relevance": 0.0,
        }

    if _is_commentary_post(content_norm) and not _is_question_like(content_norm):
        logger.info(f"    [SolutionAgent] Routing commentary post from '{author}' to professor")
        return {
            "answer": None,
            "skipped": True,
            "skip_reason": "professor_commentary",
            "needs_professor": True,
            "course_context": "",
            "rag_used": False,
            "draft_relevance": 0.0,
        }

    rag_query = _build_rag_query(topic_title, content)
    course_context = retrieve_as_context(rag_query, top_k=8, max_chars=4000)
    display_title = unquote(topic_title)
    rag_used = RAG_AVAILABLE and bool(course_context) and "Aucun contenu" not in course_context

    signature_rule = (
        "Ne signe jamais avec '[votre nom]', '[ton nom]', ou tout autre placeholder. "
        "Si tu dois signer, utilise uniquement 'L'équipe pédagogique'."
    )

    if rag_used:
        system_prompt = (
            "Tu es un tuteur pédagogique bienveillant pour le MOOC MicroPython / IoT de FUN-MOOC. "
            "Réponds uniquement avec les informations utiles au message de l'étudiant. "
            "Si les extraits ne suffisent pas pour répondre précisément, réponds uniquement par 'INSUFFICIENT_CONTEXT_SKIP'. "
            "Si le message est une salutation, un remerciement, ou une clôture MAIS contient aussi une vraie question ou une vraie demande, réponds à la question en priorité. "
            "Pour les remerciements purs ou clôtures pures, réponds brièvement en français, 1 à 2 phrases. "
            "Pour les questions techniques, reste concret, exact, et centré sur le cours. "
            + signature_rule
        )
        user_prompt = f"""
EXTRAITS DU COURS ET DU FORUM :
{course_context}

SUJET DU FORUM : {display_title}

MESSAGE DE {author} :
{content}

Réponds en français directement à {author}.
"""
    else:
        system_prompt = (
            "Tu es un tuteur pédagogique bienveillant pour le MOOC MicroPython / IoT de FUN-MOOC. "
            "Réponds de façon utile, brève, et sans inventer d'information de cours. "
            "Si tu ne peux pas répondre précisément, réponds uniquement par 'INSUFFICIENT_CONTEXT_SKIP'. "
            "Si le message contient une vraie question ou une vraie demande, même avec une salutation ou un merci, réponds à la question. "
            + signature_rule
        )
        user_prompt = f"""
SUJET DU FORUM : {display_title}

MESSAGE DE {author} :
{content}

Réponds directement à {author}.
"""

    try:
        time.sleep(1)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=220,
            temperature=0.3,
        )
        answer = response.choices[0].message.content.strip()
        logger.info(f"    [SolutionAgent] Generated {len(answer)} chars (RAG={'yes' if rag_used else 'no'})")

        if "INSUFFICIENT_CONTEXT_SKIP" in answer:
            logger.info("    [SolutionAgent] LLM reported insufficient context — routing to professor")
            return {
                "answer": None,
                "skipped": True,
                "skip_reason": "professor_context_missing",
                "needs_professor": True,
                "course_context": course_context,
                "rag_used": rag_used,
                "draft_relevance": 0.0,
            }

        return {
            "answer": answer,
            "skipped": False,
            "skip_reason": None,
            "needs_professor": False,
            "course_context": course_context,
            "rag_used": rag_used,
            "draft_relevance": 0.0,
        }

    except Exception as e:
        logger.error(f"    [SolutionAgent] LLM call failed: {e}")
        fallback = f"Bonjour {author}, merci pour ta question. Je vais vérifier cela dans les ressources du cours."
        return {
            "answer": fallback,
            "skipped": False,
            "skip_reason": None,
            "needs_professor": False,
            "course_context": course_context,
            "rag_used": rag_used,
            "draft_relevance": 0.0,
        }

logger.info("✅ Solution Agent loaded")