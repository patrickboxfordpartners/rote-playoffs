import json
from unittest.mock import patch, MagicMock

from aeo_writer.publisher import publish_to_medium, _build_post_payload, _get_user_id


class TestBuildPostPayload:
    def test_basic_payload(self):
        payload = _build_post_payload("My Title", "# Content", ["tag1", "tag2"], False, None)
        assert payload["title"] == "My Title"
        assert payload["contentFormat"] == "markdown"
        assert payload["content"] == "# Content"
        assert payload["tags"] == ["tag1", "tag2"]
        assert payload["publishStatus"] == "draft"

    def test_public_status(self):
        payload = _build_post_payload("T", "C", [], True, None)
        assert payload["publishStatus"] == "public"

    def test_tags_truncated_to_five(self):
        payload = _build_post_payload("T", "C", ["a", "b", "c", "d", "e", "f", "g"], False, None)
        assert len(payload["tags"]) == 5

    def test_canonical_url_included(self):
        payload = _build_post_payload("T", "C", [], False, "https://example.com/post")
        assert payload["canonicalUrl"] == "https://example.com/post"

    def test_canonical_url_absent_when_none(self):
        payload = _build_post_payload("T", "C", [], False, None)
        assert "canonicalUrl" not in payload


class TestGetUserId:
    @patch("aeo_writer.publisher.urlopen")
    def test_extracts_user_id(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": {"id": "user-123"}}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert _get_user_id("token-abc") == "user-123"


class TestPublishToMedium:
    @patch("aeo_writer.publisher.urlopen")
    def test_success(self, mock_urlopen):
        me_resp = MagicMock()
        me_resp.read.return_value = json.dumps({"data": {"id": "u1"}}).encode()
        me_resp.__enter__ = lambda s: s
        me_resp.__exit__ = MagicMock(return_value=False)

        post_resp = MagicMock()
        post_resp.read.return_value = json.dumps({
            "data": {"id": "post-1", "url": "https://medium.com/@user/post-1"}
        }).encode()
        post_resp.__enter__ = lambda s: s
        post_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [me_resp, post_resp]
        result = publish_to_medium("Title", "Content", ["ai"], "tok", False)
        assert result["url"] == "https://medium.com/@user/post-1"

    def test_missing_token_returns_error(self):
        result = publish_to_medium("Title", "Content", [], "", False)
        assert "error" in result
