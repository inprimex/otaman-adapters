"""Tests for Easy8Adapter — JTBD-37 PM sync adapter.

Uses unittest.mock.patch to mock urllib.request.urlopen so no live network
calls are made.
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, call, patch

import pytest

# Import the module under test.  The easy8 module provides its own stand-in
# dataclasses when otaman-core is absent, so this always works.
from otaman_adapters.easy8 import (
    EASY8_CAPABILITIES,
    Easy8Adapter,
    Easy8Client,
    Easy8Error,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(data: dict, status: int = 200) -> MagicMock:
    """Return a context-manager mock that looks like urllib.request.urlopen."""
    raw = json.dumps(data).encode()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.read = MagicMock(return_value=raw)
    cm.status = status
    return cm


def _make_empty_response(status: int = 204) -> MagicMock:
    """Simulate a 204 No Content response."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.read = MagicMock(return_value=b"")
    cm.status = status
    return cm


# ---------------------------------------------------------------------------
# EASY8_CAPABILITIES correctness
# ---------------------------------------------------------------------------

class TestEasy8Capabilities:
    def test_project_hierarchy_true(self):
        assert EASY8_CAPABILITIES.project_hierarchy is True

    def test_github_url_field_is_homepage(self):
        assert EASY8_CAPABILITIES.github_url_field == "homepage"

    def test_project_custom_fields_api_false(self):
        assert EASY8_CAPABILITIES.project_custom_fields_api is False

    def test_issue_comments_true(self):
        assert EASY8_CAPABILITIES.issue_comments is True

    def test_custom_fields_true(self):
        assert EASY8_CAPABILITIES.custom_fields is True

    def test_custom_workflow_true(self):
        assert EASY8_CAPABILITIES.custom_workflow is True

    def test_webhook_inbound_true(self):
        assert EASY8_CAPABILITIES.webhook_inbound is True

    def test_webhook_registration_api_true(self):
        assert EASY8_CAPABILITIES.webhook_registration_api is True

    def test_user_creation_api_true(self):
        assert EASY8_CAPABILITIES.user_creation_api is True

    def test_agent_identity_user_true(self):
        assert EASY8_CAPABILITIES.agent_identity_user is True

    def test_agent_identity_group_false(self):
        assert EASY8_CAPABILITIES.agent_identity_group is False

    def test_agent_identity_system_user_true(self):
        assert EASY8_CAPABILITIES.agent_identity_system_user is True

    def test_mcp_support_true(self):
        assert EASY8_CAPABILITIES.mcp_support is True

    def test_rest_api_true(self):
        assert EASY8_CAPABILITIES.rest_api is True

    def test_native_assignee_metrics_true(self):
        assert EASY8_CAPABILITIES.native_assignee_metrics is True


# ---------------------------------------------------------------------------
# Easy8Client — low-level HTTP
# ---------------------------------------------------------------------------

class TestEasy8Client:
    def test_get_sends_api_key_header(self):
        client = Easy8Client("https://example.com", "mykey")
        response = _make_response({"ok": True})
        with patch("urllib.request.urlopen", return_value=response) as mock_open:
            client.get("/projects.json")
        req = mock_open.call_args[0][0]
        assert req.get_header("X-redmine-api-key") == "mykey"

    def test_get_appends_query_params(self):
        client = Easy8Client("https://example.com", "k")
        response = _make_response({})
        with patch("urllib.request.urlopen", return_value=response) as mock_open:
            client.get("/issues.json", params={"project_id": 1, "status_id": "open"})
        req = mock_open.call_args[0][0]
        assert "project_id=1" in req.full_url

    def test_post_sends_json_body(self):
        client = Easy8Client("https://example.com", "k")
        response = _make_response({"issue": {"id": 5, "subject": "test",
                                              "project": {"id": 1}}})
        with patch("urllib.request.urlopen", return_value=response) as mock_open:
            client.post("/issues.json", {"issue": {"subject": "test"}})
        req = mock_open.call_args[0][0]
        assert req.method == "POST"
        body = json.loads(req.data)
        assert body["issue"]["subject"] == "test"

    def test_put_returns_empty_dict_on_204(self):
        client = Easy8Client("https://example.com", "k")
        empty_response = _make_empty_response(204)
        with patch("urllib.request.urlopen", return_value=empty_response):
            result = client.put("/issues/1.json", {"issue": {"notes": "hi"}})
        assert result == {}

    def test_raises_easy8_error_on_non_2xx(self):
        import urllib.error
        client = Easy8Client("https://example.com", "k")
        exc = urllib.error.HTTPError(
            url="https://example.com/issues.json",
            code=422,
            msg="Unprocessable",
            hdrs=MagicMock(),
            fp=io.BytesIO(b'{"errors":["Subject cannot be blank"]}'),
        )
        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(Easy8Error) as exc_info:
                client.post("/issues.json", {})
        assert exc_info.value.status == 422
        assert "Subject" in exc_info.value.body


# ---------------------------------------------------------------------------
# Easy8Adapter.capabilities
# ---------------------------------------------------------------------------

class TestAdapterCapabilities:
    def test_capabilities_returns_easy8_capabilities(self):
        adapter = Easy8Adapter("https://example.com", "k")
        assert adapter.capabilities is EASY8_CAPABILITIES


# ---------------------------------------------------------------------------
# Easy8Adapter.register_webhook — must make exactly 2 HTTP calls per event
# ---------------------------------------------------------------------------

class TestRegisterWebhook:
    def test_two_http_calls_per_event_single_event(self):
        """POST create + PUT activate = 2 calls for one event."""
        adapter = Easy8Adapter("https://es.example.com", "apikey")

        post_resp = _make_response({"easy_web_hook": {"id": 42, "url": "https://cb.example.com"}})
        put_resp = _make_empty_response(204)

        call_responses = [post_resp, put_resp]

        with patch("urllib.request.urlopen", side_effect=call_responses) as mock_open:
            result = adapter.register_webhook("https://cb.example.com", ["create"])

        assert mock_open.call_count == 2, (
            f"Expected 2 HTTP calls (POST create + PUT activate), got {mock_open.call_count}"
        )

        # First call: POST
        post_req = mock_open.call_args_list[0][0][0]
        assert post_req.method == "POST"
        assert "/easy_web_hooks.json" in post_req.full_url

        # Second call: PUT activate
        put_req = mock_open.call_args_list[1][0][0]
        assert put_req.method == "PUT"
        assert "/easy_web_hooks/42.json" in put_req.full_url
        body = json.loads(put_req.data)
        assert body["easy_web_hook"]["status"] == "active"

        assert result.id == 42
        assert result.url == "https://cb.example.com"

    def test_two_http_calls_per_event_multiple_events(self):
        """2 events → 4 HTTP calls total."""
        adapter = Easy8Adapter("https://es.example.com", "apikey")

        responses = [
            _make_response({"easy_web_hook": {"id": 10}}),
            _make_empty_response(204),
            _make_response({"easy_web_hook": {"id": 11}}),
            _make_empty_response(204),
        ]

        with patch("urllib.request.urlopen", side_effect=responses) as mock_open:
            result = adapter.register_webhook("https://cb.example.com", ["create", "update"])

        assert mock_open.call_count == 4
        # Result carries the last hook id
        assert result.id == 11
        assert result.events == ["create", "update"]

    def test_uses_easy_web_hooks_with_underscore_not_webhooks(self):
        """Path must be /easy_web_hooks.json, not /easy_webhooks.json."""
        adapter = Easy8Adapter("https://es.example.com", "apikey")

        responses = [
            _make_response({"easy_web_hook": {"id": 1}}),
            _make_empty_response(204),
        ]

        with patch("urllib.request.urlopen", side_effect=responses) as mock_open:
            adapter.register_webhook("https://cb.example.com", ["create"])

        post_req = mock_open.call_args_list[0][0][0]
        assert "/easy_web_hooks.json" in post_req.full_url
        assert "/easy_webhooks.json" not in post_req.full_url


# ---------------------------------------------------------------------------
# Easy8Adapter.add_comment — must use PUT with notes field
# ---------------------------------------------------------------------------

class TestAddComment:
    def test_uses_put_not_post(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        put_resp = _make_empty_response(204)

        with patch("urllib.request.urlopen", return_value=put_resp) as mock_open:
            adapter.add_comment(99, "This is a note.")

        req = mock_open.call_args[0][0]
        assert req.method == "PUT", f"Expected PUT, got {req.method}"

    def test_sends_notes_field_not_separate_endpoint(self):
        """Comment must go via issue notes field, not a comments endpoint."""
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        put_resp = _make_empty_response(204)

        with patch("urllib.request.urlopen", return_value=put_resp) as mock_open:
            adapter.add_comment(99, "Hello world.")

        req = mock_open.call_args[0][0]
        # Must target /issues/99.json, not a /comments or /journal endpoint
        assert "/issues/99.json" in req.full_url
        assert "/comments" not in req.full_url

        body = json.loads(req.data)
        assert body["issue"]["notes"] == "Hello world."

    def test_add_comment_returns_none(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        put_resp = _make_empty_response(204)

        with patch("urllib.request.urlopen", return_value=put_resp):
            result = adapter.add_comment(99, "Note.")

        assert result is None


# ---------------------------------------------------------------------------
# Easy8Adapter.handle_inbound_event — payload parsing
# ---------------------------------------------------------------------------

class TestHandleInboundEvent:
    def test_parses_action_as_event_type(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        payload = {
            "action": "create",
            "project": {"id": 5, "name": "My Project"},
            "issue": {"id": 42, "subject": "Bug"},
        }
        event = adapter.handle_inbound_event(payload)
        assert event.event_type == "create"

    def test_parses_project_id(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        payload = {
            "action": "update",
            "project": {"id": 7},
            "issue": {"id": 3},
        }
        event = adapter.handle_inbound_event(payload)
        assert event.project_id == 7

    def test_parses_issue_id(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        payload = {
            "action": "update",
            "project": {"id": 7},
            "issue": {"id": 3},
        }
        event = adapter.handle_inbound_event(payload)
        assert event.issue_id == 3

    def test_falls_back_to_object_kind_when_action_missing(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        payload = {"object_kind": "issue_destroy", "issue": {"id": 1}}
        event = adapter.handle_inbound_event(payload)
        assert event.event_type == "issue_destroy"

    def test_unknown_event_type_for_empty_payload(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        event = adapter.handle_inbound_event({})
        assert event.event_type == "unknown"

    def test_nested_project_id_from_issue(self):
        """project_id can be nested inside issue.project."""
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        payload = {
            "action": "create",
            "issue": {
                "id": 10,
                "project": {"id": 99},
            },
        }
        event = adapter.handle_inbound_event(payload)
        assert event.project_id == 99
        assert event.issue_id == 10

    def test_payload_preserved_verbatim(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        payload = {"action": "create", "issue": {"id": 1}, "extra": "data"}
        event = adapter.handle_inbound_event(payload)
        assert event.payload is payload


# ---------------------------------------------------------------------------
# Easy8Adapter.list_statuses
# ---------------------------------------------------------------------------

class TestListStatuses:
    def test_parses_statuses(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        resp_data = {
            "issue_statuses": [
                {"id": 1, "name": "Declared"},
                {"id": 2, "name": "In-Progress"},
                {"id": 3, "name": "Done"},
            ]
        }
        with patch("urllib.request.urlopen", return_value=_make_response(resp_data)):
            statuses = adapter.list_statuses()

        assert len(statuses) == 3
        assert statuses[0].name == "Declared"
        assert statuses[1].id == 2


# ---------------------------------------------------------------------------
# Easy8Adapter.list_priorities
# ---------------------------------------------------------------------------

class TestListPriorities:
    def test_parses_priorities(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        resp_data = {
            "issue_priorities": [
                {"id": 1, "name": "Low"},
                {"id": 2, "name": "High"},
            ]
        }
        with patch("urllib.request.urlopen", return_value=_make_response(resp_data)):
            priorities = adapter.list_priorities()

        assert len(priorities) == 2
        assert priorities[1].name == "High"


# ---------------------------------------------------------------------------
# Easy8Adapter.set_project_map
# ---------------------------------------------------------------------------

class TestSetProjectMap:
    def test_stores_project_map(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        adapter.set_project_map({"my-program": 42, "other": 7})
        assert adapter._project_map["my-program"] == 42
        assert adapter._project_map["other"] == 7

    def test_merges_into_existing_map(self):
        adapter = Easy8Adapter("https://es.example.com", "apikey")
        adapter._project_map["existing"] = 1
        adapter.set_project_map({"new-key": 99})
        assert adapter._project_map["existing"] == 1
        assert adapter._project_map["new-key"] == 99
