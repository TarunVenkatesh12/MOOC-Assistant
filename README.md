# MOOC Assistant 

A multi-agent pipeline that automatically extracts student questions from FUN-MOOC discussion forums, generates course-grounded responses using Retrieval-Augmented Generation, validates answer quality through a two-stage pipeline, and routes uncertain cases to a human instructor via a Streamlit dashboard.

> **IMT Atlantique** · Academic Year 2025–2026  
> Author: Tarun VENKATESH · Supervisors: Laurent TOUTAIN, Baptiste GAULTIER

---

## Documentation

| Document | Description |
|---|---|
| [MOOC Assistant Report](Assets/MOOC_Assistant_Report.pdf) | Full technical report covering RAG implementation, validation pipeline, and system architecture. |

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
## Getting Started

### Prerequisites
- Python 3.10+
- A [Groq API key](https://console.groq.com/) (free tier available)
- Playwright browsers installed

### Installation

```bash
# Clone the repository
git clone https://github.com/TarunVenkatesh12/MOOC-Assistant
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
