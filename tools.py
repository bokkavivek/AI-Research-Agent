"""Web search tool (DuckDuckGo via the `ddgs` package)."""
import os
import time

from crewai.tools import tool
from ddgs import DDGS

SNIPPET_CHARS = 300  # keep each result short to save tokens


def _max_results() -> int:
    try:
        n = int(os.getenv("MAX_SEARCH_RESULTS", "6"))
    except ValueError:
        n = 6
    return max(1, min(n, 7))


def search_web(query: str) -> str:
    """Plain function (easy to test). Returns numbered results as text."""
    query = (query or "").strip()
    if not query:
        return "SEARCH_ERROR: empty query."

    results, last_err = None, None
    for _ in range(2):  # one retry for transient failures
        try:
            results = DDGS().text(query, max_results=_max_results())
            break
        except Exception as exc:  # network error, rate limit, etc.
            last_err = exc
            time.sleep(1.5)
    if results is None:
        return (f"SEARCH_ERROR: search failed ({type(last_err).__name__}). "
                "Do not invent sources.")
    if not results:
        return "NO_RESULTS: nothing found. Try a different query or report that no sources were found."

    lines = []
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").strip()
        url = r.get("href") or ""
        snippet = (r.get("body") or "").strip()[:SNIPPET_CHARS]
        lines.append(f"[{i}] {title}\nURL: {url}\n{snippet}")
    return "\n\n".join(lines)


@tool("Web Search")
def web_search_tool(query: str) -> str:
    """Search the web with DuckDuckGo. Input: a short search query.
    Returns the top results, each with title, URL and a short snippet."""
    return search_web(query)


if __name__ == "__main__":
    import sys
    print(search_web(" ".join(sys.argv[1:]) or "what is retrieval augmented generation"))
