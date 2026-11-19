"""Web search helper (DuckDuckGo via the `ddgs` package). Never raises."""
import os
import time
from concurrent.futures import ThreadPoolExecutor

from ddgs import DDGS

SNIPPET_CHARS = 250  # per result, keeps prompts small and fast
RESULT_CHARS = 1200  # per query, keeps prompts small and fast


def _max_results() -> int:
    try:
        n = int(os.getenv("MAX_SEARCH_RESULTS", "5"))
    except ValueError:
        n = 5
    return max(1, min(n, 7))


def search_web(query: str) -> str:
    """Return numbered results as plain text, or SEARCH_ERROR / NO_RESULTS text."""
    query = (query or "").strip()
    if not query:
        return "SEARCH_ERROR: empty query."

    results, last_err = None, None
    for attempt in range(2):
        try:
            results = DDGS().text(query, max_results=_max_results())
            break
        except Exception as exc:
            last_err = exc
            if attempt == 0:
                time.sleep(1)

    if results is None:
        return f"SEARCH_ERROR: search failed ({type(last_err).__name__})."
    if not results:
        return "NO_RESULTS: nothing found for this query."

    lines = []
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").strip()
        url = (r.get("href") or "").strip()
        snippet = (r.get("body") or "").strip()[:SNIPPET_CHARS]
        lines.append(f"[{i}] {title}\nURL: {url}\n{snippet}")
    return "\n\n".join(lines)[:RESULT_CHARS]


def search_many(queries: list[str]) -> str:
    """Run several searches in parallel and join the results."""
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        texts = list(pool.map(search_web, queries))
    return "\n\n".join(f"Query: {q}\n{t}" for q, t in zip(queries, texts))