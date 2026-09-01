from score import PageExtractor, score_content_citability
from tests.test_parsers import FULL_HTML, MINIMAL_HTML


HTML_GOOD_CONTENT = """<html><head>
<meta name="description" content="A platform that helps developers ship faster with reliable infrastructure and comprehensive tools for modern development teams.">
</head><body>
<h1>Ship Faster</h1>
<p>Our platform helps developers deploy applications in seconds. We handle scaling, monitoring, and security so you can focus on building. With automatic infrastructure management, global distribution, and built-in reliability features, your applications can handle any scale.</p>
<h2>Features</h2>
<p>Auto-scaling, global CDN, and edge computing capabilities that work seamlessly together. Our infrastructure automatically scales from zero to millions of requests without any configuration changes or manual intervention required.</p>
<h3>Auto-Scaling</h3>
<p>Scale from zero to millions without configuration changes. The system automatically adjusts resources based on demand, ensuring optimal performance at all times.</p>
<h3>What makes us different?</h3>
<p>We optimize for developer experience first. This means intuitive interfaces, clear documentation, and powerful APIs that make building simple.</p>
<ul><li>One-click deploys</li><li>Preview environments</li></ul>
<ol><li>Sign up</li><li>Connect repo</li><li>Deploy</li></ol>
<table><tr><th>Plan</th><th>Price</th></tr><tr><td>Free</td><td>$0</td></tr></table>
<img src="/a.png" alt="Dashboard">
<img src="/b.png" alt="Deploy flow">
<img src="/c.png" alt="Monitoring">
</body></html>"""


HTML_LONG_PARAGRAPHS = """<html><head>
<meta name="description" content="Test">
</head><body>
<h1>Title</h1>
<p>""" + " ".join(["word"] * 200) + """</p>
<p>""" + " ".join(["word"] * 200) + """</p>
</body></html>"""


def _extract(html):
    p = PageExtractor()
    p.feed(html)
    p.close()
    return p


class TestContentCitability:
    def test_good_content_scores_high(self):
        score, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert score >= 20
        assert signals["has_single_h1"] is True
        assert signals["heading_depth"] >= 3

    def test_minimal_html_scores_low(self):
        score, signals = score_content_citability(_extract(MINIMAL_HTML))
        assert score <= 6

    def test_faq_pattern_detected(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["has_faq_patterns"] is True

    def test_long_paragraphs_penalized(self):
        _, signals = score_content_citability(_extract(HTML_LONG_PARAGRAPHS))
        assert signals["short_paragraphs"] is False

    def test_image_alt_coverage(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["alt_coverage"] >= 0.8

    def test_meta_desc_length(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["meta_desc_ok"] is True

    def test_lists_detected(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["has_lists"] is True

    def test_tables_detected(self):
        _, signals = score_content_citability(_extract(HTML_GOOD_CONTENT))
        assert signals["has_tables"] is True

    def test_full_html_word_count(self):
        _, signals = score_content_citability(_extract(FULL_HTML))
        assert signals["word_count"] > 0
