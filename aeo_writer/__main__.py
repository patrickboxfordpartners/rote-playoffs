"""AEO Content Agent — CLI entry point."""

import argparse
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError

from .detector import analyze
from .reviewer import start_review, result_to_json
from .writer import extract_voice, generate_draft
from .publisher import publish_to_medium


def _read_input(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        from html.parser import HTMLParser

        class Strip(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []
                self._skip = {"script", "style"}
                self._stack = []
            def handle_starttag(self, tag, attrs):
                self._stack.append(tag)
            def handle_endtag(self, tag):
                if self._stack and self._stack[-1] == tag:
                    self._stack.pop()
            def handle_data(self, data):
                if not any(t in self._skip for t in self._stack):
                    self.parts.append(data)

        req = Request(path_or_url, headers={"User-Agent": "AEO-Writer/1.0"})
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        s = Strip()
        s.feed(html)
        return "\n\n".join(p.strip() for p in " ".join(s.parts).split("\n\n") if p.strip())

    with open(path_or_url) as f:
        return f.read()


def _format_report(result) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("CITABILITY REPORT")
    lines.append("=" * 60)

    pct = round((1 - result.overall_score) * 100)
    lines.append(f"\nOverall: {pct}/100 — {result.risk_level}")
    lines.append("")

    for signal, score in result.signal_scores.items():
        bar_len = round((1 - score) * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        pct = round((1 - score) * 100)
        lines.append(f"  {signal:<14} {bar}  {pct}%")

    if result.flags:
        lines.append(f"\n{len(result.flags)} issues found:\n")
        seen = set()
        for flag in result.flags:
            key = (flag.signal, flag.start)
            if key in seen:
                continue
            seen.add(key)
            snippet = result.text[flag.start:flag.end][:60]
            if len(result.text[flag.start:flag.end]) > 60:
                snippet += "..."
            lines.append(f"  [{flag.signal.upper()}] \"{snippet}\"")
            lines.append(f"    → {flag.annotation}")
            lines.append("")

    return "\n".join(lines)


def cmd_detect(args):
    try:
        text = _read_input(args.input)
    except (FileNotFoundError, URLError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    result = analyze(text)

    if args.json:
        print(result_to_json(result))
        return

    if args.no_browser:
        print(_format_report(result))
        return

    edited = start_review(result, mode="detect", open_browser=True)
    if edited:
        out_path = args.input + ".reviewed.md" if not args.input.startswith("http") else "reviewed.md"
        with open(out_path, "w") as f:
            f.write(edited)
        print(f"\nSaved reviewed text to {out_path}")


def cmd_write(args):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting voice from {args.target_url}...")
    voice = extract_voice(args.target_url)

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else []

    print(f"Generating draft on: {args.topic}...")
    draft = generate_draft(args.topic, voice, keywords)

    slug = args.topic.lower().replace(" ", "-")[:40]
    os.makedirs("drafts", exist_ok=True)
    draft_path = f"drafts/{slug}.md"
    with open(draft_path, "w") as f:
        f.write(draft)
    print(f"Draft saved to {draft_path}")

    result = analyze(draft)
    print(f"\nInitial citability: {round((1 - result.overall_score) * 100)}/100 — {result.risk_level}")
    print(f"Issues found: {len(result.flags)}")

    final_text = draft
    if not args.no_review:
        edited = start_review(result, mode="write", open_browser=True)
        if edited:
            final_text = edited
            result2 = analyze(final_text)
            print(f"\nPost-edit citability: {round((1 - result2.overall_score) * 100)}/100 — {result2.risk_level}")

            if result2.overall_score > 0.6:
                print("Warning: content still scores WEAK. Consider another review pass.")

    if args.output:
        with open(args.output, "w") as f:
            f.write(final_text)
        print(f"Final article saved to {args.output}")
        return

    token = args.medium_token or os.environ.get("MEDIUM_TOKEN", "")
    if token:
        title = final_text.split("\n")[0].lstrip("#").strip() or args.topic
        tags = keywords[:5] if keywords else []
        print(f"\nPublishing to Medium...")
        pub = publish_to_medium(title, final_text, tags, token, args.publish, canonical_url=args.target_url)
        if "url" in pub:
            print(f"Published: {pub['url']}")
        else:
            print(f"Publish failed: {pub['error']}")
            fallback = f"drafts/{slug}-final.md"
            with open(fallback, "w") as f:
                f.write(final_text)
            print(f"Saved to {fallback}")
    else:
        if args.publish:
            print("Warning: --publish was specified but no MEDIUM_TOKEN is set. Saving to file instead.", file=sys.stderr)
        fallback = f"drafts/{slug}-final.md"
        with open(fallback, "w") as f:
            f.write(final_text)
        print(f"\nNo MEDIUM_TOKEN set. Saved final article to {fallback}")
        print("Get a token: https://medium.com/me/settings/security → Integration tokens")


def main():
    parser = argparse.ArgumentParser(
        prog="aeo-writer",
        description="AEO Content Agent — improve your content's citability for AI assistants",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    det = sub.add_parser("detect", help="Run citability audit on existing content")
    det.add_argument("input", help="Path to text/markdown file, or URL")
    det.add_argument("--no-browser", action="store_true", help="Print results to terminal")
    det.add_argument("--json", action="store_true", help="Output as JSON")
    det.set_defaults(func=cmd_detect)

    wr = sub.add_parser("write", help="Generate, review, and publish new content")
    wr.add_argument("--topic", required=True, help="Article topic")
    wr.add_argument("--target-url", required=True, help="Site URL to match voice")
    wr.add_argument("--keywords", default="", help="Comma-separated target keywords")
    wr.add_argument("--medium-token", default="", help="Medium integration token")
    wr.add_argument("--publish", action="store_true", help="Publish as public (default: draft)")
    wr.add_argument("--no-review", action="store_true", help="Skip review UI")
    wr.add_argument("--output", default="", help="Save to file instead of publishing")
    wr.set_defaults(func=cmd_write)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
