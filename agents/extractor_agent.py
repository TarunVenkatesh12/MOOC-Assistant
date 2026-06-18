from smolagents import tool
import os
import json
import re
from dotenv import load_dotenv
import logging
from tools.mcp_browser import real_navigate_tool, real_get_content_tool, real_wait_tool, real_login_tool

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Primary extractor ─────────────────────────────────────────────────────────

@tool
def extract_conversation(page_content: str) -> str:
    """
    Extract ALL FUN-MOOC forum posts from a Playwright accessibility snapshot.

    Args:
        page_content: YAML/text snapshot from real_get_content_tool()

    Returns:
        JSON string  {success, posts, post_count}
    """
    posts              = []
    lines              = page_content.split('\n')
    current_post       = None
    post_content_buffer = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # ── New post boundary: "By:" label ───────────────────────────────────
        if 'text: "By:"' in line or line == 'text: "By:"':
            # Flush previous post
            if current_post and len(''.join(post_content_buffer)) > 30:
                current_post['content'] = '\n\n'.join(post_content_buffer)[:2000]
                posts.append(current_post)

            current_post        = {'author': 'Utilisateur', 'date': 'Recent', 'content': ''}
            post_content_buffer = []

            # Author — next link within 15 lines
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.search(r'link\s+"([^"]+)"\s*\[ref=', lines[j])
                if m:
                    current_post['author'] = m.group(1)
                    i = j + 1
                    break

            # Date — "on DD Month YYYY" pattern within next 15 lines
            for j in range(i, min(i + 15, len(lines))):
                m = re.search(
                    r'(on\s+\d{1,2}\s+\w+\s+\d{4}[^"]*|\d{1,2}\s+\w+\s+\d{4}[^"]*)',
                    lines[j]
                )
                if m:
                    current_post['date'] = m.group(1).strip()
                    i = j + 1
                    break
            continue

        # ── Content collection ────────────────────────────────────────────────
        if current_post:
            # Paragraph blocks
            m = re.search(r'paragraph\s*\[ref=[^\]]+\]:\s*(.*)', line)
            if m:
                text = m.group(1).strip().strip('"')
                if len(text) > 2:
                    post_content_buffer.append(text)
                i += 1
                continue

            # Code blocks
            m = re.search(r'code\s*\[ref=[^\]]+\]:\s*(.*)', line)
            if m:
                code = m.group(1).strip().strip('"')
                if code:
                    post_content_buffer.append(f"\n```\n{code}\n```")
                i += 1
                continue

            # Inline URLs
            m = re.search(r'link\s+"([^"]+)"\s*\[ref=', line)
            if m:
                url_text = m.group(1)
                if len(url_text) > 5 and 'http' in url_text:
                    post_content_buffer.append(f"[{url_text}]({url_text})")
                i += 1
                continue

            # Generic text nodes
            m = re.search(r'text:\s*"([^"]*)"', line)
            if m:
                text  = m.group(1).strip()
                noise = {'By:', current_post.get('author', ''), 'Edit', 'Reply', 'Quote', ''}
                if len(text) > 2 and text not in noise:
                    post_content_buffer.append(text)
                i += 1
                continue

        i += 1

    # Flush final post
    if current_post and post_content_buffer:
        current_post['content'] = '\n\n'.join(post_content_buffer)[:2000]
        posts.append(current_post)

    return json.dumps(
        {"success": True, "posts": posts, "post_count": len(posts)},
        ensure_ascii=False, indent=2
    )


# ── Improved fallback extractor ───────────────────────────────────────────────

@tool
def extract_conversation_improved(page_content: str) -> str:
    """
    Fallback extractor — broader patterns for when primary finds 0 posts.

    Args:
        page_content: Raw snapshot string

    Returns:
        JSON string  {success, posts, post_count}
    """
    posts        = []
    lines        = str(page_content).split('\n')
    current_post = None
    content_buf  = []

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()

        if re.search(r'text:\s*"By:"', line):
            if current_post and content_buf:
                current_post['content'] = '\n\n'.join(content_buf)[:2000]
                posts.append(current_post)

            current_post = {'author': 'Student', 'date': 'Recent', 'content': ''}
            content_buf  = []

            # Author
            for j in range(i + 1, min(i + 20, len(lines))):
                m = re.search(r'link\s+"([^"]{2,})"', lines[j])
                if m and m.group(1) not in ('Edit', 'Reply', 'Quote', 'Post reply'):
                    current_post['author'] = m.group(1)
                    break

            # Date
            for j in range(i + 1, min(i + 20, len(lines))):
                m = re.search(
                    r'(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4})', lines[j]
                )
                if m:
                    current_post['date'] = m.group(1)
                    break
            continue

        if current_post:
            m = re.search(r'paragraph[^:]*:\s*"?([^"]{5,})"?', line)
            if m:
                content_buf.append(m.group(1).strip())
                continue

            m = re.search(r'\bcode\b[^:]*:\s*"?([^"]{3,})"?', line)
            if m:
                content_buf.append(f"\n```\n{m.group(1).strip()}\n```")
                continue

            m = re.search(r'text:\s*"([^"]{5,})"', line)
            if m:
                t     = m.group(1).strip()
                noise = {'By:', 'Edit', 'Reply', 'Quote', 'Post reply',
                         current_post.get('author', '')}
                if t not in noise:
                    content_buf.append(t)

    if current_post and content_buf:
        current_post['content'] = '\n\n'.join(content_buf)[:2000]
        posts.append(current_post)

    return json.dumps(
        {"success": True, "posts": posts, "post_count": len(posts)},
        ensure_ascii=False, indent=2
    )


# ── Main entry point ──────────────────────────────────────────────────────────

@tool
def extract_forum_posts_dom() -> str:
    """
    Extract ALL forum posts from the current browser page.
    Tries primary extractor first; falls back to improved extractor if 0 posts found.

    Returns:
        JSON string  {success, posts, post_count}
    """
    try:
        logger.info("EXTRACTING FORUM POSTS — Playwright snapshot")
        real_wait_tool(2)

        yaml_str = str(real_get_content_tool())
        logger.info(f"Snapshot size: {len(yaml_str)} chars")

        # Primary pass
        result    = extract_conversation(yaml_str)
        conv_data = json.loads(result)

        if conv_data.get("post_count", 0) == 0:
            logger.warning("Primary extractor: 0 posts — trying improved extractor")
            result    = extract_conversation_improved(yaml_str)
            conv_data = json.loads(result)

        logger.info(f"Extraction done — {conv_data.get('post_count', 0)} posts")
        return result

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return json.dumps(
            {"success": False, "posts": [], "post_count": 0, "error": str(e)},
            ensure_ascii=False
        )


# ── Debug helper ──────────────────────────────────────────────────────────────

@tool
def debug_page_structure() -> str:
    """
    Save raw page snapshot to disk for debugging extraction patterns.

    Returns:
        Status message with file path and char count
    """
    try:
        yaml_str   = str(real_get_content_tool())
        debug_file = "debug_forum_structure.txt"
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(yaml_str)
        logger.info(f"Debug snapshot saved: {debug_file}")
        return f"Saved {len(yaml_str)} chars → {debug_file}"
    except Exception as e:
        return f"Debug failed: {e}"


logger.info("Extractor Agent loaded — FUN-MOOC ready!")