import streamlit as st
from dotenv import load_dotenv
import logging
from agents.orchestrator_agent import extract_questions

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="MOOC Assistant",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    * { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #0a0c10; color: #e2e8f0; }
    section[data-testid="stSidebar"] { background-color: #0d1117 !important; border-right: 1px solid #1e2433; }
    .main .block-container { padding-top: 1.5rem; padding-bottom: 2rem; background-color: #0a0c10; max-width: 1200px; }
    .sidebar-brand { padding: 18px 0 16px 0; border-bottom: 1px solid #1e2433; margin-bottom: 20px; }
    .sidebar-brand-text { font-size: 13px; font-weight: 700; letter-spacing: 3px; color: #4a90d9; text-transform: uppercase; text-align: center; }
    .sidebar-brand-sub { font-size: 11px; color: #4a5568; text-align: center; margin-top: 4px; letter-spacing: 1px; }
    .nav-section-label { font-size: 10px; font-weight: 600; letter-spacing: 2px; color: #4a5568; text-transform: uppercase; padding: 0 4px; margin: 20px 0 8px 0; }
    .metrics-section-label { font-size: 10px; font-weight: 600; letter-spacing: 2px; color: #4a5568; text-transform: uppercase; padding: 0 4px; margin: 24px 0 10px 0; }
    .metric-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-radius: 8px; background: #111827; margin-bottom: 6px; border: 1px solid #1e2433; }
    .metric-row-label { font-size: 12px; color: #6b7280; font-weight: 500; letter-spacing: 0.5px; }
    .metric-row-value { font-size: 18px; font-weight: 700; color: #e2e8f0; }
    .metric-row-value.green { color: #34d399; }
    .metric-row-value.amber { color: #fbbf24; }
    .stButton button { background: #1a56db; color: #ffffff; border: none; border-radius: 8px; padding: 12px 20px; font-weight: 600; font-size: 13px; letter-spacing: 0.5px; width: 100%; text-transform: uppercase; }
    .page-header { padding: 20px 24px; border-radius: 10px; background: #0d1117; border: 1px solid #1e2433; margin-bottom: 24px; }
    .page-header-title { font-size: 18px; font-weight: 600; color: #e2e8f0; }
    .page-header-sub { font-size: 12px; color: #4a5568; margin-top: 4px; }
    .topic-card { background: #0d1117; border: 1px solid #1e2433; border-radius: 10px; margin-bottom: 16px; overflow: hidden; }
    .topic-card-header { padding: 14px 20px; background: #111827; border-bottom: 1px solid #1e2433; display: flex; justify-content: space-between; }
    .topic-card-title { font-size: 13px; font-weight: 600; color: #c9d4e8; }
    .topic-badge { font-size: 11px; font-weight: 600; color: #4a90d9; background: #1a2235; padding: 3px 10px; border-radius: 20px; border: 1px solid #2a3a5c; }
    .topic-card-body { padding: 20px; }
    .post-content-box { background: #111827; border: 1px solid #1e2433; border-left: 3px solid #2563eb; border-radius: 8px; padding: 16px 18px; color: #c9d4e8; margin: 10px 0 14px 0; }
    .response-box { background: #0f1f0f; border: 1px solid #1e3a1e; border-left: 3px solid #16a34a; border-radius: 8px; padding: 16px 18px; color: #c9d4e8; margin-bottom: 10px; }
    .response-label { font-size: 10px; font-weight: 700; letter-spacing: 2px; color: #16a34a; text-transform: uppercase; margin-bottom: 10px; }
    .score-row { display: flex; align-items: center; gap: 16px; padding: 10px 14px; background: #111827; border: 1px solid #1e2433; border-radius: 8px; margin-top: 8px; flex-wrap: wrap; }
    .score-item { display: flex; align-items: center; gap: 8px; }
    .score-label { font-size: 11px; color: #6b7280; }
    .score-bar-wrap { width: 80px; height: 5px; background: #1e2433; border-radius: 3px; overflow: hidden; }
    .score-bar-fill { height: 100%; border-radius: 3px; }
    .score-val { font-size: 12px; font-weight: 600; color: #e2e8f0; }
    .status-chip { font-size: 10px; font-weight: 700; letter-spacing: 1px; padding: 3px 10px; border-radius: 20px; text-transform: uppercase; margin-left: auto; }
    .status-valid { background: #052e16; color: #34d399; border: 1px solid #166534; }
    .status-corrected { background: #2d1b00; color: #fbbf24; border: 1px solid #92400e; }
    .post-divider { height: 1px; background: #1e2433; margin: 20px 0; }
    .review-card { background: #0d1117; border: 1px solid #1e2433; border-radius: 10px; margin-bottom: 12px; overflow: hidden; }
    .review-card-header { padding: 12px 18px; background: #111827; border-bottom: 1px solid #1e2433; display: flex; justify-content: space-between; }
    .review-author { font-size: 13px; font-weight: 600; color: #c9d4e8; }
    .review-topic { font-size: 11px; color: #4a5568; margin-top: 2px; }
    .reason-chip { font-size: 10px; font-weight: 700; letter-spacing: 1px; padding: 3px 10px; border-radius: 20px; text-transform: uppercase; white-space: nowrap; }
    .reason-feedback { background: #1e1040; color: #a78bfa; border: 1px solid #4c1d95; }
    .reason-admin { background: #1f0a0a; color: #f87171; border: 1px solid #7f1d1d; }
    .reason-context { background: #0c1f30; color: #60a5fa; border: 1px solid #1e3a5f; }
    .reason-peer { background: #141414; color: #9ca3af; border: 1px solid #374151; }
    .reason-greeting { background: #141414; color: #9ca3af; border: 1px solid #374151; }
    .reason-relevance { background: #1c1008; color: #fbbf24; border: 1px solid #78350f; }
    .review-content { padding: 14px 18px; font-size: 13px; line-height: 1.7; color: #8892a4; border-bottom: 1px solid #1e2433; }
    .review-ai-block { padding: 12px 18px; background: #0f1a2e; border-top: 1px solid #1e2433; border-bottom: 1px solid #1e2433; }
    .review-ai-label { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; color: #4a90d9; margin-bottom: 8px; text-transform: uppercase; }
    .review-ai-text { font-size: 13px; color: #6b7280; line-height: 1.6; margin-bottom: 10px; }
    .review-footer { padding: 10px 18px; font-size: 11px; color: #4a5568; display: flex; align-items: center; gap: 8px; }
    .review-footer-dot { width: 6px; height: 6px; border-radius: 50%; background: #fbbf24; display: inline-block; }
    .empty-state { text-align: center; padding: 60px 20px; color: #4a5568; font-size: 14px; }
    .empty-state-title { font-size: 16px; font-weight: 600; color: #6b7280; margin-bottom: 8px; }
    .main-topbar { display: flex; align-items: center; justify-content: space-between; padding: 16px 24px; background: #0d1117; border: 1px solid #1e2433; border-radius: 10px; margin-bottom: 24px; }
    .main-topbar-title { font-size: 16px; font-weight: 700; color: #e2e8f0; letter-spacing: 2px; text-transform: uppercase; }
    .main-topbar-status { font-size: 11px; color: #4a5568; letter-spacing: 1px; }
    .status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #34d399; margin-right: 6px; vertical-align: middle; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = {
        "topics": [], "hitl_posts": [], "ignored_posts": [],
        "extracted_count": 0, "answered_count": 0, "professor_count": 0,
        "ignored_count": 0, "ignored_reason_counts": {}, "discovered_topic_count": 0
    }
if "active_page" not in st.session_state:
    st.session_state.active_page = "conversations"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class='sidebar-brand'>
        <div class='sidebar-brand-text'>MOOC Assistant</div>
        <div class='sidebar-brand-sub'>Automated Response System</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("RUN EXTRACTION", type="primary", use_container_width=True):
        with st.spinner("Extracting posts and generating responses..."):
            try:
                extracted_data = extract_questions()
                st.session_state.extracted_data = extracted_data
                st.session_state.active_page = "conversations"
                st.rerun()
            except Exception as e:
                st.error(f"Extraction failed: {str(e)}")
                logger.error(f"Extraction error: {e}")

    st.markdown("<div class='nav-section-label'>Navigation</div>", unsafe_allow_html=True)

    for _label, _page in [
        ("Conversations and Responses", "conversations"),
        ("Professor Review", "review"),
        ("Others", "others"),
    ]:
        is_active = st.session_state.active_page == _page
        if st.button(
            _label,
            key=f"nav_btn_{_page}",
            use_container_width=True,
            type="primary" if is_active else "secondary"
        ):
            st.session_state.active_page = _page
            st.rerun()

    extracted_data = st.session_state.extracted_data
    total_topics   = extracted_data.get("discovered_topic_count", len(extracted_data.get("topics", [])))
    extracted_total = extracted_data.get("extracted_count", 0)
    responded_count = extracted_data.get("answered_count", 0)
    professor_count = extracted_data.get("professor_count", 0)
    ignored_count   = extracted_data.get("ignored_count", len(extracted_data.get("ignored_posts", [])))

    st.markdown("<div class='metrics-section-label'>Metrics</div>", unsafe_allow_html=True)
    for label, value, cls in [
        ("Topics",          total_topics,    ""),
        ("Total Extracted", extracted_total, ""),
        ("Responses",       responded_count, "green"),
        ("Prof. Review",    professor_count, "amber"),
        ("Others",          ignored_count,   ""),
    ]:
        st.markdown(f"""
        <div class='metric-row'>
            <span class='metric-row-label'>{label}</span>
            <span class='metric-row-value {cls}'>{value}</span>
        </div>
        """, unsafe_allow_html=True)

# ── Main area setup ───────────────────────────────────────────────────────────
extracted_data  = st.session_state.extracted_data
page            = st.session_state.active_page
extracted_total = extracted_data.get("extracted_count", 0)

status_text = (
    f"<span class='status-dot'></span>{extracted_total} posts extracted"
    if extracted_total > 0 else "No data — run extraction"
)
st.markdown(f"""
<div class='main-topbar'>
    <span class='main-topbar-title'>MOOC Assistant</span>
    <span class='main-topbar-status'>{status_text}</span>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Conversations and Responses
# ══════════════════════════════════════════════════════════════════════════════
if page == "conversations":
    st.markdown("""
    <div class='page-header'>
        <div class='page-header-title'>Conversations and Responses</div>
        <div class='page-header-sub'>AI-generated responses for student forum posts</div>
    </div>
    """, unsafe_allow_html=True)

    has_content = False

    for topic in extracted_data.get("topics", []):
        valid_posts = [p for p in topic.get("posts", []) if p.get("ai_response")]
        if not valid_posts:
            continue

        has_content = True
        post_word = "post" if len(valid_posts) == 1 else "posts"

        st.markdown(f"""
        <div class='topic-card'>
            <div class='topic-card-header'>
                <span class='topic-card-title'>{topic['title']}</span>
                <span class='topic-badge'>{len(valid_posts)} {post_word}</span>
            </div>
            <div class='topic-card-body'>
        """, unsafe_allow_html=True)

        for post_idx, post in enumerate(valid_posts):
            st.markdown(f"""
            <div class='post-meta'>Post {post_idx + 1} &nbsp;·&nbsp; {post.get('date', 'Recent')}</div>
            <div class='post-author' style='font-size:14px;font-weight:600;color:#93c5fd;margin-bottom:4px;'>{post['author']}</div>
            <div class='post-content-box'>{post['content']}</div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div class='response-box'>
                <div class='response-label'>Response</div>
                {post['ai_response']}
            </div>
            """, unsafe_allow_html=True)

            val = post.get("validation")
            if val:
                rel   = val.get("answer_relevance", 0)
                clar  = val.get("clarity_score", 0)
                rel_pct  = int(rel * 100)
                clar_pct = int(clar * 100)
                rel_color  = "#34d399" if rel >= 0.7 else "#fbbf24" if rel >= 0.5 else "#f87171"
                clar_color = "#34d399" if clar >= 0.7 else "#fbbf24" if clar >= 0.5 else "#f87171"
                is_valid  = val.get("is_valid", True)
                corrected = val.get("was_corrected", False)
                chip_class = "status-valid" if is_valid and not corrected else "status-corrected"
                chip_text  = "Validated" if is_valid and not corrected else "Corrected"

                st.markdown(f"""
                <div class='score-row'>
                    <div class='score-item'>
                        <span class='score-label'>Relevance</span>
                        <div class='score-bar-wrap'>
                            <div class='score-bar-fill' style='width:{rel_pct}%;background:{rel_color};'></div>
                        </div>
                        <span class='score-val'>{rel:.2f}</span>
                    </div>
                    <div class='score-item'>
                        <span class='score-label'>Clarity</span>
                        <div class='score-bar-wrap'>
                            <div class='score-bar-fill' style='width:{clar_pct}%;background:{clar_color};'></div>
                        </div>
                        <span class='score-val'>{clar:.2f}</span>
                    </div>
                    <span class='status-chip {chip_class}'>{chip_text}</span>
                </div>
                """, unsafe_allow_html=True)

            if post_idx < len(valid_posts) - 1:
                st.markdown("<div class='post-divider'></div>", unsafe_allow_html=True)

        st.markdown("</div></div>", unsafe_allow_html=True)

    if not has_content:
        st.markdown("""
        <div class='empty-state'>
            <div class='empty-state-title'>No responses generated yet</div>
            <div>Click "Run Extraction" in the sidebar to begin.</div>
        </div>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Professor Review
# ══════════════════════════════════════════════════════════════════════════════
elif page == "review":
    st.markdown("""
    <div class='page-header'>
        <div class='page-header-title'>Professor Review</div>
        <div class='page-header-sub'>Posts requiring manual attention — includes AI draft response where available</div>
    </div>
    """, unsafe_allow_html=True)

    hitl_posts = extracted_data.get("hitl_posts", [])

    if extracted_total == 0:
        st.markdown("""
        <div class='empty-state'>
            <div class='empty-state-title'>No data yet</div>
            <div>Click "Run Extraction" in the sidebar to begin.</div>
        </div>
        """, unsafe_allow_html=True)
    elif not hitl_posts:
        st.markdown("""
        <div class='empty-state'>
            <div class='empty-state-title'>All clear</div>
            <div>No posts flagged for review in this run.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"<p style='font-size:12px;color:#4a5568;margin-bottom:16px;letter-spacing:0.5px;'>{len(hitl_posts)} POSTS PENDING REVIEW</p>", unsafe_allow_html=True)

        for p in hitl_posts:
            # Read hitl_reason first (set by orchestrator), fall back to skip_reason
            skip_reason = p.get("hitl_reason") or p.get("skip_reason", "")

            if "commentary" in skip_reason.lower() or "feedback" in skip_reason.lower():
                chip_class  = "reason-feedback"
                chip_text   = "Student Feedback"
                reason_text = "Student shared feedback or opinion — professor should acknowledge."
            elif "grading" in skip_reason.lower() or "admin" in skip_reason.lower():
                chip_class  = "reason-admin"
                chip_text   = "Admin / Grading"
                reason_text = "Grading, enrollment, or administrative question."
            elif "context" in skip_reason.lower() or "insufficient" in skip_reason.lower():
                chip_class  = "reason-context"
                chip_text   = "Insufficient Context"
                reason_text = "Course context did not contain enough information to answer reliably."
            elif "greeting" in skip_reason.lower() or "low_value" in skip_reason.lower():
                chip_class  = "reason-greeting"
                chip_text   = "Greeting / Closure"
                reason_text = "Greeting, thank-you, or closure post."
            elif "unexpected" in skip_reason.lower():
                chip_class  = "reason-admin"
                chip_text   = "Unexpected Skip"
                reason_text = "Post was dropped by an unhandled pipeline path — needs manual check."
            else:
                chip_class  = "reason-relevance"
                chip_text   = "Low Relevance"
                reason_text = "AI response quality was below the acceptable threshold."

            ai_resp = p.get("draft_ai_response") or p.get("ai_response") or ""
            val     = p.get("validation") or {}
            rel     = val.get("answer_relevance", 0)
            clar    = val.get("clarity_score", 0)
            grnd    = val.get("grounding_score", 0)

            content_preview  = p.get("content", "")[:400]
            content_ellipsis = "..." if len(p.get("content", "")) > 400 else ""
            ai_preview       = ai_resp[:600]
            ai_ellipsis      = "..." if len(ai_resp) > 600 else ""

            st.markdown(f"""
            <div class='review-card'>
                <div class='review-card-header'>
                    <div>
                        <div class='review-author'>{p['author']}</div>
                        <div class='review-topic'>{p.get('topic_title', '')}</div>
                    </div>
                    <span class='reason-chip {chip_class}'>{chip_text}</span>
                </div>
                <div class='review-content'>{content_preview}{content_ellipsis}</div>
            """, unsafe_allow_html=True)

            if ai_resp:
                rel_pct  = int(rel * 100)
                clar_pct = int(clar * 100)
                grnd_pct = int(grnd * 100)
                rel_color  = "#34d399" if rel >= 0.7 else "#fbbf24" if rel >= 0.5 else "#f87171"
                clar_color = "#34d399" if clar >= 0.7 else "#fbbf24" if clar >= 0.5 else "#f87171"
                grnd_color = "#34d399" if grnd >= 0.7 else "#fbbf24" if grnd >= 0.5 else "#f87171"
                st.markdown(f"""
                <div class='review-ai-block'>
                    <div class='review-ai-label'>AI Draft Response — Needs Professor Review</div>
                    <div class='review-ai-text'>{ai_preview}{ai_ellipsis}</div>
                    <div style='display:flex;gap:16px;flex-wrap:wrap;padding-top:8px;'>
                        <div class='score-item'>
                            <span class='score-label'>Relevance</span>
                            <div class='score-bar-wrap'>
                                <div class='score-bar-fill' style='width:{rel_pct}%;background:{rel_color};'></div>
                            </div>
                            <span class='score-val'>{rel:.2f}</span>
                        </div>
                        <div class='score-item'>
                            <span class='score-label'>Grounding</span>
                            <div class='score-bar-wrap'>
                                <div class='score-bar-fill' style='width:{grnd_pct}%;background:{grnd_color};'></div>
                            </div>
                            <span class='score-val'>{grnd:.2f}</span>
                        </div>
                        <div class='score-item'>
                            <span class='score-label'>Clarity</span>
                            <div class='score-bar-wrap'>
                                <div class='score-bar-fill' style='width:{clar_pct}%;background:{clar_color};'></div>
                            </div>
                            <span class='score-val'>{clar:.2f}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown(f"""
                <div class='review-footer'>
                    <span class='review-footer-dot'></span>
                    <span>{reason_text}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Others (instructor posts + empty posts)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "others":
    st.markdown("""
    <div class='page-header'>
        <div class='page-header-title'>Others</div>
        <div class='page-header-sub'>Instructor posts and empty posts — ignored from response generation</div>
    </div>
    """, unsafe_allow_html=True)

    others_posts          = extracted_data.get("ignored_posts", [])
    ignored_reason_counts = extracted_data.get("ignored_reason_counts", {})

    if extracted_total == 0:
        st.markdown("""
        <div class='empty-state'>
            <div class='empty-state-title'>No data yet</div>
            <div>Click "Run Extraction" in the sidebar to begin.</div>
        </div>
        """, unsafe_allow_html=True)
    elif not others_posts:
        st.markdown("""
        <div class='empty-state'>
            <div class='empty-state-title'>No ignored posts</div>
            <div>All extracted posts were processed.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"<p style='font-size:12px;color:#4a5568;margin-bottom:16px;letter-spacing:0.5px;'>{len(others_posts)} POSTS IGNORED THIS RUN</p>", unsafe_allow_html=True)

        for p in others_posts:
            preview  = p.get("content", "")[:400]
            ellipsis = "..." if len(p.get("content", "")) > 400 else ""
            reason   = p.get("skip_reason", "other")
            chip_label = "Instructor" if reason == "instructor" else reason.replace("_", " ").title()

            st.markdown(f"""
            <div class='review-card'>
                <div class='review-card-header'>
                    <div>
                        <div class='review-author'>{p['author']}</div>
                        <div class='review-topic'>{p.get('topic_title', '')}</div>
                    </div>
                    <span class='reason-chip reason-peer'>{chip_label}</span>
                </div>
                <div class='review-content'>{preview}{ellipsis}</div>
                <div class='review-footer'>
                    <span class='review-footer-dot'></span>
                    <span>Ignored from response generation.</span>
                </div>
            </div>
            """, unsafe_allow_html=True)