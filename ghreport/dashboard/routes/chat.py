"""Chat route — natural-language queries over the dashboard DB."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..ai import chat_with_data
from ..db import SCHEMA

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Compact schema DDL for the LLM (strip index lines)
_SCHEMA_DDL = "\n".join(
    line for line in SCHEMA.strip().splitlines()
    if not line.strip().startswith("CREATE INDEX")
)


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@router.post("")
async def chat(request: Request, body: ChatRequest):
    """Send a natural-language question about the data."""
    client = request.app.state.ai_client
    if client is None:
        raise HTTPException(
            503, "AI chat not available — Copilot SDK not initialized"
        )

    db = request.app.state.db

    # Build a data-range summary from repos table
    cursor = await db.db.execute(
        "SELECT MIN(data_since) AS earliest,"
        " MAX(last_synced_at) AS latest FROM repos"
    )
    row = await cursor.fetchone()
    earliest = row["earliest"] or "unknown"
    latest = row["latest"] or "unknown"
    data_range = f"{earliest} to {latest}"

    result = await chat_with_data(
        client,
        db.db,
        _SCHEMA_DDL,
        body.message,
        [m.model_dump() for m in body.history],
        data_range=data_range,
    )

    return result
