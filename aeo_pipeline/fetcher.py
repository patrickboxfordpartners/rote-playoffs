"""Optional enhanced fetching with Firecrawl and Tavily.

Falls back to stdlib urllib when API keys are not set.
Set FIRECRAWL_API_KEY for JS-rendered page scraping.
Set TAVILY_API_KEY for search-enhanced content extraction.
"""

import os
import urllib.request
import urllib.error


def _stdlib_fetch(url, timeout=10):
    """Fetch HTML with stdlib urllib. Returns (html_string, error_or_None)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AEO-Toolkit/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        return html, None
    except Exception as e:
        return None, str(e)


def fetch_rendered_html(url):
    """Fetch fully rendered HTML (JS executed). Uses Firecrawl if available, else stdlib.

    Returns (html_string, error_or_None, method_used).
    """
    fc_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if fc_key:
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=fc_key)
            result = app.scrape(url, formats=["html"])
            html = getattr(result, "html", "") or ""
            if not html and hasattr(result, "content"):
                html = result.content or ""
            if html:
                return html, None, "firecrawl"
        except Exception:
            pass

    html, err = _stdlib_fetch(url)
    return html, err, "stdlib"


def extract_content(url):
    """Extract clean text content from a URL. Uses Tavily if available, else stdlib.

    Returns (text_string, metadata_dict, method_used).
    """
    tv_key = os.environ.get("TAVILY_API_KEY", "")
    if tv_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tv_key)
            result = client.extract(urls=[url])
            if result and result.get("results"):
                r = result["results"][0]
                return r.get("raw_content", ""), {"url": r.get("url", url)}, "tavily"
        except Exception as e:
            pass

    html, err = _stdlib_fetch(url)
    if err:
        return "", {}, "stdlib"

    from aeo_pipeline.__main__ import _extract_text
    text = _extract_text(html)
    return text, {}, "stdlib"


def search_context(query, max_results=5):
    """Search for contextual information about a topic. Tavily only.

    Returns (results_list, error_or_None).
    """
    tv_key = os.environ.get("TAVILY_API_KEY", "")
    if not tv_key:
        return [], "TAVILY_API_KEY not set"

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tv_key)
        result = client.search(query, max_results=max_results)
        return result.get("results", []), None
    except Exception as e:
        return [], str(e)
