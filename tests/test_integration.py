import subprocess
import sys


class TestCLIIntegration:
    def test_exits_1_on_missing_url(self):
        result = subprocess.run(
            [sys.executable, "score.py"],
            capture_output=True, text=True,
            cwd="/Users/patrickmitchell/rote-playoffs"
        )
        assert result.returncode == 1
        assert "Usage:" in result.stderr

    def test_exits_1_on_invalid_url(self):
        result = subprocess.run(
            [sys.executable, "score.py", "not-a-url"],
            capture_output=True, text=True,
            cwd="/Users/patrickmitchell/rote-playoffs"
        )
        assert result.returncode == 1

    def test_runs_on_example_dot_com(self):
        result = subprocess.run(
            [sys.executable, "score.py", "https://example.com"],
            capture_output=True, text=True,
            timeout=30,
            cwd="/Users/patrickmitchell/rote-playoffs"
        )
        assert result.returncode == 0
        assert "AI VISIBILITY AUDIT" in result.stdout
        assert "/ 100" in result.stdout
        assert "AI Crawler Access" in result.stdout
        assert "gravitasindex.com" in result.stdout
