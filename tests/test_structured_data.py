from score import PageExtractor, score_structured_data
from tests.test_parsers import FULL_HTML, MINIMAL_HTML


HTML_NO_GRAPH = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Test"}</script>
<meta property="og:title" content="Test">
<meta property="og:description" content="Desc">
<meta property="og:image" content="https://example.com/img.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Test">
<meta name="twitter:description" content="Desc">
</head><body></body></html>"""


HTML_FAQ_SCHEMA = """<html><head>
<script type="application/ld+json">{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "Organization", "name": "X", "url": "https://x.com", "logo": "https://x.com/logo.png", "description": "Desc", "sameAs": ["https://twitter.com/x"]},
    {"@type": "FAQPage", "mainEntity": [{"@type": "Question"}]},
    {"@type": "BreadcrumbList", "itemListElement": []}
  ]
}</script>
<meta property="og:title" content="X">
<meta property="og:description" content="D">
<meta property="og:image" content="https://x.com/og.png">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="X">
<meta name="twitter:description" content="D">
</head><body></body></html>"""


def _extract(html):
    p = PageExtractor()
    p.feed(html)
    p.close()
    return p


class TestStructuredData:
    def test_full_html_scores_high(self):
        score, signals = score_structured_data(_extract(FULL_HTML))
        assert signals["has_jsonld"] is True
        assert signals["has_graph"] is True
        assert signals["has_org_or_local"] is True
        assert score >= 25

    def test_minimal_html_scores_zero(self):
        score, signals = score_structured_data(_extract(MINIMAL_HTML))
        assert score == 0
        assert signals["has_jsonld"] is False

    def test_no_graph_loses_5_points(self):
        score_with, _ = score_structured_data(_extract(FULL_HTML))
        score_without, signals = score_structured_data(_extract(HTML_NO_GRAPH))
        assert signals["has_graph"] is False
        assert score_with > score_without

    def test_faq_and_breadcrumb_schemas(self):
        score, signals = score_structured_data(_extract(HTML_FAQ_SCHEMA))
        assert signals["has_faq_or_howto"] is True
        assert signals["has_breadcrumb"] is True

    def test_og_tags_detected(self):
        _, signals = score_structured_data(_extract(FULL_HTML))
        assert signals["has_og_tags"] is True

    def test_twitter_tags_detected(self):
        _, signals = score_structured_data(_extract(FULL_HTML))
        assert signals["has_twitter_tags"] is True
