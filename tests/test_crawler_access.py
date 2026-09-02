from score import parse_robots, is_bot_blocked, score_crawler_access


ROBOTS_BLOCK_ALL = """User-agent: *
Disallow: /"""

ROBOTS_BLOCK_GPTBOT = """User-agent: GPTBot
Disallow: /

User-agent: *
Allow: /"""

ROBOTS_BLOCK_MULTIPLE = """User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: *
Allow: /"""

ROBOTS_ALLOW_ALL = """User-agent: *
Allow: /"""

ROBOTS_EMPTY = ""


class TestParseRobots:
    def test_parses_block_all(self):
        agents = parse_robots(ROBOTS_BLOCK_ALL)
        assert "*" in agents
        assert ("disallow", "/") in agents["*"]

    def test_parses_specific_bot(self):
        agents = parse_robots(ROBOTS_BLOCK_GPTBOT)
        assert "gptbot" in agents
        assert ("disallow", "/") in agents["gptbot"]

    def test_handles_empty(self):
        agents = parse_robots(ROBOTS_EMPTY)
        assert agents == {}

    def test_ignores_comments(self):
        agents = parse_robots("# comment\nUser-agent: *\nDisallow: /private # no bots")
        assert "*" in agents
        assert ("disallow", "/private") in agents["*"]


class TestIsBotBlocked:
    def test_bot_explicitly_blocked(self):
        agents = parse_robots(ROBOTS_BLOCK_GPTBOT)
        assert is_bot_blocked(agents, "GPTBot") is True

    def test_bot_not_mentioned_wildcard_allows(self):
        agents = parse_robots(ROBOTS_ALLOW_ALL)
        assert is_bot_blocked(agents, "GPTBot") is False

    def test_wildcard_blocks_unnamed_bot(self):
        agents = parse_robots(ROBOTS_BLOCK_ALL)
        assert is_bot_blocked(agents, "ClaudeBot") is True

    def test_bot_explicitly_allowed_overrides_wildcard(self):
        robots = "User-agent: GPTBot\nAllow: /\n\nUser-agent: *\nDisallow: /"
        agents = parse_robots(robots)
        assert is_bot_blocked(agents, "GPTBot") is False

    def test_empty_robots_allows_all(self):
        agents = parse_robots(ROBOTS_EMPTY)
        assert is_bot_blocked(agents, "GPTBot") is False


class TestScoreCrawlerAccess:
    def _make_fetched(self, robots="", robots_status=200,
                      llms_status=404, llms_full_status=404,
                      sitemap="", sitemap_status=404):
        return {
            "html": (200, "<html></html>"),
            "robots": (robots_status, robots),
            "llms": (llms_status, "# llms.txt" if llms_status == 200 else ""),
            "llms_full": (llms_full_status, "# full" if llms_full_status == 200 else ""),
            "sitemap": (sitemap_status, sitemap),
        }

    def test_perfect_score(self):
        fetched = self._make_fetched(
            robots=ROBOTS_ALLOW_ALL,
            llms_status=200,
            llms_full_status=200,
            sitemap='<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/</loc></url></urlset>',
            sitemap_status=200,
        )
        score, signals = score_crawler_access(fetched)
        assert score == 25

    def test_no_robots_still_allows_bots(self):
        fetched = self._make_fetched(robots_status=404)
        score, signals = score_crawler_access(fetched)
        assert signals["robots_exists"] is False
        assert signals["GPTBot_allowed"] is True
        assert signals["ClaudeBot_allowed"] is True
        assert signals["PerplexityBot_allowed"] is True
        assert signals["GoogleOther_allowed"] is True
        assert score == 12  # 4 bots * 3pts each, no robots.txt bonus

    def test_blocked_bots_lose_points(self):
        fetched = self._make_fetched(robots=ROBOTS_BLOCK_MULTIPLE)
        score, signals = score_crawler_access(fetched)
        assert signals["GPTBot_allowed"] is False
        assert signals["ClaudeBot_allowed"] is False
        assert signals["PerplexityBot_allowed"] is True
        assert score == 3 + 3 + 3  # robots(3) + perplexity(3) + google(3)

    def test_llms_txt_awards_5_points(self):
        fetched = self._make_fetched(robots=ROBOTS_ALLOW_ALL, llms_status=200)
        score, _ = score_crawler_access(fetched)
        # 3(robots) + 12(bots) + 5(llms) = 20
        assert score == 20
