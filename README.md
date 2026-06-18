# MOOC Assistant — Third Semester

A multi-agent pipeline that automatically extracts student questions from FUN-MOOC discussion forums, generates course-grounded responses using Retrieval-Augmented Generation, validates answer quality through a two-stage pipeline, and routes uncertain cases to a human instructor via a Streamlit dashboard.

> **IMT Atlantique** · Academic Year 2025–2026  
> Author: Tarun VENKATESH · Supervisors: Laurent TOUTAIN, Baptiste GAULTIER

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Component Descriptions](#component-descriptions)
- [RAG Pipeline](#rag-pipeline)
- [Validation Agent](#validation-agent)
- [Streamlit Dashboard](#streamlit-dashboard)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Semester 1 Recap](#semester-1-recap)
- [Future Enhancements](#future-enhancements)

---

## Overview

High-enrolment MOOC courses on the [FUN-MOOC](https://www.fun-mooc.fr) platform accumulate hundreds of student questions across forum threads faster than instructors can respond manually. This project builds a pipeline of four specialised agents that work sequentially to reduce that workload.

The system is **not a single chatbot**. Each agent holds a distinct responsibility: the extractor scrapes the forum, the solution agent generates a grounded response, the validator checks its quality, and the orchestrator decides whether to publish it automatically or send it to instructor review. The final output is surfaced through a Streamlit dashboard with three mutually exclusive views.

The course targeted is the **MicroPython / IoT** course on FUN-MOOC (Open edX platform), delivered in French.

---

## System Architecture

```
Orchestrator Agent
       │
       ▼
Extractor Agent  ←──  FUN-MOOC Forum (via Playwright + MCP)
       │
       ▼
Solution Agent   ←──  RAG Index (Course HTML/XML + Forum Posts)
       │
       ▼
Validator Agent
       │
  ┌────┴────────────┐
  ▼                 ▼
Auto            Professor
Response        Review
  │                 │
  └────────┬────────┘
           ▼
    Streamlit Dashboard
    (+ Ignored Posts)
```

The orchestrator drives the entire pipeline sequentially. After each topic is processed, newly answered posts are appended back into the RAG index, incrementally enriching the knowledge base with real student questions over time.

---

## Component Descriptions

### Orchestrator Agent (`agents/orchestrator_agent.py`)
Drives the full pipeline. It calls the extractor for a configurable set of forum topics, iterates over each extracted post through the solution and validator agents, and aggregates the final counts that the dashboard reads. After each topic, it calls the RAG indexer to add newly answered posts to the index.

### Extractor Agent (`agents/extractor_agent.py`)
Uses [Playwright](https://github.com/microsoft/playwright) via the MCP browser tool to navigate the FUN-MOOC forum. Handles:
- LMS login and two-step session warm-up (main LMS cookie → forum iframe cookie)
- Forum listing page scanning and topic URL discovery (handles both relative and absolute URL formats)
- Paginated topic thread navigation
- DOM-based post extraction returning structured records: `author`, `date`, `content`

### Solution Agent (`agents/solution_agent.py`)
Receives a topic title and a post dictionary. Applies intent-aware filtering first, then:
- Queries the RAG retriever for relevant course context
- Constructs a structured prompt and calls **Llama 3.1** (`llama-3.1-8b-instant`) via the Groq API
- Generates a response in French constrained to the retrieved context
- Emits a skip token if the context is insufficient for a confident answer

**Intent-aware filtering** classifies each post before generation:
- Instructor posts (by username) → skipped entirely
- Pure greetings, administrative questions, complaints, certificate requests → routed to Professor Review
- Posts with genuine technical or conceptual questions → forwarded for RAG-augmented generation

### Validator Agent (`agents/validator_agent.py`)
Evaluates every draft response in two stages before it appears in the dashboard.

**Stage 1 — Rule-based checks (deterministic, no API call):**
- Detects the LLM's generic fallback phrase (`"Je vais vérifier cela dans les ressources du cours"`) → replaces with a polite redirection
- Detects first-person confusion phrases (`"je ne sais pas"`, `"je n'arrive pas"`) → classifies as invalid

**Stage 2 — LLM scoring (only if Stage 1 passes):**
Uses **Llama 3.3 70B** (`llama-3.3-70b-versatile`, temperature 0.1) to return a structured JSON evaluation:

| Field | Type | Description |
|---|---|---|
| `answer_relevance` | 0.0–1.0 | Does the answer address the student's actual question? |
| `grounding_score` | 0.0–1.0 | Is the answer supported by the retrieved course context? |
| `clarity_score` | 0.0–1.0 | Is the answer clearly written and pedagogically appropriate? |
| `is_valid` | boolean | True if `answer_relevance ≥ 0.6` AND `clarity_score ≥ 0.6` |
| `issues` | list | Specific problems identified |
| `fixed_answer` | string | Optionally corrected version of the answer |

**Post-validation routing:**
- `answer_relevance ≤ 0.4` → Professor Review (regardless of other scores)
- Empty/very short context (`< 100 chars`) AND `relevance < 0.6` → Professor Review
- Passes all conditions → published as Auto Response

---

## RAG Pipeline

### Course Data Ingestion
The course was provided as an edX-format archive. The ingestion script (`agents/rag_builder.py`) recursively scans the `course_data/` directory:
- **HTML lesson files**: custom `HTMLParser` subclass strips tags, collects visible text
- **XML exercise files**: extracts `display_name`, `title`, `label`, markdown fields, embedded HTML blocks, exercise choices, options, hints, and solutions
- Files yielding fewer than 40 characters are skipped

Each document is split into **600-character overlapping chunks with 150-character overlap** to prevent concepts being cut across boundaries.

### Embedding Model
Uses [`paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) from the SentenceTransformers library, producing **384-dimensional dense embeddings**. The multilingual model was chosen specifically because the course mixes French educational language with English technical vocabulary (function names, library names, protocol names).

### Retrieval Logic
At index build time, all chunks are encoded in batches of 64 and stored as an L2-normalised NumPy matrix of shape `(N, 384)`.

At query time, the retriever encodes the combined query (`post content + topic title`) into a single vector and computes cosine similarity via matrix-vector multiplication:

```
scores = E · q^T  ∈ R^N
```

- Chunks scoring **≥ 0.25** are retained
- If none meet the threshold, **top-k chunks are returned regardless** (prevents empty retrieval)
- Context string prioritises course chunks first, then forum chunks as secondary context
- Total context budget: **4000 characters**

### Forum Post Indexing
After each topic is processed, validated auto-responses are serialised as compound text blocks (topic title + author + student message + AI response) and appended to the index using **800-character chunks**. New chunks are encoded and appended to the existing matrix with `numpy.vstack` — no full rebuild needed. This is a lightweight form of continual learning that improves retrieval quality over time.

---

## Validation Agent

See [Component Descriptions → Validator Agent](#validator-agent) above for full details.

The hybrid two-stage design avoids two failure modes: a purely rule-based validator would miss semantic failures (correct vocabulary, wrong answer), while a purely LLM-based validator on every response would double API call volume. Rule-based checks gate the expensive LLM call.

---

## Streamlit Dashboard

The dashboard reads the JSON output from the orchestrator and presents three mutually exclusive views:

| View | Contents |
|---|---|
| **Conversations & Responses** | Automated answers with validation scores (relevance, grounding, clarity) |
| **Professor Review** | Flagged posts with draft responses and scores for instructor inspection |
| **Others** | Ignored posts with their skip reason (instructor, greeting, admin, etc.) |

The sidebar displays aggregate counters: Topics, Total Extracted, Responses, Prof. Review, Others.

Category assignment is enforced with strict priority: instructor/empty posts → ignored first; admin/low-value posts → Professor Review; posts that pass all filters and validation → Auto Response. No post can appear in more than one view.

---

## Getting Started

### Prerequisites
- Python 3.10+
- A [Groq API key](https://console.groq.com/) (free tier available)
- Playwright browsers installed

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/mooc-assistant
cd mooc-assistant

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Configuration

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
MOOC_USERNAME=your_fun_mooc_email
MOOC_PASSWORD=your_fun_mooc_password
```

### Build the RAG Index

Place your edX course export in a `course_data/` directory, then run:

```bash
python agents/rag_builder.py
```

### Run the Dashboard

```bash
streamlit run dashboard/app.py
```

Click **Run Extraction** in the sidebar to start the pipeline.

---

## Future Enhancements

**Live post monitoring** — The current system is batch-based (run manually). A scheduled polling approach (e.g. every 30–60 minutes using APScheduler) comparing new topic URLs and post counts against a persisted record would allow near-real-time response. A webhook from the Open edX API would eliminate polling overhead entirely.

**Instructor feedback loop** — When an instructor edits or approves a draft in Professor Review, that corrected answer could be added to the RAG index as a high-quality, verified example, progressively enriching the knowledge base with teacher-level explanations.

**Video transcript indexing** — The most significant gap in the current RAG index is video content. The course delivers a substantial portion of its knowledge through video lectures. Indexing auto-generated or manually curated transcripts would dramatically expand retrieval coverage.

---

## Tech Stack

| Component | Technology |
|---|---|
| Forum automation | Playwright + MCP browser tool |
| LLM (generation) | Llama 3.1 8B Instant via Groq API |
| LLM (validation) | Llama 3.3 70B Versatile via Groq API |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (SentenceTransformers) |
| Vector similarity | NumPy cosine similarity (L2-normalised matrix multiplication) |
| Dashboard | Streamlit |
| Language | Python 3.10+ |

---
