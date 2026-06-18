import logging
import json
import random
import re
from urllib.parse import unquote
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

from agents.extractor_agent import (
    real_login_tool,
    real_navigate_tool,
    real_wait_tool,
    extract_forum_posts_dom,
)
from tools.mcp_browser import real_get_content_tool

from agents.solution_agent import (
    generate_solution,
    _needs_professor_review,
    _needs_professor_only,
    RAG_AVAILABLE,
)
from agents.validator_agent import validate_solution

try:
    from rag.retriever import add_forum_posts_to_index
except (ImportError, ModuleNotFoundError):
    def add_forum_posts_to_index(posts, topic_title, **kwargs) -> int:
        return 0

FORUM_HOST = "https://forum.fun-mooc.fr"

COURSEWARE_URL = (
    "https://lms.fun-mooc.fr/courses/course-v1:MinesTelecom+04057+session01"
    "/courseware/c925b2ed43804c24bcb17d63a5a93658/"
)
FORUM_SECTION_URL = (
    "https://lms.fun-mooc.fr/courses/course-v1:MinesTelecom+04057+session01"
    "/courseware/c925b2ed43804c24bcb17d63a5a93658/4a4fc16167d949b5aebf78cf227c533c/"
)

FORUM_LISTING_PAGES = [
    f"{FORUM_HOST}/forum/forum/forum-g%C3%A9n%C3%A9ral-du-cours-8322/",
    f"{FORUM_HOST}/forum/forum/forum-g%C3%A9n%C3%A9ral-du-cours-8322/?page=2",
    f"{FORUM_HOST}/forum/forum/forum-g%C3%A9n%C3%A9ral-du-cours-8322/?page=3",
]

INSTRUCTOR_NAMES = {"bgaultier", "baptiste", "equipe pédagogique", "staff"}

def _warm_up_session() -> None:
    logger.info("Step 1 — Courseware root (LMS session cookie) ...")
    real_navigate_tool(COURSEWARE_URL)
    real_wait_tool(2)
    logger.info("Step 2 — Forum section page (iframe auth cookie) ...")
    real_navigate_tool(FORUM_SECTION_URL)
    real_wait_tool(3)
    logger.info("Session warm-up complete")

def _extract_topic_urls_from_snapshot(snapshot: str) -> list:
    urls = []
    for m in re.finditer(r'/url:\s*(/forum/forum/[^\s\n]+/topic/[^\s\n?#/]+/?)', snapshot):
        full = FORUM_HOST + m.group(1).rstrip('/')
        if full not in urls:
            urls.append(full)
    for m in re.finditer(r'https://forum\.fun-mooc\.fr/forum/forum/[^\s"\'<>\n]+/topic/[^\s"\'<>\n?#/]+/?', snapshot):
        full = m.group(0).rstrip('/')
        if full not in urls:
            urls.append(full)
    return urls

def _scrape_topic_urls_from_listing(page_url: str) -> list:
    logger.info(f"  Scanning listing page -> {page_url}")
    real_navigate_tool(page_url)
    real_wait_tool(3)
    snapshot = str(real_get_content_tool())
    logger.info(f"  Snapshot: {len(snapshot)} chars")
    urls = _extract_topic_urls_from_snapshot(snapshot)
    logger.info(f"  Found {len(urls)} topic URLs")
    return urls

def collect_all_topic_urls() -> list:
    all_urls = []
    for page_url in FORUM_LISTING_PAGES:
        for u in _scrape_topic_urls_from_listing(page_url):
            if u not in all_urls:
                all_urls.append(u)
    logger.info(f"Total unique topics: {len(all_urls)}")
    return all_urls

def discover_random_topics(limit: int = 5) -> list:
    all_urls = collect_all_topic_urls()
    if not all_urls:
        logger.error("No topic URLs found")
        return []
    random.shuffle(all_urls)
    topics = []
    for i, url in enumerate(all_urls[:limit], 1):
        slug = url.rstrip("/").split("/")[-1]
        slug_decoded = unquote(slug)
        title = re.sub(r"-\d+$", "", slug_decoded).replace("-", " ").title()
        topics.append({"title": title, "url": url, "category": "Forum general"})
        logger.info(f"  Topic {i}: {title}")
    return topics

def _get_topic_page_count(snapshot: str) -> int:
    page_nums = re.findall(r'/url:\s*/forum/forum/[^\s\n]+/topic/[^\s\n]+/\?page=(\d+)', snapshot)
    if page_nums:
        return max(int(p) for p in page_nums)
    nums = re.findall(r'link\s+"(\d+)"\s*\[ref=', snapshot)
    if nums:
        return max(int(n) for n in nums)
    return 1

def extract_all_posts_from_topic(topic_url: str) -> list:
    all_posts = []
    logger.info(f"    Loading topic page 1: {topic_url}")
    real_navigate_tool(topic_url)
    real_wait_tool(2)
    snapshot = str(real_get_content_tool())
    page_count = _get_topic_page_count(snapshot)
    logger.info(f"    Topic has {page_count} page(s)")
    result = extract_forum_posts_dom()
    conv_data = json.loads(result)
    posts = conv_data.get("posts", [])
    logger.info(f"    Page 1: {len(posts)} posts")
    all_posts.extend(posts)
    for page_num in range(2, page_count + 1):
        page_url = f"{topic_url}/?page={page_num}"
        logger.info(f"    Loading topic page {page_num}: {page_url}")
        real_navigate_tool(page_url)
        real_wait_tool(2)
        result = extract_forum_posts_dom()
        conv_data = json.loads(result)
        posts = conv_data.get("posts", [])
        logger.info(f"    Page {page_num}: {len(posts)} posts")
        all_posts.extend(posts)
    return all_posts

def _is_instructor(author: str) -> bool:
    a = (author or "").lower()
    return any(name in a for name in INSTRUCTOR_NAMES)

def _skipped_record(post: dict, topic_title: str, topic_url: str, reason: str) -> dict:
    return {
        "topic_title": topic_title,
        "topic_url": topic_url,
        "author": post.get("author", "Unknown"),
        "date": post.get("date", "Recent"),
        "content": post.get("content", ""),
        "skip_reason": reason,
    }

def extract_questions() -> dict:
    logger.info("=" * 80)
    logger.info("AUTO-RESPONSE EXTRACTION STARTED")
    logger.info("Pipeline: Extractor Agent -> Solution Agent -> Validator Agent")
    if RAG_AVAILABLE:
        logger.info("RAG mode: answers grounded in course materials + forum history")
    else:
        logger.warning("RAG index missing — run: python build_rag.py")

    real_login_tool()
    logger.info("Login completed")
    _warm_up_session()

    random_topics = discover_random_topics(3)
    discovered_topic_count = len(random_topics)

    all_topics = []
    total_posts = 0
    hitl_posts = []
    ignored_posts = []
    ignored_reason_counts = {
        "instructor": 0,
        "other": 0,
    }
    extracted_count = 0
    answered_count = 0
    professor_count = 0

    for i, topic in enumerate(random_topics, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"TOPIC {i}/{len(random_topics)}: {topic['title']}")
        logger.info(f"URL: {topic['url']}")

        try:
            posts = extract_all_posts_from_topic(topic["url"])
            display_title = unquote(topic["title"])

            topic_data = {
                "title": display_title,
                "url": topic["url"],
                "category": topic["category"],
                "posts": [],
            }

            topic_total = 0

            for post_idx, post in enumerate(posts, 1):
                logger.info(f"  Processing post {post_idx}/{len(posts)}")
                extracted_count += 1
                topic_total += 1

                author = post.get("author", "")
                content = post.get("content", "")

                if not content.strip():
                    ignored_reason_counts["other"] += 1
                    ignored_posts.append(_skipped_record(post, display_title, topic["url"], "other"))
                    continue

                if _is_instructor(author):
                    logger.info(f"    [Ignored] Instructor post from {author}")
                    ignored_reason_counts["instructor"] += 1
                    ignored_posts.append(_skipped_record(post, display_title, topic["url"], "instructor"))
                    continue

                solution = generate_solution(topic["title"], post)

                if solution["skipped"]:
                    reason = solution["skip_reason"]

                    if reason in {"professor_commentary", "professor_context_missing", "admin_grading", "low_value"}:
                        professor_count += 1
                        topic_data["posts"].append({
                            **post,
                            "ai_response": None,
                            "draft_ai_response": None,
                            "needs_hitl": True,
                            "hitl_reason": "low_value" if reason == "low_value" else "commentary" if reason == "professor_commentary" else "insufficient_context" if reason == "professor_context_missing" else "admin_grading",
                            "instructor_replies": [],
                            "validation": None,
                            "skip_reason": reason,
                        })
                        hitl_posts.append(_skipped_record(post, display_title, topic["url"], reason))
                        continue

                    ignored_reason_counts["other"] += 1
                    ignored_posts.append(_skipped_record(post, display_title, topic["url"], reason))
                    continue

                draft_answer = solution["answer"]
                course_context = solution["course_context"]

                if not draft_answer:
                    ignored_reason_counts["other"] += 1
                    ignored_posts.append(_skipped_record(post, display_title, topic["url"], "other"))
                    continue

                validation = validate_solution(
                    topic_title=topic["title"],
                    post=post,
                    course_context=course_context,
                    draft_answer=draft_answer,
                )

                final_answer = validation["final_answer"]
                answer_relevance = validation["answer_relevance"]

                flag_for_professor = _needs_professor_review(
                    course_context=course_context,
                    answer_relevance=answer_relevance,
                )

                if flag_for_professor:
                    professor_count += 1
                    logger.info(f"    [HITL] Post {post_idx} flagged for low relevance ({answer_relevance:.2f})")

                logger.info(
                    f"    Post {post_idx}: relevance={answer_relevance:.2f} "
                    f"clarity={validation['clarity_score']:.2f} "
                    f"corrected={validation['was_corrected']} "
                    f"hitl={flag_for_professor}"
                )

                topic_data["posts"].append({
                    **post,
                    "ai_response": None if flag_for_professor else final_answer,
                    "draft_ai_response": final_answer if flag_for_professor else None,
                    "needs_hitl": flag_for_professor,
                    "hitl_reason": "low_relevance" if flag_for_professor else None,
                    "instructor_replies": [],
                    "validation": {
                        "is_valid": validation["is_valid"],
                        "answer_relevance": answer_relevance,
                        "grounding_score": validation["grounding_score"],
                        "clarity_score": validation["clarity_score"],
                        "issues": validation["issues"],
                        "was_corrected": validation["was_corrected"],
                    },
                })

                if flag_for_professor:
                    hitl_posts.append({
                        **_skipped_record(post, display_title, topic["url"], "low_relevance"),
                        "hitl_reason": "low_relevance",
                        "draft_ai_response": final_answer,
                        "validation": {
                            "answer_relevance": answer_relevance,
                            "grounding_score": validation["grounding_score"],
                            "clarity_score": validation["clarity_score"],
                        },
                    })
                else:
                    answered_count += 1

            topic_data["post_count"] = len(topic_data["posts"])
            all_topics.append(topic_data)
            total_posts += topic_total
            logger.info(f"  {topic_total} posts processed")

            if RAG_AVAILABLE:
                indexable_posts = [
                    p for p in topic_data["posts"]
                    if p.get("content") and p.get("ai_response")
                ]
                added = add_forum_posts_to_index(indexable_posts, display_title)
                logger.info(f"  {added} new chunks added to RAG index from this topic")

        except Exception as e:
            logger.error(f"Topic {i} failed: {e}")
            all_topics.append({
                "title": topic["title"],
                "posts": [],
                "post_count": 0,
            })

    logger.info(f"\nEXTRACTION COMPLETE — {len(all_topics)} topics, {extracted_count} posts extracted")
    logger.info(f"Responses={answered_count}, Professor Review={professor_count}, Ignored={len(ignored_posts)}")

    return {
        "success": True,
        "topics": all_topics,
        "discovered_topic_count": discovered_topic_count,
        "total_posts": total_posts,
        "extracted_count": extracted_count,
        "answered_count": answered_count,
        "professor_count": professor_count,
        "ignored_count": len(ignored_posts),
        "ignored_reason_counts": ignored_reason_counts,
        "auto_responses": True,
        "rag_enabled": RAG_AVAILABLE,
        "hitl_posts": hitl_posts,
        "ignored_posts": ignored_posts,
    }

def generate_answers(questions):
    results = []
    for q in questions:
        topic_title = q.get("topic_title", q.get("title", "Question"))
        solution = generate_solution(topic_title, q)
        answer = solution["answer"] if not solution["skipped"] else None
        results.append({"question": q, "answer": answer, "status": "success"})
    return results