import json
import threading
import time
from urllib.request import urlopen, Request
from urllib.error import URLError

from aeo_writer.detector import analyze
from aeo_writer.reviewer import markdown_to_html, result_to_json, ReviewServer
from conftest import HUMAN_WRITTEN_TEXT


class TestMarkdownToHtml:
    def test_headings(self):
        assert "<h2>" in markdown_to_html("## Hello")
        assert "<h3>" in markdown_to_html("### World")

    def test_bold(self):
        assert "<strong>" in markdown_to_html("This is **bold** text")

    def test_italic(self):
        assert "<em>" in markdown_to_html("This is *italic* text")

    def test_links(self):
        html = markdown_to_html("[click](https://example.com)")
        assert 'href="https://example.com"' in html

    def test_paragraphs(self):
        html = markdown_to_html("First paragraph.\n\nSecond paragraph.")
        assert html.count("<p>") == 2

    def test_lists(self):
        html = markdown_to_html("- item one\n- item two\n- item three")
        assert "<li>" in html

    def test_empty_string(self):
        assert markdown_to_html("") == ""


class TestResultToJson:
    def test_valid_json(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        data = json.loads(result_to_json(result))
        assert "text" in data
        assert "overall_score" in data
        assert "flags" in data
        assert isinstance(data["flags"], list)

    def test_flags_have_required_fields(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        data = json.loads(result_to_json(result))
        for flag in data["flags"]:
            assert "start" in flag
            assert "end" in flag
            assert "signal" in flag
            assert "annotation" in flag


class TestReviewServer:
    def test_server_starts_and_serves_html(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        server = ReviewServer(result, mode="detect", open_browser=False)
        thread = threading.Thread(target=server.serve_until_approved)
        thread.daemon = True
        thread.start()
        time.sleep(0.3)

        try:
            resp = urlopen(f"http://127.0.0.1:{server.port}/")
            html = resp.read().decode()
            assert "Content Citability Review" in html
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_api_data_endpoint(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        server = ReviewServer(result, mode="detect", open_browser=False)
        thread = threading.Thread(target=server.serve_until_approved)
        thread.daemon = True
        thread.start()
        time.sleep(0.3)

        try:
            resp = urlopen(f"http://127.0.0.1:{server.port}/api/data")
            data = json.loads(resp.read())
            assert "overall_score" in data
            assert "flags" in data
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_approve_endpoint_stops_server(self):
        result = analyze(HUMAN_WRITTEN_TEXT)
        server = ReviewServer(result, mode="detect", open_browser=False)
        thread = threading.Thread(target=server.serve_until_approved)
        thread.daemon = True
        thread.start()
        time.sleep(0.3)

        try:
            req = Request(
                f"http://127.0.0.1:{server.port}/api/approve",
                data=json.dumps({"text": "edited text"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urlopen(req)
            assert resp.status == 200
            assert server.approved_text == "edited text"
        finally:
            server.shutdown()
            thread.join(timeout=2)
