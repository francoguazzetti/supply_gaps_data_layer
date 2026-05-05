"""
FastAPI backend for the MercadoLibre agent chat UI.

Start with:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    (run from /workspaces/supply_gaps_data_layer/)
"""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Bootstrap: .env + sys.path so scripts/ and mercadolibre/ are importable
# ---------------------------------------------------------------------------

_here = os.path.dirname(__file__)
_repo_root = os.path.join(_here, "..")

load_dotenv(dotenv_path=os.path.join(_repo_root, ".env"))
sys.path.insert(0, os.path.join(_repo_root, "scripts"))   # for agent.py
# mercadolibre/ is at repo root — already on path when run via `uvicorn backend.main:app`
# from repo root, but we add it explicitly for robustness.
if os.path.abspath(_repo_root) not in sys.path:
    sys.path.insert(0, os.path.abspath(_repo_root))

from agent import build_agent                                       # noqa: E402
from mercadolibre.browser_pool import init_pool, shutdown_pool      # noqa: E402

# ---------------------------------------------------------------------------
# App lifecycle — warm browser pool + agent executor built once at startup
# ---------------------------------------------------------------------------

_agent_executor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent_executor

    proxy = os.environ.get("SCRAPER_PROXY")  # e.g. http://user:pass@gate.smartproxy.com:7000
    pool_size = int(os.environ.get("BROWSER_POOL_SIZE", "2"))

    await init_pool(size=pool_size, proxy=proxy)
    _agent_executor = build_agent(model="gpt-4o")

    yield

    await shutdown_pool()


app = FastAPI(title="MercadoLibre Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    model: str = "gpt-4o"


# ---------------------------------------------------------------------------
# SSE streaming generator — Vercel AI SDK data stream protocol
#
# Protocol: https://sdk.vercel.ai/docs/ai-sdk-ui/stream-protocol
#   Text token:  0:"<token>"\n
#   Finish:      d:{"finishReason":"stop","usage":{...}}\n
#   Error:       3:"<error message>"\n
#
# The browser pool eliminates the browser cold-start cost (~3-5s), but the
# Playwright page fetch (navigation + JS rendering) still takes a few seconds
# before the LLM starts streaming. The frontend shows "Buscando…" during that gap.
# ---------------------------------------------------------------------------


async def stream_agent_response(message: str, model: str):
    try:
        executor = build_agent(model=model) if model != "gpt-4o" else _agent_executor

        async for event in executor.astream_events({"input": message}, version="v2"):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield f"0:{json.dumps(chunk.content, ensure_ascii=False)}\n"

        yield 'd:{"finishReason":"stop","usage":{"promptTokens":0,"completionTokens":0}}\n'

    except asyncio.CancelledError:
        return
    except Exception as exc:
        yield f"3:{json.dumps(str(exc), ensure_ascii=False)}\n"
        yield 'd:{"finishReason":"error"}\n'


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    return StreamingResponse(
        stream_agent_response(request.message, request.model),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "x-vercel-ai-data-stream": "v1",
        },
    )


@app.get("/health")
async def health():
    from mercadolibre.browser_pool import get_pool
    pool = get_pool()
    return {
        "status": "ok",
        "agent_ready": _agent_executor is not None,
        "browser_pool": pool is not None,
        "proxy_configured": bool(os.environ.get("SCRAPER_PROXY")),
    }
