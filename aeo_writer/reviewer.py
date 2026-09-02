"""Side-by-side review UI — local HTTP server with detection annotations."""

import json
import os
import re
import socket
import threading
import webbrowser
from dataclasses import asdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from string import Template

from .detector import DetectionResult, analyze


def markdown_to_html(md: str) -> str:
    if not md:
        return ""
    html = md
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'((?:<li>.*</li>\n?)+)', r'<ul>\1</ul>', html)
    paras = re.split(r'\n\s*\n', html)
    parts = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if p.startswith('<h') or p.startswith('<ul'):
            parts.append(p)
        else:
            parts.append(f'<p>{p}</p>')
    return '\n'.join(parts)


def result_to_json(result: DetectionResult) -> str:
    d = asdict(result)
    return json.dumps(d)


def _find_port(start: int = 8787) -> int:
    for port in range(start, start + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    raise RuntimeError("No available port found")


class ReviewServer:
    def __init__(self, result: DetectionResult, mode: str = "detect", open_browser: bool = True):
        self.result = result
        self.mode = mode
        self.open_browser = open_browser
        self.approved_text = None
        self._stop_event = threading.Event()

        self.port = _find_port()
        template_path = os.path.join(os.path.dirname(__file__), "templates", "review.html")
        with open(template_path) as f:
            self._html = f.read()

        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    body = server_ref._html.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/api/data":
                    body = result_to_json(server_ref.result).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length)) if length else {}

                if self.path == "/api/recheck":
                    new_text = data.get("text", "")
                    server_ref.result = analyze(new_text)
                    body = result_to_json(server_ref.result).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/api/approve":
                    server_ref.approved_text = data.get("text", "")
                    server_ref._stop_event.set()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    body = b'{"ok": true}'
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def log_message(self, fmt, *args):
                pass

        self._httpd = HTTPServer(('127.0.0.1', self.port), Handler)

    def serve_until_approved(self):
        if self.open_browser:
            webbrowser.open(f"http://127.0.0.1:{self.port}/")
        while not self._stop_event.is_set():
            self._httpd.handle_request()

    def shutdown(self):
        self._stop_event.set()
        self._httpd.server_close()


def start_review(result: DetectionResult, mode: str = "detect", open_browser: bool = True) -> str | None:
    server = ReviewServer(result, mode=mode, open_browser=open_browser)
    print(f"Review UI: http://127.0.0.1:{server.port}/")
    server.serve_until_approved()
    return server.approved_text
