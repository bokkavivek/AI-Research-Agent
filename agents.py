"""Research -> analysis -> report. Three agents, one run, current information."""
import os
import sys
import warnings
from datetime import datetime

from crewai import LLM, Agent, Crew, Process, Task
from dotenv import load_dotenv

from tools import search_many

warnings.filterwarnings("ignore", message="A function callback cannot be saved")
load_dotenv()

MAX_TOPIC_CHARS = 200


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


def make_agents(llm: LLM, verbose: bool = False):
    researcher = Agent(
        role="Researcher",
        goal="Find the most important current facts about {topic}, each with a source link and date.",
        backstory=(
            "You read search results carefully and prefer official sites, company announcements, "
            "government sources, and established news. You never state anything without a link."
        ),
        llm=llm, verbose=verbose, allow_delegation=False, max_iter=1, tools=[],
    )
    analyst = Agent(
        role="Analyst",
        goal="Check the researcher's facts against their sources and keep the reliable, current ones.",
        backstory=(
            "You verify every claim. You remove anything unsupported, outdated, unlinked, or repeated, "
            "and you rank what remains by importance to a general reader."
        ),
        llm=llm, verbose=verbose, allow_delegation=False, max_iter=1, tools=[],
    )
    writer = Agent(
        role="Report Writer",
        goal="Write a clear, professional report about {topic} as of {today}.",
        backstory=(
            "You write reports for ordinary readers in plain language. You use only the verified "
            "facts you are given, and you never describe your own process."
        ),
        llm=llm, verbose=verbose, allow_delegation=False, max_iter=1, tools=[],
    )
    return researcher, analyst, writer


def make_tasks(researcher, analyst, writer, notify):
    research_task = Task(
        description=(
            "Topic: {topic}. Date: {today}.\n\n"
            "Search results:\n{search_results}\n\n"
            "Pick 6-8 key facts about {topic} from these results. For each fact, give the claim, "
            "the source name, the full URL, and the publication date (or 'date not stated'). "
            "Prefer official and recent sources. If the results are empty or contain SEARCH_ERROR "
            "or NO_RESULTS, say so plainly. Never invent facts, numbers, dates, or links."),
        expected_output="6-8 facts with claim, source name, URL, and date, or a plain statement that no sources were found.",
        agent=researcher,
        callback=lambda _o: notify("Verifying the sources..."),
    )
    analysis_task = Task(
        description=(
            "Topic: {topic}. Date: {today}.\n\n"
            "Review the researcher's facts. Keep only facts that their source supports and that are "
            "current as of {today}. Remove unsupported, outdated, unlinked, and repeated items. "
            "Rank the remaining facts by importance. Keep the source name and URL with each fact. "
            "If nothing reliable remains, say so and name the kind of source that is missing. "
            "Do not add facts that are not in the findings."),
        expected_output="3-6 ranked, verified facts with source name, URL, and date, or a note that nothing reliable was found.",
        agent=analyst,
        context=[research_task],
        callback=lambda _o: notify("Writing your report..."),
    )
    write_task = Task(
        description=(
            "Write a report about {topic} as of {today}, using ONLY the verified facts from the analysis.\n\n"
            "Structure, in Markdown:\n"
            "# Title\n"
            "## Summary (2-3 sentences that answer the topic directly)\n"
            "## Key Findings (3-6 bullets, each with its date and a link like [Source name](URL))\n"
            "## What This Means (2-3 practical sentences for the reader)\n"
            "## Sources (a short list of the links used)\n\n"
            "Keep it under 400 words. If the verified facts are limited, say so in one sentence. "
            "Do not mention research, analysis, verification, agents, or any internal process. "
            "Do not add facts that are not in the analysis."),
        expected_output="A complete Markdown report with summary, key findings with links, practical meaning, and sources.",
        agent=writer,
        context=[analysis_task],
    )
    return research_task, analysis_task, write_task


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
    """Run research -> analysis -> report and return the report as Markdown.

    on_step(stage_name) is called as each stage starts.
    Raises ResearchError with a user-safe message on failure.
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
        notify("Searching for current information...")
        search_results = search_many([
            f"{topic} {year}",
            f"{topic} latest news {year}",
            f"{topic} guide {year}",
        ])

        llm = get_llm()
        researcher, analyst, writer = make_agents(llm, verbose)
        research_task, analysis_task, write_task = make_tasks(
            researcher, analyst, writer, notify)

        crew = Crew(
            agents=[researcher, analyst, writer],
            tasks=[research_task, analysis_task, write_task],
            process=Process.sequential,
            verbose=verbose,
        )
        result = crew.kickoff(inputs={
            "topic": topic,
            "today": today,
            "search_results": search_results,
        })
    except ResearchError:
        raise
    except Exception as exc:
        raise _friendly_error(exc) from None

    report = (getattr(result, "raw", "") or "").strip()
    if not report:
        raise ResearchError("The report came back empty. Please try again.")
    return report


if __name__ == "__main__":
    try:
        print(run_research(" ".join(sys.argv[1:]),
                           on_step=lambda s: print(f"[step] {s}")))
    except ResearchError as e:
        print(f"Error: {e}")