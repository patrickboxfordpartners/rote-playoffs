from score import format_report


class TestFormatter:
    def test_contains_domain(self):
        output = format_report(
            "https://example.com",
            {"crawler": 15, "structured": 20, "citability": 18, "authority": 12},
            {},
            []
        )
        assert "example.com" in output

    def test_contains_total_score(self):
        output = format_report(
            "https://example.com",
            {"crawler": 15, "structured": 20, "citability": 18, "authority": 12},
            {},
            []
        )
        assert "65 / 100" in output

    def test_contains_bar_chart(self):
        output = format_report(
            "https://example.com",
            {"crawler": 25, "structured": 0, "citability": 25, "authority": 0},
            {},
            []
        )
        assert "AI Crawler Access" in output
        assert "Structured Data" in output

    def test_contains_recommendations(self):
        recs = [{"title": "Add llms.txt", "points": 8, "why": "AI looks here first", "code": "# llms.txt\n> Example"}]
        output = format_report(
            "https://example.com",
            {"crawler": 0, "structured": 0, "citability": 0, "authority": 0},
            {},
            recs
        )
        assert "Add llms.txt" in output
        assert "+8pts" in output

    def test_contains_gravitasindex_cta(self):
        output = format_report(
            "https://example.com",
            {"crawler": 0, "structured": 0, "citability": 0, "authority": 0},
            {},
            []
        )
        assert "gravitasindex.com" in output
