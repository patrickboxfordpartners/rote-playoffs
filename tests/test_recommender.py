from score import PageExtractor, generate_recommendations
from tests.test_parsers import MINIMAL_HTML


def _extract(html):
    p = PageExtractor()
    p.feed(html)
    p.close()
    return p


def _minimal_fetched():
    return {
        "html": (200, MINIMAL_HTML),
        "robots": (200, "User-agent: *\nAllow: /"),
        "llms": (404, ""),
        "llms_full": (404, ""),
        "sitemap": (404, ""),
    }


class TestRecommender:
    def test_returns_list(self):
        ext = _extract(MINIMAL_HTML)
        signals = {
            "llms_txt": False, "llms_full_txt": False,
            "has_org_or_local": False, "has_graph": False,
            "has_sameas": False, "sameas_count": 0,
            "GPTBot_allowed": True, "ClaudeBot_allowed": True,
            "PerplexityBot_allowed": True, "GoogleOther_allowed": True,
            "has_faq_or_howto": False, "has_breadcrumb": False,
            "has_og_tags": False, "has_twitter_tags": False,
            "meta_desc_ok": False, "meta_desc_len": 0,
            "brand_consistent": False, "has_contact_link": False,
            "has_about_link": False, "has_author": False,
            "schema_completeness": 0.0, "sitemap": False,
            "robots_exists": True,
        }
        recs = generate_recommendations(ext, _minimal_fetched(), signals)
        assert isinstance(recs, list)
        assert len(recs) <= 5

    def test_sorted_by_points_desc(self):
        ext = _extract(MINIMAL_HTML)
        signals = {
            "llms_txt": False, "llms_full_txt": False,
            "has_org_or_local": False, "has_graph": False,
            "has_sameas": False, "sameas_count": 0,
            "GPTBot_allowed": True, "ClaudeBot_allowed": True,
            "PerplexityBot_allowed": True, "GoogleOther_allowed": True,
            "has_faq_or_howto": False, "has_breadcrumb": False,
            "has_og_tags": False, "has_twitter_tags": False,
            "meta_desc_ok": False, "meta_desc_len": 0,
            "brand_consistent": False, "has_contact_link": False,
            "has_about_link": False, "has_author": False,
            "schema_completeness": 0.0, "sitemap": False,
            "robots_exists": True,
        }
        recs = generate_recommendations(ext, _minimal_fetched(), signals)
        points = [r["points"] for r in recs]
        assert points == sorted(points, reverse=True)

    def test_each_rec_has_required_fields(self):
        ext = _extract(MINIMAL_HTML)
        signals = {
            "llms_txt": False, "llms_full_txt": False,
            "has_org_or_local": False, "has_graph": False,
            "has_sameas": False, "sameas_count": 0,
            "GPTBot_allowed": True, "ClaudeBot_allowed": True,
            "PerplexityBot_allowed": True, "GoogleOther_allowed": True,
            "has_faq_or_howto": False, "has_breadcrumb": False,
            "has_og_tags": False, "has_twitter_tags": False,
            "meta_desc_ok": False, "meta_desc_len": 0,
            "brand_consistent": False, "has_contact_link": False,
            "has_about_link": False, "has_author": False,
            "schema_completeness": 0.0, "sitemap": False,
            "robots_exists": True,
        }
        recs = generate_recommendations(ext, _minimal_fetched(), signals)
        for rec in recs:
            assert "title" in rec
            assert "points" in rec
            assert "why" in rec
            assert "code" in rec

    def test_llms_txt_recommendation_personalized(self):
        ext = _extract(MINIMAL_HTML)
        signals = {
            "llms_txt": False, "llms_full_txt": False,
            "has_org_or_local": False, "has_graph": False,
            "has_sameas": False, "sameas_count": 0,
            "GPTBot_allowed": True, "ClaudeBot_allowed": True,
            "PerplexityBot_allowed": True, "GoogleOther_allowed": True,
            "has_faq_or_howto": False, "has_breadcrumb": False,
            "has_og_tags": False, "has_twitter_tags": False,
            "meta_desc_ok": False, "meta_desc_len": 0,
            "brand_consistent": False, "has_contact_link": False,
            "has_about_link": False, "has_author": False,
            "schema_completeness": 0.0, "sitemap": False,
            "robots_exists": True,
        }
        recs = generate_recommendations(ext, _minimal_fetched(), signals)
        llms_recs = [r for r in recs if "llms.txt" in r["title"].lower()]
        if llms_recs:
            assert "My Page" in llms_recs[0]["code"]
