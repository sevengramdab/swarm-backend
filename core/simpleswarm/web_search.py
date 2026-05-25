"""
web_search.py
=============
Lightweight web search for the ReAct agent.
Uses DuckDuckGo Lite (no API key required).
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
import re
from typing import List, Optional


def search_web(query: str, max_results: int = 5) -> List[dict]:
    """
    Search the web via DuckDuckGo Lite.
    Returns a list of {title, url, snippet} dicts.
    """
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        results = []
        # Naive regex extraction of DuckDuckGo lite results
        # Each result is in a .result block
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        snippets = re.findall(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        for i, (href, title_raw) in enumerate(blocks[:max_results]):
            title = re.sub(r"<[^>]+>", "", title_raw).strip()
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
            # DuckDuckGo redirects through their own URL
            if href.startswith("/"):
                href = f"https://duckduckgo.com{href}"
            results.append({"title": title, "url": href, "snippet": snippet})

        return results
    except Exception as e:
        return [{"title": "Search error", "url": "", "snippet": str(e)}]


class WebSearchTool:
    """Tool wrapper for the ReAct agent."""

    def search(self, query: str, max_results: int = 5) -> dict:
        results = search_web(query, max_results)
        return {
            "success": True,
            "query": query,
            "results": results,
            "result_count": len(results),
        }
