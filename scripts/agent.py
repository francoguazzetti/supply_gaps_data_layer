"""
MercadoLibre LangChain Agent
=============================
A LangChain agent that uses the MercadoLibre scraper as a tool to search
for products and answer questions about prices, sellers, and availability.

Setup
-----
  pip install langchain langchain-openai
  pip install beautifulsoup4 playwright playwright-stealth
  python -m playwright install chromium

Usage
-----
  export OPENAI_API_KEY="your-key-here"
  python3 agent.py
  python3 agent.py --query "notebook lenovo"
  python3 agent.py --query "celular samsung" --pages 2
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# Make the mercadolibre package importable regardless of CWD
# ---------------------------------------------------------------------------

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from mercadolibre import ScraperConfig, scrape_one          # noqa: E402
from mercadolibre.browser_pool import get_pool              # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definition — async so it runs in the FastAPI event loop and can share
# the warm browser pool without cross-loop conflicts.
# ---------------------------------------------------------------------------


@tool
async def search_mercadolibre(
    query: str,
    max_pages: int = 1,
) -> str:
    """Search for products on MercadoLibre Argentina and return structured results.

    Use this tool whenever the user asks about product prices, availability,
    sellers, discounts, or any product information from MercadoLibre Argentina.

    Args:
        query: The product search keyword(s) in Spanish (e.g. "notebook lenovo",
               "celular samsung", "zapatillas nike").
        max_pages: Number of result pages to scrape (1–5). Use 1 for a quick
                   lookup, 2–3 for broader price comparisons.

    Returns:
        A JSON string with a summary and the list of products found.
        Each product includes: title, price, currency, original_price, discount,
        seller, rating, installments, shipping, product_url, offer_type.
    """
    logger.info("Tool called: search_mercadolibre(query=%r, pages=%d)", query, max_pages)

    config = ScraperConfig(query=query, max_pages=max_pages)
    # get_pool() returns the warm pool when running inside FastAPI;
    # returns None when running standalone (CLI) — scraper falls back to launching its own browser.
    products = await scrape_one(config, pool=get_pool())

    if not products:
        return json.dumps({
            "error": "No products found. MercadoLibre may have blocked the request or returned no results.",
            "products": [],
        })

    main_offers = [p for p in products if p["offer_type"] == "main"]
    alt_offers  = [p for p in products if p["offer_type"] != "main"]

    return json.dumps(
        {
            "total_results": len(products),
            "main_offers": len(main_offers),
            "alternative_offers": len(alt_offers),
            "products": products,
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a helpful shopping assistant specialized in the Argentine market.
You have access to a tool that scrapes real-time product data from
MercadoLibre Argentina (mercadolibre.com.ar).

When the user asks about products, prices, or sellers:
1. Call the search_mercadolibre tool with a relevant Spanish query.
2. Analyse the returned data and answer the user clearly in their language.
3. Highlight the best deals (lowest price, biggest discount, free shipping).
4. Format prices with the currency symbol and dot-separated thousands
   (e.g. $ 1.299.999).
5. If the user asks for a comparison, summarise the top 3–5 options.

Always be concise, factual, and base your answer only on the data returned
by the tool — do not invent prices or sellers.
"""


def build_agent(model: str = "gpt-4o") -> AgentExecutor:
    """Build and return a LangChain AgentExecutor with the MercadoLibre tool."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY environment variable is not set.\n"
            "Export it with:  export OPENAI_API_KEY='your-key-here'"
        )

    llm = ChatOpenAI(model=model, api_key=api_key, max_tokens=4096)
    tools = [search_mercadolibre]
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LangChain agent that searches MercadoLibre Argentina.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Product query to send directly to the agent (skips interactive mode).",
    )
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model ID to use.")
    args = parser.parse_args()

    agent_executor = build_agent(model=args.model)

    if args.query:
        result = agent_executor.invoke({"input": args.query})
        print("\n" + "=" * 80)
        print(result["output"])
        print("=" * 80)
    else:
        print("MercadoLibre Agent — type your question or 'exit' to quit.")
        print("-" * 60)
        while True:
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                break
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                print("Bye!")
                break
            result = agent_executor.invoke({"input": user_input})
            print(f"\nAgent: {result['output']}")


if __name__ == "__main__":
    main()
