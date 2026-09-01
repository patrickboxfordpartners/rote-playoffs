#!/usr/bin/env python3
"""AI Visibility Audit - scores how discoverable a site is to AI assistants."""

import json
import re
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from statistics import median
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import xml.etree.ElementTree as ET


# ---------------------------------------------------------------------------
# HTML Extraction
# ---------------------------------------------------------------------------

class PageExtractor(HTMLParser):
    """Extracts signals from HTML for AI visibility scoring."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta = {}
        self.json_ld = []
        self.headings = []
        self.paragraphs = []
        self.links = []
        self.images = []
        self.has_lists = False
        self.has_tables = False
        self._tag_stack = []
        self._current_data = []
        self._in_jsonld = False
        self._jsonld_buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._tag_stack.append(tag)
        self._current_data = []

        if tag == "meta":
            key = a.get("name", a.get("property", "")).lower()
            val = a.get("content", "")
            if key and val:
                self.meta[key] = val

        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_buf = []

        if tag == "a":
            href = a.get("href", "")
            if href:
                self.links.append(href)

        if tag == "img":
            self.images.append({"src": a.get("src", ""), "alt": a.get("alt", None)})

        if tag in ("ul", "ol"):
            self.has_lists = True
        if tag == "table":
            self.has_tables = True

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_buf.append(data)
        self._current_data.append(data)

    def handle_endtag(self, tag):
        text = " ".join(self._current_data).strip()

        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            raw = "".join(self._jsonld_buf).strip()
            if raw:
                try:
                    self.json_ld.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass

        if tag == "title" and not self.title:
            self.title = text

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and text:
            self.headings.append((int(tag[1]), text))

        if tag == "p" and text:
            self.paragraphs.append(text)

        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        self._current_data = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
