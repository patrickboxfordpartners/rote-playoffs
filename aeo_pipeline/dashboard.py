"""Local HTTP dashboard for the AI Readiness Report."""

import json
import os
import re
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, urljoin
from html.parser import HTMLParser

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_ANNOTATION_CSS = """
<style id="aeo-overlay-css">
.aeo-highlight {
  background: rgba(180, 83, 9, 0.15);
  outline: 2px solid rgba(180, 83, 9, 0.4);
  border-radius: 3px;
  cursor: pointer;
  position: relative;
  transition: background 0.2s, outline-color 0.2s;
}
.aeo-highlight:hover {
  background: rgba(180, 83, 9, 0.3);
  outline-color: rgba(180, 83, 9, 0.8);
}
.aeo-highlight.aeo-active {
  background: rgba(180, 83, 9, 0.35);
  outline-color: #b45309;
}
.aeo-tooltip {
  position: fixed;
  max-width: 320px;
  padding: 10px 14px;
  background: #1a1a2e;
  color: #f1f5f9;
  font: 13px/1.5 -apple-system, BlinkMacSystemFont, sans-serif;
  border-radius: 6px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.25);
  z-index: 100000;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
}
.aeo-tooltip.aeo-visible { opacity: 1; }
.aeo-tooltip-signal {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fbbf24;
  margin-bottom: 4px;
}
</style>
"""

_ANNOTATION_JS = """
<script id="aeo-overlay-js">
(function() {
  var DATA = __ANNOTATION_DATA__;

  var tooltip = document.createElement('div');
  tooltip.className = 'aeo-tooltip';
  tooltip.innerHTML = '<div class="aeo-tooltip-signal"></div><div class="aeo-tooltip-text"></div>';
  document.body.appendChild(tooltip);

  function findTextNodes(root) {
    var nodes = [];
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while (node = walker.nextNode()) {
      var tag = node.parentElement ? node.parentElement.tagName : '';
      if (tag !== 'SCRIPT' && tag !== 'STYLE' && tag !== 'NOSCRIPT') {
        nodes.push(node);
      }
    }
    return nodes;
  }

  function highlightSnippet(textNodes, snippet, signal, annotation) {
    var snippetLower = snippet.toLowerCase().substring(0, 60);
    for (var i = 0; i < textNodes.length; i++) {
      var nodeText = textNodes[i].textContent.toLowerCase();
      var idx = nodeText.indexOf(snippetLower);
      if (idx === -1) continue;

      var range = document.createRange();
      range.setStart(textNodes[i], idx);
      range.setEnd(textNodes[i], Math.min(idx + snippet.length, textNodes[i].textContent.length));

      var mark = document.createElement('span');
      mark.className = 'aeo-highlight';
      mark.setAttribute('data-signal', signal);
      mark.setAttribute('data-annotation', annotation);
      try { range.surroundContents(mark); } catch(e) { continue; }
      return true;
    }
    return false;
  }

  var textNodes = findTextNodes(document.body);
  var seen = {};
  if (DATA.flags) {
    DATA.flags.forEach(function(f) {
      var key = f.signal + ':' + f.start;
      if (seen[key]) return;
      seen[key] = true;
      var snippet = DATA.text.substring(f.start, Math.min(f.end, f.start + 60));
      highlightSnippet(textNodes, snippet, f.signal, f.annotation);
    });
  }

  document.addEventListener('mouseover', function(e) {
    var el = e.target.closest('.aeo-highlight');
    if (!el) return;
    tooltip.querySelector('.aeo-tooltip-signal').textContent = el.getAttribute('data-signal');
    tooltip.querySelector('.aeo-tooltip-text').textContent = el.getAttribute('data-annotation');
    var rect = el.getBoundingClientRect();
    tooltip.style.left = Math.min(rect.left, window.innerWidth - 340) + 'px';
    tooltip.style.top = (rect.bottom + 8) + 'px';
    tooltip.classList.add('aeo-visible');
  });
  document.addEventListener('mouseout', function(e) {
    if (e.target.closest('.aeo-highlight')) {
      tooltip.classList.remove('aeo-visible');
    }
  });

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || msg.type !== 'highlight') return;
    var text = msg.text.toLowerCase().substring(0, 40);
    var marks = document.querySelectorAll('.aeo-highlight');
    marks.forEach(function(m) { m.classList.remove('aeo-active'); });
    for (var i = 0; i < marks.length; i++) {
      if (marks[i].textContent.toLowerCase().indexOf(text) !== -1) {
        marks[i].classList.add('aeo-active');
        marks[i].scrollIntoView({ behavior: 'smooth', block: 'center' });
        break;
      }
    }
  });
})();
</script>
"""


def _serialize_data(data):
    """Convert pipeline data dict into JSON for the dashboard template."""
    cr = data["content_result"]
    out = {
        "url": data["url"],
        "domain": urlparse(data["url"]).netloc or data["url"],
        "combined_score": data["combined_score"],
        "visibility_total": data["visibility_total"],
        "visibility_scores": data["visibility_scores"],
        "content_pct": data["content_pct"],
        "content_risk_level": cr.risk_level if cr else None,
        "content_signal_scores": {k: round(v, 3) for k, v in cr.signal_scores.items()} if cr else None,
        "content_flags": [
            {"signal": f.signal, "start": f.start, "end": f.end, "annotation": f.annotation}
            for f in cr.flags
        ] if cr else [],
        "text": cr.text if cr else "",
        "action_plan": [
            {"category": c, "action": a, "impact": i}
            for c, a, i in _build_actions(data)
        ],
        "recommendations": [
            {"title": r["title"], "points": r["points"], "why": r["why"], "code": r.get("code", "")}
            for r in data["recommendations"]
        ],
        "signals": data["signals"],
        "agent_readiness": data.get("agent_readiness"),
        "executive_summary": data.get("executive_summary", ""),
        "delta_narrative": data.get("delta_narrative", ""),
        "rewritten_meta": data.get("rewritten_meta", []),
        "content_suggestions": data.get("content_suggestions", []),
        "priority_actions": data.get("priority_actions", []),
    }
    return json.dumps(out)


def _build_annotation_data(data):
    """Build the data blob injected into the proxied site for highlights."""
    cr = data["content_result"]
    out = {
        "flags": [
            {"signal": f.signal, "start": f.start, "end": f.end, "annotation": f.annotation}
            for f in cr.flags
        ] if cr else [],
        "text": cr.text if cr else "",
    }
    return json.dumps(out)


def _build_actions(data):
    """Duplicated from __main__ to avoid circular import."""
    actions = []
    for rec in data["recommendations"][:4]:
        actions.append(("TECHNICAL", rec["title"], f"+{rec['points']}pts visibility"))

    cr = data["content_result"]
    if cr:
        advice = {
            "burstiness": "Vary sentence lengths — mix short punchy sentences with longer ones",
            "vocabulary": "Replace generic filler words with specific, concrete terms",
            "hedging": "Replace hedging phrases with definitive, citable statements",
            "monotony": "Vary paragraph structure — start with questions, numbers, or quotes",
            "specificity": "Add concrete details: numbers, names, examples, data points",
        }
        worst = sorted(cr.signal_scores.items(), key=lambda x: x[1], reverse=True)
        for signal, score in worst:
            if score > 0.3:
                actions.append((
                    "CONTENT",
                    advice.get(signal, f"Improve {signal}"),
                    f"{signal} at {round((1 - score) * 100)}%",
                ))
    return actions[:7]


def _script_safe(json_str):
    """Make a JSON string safe to embed inside an inline <script> tag.

    A literal "</script>" (or "<!--") inside JSON string values — e.g. a
    JSON-LD code snippet in a recommendation — would otherwise terminate the
    script element early and break the whole page. Escaping "<" as "\\u003c"
    keeps the payload valid JSON while preventing premature tag closing.
    """
    return json_str.replace("<", "\\u003c")


def _fetch_and_annotate(url, annotation_json):
    """Fetch the site HTML and inject annotation overlays.

    Uses Firecrawl for JS-rendered pages when FIRECRAWL_API_KEY is set,
    falls back to stdlib urllib.
    """
    from .fetcher import fetch_rendered_html

    html, err, method = fetch_rendered_html(url)
    if err or not html:
        return "<html><body><p style='padding:2rem;font-family:sans-serif;color:#64748b'>Could not load site preview.</p></body></html>"

    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    base_tag = f'<base href="{base_url}/" target="_blank">'

    css = _ANNOTATION_CSS
    js = _ANNOTATION_JS.replace("__ANNOTATION_DATA__", _script_safe(annotation_json))

    if re.search(r'<head[^>]*>', html, re.IGNORECASE):
        html = re.sub(r'(<head[^>]*>)', r'\1' + base_tag, html, count=1, flags=re.IGNORECASE)
    else:
        html = base_tag + html

    if '</body>' in html.lower():
        insert_pos = html.lower().rfind('</body>')
        html = html[:insert_pos] + css + js + html[insert_pos:]
    else:
        html += css + js

    return html


def start_dashboard(data, open_browser=True):
    """Serve the dashboard on a local port and open the browser."""
    template = (_TEMPLATE_DIR / "dashboard.html").read_text()
    report_json = _serialize_data(data)
    annotation_json = _build_annotation_data(data)

    dashboard_html = template.replace("__REPORT_DATA__", _script_safe(report_json))
    site_html = _fetch_and_annotate(data["url"], annotation_json)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/site":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(site_html.encode("utf-8", errors="replace"))
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(dashboard_html.encode())

        def log_message(self, format, *args):
            pass

    for port in range(8900, 8920):
        try:
            server = HTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        print("Could not find an available port (8900-8919).")
        return

    url = f"http://127.0.0.1:{port}"
    print(f"Dashboard: {url}")
    print("Press Ctrl+C to stop.\n")

    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
