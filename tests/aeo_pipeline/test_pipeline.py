"""Tests for the AEO pipeline — unified AI readiness assessment."""

import json
import types
from unittest.mock import patch, MagicMock
from aeo_pipeline.__main__ import (
    _extract_text,
    _bar,
    _grade,
    _build_action_plan,
    run_pipeline,
    format_report,
    format_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Acme Corp — Best Widgets</title>
    <meta name="description" content="Acme Corp makes the best widgets in the world. We have been making widgets since 1999 and serve over 10,000 customers globally.">
    <meta property="og:title" content="Acme Corp">
    <meta property="og:description" content="Best widgets">
    <meta property="og:image" content="https://acme.com/og.png">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Acme Corp">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Acme Corp",
        "url": "https://acme.com",
        "sameAs": ["https://twitter.com/acme"]
    }
    </script>
</head>
<body>
    <h1>Welcome to Acme Corp</h1>
    <p>We make precision-engineered widgets used by 10,000 customers across 47 countries. Each widget undergoes 12-point quality inspection before shipping.</p>
    <h2>Our Products</h2>
    <p>The Model X500 processes 500 units per hour at 99.7% accuracy. Released in March 2024, it reduced manufacturing defects by 34% for our pilot customers.</p>
    <h2>Why Choose Acme?</h2>
    <p>Three reasons: 25-year track record, ISO 9001 certification since 2003, and a 98.2% customer retention rate. We publish our quality metrics quarterly.</p>
    <ul><li>Free shipping on orders over $500</li><li>30-day money-back guarantee</li></ul>
    <h3>What customers ask</h3>
    <h3>How long does shipping take?</h3>
    <p>Standard shipping takes 3-5 business days within the continental US. Express shipping delivers in 1-2 days for an additional $15.</p>
    <a href="/about">About Us</a>
    <a href="/contact">Contact</a>
    <a href="https://twitter.com/acme">Twitter</a>
    <img src="widget.jpg" alt="Acme X500 Widget">
</body>
</html>"""


def _make_fetched(html=SAMPLE_HTML, robots_ok=True, llms_ok=False, sitemap_ok=False):
    return {
        "html": (200, html),
        "robots": (200, "User-agent: *\nAllow: /") if robots_ok else (404, ""),
        "llms": (200, "# Acme\n> Widgets") if llms_ok else (404, ""),
        "llms_full": (404, ""),
        "llms_alt": (404, ""),
        "sitemap": (200, '<?xml version="1.0"?><urlset><url><loc>https://acme.com/</loc></url></urlset>') if sitemap_ok else (404, ""),
    }


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_extract_text_strips_scripts_and_styles():
    html = "<p>Hello</p><script>var x=1;</script><style>body{}</style><p>World</p>"
    text = _extract_text(html)
    assert "Hello" in text
    assert "World" in text
    assert "var x" not in text
    assert "body{}" not in text


def test_extract_text_joins_paragraphs():
    html = "<p>First paragraph.</p><p>Second paragraph.</p>"
    text = _extract_text(html)
    assert "First paragraph." in text
    assert "Second paragraph." in text


def test_bar_empty():
    assert _bar(0, 100) == "░" * 10


def test_bar_full():
    assert _bar(100, 100) == "█" * 10


def test_bar_half():
    result = _bar(50, 100)
    assert result.count("█") == 5
    assert result.count("░") == 5


def test_grade_boundaries():
    assert _grade(80)[0] == "A"
    assert _grade(79)[0] == "B"
    assert _grade(60)[0] == "B"
    assert _grade(59)[0] == "C"
    assert _grade(40)[0] == "C"
    assert _grade(39)[0] == "D"
    assert _grade(20)[0] == "D"
    assert _grade(19)[0] == "F"


def test_build_action_plan_includes_technical_and_content():
    from aeo_writer.detector import DetectionResult, FlaggedSpan

    cr = DetectionResult(
        text="test",
        overall_score=0.7,
        signal_scores={
            "burstiness": 0.8,
            "vocabulary": 0.6,
            "hedging": 0.2,
            "monotony": 0.5,
            "specificity": 0.9,
        },
        risk_level="WEAK",
        flags=[],
    )
    data = {
        "recommendations": [
            {"title": "Add llms.txt", "points": 5, "why": "test", "code": "test"},
        ],
        "content_result": cr,
    }
    actions = _build_action_plan(data)
    categories = [a[0] for a in actions]
    assert "TECHNICAL" in categories
    assert "CONTENT" in categories


def test_build_action_plan_skips_good_signals():
    from aeo_writer.detector import DetectionResult

    cr = DetectionResult(
        text="test",
        overall_score=0.1,
        signal_scores={
            "burstiness": 0.1,
            "vocabulary": 0.2,
            "hedging": 0.1,
            "monotony": 0.15,
            "specificity": 0.05,
        },
        risk_level="STRONG",
        flags=[],
    )
    data = {"recommendations": [], "content_result": cr}
    actions = _build_action_plan(data)
    assert len(actions) == 0


def test_build_action_plan_limits_to_seven():
    from aeo_writer.detector import DetectionResult

    cr = DetectionResult(
        text="test",
        overall_score=0.8,
        signal_scores={
            "burstiness": 0.9,
            "vocabulary": 0.9,
            "hedging": 0.9,
            "monotony": 0.9,
            "specificity": 0.9,
        },
        risk_level="WEAK",
        flags=[],
    )
    recs = [{"title": f"Fix {i}", "points": i, "why": "t", "code": "c"} for i in range(5)]
    data = {"recommendations": recs, "content_result": cr}
    actions = _build_action_plan(data)
    assert len(actions) <= 7


# ---------------------------------------------------------------------------
# Integration tests (mocked network)
# ---------------------------------------------------------------------------

@patch("aeo_pipeline.__main__.fetch_all")
def test_run_pipeline_returns_combined_score(mock_fetch):
    mock_fetch.return_value = _make_fetched()
    data, error = run_pipeline("https://acme.com")
    assert error is None
    assert 0 <= data["combined_score"] <= 100
    assert data["visibility_total"] >= 0
    assert data["content_result"] is not None
    assert data["content_pct"] is not None


@patch("aeo_pipeline.__main__.fetch_all")
def test_run_pipeline_unreachable_url(mock_fetch):
    mock_fetch.return_value = {"html": (0, ""), "robots": (0, ""), "llms": (0, ""), "llms_full": (0, ""), "llms_alt": (0, ""), "sitemap": (0, "")}
    data, error = run_pipeline("https://unreachable.test")
    assert data is None
    assert "Could not reach" in error


@patch("aeo_pipeline.__main__.fetch_all")
def test_run_pipeline_short_content_skips_detection(mock_fetch):
    short_html = "<html><body><p>Hi</p></body></html>"
    mock_fetch.return_value = _make_fetched(html=short_html)
    data, error = run_pipeline("https://acme.com")
    assert error is None
    assert data["content_result"] is None
    assert data["content_pct"] is None
    assert data["combined_score"] == data["visibility_total"]


@patch("aeo_pipeline.__main__.fetch_all")
def test_format_report_contains_sections(mock_fetch):
    mock_fetch.return_value = _make_fetched()
    data, _ = run_pipeline("https://acme.com")
    report = format_report(data)
    assert "AI READINESS REPORT" in report
    assert "TECHNICAL VISIBILITY" in report
    assert "CONTENT QUALITY" in report
    assert "PRIORITY ACTION PLAN" in report
    assert "acme.com" in report


@patch("aeo_pipeline.__main__.fetch_all")
def test_format_json_valid(mock_fetch):
    mock_fetch.return_value = _make_fetched()
    data, _ = run_pipeline("https://acme.com")
    raw = format_json(data)
    parsed = json.loads(raw)
    assert "combined_score" in parsed
    assert "visibility" in parsed
    assert "content" in parsed
    assert "action_plan" in parsed
    assert isinstance(parsed["action_plan"], list)


@patch("aeo_pipeline.__main__.fetch_all")
def test_format_json_null_content_when_short(mock_fetch):
    short_html = "<html><body><p>Hi</p></body></html>"
    mock_fetch.return_value = _make_fetched(html=short_html)
    data, _ = run_pipeline("https://acme.com")
    raw = format_json(data)
    parsed = json.loads(raw)
    assert parsed["content"] is None
