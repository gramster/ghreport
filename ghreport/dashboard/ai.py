"""AI-powered insights using GitHub Models API (OpenAI-compatible)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# GitHub Models endpoint — uses the user's GH_TOKEN for auth
_ENDPOINT = "https://models.inference.ai.azure.com"
_MODEL = "gpt-4o-mini"

_client: AsyncOpenAI | None = None


def _get_client(token: str) -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=_ENDPOINT, api_key=token)
    return _client


async def _chat(token: str, system: str, user: str, max_tokens: int = 2048) -> str:
    """Send a chat completion request and return the text response."""
    client = _get_client(token)
    resp = await client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 1. Activity digest
# ---------------------------------------------------------------------------

_DIGEST_SYSTEM = """\
You are a concise engineering metrics analyst. Given structured repository
activity data, produce a brief narrative digest (3-6 bullet points).
Focus on: velocity trends, responsiveness, risk areas, and wins.
Use concrete numbers. Do NOT repeat raw data — synthesize insights.
Output markdown bullet points only, no headings."""


async def generate_digest(
    token: str,
    owner: str,
    repo: str,
    summary: dict,
    revisits: dict,
    pr_activity: dict,
    time_to_merge: dict,
    time_to_close: dict,
    time_to_response: dict,
) -> str:
    """Generate a natural-language activity digest from repo metrics."""
    payload = {
        "repository": f"{owner}/{repo}",
        "summary": summary,
        "issue_revisits": _truncate(revisits, 200),
        "pr_activity": _truncate(pr_activity, 200),
        "time_to_merge_by_month": _summarize_monthly(time_to_merge.get("months", {})),
        "time_to_close_by_month": _summarize_monthly(time_to_close.get("months", {})),
        "time_to_response_by_month": _summarize_monthly(time_to_response.get("months", {})),
    }
    return await _chat(
        token,
        _DIGEST_SYSTEM,
        json.dumps(payload, default=str),
    )


# ---------------------------------------------------------------------------
# 2. Anomaly detection
# ---------------------------------------------------------------------------

_ANOMALY_SYSTEM = """\
You are a repository health monitor. Given current-period metrics and
historical baseline statistics, identify anomalies — metrics that deviate
significantly from the baseline. For each anomaly explain:
- What changed (metric name, current vs baseline)
- Possible causes
- Suggested action

Output 2-5 markdown bullet points. If nothing is anomalous, say so briefly."""


async def detect_anomalies(
    token: str,
    owner: str,
    repo: str,
    current: dict,
    baseline: dict,
) -> str:
    """Compare current period vs historical baseline, narrate anomalies."""
    payload = {
        "repository": f"{owner}/{repo}",
        "current_period": current,
        "historical_baseline": baseline,
    }
    return await _chat(
        token,
        _ANOMALY_SYSTEM,
        json.dumps(payload, default=str),
    )


# ---------------------------------------------------------------------------
# 3. Issue clustering
# ---------------------------------------------------------------------------

_CLUSTER_SYSTEM = """\
You are an issue triage specialist. Given a list of open GitHub issues
(number, title, labels), group them into 3-8 meaningful clusters by topic
or theme. For each cluster provide:
- A short descriptive name
- The issue numbers in that cluster
- A one-sentence summary of the theme

Output valid JSON: {"clusters": [{"name": "...", "issues": [1,2,3], "summary": "..."}]}
Only output the JSON, no markdown fences or commentary."""


async def cluster_issues(
    token: str,
    owner: str,
    repo: str,
    issues: list[dict],
) -> list[dict]:
    """Cluster open issues by topic using LLM analysis."""
    # Cap at ~150 issues to stay within context limits
    truncated = issues[:150]
    items = [
        {"number": i["number"], "title": i["title"], "labels": i.get("labels", [])}
        for i in truncated
    ]
    payload = {
        "repository": f"{owner}/{repo}",
        "total_open_issues": len(issues),
        "issues": items,
    }
    raw = await _chat(
        token,
        _CLUSTER_SYSTEM,
        json.dumps(payload, default=str),
        max_tokens=3000,
    )
    try:
        parsed = json.loads(raw)
        return parsed.get("clusters", [])
    except json.JSONDecodeError:
        logger.warning("Failed to parse cluster JSON: %s", raw[:200])
        return [{"name": "Parse error", "issues": [], "summary": raw[:500]}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(data: dict, max_items: int = 100) -> dict:
    """Truncate list values in a dict to avoid blowing up context."""
    out = {}
    for k, v in data.items():
        if isinstance(v, list) and len(v) > max_items:
            out[k] = v[:max_items]
            out[f"{k}_truncated_from"] = len(v)
        else:
            out[k] = v
    return out


def _summarize_monthly(months: dict) -> dict:
    """Reduce monthly bucket lists to {month: {count, median, p90}}."""
    import statistics
    summary = {}
    for month, values in months.items():
        if not values:
            continue
        vals = sorted(values)
        n = len(vals)
        summary[month] = {
            "count": n,
            "median": round(statistics.median(vals), 1),
            "p90": round(vals[int(n * 0.9)] if n >= 5 else vals[-1], 1),
        }
    return summary
