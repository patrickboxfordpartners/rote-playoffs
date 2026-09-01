from score import PageExtractor


FULL_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Acme Corp - Cloud Platform</title>
    <meta name="description" content="Acme Corp provides cloud infrastructure for startups.">
    <meta property="og:title" content="Acme Corp">
    <meta property="og:description" content="Cloud infrastructure for startups">
    <meta property="og:image" content="https://acme.example.com/og.png">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Acme Corp">
    <meta name="twitter:description" content="Cloud infrastructure for startups">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "name": "Acme Corp",
                "url": "https://acme.example.com",
                "logo": "https://acme.example.com/logo.png",
                "description": "Cloud infrastructure for startups",
                "sameAs": [
                    "https://twitter.com/acme",
                    "https://linkedin.com/company/acme",
                    "https://github.com/acme"
                ]
            },
            {
                "@type": "WebSite",
                "name": "Acme Corp",
                "url": "https://acme.example.com"
            }
        ]
    }
    </script>
</head>
<body>
    <h1>Cloud Platform for Startups</h1>
    <p>Acme Corp builds reliable cloud infrastructure that scales with your team.</p>
    <h2>Features</h2>
    <p>Deploy in seconds. Scale without limits.</p>
    <ul><li>Auto-scaling</li><li>Global CDN</li></ul>
    <h3>Pricing</h3>
    <p>Simple, transparent pricing for every stage.</p>
    <table><tr><td>Free</td><td>$0/mo</td></tr></table>
    <h2>FAQ</h2>
    <h3>What regions do you support?</h3>
    <p>We support US, EU, and APAC regions.</p>
    <a href="/about">About</a>
    <a href="/contact">Contact Us</a>
    <a href="https://twitter.com/acme">Twitter</a>
    <img src="/hero.png" alt="Cloud dashboard screenshot">
    <img src="/logo.png">
</body>
</html>"""


MINIMAL_HTML = """<!DOCTYPE html>
<html>
<head><title>My Page</title></head>
<body><p>Hello world.</p></body>
</html>"""


class TestPageExtractor:
    def test_extracts_title(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.title == "Acme Corp - Cloud Platform"

    def test_extracts_meta_description(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.meta["description"] == "Acme Corp provides cloud infrastructure for startups."

    def test_extracts_og_tags(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.meta["og:title"] == "Acme Corp"
        assert p.meta["og:image"] == "https://acme.example.com/og.png"

    def test_extracts_twitter_tags(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.meta["twitter:card"] == "summary_large_image"

    def test_extracts_json_ld(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert len(p.json_ld) == 1
        assert "@graph" in p.json_ld[0]

    def test_extracts_headings(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        levels = [h[0] for h in p.headings]
        assert 1 in levels
        assert 2 in levels
        assert 3 in levels
        h1_texts = [h[1] for h in p.headings if h[0] == 1]
        assert "Cloud Platform for Startups" in h1_texts

    def test_extracts_paragraphs(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert len(p.paragraphs) >= 3

    def test_extracts_links(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert "/about" in p.links
        assert "/contact" in p.links

    def test_extracts_images(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert len(p.images) == 2
        assert p.images[0]["alt"] == "Cloud dashboard screenshot"
        assert p.images[1]["alt"] is None

    def test_detects_lists(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.has_lists is True

    def test_detects_tables(self):
        p = PageExtractor()
        p.feed(FULL_HTML)
        p.close()
        assert p.has_tables is True

    def test_minimal_html(self):
        p = PageExtractor()
        p.feed(MINIMAL_HTML)
        p.close()
        assert p.title == "My Page"
        assert len(p.json_ld) == 0
        assert p.has_lists is False
        assert p.has_tables is False

    def test_empty_html(self):
        p = PageExtractor()
        p.feed("")
        p.close()
        assert p.title == ""
        assert len(p.headings) == 0
