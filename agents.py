"""Shared agent/crew definitions, used by both the notebook and app.py."""
import os
import sys
import warnings

from crewai import LLM, Agent, Crew, Process, Task
from dotenv import load_dotenv

from tools import web_search_tool

warnings.filterwarnings("ignore", message="A function callback cannot be saved")
load_dotenv()

MAX_TOPIC_CHARS = 200


class ResearchError(Exception):
    """Error whose message is safe to show to the user."""


# ---------- LLM (one shared configuration) ----------
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
        max_tokens = int(os.getenv("MAX_OUTPUT_TOKENS", "2000"))
    except ValueError:
        max_tokens = 2000
    return LLM(model=model, api_key=key, temperature=0.2, max_tokens=max_tokens)


# ---------- Crew ----------
def build_crew(llm: LLM, on_step=None, verbose: bool = False) -> Crew:
    """on_step(agent_name) is called each time an agent finishes its task."""

    def done(name):
        def _cb(_output):
            if on_step:
                on_step(name)
        return _cb

    researcher = Agent(
        role="Web Researcher",
        goal="Find accurate, relevant information about {topic}, with source URLs.",
        backstory="You research carefully and never state anything without a source.",
        tools=[web_search_tool], llm=llm, verbose=verbose,
        allow_delegation=False, max_iter=4,
    )
    analyst = Agent(
        role="Research Analyst",
        goal="Turn raw findings about {topic} into clear, de-duplicated insights.",
        backstory="You spot trends and key points and drop noise and repetition.",
        llm=llm, verbose=verbose, allow_delegation=False, max_iter=2,
    )
    writer = Agent(
        role="Report Writer",
        goal="Write a professional Markdown research report on {topic}.",
        backstory="You write clear, well-structured reports using only the facts you are given.",
        llm=llm, verbose=verbose, allow_delegation=False, max_iter=2,
    )

    research_task = Task(
        description=(
            "Research: {topic}\n"
            "Use the Web Search tool at most 2 times. Collect 5-7 relevant findings "
            "with their source URLs. If search fails or returns nothing, say so; "
            "never invent facts or sources."),
        expected_output="A bullet list of findings, each with its source URL.",
        agent=researcher, callback=done("Researcher"),
    )
    analysis_task = Task(
        description=(
            "Analyze the research findings. Identify key insights, trends and "
            "important points. Remove duplicates and irrelevant items. "
            "Keep the source URL attached to each insight."),
        expected_output="A short list of key insights and trends, each with source URLs.",
        agent=analyst, context=[research_task], callback=done("Analyst"),
    )
    report_task = Task(
        description=(
            "Write the final report on {topic} in Markdown using ONLY the analysis. "
            "Sections: # Title, ## Introduction, ## Key Findings, ## Analysis, "
            "## Conclusion, ## Sources. List only URLs that appear in the analysis."),
        expected_output="A complete Markdown research report.",
        agent=writer, context=[analysis_task], callback=done("Report Writer"),
    )

    return Crew(
        agents=[researcher, analyst, writer],
        tasks=[research_task, analysis_task, report_task],
        process=Process.sequential, verbose=verbose,
    )


# ---------- Error handling ----------
def _friendly_error(exc: Exception) -> ResearchError:
    text = f"{type(exc).__name__} {exc}".lower()
    if any(s in text for s in ("model_not_found", "does not exist", "notfound")):
        msg = ("The Groq model in GROQ_MODEL was not found. Run `python list_models.py` "
               "and set a model from that list in .env.")
    elif any(s in text for s in ("authentication", "invalid api key", "401")):
        msg = "Groq rejected the API key. Check GROQ_API_KEY in your .env file."
    elif any(s in text for s in ("ratelimit", "rate limit", "429")):
        msg = "Groq rate limit reached. Wait a minute and retry, or use a smaller model via GROQ_MODEL."
    elif any(s in text for s in ("connection", "timeout", "timed out", "network", "resolve")):
        msg = "Network problem while contacting Groq or the search engine. Check your internet and retry."
    else:
        msg = f"Unexpected error ({type(exc).__name__}). Run with verbose=True to see details."
    return ResearchError(msg)


# ---------- Public entry point ----------
def run_research(topic: str, on_step=None, verbose: bool = False) -> str:
    """Run the full pipeline and return the final report as Markdown."""
    topic = (topic or "").strip()
    if not topic:
        raise ResearchError("Please enter a research topic.")
    if len(topic) > MAX_TOPIC_CHARS:
        raise ResearchError(f"Topic is too long (max {MAX_TOPIC_CHARS} characters).")

    crew = build_crew(get_llm(), on_step=on_step, verbose=verbose)
    try:
        result = crew.kickoff(inputs={"topic": topic})
    except Exception as exc:
        raise _friendly_error(exc) from None

    report = (getattr(result, "raw", "") or "").strip()
    if not report:
        raise ResearchError("The agents returned an empty report. Try again or rephrase the topic.")
    return report


if __name__ == "__main__":
    try:
        print(run_research(" ".join(sys.argv[1:]),
                           on_step=lambda n: print(f"[done] {n}")))
    except ResearchError as e:
        print(f"Error: {e}")
