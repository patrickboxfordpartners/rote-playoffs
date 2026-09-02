import subprocess
import sys
import os
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE_FILE = os.path.join(PROJECT_ROOT, "tests", "aeo_writer", "_sample_article.md")


def setup_module():
    with open(SAMPLE_FILE, "w") as f:
        f.write(
            "In today's rapidly evolving digital landscape, businesses must leverage "
            "comprehensive strategies. Moreover, it's worth noting that robust approaches "
            "are essential.\n\n"
            "Furthermore, organizations should consider the multifaceted nature of growth. "
            "It's possible that these methodologies could potentially help. To some extent, "
            "the nuanced dynamics may determine outcomes.\n\n"
            "Ultimately, the crucial takeaway is clear. By harnessing cutting-edge tools, "
            "companies can move the needle effectively."
        )


def teardown_module():
    if os.path.exists(SAMPLE_FILE):
        os.remove(SAMPLE_FILE)


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "aeo_writer", *args],
        capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=10,
    )


class TestDetectMode:
    def test_detect_file_prints_report(self):
        result = _run("detect", SAMPLE_FILE, "--no-browser")
        assert result.returncode == 0
        assert "CITABILITY REPORT" in result.stdout

    def test_detect_json_output(self):
        result = _run("detect", SAMPLE_FILE, "--no-browser", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "overall_score" in data
        assert "flags" in data

    def test_detect_missing_file(self):
        result = _run("detect", "/nonexistent/file.md", "--no-browser")
        assert result.returncode != 0

    def test_detect_shows_signal_scores(self):
        result = _run("detect", SAMPLE_FILE, "--no-browser")
        assert "burstiness" in result.stdout.lower() or "Burstiness" in result.stdout
        assert "vocabulary" in result.stdout.lower() or "Vocabulary" in result.stdout


class TestWriteMode:
    def test_write_without_api_key_errors(self):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-m", "aeo_writer", "write",
             "--topic", "test", "--target-url", "https://example.com",
             "--no-review", "--output", "/dev/null"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=10, env=env,
        )
        assert result.returncode != 0
        assert "ANTHROPIC_API_KEY" in result.stderr


class TestHelpText:
    def test_help_shows_both_commands(self):
        result = _run("--help")
        assert "detect" in result.stdout
        assert "write" in result.stdout

    def test_detect_help(self):
        result = _run("detect", "--help")
        assert result.returncode == 0
