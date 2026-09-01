from score import PageExtractor, score_entity_authority
from tests.test_parsers import FULL_HTML, MINIMAL_HTML


HTML_NO_SAMEAS = """<html><head>
<title>Acme Corp</title>
<meta property="og:title" content="Acme Corp">
<script type="application/ld+json">{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Acme Corp"
}</script>
</head><body>
<a href="/about">About</a>
<a href="/contact">Contact</a>
</body></html>"""


HTML_BRAND_MISMATCH = """<html><head>
<title>Acme Corp - Home</title>
<meta property="og:title" content="Acme Industries">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme LLC"}</script>
</head><body></body></html>"""


HTML_WITH_AUTHOR = """<html><head>
<title>Blog Post</title>
<script type="application/ld+json">{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "Organization", "name": "Blog", "sameAs": ["https://twitter.com/blog", "https://github.com/blog", "https://linkedin.com/company/blog"]},
    {"@type": "Person", "name": "Jane Doe"}
  ]
}</script>
</head><body>
<a href="/about">About</a>
<a href="/contact">Contact</a>
</body></html>"""


def _extract(html):
    p = PageExtractor()
    p.feed(html)
    p.close()
    return p


class TestEntityAuthority:
    def test_full_html_scores_high(self):
        score, signals = score_entity_authority(_extract(FULL_HTML))
        assert score >= 15
        assert signals["has_sameas"] is True
        assert signals["sameas_count"] >= 3

    def test_minimal_scores_zero(self):
        score, signals = score_entity_authority(_extract(MINIMAL_HTML))
        assert score == 0

    def test_no_sameas_loses_points(self):
        score, signals = score_entity_authority(_extract(HTML_NO_SAMEAS))
        assert signals["has_sameas"] is False
        assert signals["sameas_count"] == 0

    def test_author_detected(self):
        _, signals = score_entity_authority(_extract(HTML_WITH_AUTHOR))
        assert signals["has_author"] is True

    def test_contact_about_links(self):
        _, signals = score_entity_authority(_extract(FULL_HTML))
        assert signals["has_contact_link"] is True
        assert signals["has_about_link"] is True

    def test_brand_consistency(self):
        _, signals = score_entity_authority(_extract(FULL_HTML))
        assert signals["brand_consistent"] is True

    def test_brand_mismatch(self):
        _, signals = score_entity_authority(_extract(HTML_BRAND_MISMATCH))
        assert signals["brand_consistent"] is False
