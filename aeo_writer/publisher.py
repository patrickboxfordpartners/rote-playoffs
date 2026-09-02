"""Medium API publisher — creates draft or public posts."""

import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

_API_BASE = "https://api.medium.com/v1"


def _build_post_payload(
    title: str,
    content: str,
    tags: list[str],
    publish: bool,
    canonical_url: str | None,
) -> dict:
    payload = {
        "title": title,
        "contentFormat": "markdown",
        "content": content,
        "tags": tags[:5],
        "publishStatus": "public" if publish else "draft",
    }
    if canonical_url:
        payload["canonicalUrl"] = canonical_url
    return payload


def _get_user_id(token: str) -> str:
    req = Request(f"{_API_BASE}/me", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data["data"]["id"]


def publish_to_medium(
    title: str,
    content: str,
    tags: list[str],
    token: str,
    publish: bool = False,
    canonical_url: str | None = None,
) -> dict:
    if not token:
        return {"error": "No Medium token provided. Set MEDIUM_TOKEN environment variable."}

    try:
        user_id = _get_user_id(token)
    except (URLError, HTTPError, KeyError) as e:
        return {"error": f"Failed to authenticate with Medium: {e}"}

    payload = _build_post_payload(title, content, tags, publish, canonical_url)
    body = json.dumps(payload).encode()

    req = Request(
        f"{_API_BASE}/users/{user_id}/posts",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return {
            "url": data["data"]["url"],
            "id": data["data"]["id"],
        }
    except (URLError, HTTPError) as e:
        return {"error": f"Failed to publish: {e}"}
