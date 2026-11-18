# 🔎 AI Research Agent

A multi-agent AI system that turns a topic into a structured Markdown research report. Three specialised agents (Researcher, Analyst, Report Writer) work in sequence using **CrewAI**, **Groq** for LLM inference and **DuckDuckGo** for web search. Users log in, run research from a **Streamlit** app, and their reports are saved to **PostgreSQL** so they can view them later.

## Features

- Three-agent pipeline: research, analysis, report writing
- Live web search (DuckDuckGo, 5-7 sources per run)
- User sign-up and login with bcrypt-hashed passwords
- Per-user report history stored in PostgreSQL, private to each account
- Streamlit dashboard with per-agent status and Markdown download
- One shared, configurable Groq model (`.env`)
- Handles invalid API key, rate limits, network failures, empty topics, search failures, database errors and missing environment variables
- API keys and database credentials stay in `.env` and are never shown in the UI or logs

## Architecture

```mermaid
flowchart LR
    U[User topic] --> R[Researcher<br/>web search tool]
    R -->|findings + URLs| A[Analyst]
    A -->|key insights| W[Report Writer]
    W --> O[Markdown report]
    O --> DB[(PostgreSQL<br/>users + reports)]
    R -.-> S[(DuckDuckGo)]
    R & A & W -.-> L[(Groq LLM)]
```

## Tech stack

Python 3.10-3.13 · CrewAI · Groq (via LiteLLM) · Streamlit · DuckDuckGo (`ddgs`) · PostgreSQL · psycopg2 · bcrypt · python-dotenv

## Project structure

```
AI-Research-Agent/
├── app.py                    # Streamlit frontend (login, research, history)
├── agents.py                 # LLM config, agents, tasks, crew, run_research()
├── db.py                     # PostgreSQL connection, users, saved reports
├── tools.py                  # DuckDuckGo search tool
├── list_models.py            # lists Groq models your key can use
├── requirements.txt
├── .env.example
└── .gitignore
```

## Installation

```bash
git clone <your-repo-url>
cd AI-Research-Agent
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

> CrewAI does not support Python 3.14 yet. Use Python 3.10-3.13.

## PostgreSQL setup

1. Install PostgreSQL from [postgresql.org/download](https://www.postgresql.org/download/) and remember the password you set for the `postgres` user.
2. Create a database named `research_agent`, either in pgAdmin (right-click **Databases** → **Create**) or with:
   ```sql
   CREATE DATABASE research_agent;
   ```
3. Set `DATABASE_URL` in your `.env` file (see Environment setup below).

The app creates its tables (`users` and `research_reports`) automatically on first run.

## Environment setup

1. Create a free key at [console.groq.com/keys](https://console.groq.com/keys).
2. Copy the template: `copy .env.example .env` (macOS/Linux: `cp .env.example .env`).
3. Put your Groq key and database URL in `.env`.
4. Run `python list_models.py` and set `GROQ_MODEL` to one of the printed ids. Groq retires models regularly, so a hard-coded name can break.

| Variable | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | Groq API key | required |
| `GROQ_MODEL` | Model id (no `groq/` prefix) | required |
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql://postgres:yourpassword@localhost:5432/research_agent` | required |
| `MAX_SEARCH_RESULTS` | Search results per query (1-7) | 6 |
| `MAX_OUTPUT_TOKENS` | Output cap per LLM call | 2000 |

## Run

**Streamlit app**

```bash
streamlit run app.py
```

Sign up with a username and password, then enter a topic and click **Run research**. Your past reports appear in the sidebar after you log in.

**Command line**

```bash
python agents.py "Impact of AI on healthcare"
```

**Check the database connection**

```bash
python -c "from db import init_db; init_db(); print('Connected and tables ready')"
```

## Testing

| Test | Command | Expected |
|---|---|---|
| Search only (no API key needed) | `python tools.py "what is RAG"` | Numbered results with URLs |
| Model list | `python list_models.py` | Model ids |
| Database connection | `python -c "from db import init_db; init_db()"` | No error |
| Full pipeline | `python agents.py "Electric vehicles in India"` | `[done]` x3, then a Markdown report |
| Sign-up and login | Create two accounts and log in to each | Each user sees only their own reports |
| Empty topic | Click **Run research** with an empty box | Warning message |
| Missing key | Blank `GROQ_API_KEY` in `.env` | Clear error, no crash |
| Bad model | Set `GROQ_MODEL=nonexistent` | "model was not found" message |
| Offline | Disconnect the internet | Network or search-failure message |

## Output format

Every report follows this structure:

```markdown
# <Title>
## Introduction
## Key Findings
## Analysis
## Conclusion
## Sources
```

## Troubleshooting

- **`No matching distribution found for crewai`**: your Python is too new; use 3.10-3.13.
- **`model_not_found`**: run `python list_models.py` and update `GROQ_MODEL`.
- **Rate limit (429)**: wait a minute or choose a smaller model.
- **`Could not connect to PostgreSQL`**: check that the PostgreSQL service is running (`services.msc` on Windows) and that the password in `DATABASE_URL` is correct.
- **`column "password_hash" does not exist`**: tables were created by an older version. Drop `research_reports` and `users` in pgAdmin, then restart the app.
- **`GROQ_API_KEY is missing`**: the `.env` file is missing or in a different folder from `app.py`.
- **Odd file errors on Windows**: avoid keeping the project and `.venv` inside OneDrive.

## Limitations

- Reports are based on search-result snippets, not full page content, so verify important claims with the cited sources.
- The Researcher is limited to 2 searches per run to control cost.
- Login has no rate limiting or email verification, so it is suitable for a portfolio project, not a public service.
- Sessions end when the browser session does, so you may need to log in again after a page refresh.
- Token usage and quality have not been benchmarked.

## Future improvements

- Fetch and summarise full pages for deeper research
- Add a fact-checker agent
- Export reports to PDF
- Delete individual reports from history
- Login rate limiting and email verification
- Measure token usage and latency per agent
- Add automated tests and CI

## Deployment

For the live demo, use a hosted PostgreSQL database (for example Neon or Supabase) and set `DATABASE_URL` as a secret in your hosting platform. Do not commit `.env`.