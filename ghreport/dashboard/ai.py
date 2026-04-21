"""AI-powered insights using the GitHub Copilot SDK."""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

_MODEL = "gpt-4.1"


async def create_copilot_client():
    """Create and start a CopilotClient instance."""
    from copilot import CopilotClient
    client = CopilotClient()
    await client.start()
    return client


async def close_copilot_client(client):
    """Stop a CopilotClient instance."""
    if client is not None:
        await client.stop()


async def _chat(client, system: str, user: str) -> str:
    """Send a one-shot message via Copilot SDK and return the text response."""
    from copilot.session import PermissionHandler

    result = ""
    done = asyncio.Event()

    async with await client.create_session(
        on_permission_request=PermissionHandler.approve_all,
        model=_MODEL,
        system_message={"content": system},
        infinite_sessions={"enabled": False},
    ) as session:
        def on_event(event):
            nonlocal result
            if event.type.value == "assistant.message":
                result = event.data.content or ""
            elif event.type.value == "session.idle":
                done.set()

        session.on(on_event)
        await session.send(user)
        await done.wait()

    return result


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
    client,
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
        client,
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
    client,
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
        client,
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
    client,
    owner: str,
    repo: str,
    issues: list[dict],
    existing_clusters: list[str] | None = None,
) -> list[dict]:
    """Cluster open issues by topic using LLM analysis."""
    # Cap at ~150 issues to stay within context limits
    truncated = issues[:150]
    items = [
        {"number": i["number"], "title": i["title"], "labels": i.get("labels", [])}
        for i in truncated
    ]
    payload: dict = {
        "repository": f"{owner}/{repo}",
        "total_open_issues": len(issues),
        "issues": items,
    }
    system = _CLUSTER_SYSTEM
    if existing_clusters:
        payload["existing_cluster_names"] = existing_clusters
        system += (
            "\n\nEXISTING CLUSTERS: The repository already has these clusters: "
            + ", ".join(existing_clusters)
            + ". Assign issues to these existing clusters when they fit. "
            "Create new clusters only when no existing cluster is appropriate."
        )
    raw = await _chat(
        client,
        system,
        json.dumps(payload, default=str),
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


# ---------------------------------------------------------------------------
# 4. Data chat — natural-language queries over the DB
# ---------------------------------------------------------------------------

_CHAT_SYSTEM = """\
You are a data analyst assistant for a GitHub repository dashboard.
You answer questions about issues, pull requests, team activity, and
trends by writing SQLite queries against the database described below.

TODAY: {today}
DATA RANGE: {data_range}

DATABASE SCHEMA:
{schema}

RULES:
1. When you need data to answer, output EXACTLY one JSON object:
   {{"sql": "SELECT ..."}}
   Output ONLY that JSON — no markdown fences, no commentary.
2. Only SELECT statements are allowed. Never write INSERT/UPDATE/DELETE/DROP.
3. Keep queries concise. LIMIT results to 200 rows max.
4. After receiving query results, provide a clear, concise analysis
   in plain markdown. Use bullet points or short tables where helpful.
5. If you can answer without a query (e.g. clarification), just respond
   in plain text — no JSON.
6. If you need multiple queries, do them one at a time. After each
   result set you can issue another {{"sql": "..."}} or give the
   final answer.
7. Use the repos table to resolve owner/name to repo_id when needed.
8. Date columns are ISO-8601 text (e.g. '2025-01-15T10:30:00Z').
   Use date/time functions accordingly.
"""


async def chat_with_data(
    client,
    db_conn,
    schema_ddl: str,
    message: str,
    history: list[dict],
    data_range: str = "",
) -> dict:
    """Multi-round chat: LLM can issue SQL queries, we execute and feed back.

    Returns {"answer": str, "steps": [{"sql": str, "rows": list}...]}.
    """
    from datetime import date
    from copilot.session import PermissionHandler

    system = _CHAT_SYSTEM.format(
        today=date.today().isoformat(),
        data_range=data_range or "all available data",
        schema=schema_ddl,
    )

    steps: list[dict] = []
    max_rounds = 4

    # Build conversation so far
    messages = []
    for h in history[-10:]:  # keep last 10 turns
        messages.append(h)
    messages.append({"role": "user", "content": message})

    for _round in range(max_rounds):
        # Flatten messages into a single user prompt for _chat
        # (system is passed separately)
        user_text = "\n\n".join(
            f"[{m['role'].upper()}]: {m['content']}"
            for m in messages
        )
        raw = await _chat(client, system, user_text)

        # Check if the response is a SQL query request
        sql = _extract_sql(raw)
        if sql is None:
            # Final answer — no more queries needed
            return {"answer": raw, "steps": steps}

        # Validate: only SELECT allowed
        normalized = sql.strip().upper()
        if not normalized.startswith("SELECT"):
            return {
                "answer": "I can only run SELECT queries.",
                "steps": steps,
            }

        # Execute the query read-only
        try:
            cursor = await db_conn.execute(sql)
            cols = [d[0] for d in cursor.description] \
                if cursor.description else []
            rows = [dict(zip(cols, r))
                    for r in await cursor.fetchall()]
            # Cap row count sent back to LLM
            truncated = len(rows) > 200
            rows = rows[:200]
        except Exception as exc:
            error_msg = str(exc)
            steps.append({"sql": sql, "error": error_msg})
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"SQL error: {error_msg}. "
                           "Please fix the query.",
            })
            continue

        step = {"sql": sql, "row_count": len(rows),
                "rows": rows[:50]}  # store first 50 in response
        if truncated:
            step["truncated"] = True
        steps.append(step)

        # Feed results back as next user message
        result_text = json.dumps(
            {"columns": cols, "row_count": len(rows),
             "rows": rows}, default=str)
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": f"Query results ({len(rows)} rows"
                       f"{', truncated' if truncated else ''}):"
                       f"\n{result_text}\n\n"
                       "Now provide your analysis, or issue "
                       "another query if needed.",
        })

    # Ran out of rounds — return what we have
    return {
        "answer": "I wasn't able to complete the analysis "
                  "within the allowed number of query rounds.",
        "steps": steps,
    }


def _extract_sql(text: str) -> str | None:
    """Extract a SQL query from LLM output if present."""
    stripped = text.strip()
    # Try JSON parse first
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict) and "sql" in obj:
            return obj["sql"]
    except (json.JSONDecodeError, TypeError):
        pass
    # Try finding JSON embedded in text
    start = stripped.find('{"sql"')
    if start >= 0:
        end = stripped.find("}", start)
        if end >= 0:
            try:
                obj = json.loads(stripped[start:end + 1])
                return obj.get("sql")
            except (json.JSONDecodeError, TypeError):
                pass
    return None
