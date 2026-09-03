"""Agent readiness scanning via ora.ai and isitagentready.com.

Adds a third dimension to the AI Readiness Report: how well the site
works for AI agents that want to interact (not just read) the content.

No API keys required — both services are free public APIs.
"""

import json
import urllib.request
import urllib.error
from urllib.parse import urlparse


def scan_ora(domain, timeout=30):
    """Run an ora.ai agent readiness scan.

    Returns (result_dict, error_or_None).
    result_dict keys: score, maxScore, grade, layers[], agenticSummary
    """
    url = "https://ora.ai/api/scan"
    body = json.dumps({"url": domain}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "AEO-Toolkit/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        layers = []
        for layer in data.get("layers", []):
            checks = []
            for check in layer.get("checks", []):
                checks.append({
                    "name": check.get("name", ""),
                    "status": check.get("status", ""),
                    "score": check.get("score", 0),
                    "maxScore": check.get("maxScore", 0),
                    "recommendation": check.get("recommendation", ""),
                })
            layers.append({
                "id": layer.get("id", ""),
                "name": layer.get("name", ""),
                "score": sum(c["score"] for c in checks),
                "maxScore": sum(c["maxScore"] for c in checks),
                "checks": checks,
            })
        return {
            "source": "ora.ai",
            "score": data.get("score", 0),
            "maxScore": data.get("maxScore", 100),
            "grade": data.get("grade", ""),
            "summary": data.get("agenticSummary", data.get("ctaMessage", "")),
            "layers": layers,
        }, None
    except Exception as e:
        return None, str(e)


def scan_cloudflare(url, timeout=30):
    """Run an isitagentready.com (Cloudflare) scan.

    Returns (result_dict, error_or_None).
    result_dict keys: level, levelName, checks (categorized)
    """
    api_url = "https://isitagentready.com/api/scan"
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    body = json.dumps({"url": url}).encode()
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "AEO-Toolkit/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)

        categories = {}
        for cat_name, cat_checks in data.get("checks", {}).items():
            items = []
            for check_name, check_data in cat_checks.items():
                if not isinstance(check_data, dict):
                    continue
                items.append({
                    "name": check_name,
                    "status": check_data.get("status", ""),
                    "message": check_data.get("message", ""),
                })
            categories[cat_name] = items

        return {
            "source": "isitagentready.com",
            "level": data.get("level", 0),
            "levelName": data.get("levelName", ""),
            "categories": categories,
        }, None
    except Exception as e:
        return None, str(e)


def scan_agent_readiness(url):
    """Run both scans and merge results.

    Returns (merged_dict, errors_list). merged_dict is always returned
    even if one source fails.
    """
    domain = urlparse(url if url.startswith("http") else f"https://{url}").netloc
    errors = []

    ora_result, ora_err = scan_ora(domain)
    if ora_err:
        errors.append(f"ora.ai: {ora_err}")

    cf_result, cf_err = scan_cloudflare(url)
    if cf_err:
        errors.append(f"isitagentready.com: {cf_err}")

    merged = {
        "ora": ora_result,
        "cloudflare": cf_result,
        "agent_score": ora_result["score"] if ora_result else None,
        "agent_grade": ora_result["grade"] if ora_result else None,
        "agent_summary": ora_result["summary"] if ora_result else None,
        "cf_level": cf_result["level"] if cf_result else None,
        "cf_level_name": cf_result["levelName"] if cf_result else None,
    }

    return merged, errors if errors else None
