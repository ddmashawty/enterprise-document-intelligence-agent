from __future__ import annotations

from doc_agent.collect.base import FetchResult, ProbeResult

GONE = (403, 404, 410)


def failed(kind: str, res: FetchResult) -> ProbeResult:
    """ProbeResult for a fetch that neither succeeded nor returned a clean 'not there'."""
    if res.blocked:
        return ProbeResult(kind, res.url, "blocked", res.blocked)
    if res.skipped:
        return ProbeResult(kind, res.url, "skipped", res.skipped)
    if res.status in GONE:
        return ProbeResult(kind, res.url, "not_found", f"HTTP {res.status}")
    return ProbeResult(kind, res.url, "error", res.error or f"HTTP {res.status}")
