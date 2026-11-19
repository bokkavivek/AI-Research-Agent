"""Pipeline: research -> analysis (with retry) -> writer. Searches run in parallel."""
import os
import re
import sys
import warnings
from datetime import datetime

from crewai import LLM, Agent, Crew, Process, Task
from dotenv import load_dotenv

from tools import search_many

warnings.filterwarnings("ignore", message="A function callback cannot be saved")
load_dotenv()

MAX_TOPIC_CHARS = 200
MAX_ROUNDS = 2  # one retry with broader searches if the analysis fails


class ResearchError(Exception):
    """Error whose message is safe to show to the user."""


def get_llm() -> LLM:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key.startswith("your_"):
        raise ResearchError(
            "GROQ_API_KEY is missing. Copy .env.example to .env and add your key.")
    model = os.getenv("GROQ_MODEL", "").strip()
    if not model or model.startswith("choose_"):
        raise ResearchError(
            "GROQ_MODEL is missing. Run `python list_models.py` and set one in .env.")
    if not model.startswith("groq/"):
        model = f"groq/{model}"
    try:
        max_tokens = int(os.getenv("MAX_OUTPUT_TOKENS", "1500"))
    except ValueError:
        max_tokens = 1500
    return LLM(model=model, api_key=key, temperature=0.2, max_tokens=max_tokens)


def _queries(topic: str, year: str, round_no: int) -> list[str]:
    queries = [f"{topic} {year}", f"{topic} news {year}", f"{topic} guide {year}"]
    if round_no > 1:
        queries.append(f"{topic} official announcement {year}")
    return queries

def _passed(review: str) -> bool:
    """Accept STATUS: PASS in any reasonable format, e.g. **STATUS: PASS** or 'Status - pass'."""
    m = re.search(r"STATUS\W{0,3}(PASS|FAIL)", review, re.IGNORECASE)
    return bool(m) and m.group(1).upper() == "PASS"


def make_agents(llm: LLM, verbose: bool = False):
    researcher = Agent(
        role="Researcher",
        goal="Extract the most important current facts about {topic} from the search results, each with a source link.",
        backstory=(
            "You read search results carefully and prefer official sites, company announcements, "
            "government sources, and established news. You never state anything without a link."
        ),
        llm=llm, verbose=verbose, allow_delegation=False, max_iter=1, tools=[],
    )
    analyst = Agent(
        role="Analyst",
        goal="Verify the researcher's facts against their sources and keep only the reliable, current ones.",
        backstory=(
            "You check every claim. You drop anything outdated, unlinked, unsupported, or repeated, "
            "and you rank what remains by importance to a general reader."
        ),
        llm=llm, verbose=verbose, allow_delegation=False, max_iter=1, tools=[],
    )
    writer = Agent(
        role="Expert Writer",
        goal="Write a clear, detailed, and useful answer about {topic} as of {today}.",
        backstory=(
            "You explain topics to ordinary readers in plain language. You answer the question "
            "first, then give useful detail, and you never describe your own process."
        ),
        llm=llm, verbose=verbose, allow_delegation=False, max_iter=1, tools=[],
    )
    return researcher, analyst, writer


def make_tasks(researcher, analyst, writer):
    research_task = Task(
        description=(
            "Topic: {topic}. Date: {today}.\n"
            "Previous analyst feedback (fix these, and do not reuse rejected sources): {feedback}\n\n"
            "Search results:\n{search_results}\n\n"
            "Pick 6-8 key facts from these results. For each one, record: the claim, the source "
            "name, the full URL, and the publication date. Prefer official and primary sources. "
            "If a result has no date, say so. If the results are empty or contain SEARCH_ERROR or "
            "NO_RESULTS, say that no sources were found. Never invent facts, numbers, dates, or links."),
        expected_output="6-8 facts, each with claim, source name, full URL, and date, or a statement that no sources were found.",
        agent=researcher,
    )
    analysis_task = Task(
        description=(
            "Topic: {topic}. Date: {today}.\n"
            "Review the researcher's facts:\n{findings}\n\n"
            "For each fact, confirm the source supports it and that it is current. Drop any fact "
            "that is unsupported, outdated, unlinked, undated, or repeated. "
            "If fewer than 3 reliable facts remain, reply with exactly: STATUS: FAIL, then say what "
            "kind of source is missing.\n"
            "Otherwise begin your reply with exactly: STATUS: PASS\n"
            "Then list the 3-6 strongest verified facts, ordered by importance, each with its claim, "
            "source name, URL, and date. Never add facts that are not in the findings."),
        expected_output="STATUS: PASS with 3-6 verified, linked facts, or STATUS: FAIL with the missing source type.",
        agent=analyst,
    )
    write_task = Task(
        description=(
            "Write an answer to the user's question about {topic} using ONLY these verified facts:\n"
            "{verified}\n\n"
            "Format:\n"
            "- A direct answer in 2-3 sentences.\n"
            "- A '### Key points' heading, then 3-6 bullets. Each bullet gives one fact, its date, "
            "and a link like [Source name](URL).\n"
            "- A '### What this means for you' heading, then 2-3 practical sentences.\n"
            "- A '### Sources' heading, then a short list of the links used.\n"
            "Keep the total under 350 words. Use only facts from the verified list. "
            "Do not mention research, analysis, checking, verification, agents, or any internal process. "
            "If some information is uncertain, say so in one sentence."),
        expected_output="A detailed, linked answer with sections for key points, practical meaning, and sources.",
        agent=writer,
    )
    return research_task, analysis_task, write_task


def _run(crew: Crew, inputs: dict) -> str:
    return (crew.kickoff(inputs=inputs).raw or "").strip()


def _friendly_error(exc: Exception) -> ResearchError:
    text = f"{type(exc).__name__} {exc}".lower()
    if any(s in text for s in ("model_not_found", "does not exist", "notfound")):
        msg = "The Groq model in GROQ_MODEL was not found. Run `python list_models.py` and pick one."
    elif any(s in text for s in ("authentication", "invalid api key", "401")):
        msg = "Groq rejected the API key. Check GROQ_API_KEY in your .env file."
    elif any(s in text for s in ("ratelimit", "rate limit", "429")):
        msg = "Groq rate limit reached. Wait a minute and retry."
    elif any(s in text for s in ("connection", "timeout", "timed out", "network", "resolve")):
        msg = "Network problem. Check your internet connection and retry."
    elif "tool_use_failed" in text or "failed_generation" in text:
        msg = "The model produced an invalid response. Please try again."
    else:
        msg = f"Unexpected error ({type(exc).__name__}). Run with verbose=True to see details."
    return ResearchError(msg)


def run_research(topic: str, on_step=None, verbose: bool = False) -> str:
    """Research, analyze, and write a detailed Markdown answer.

    on_step(stage_name) is called as each stage starts.
    Raises ResearchError with a user-safe message if no reliable answer is found.
    """
    topic = (topic or "").strip()
    if not topic:
        raise ResearchError("Please enter a research topic.")
    if len(topic) > MAX_TOPIC_CHARS:
        raise ResearchError(f"Topic is too long (max {MAX_TOPIC_CHARS} characters).")

    notify = on_step or (lambda _stage: None)
    now = datetime.now()
    today, year = now.strftime("%B %d, %Y"), now.strftime("%Y")

    try:
        llm = get_llm()
        researcher, analyst, writer = make_agents(llm, verbose)
        research_task, analysis_task, write_task = make_tasks(researcher, analyst, writer)

        research_crew = Crew(agents=[researcher], tasks=[research_task],
                             process=Process.sequential, verbose=verbose)
        analysis_crew = Crew(agents=[analyst], tasks=[analysis_task],
                             process=Process.sequential, verbose=verbose)
        write_crew = Crew(agents=[writer], tasks=[write_task],
                          process=Process.sequential, verbose=verbose)

        feedback = "None. This is the first attempt."
        verified = None

        for round_no in range(1, MAX_ROUNDS + 1):
            notify("Searching for current information...")
            search_results = search_many(_queries(topic, year, round_no))

            notify("Gathering the key facts...")
            findings = _run(research_crew, {
                "topic": topic, "today": today,
                "feedback": feedback, "search_results": search_results,
            })

            notify("Verifying the sources...")
            review = _run(analysis_crew, {
                "topic": topic, "today": today, "findings": findings,
            })
            if review.upper().startswith("STATUS: PASS"):
                verified = review
                break
            feedback = review  # analyst's reasons go back to the researcher

        if verified is None:
            raise ResearchError(
                "We couldn't find reliable, up-to-date information on this yet. "
                "Try a more specific question.")

        notify("Writing your answer...")
        answer = _run(write_crew, {
            "topic": topic, "today": today, "verified": verified,
        })
    except ResearchError:
        raise
    except Exception as exc:
        raise _friendly_error(exc) from None

    if not answer:
        raise ResearchError("The answer came back empty. Please try again.")
    return answer


if __name__ == "__main__":
    try:
        print(run_research(" ".join(sys.argv[1:]),
                           on_step=lambda s: print(f"[step] {s}")))
    except ResearchError as e:
        print(f"Error: {e}")