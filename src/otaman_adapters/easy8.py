"""Easy8 (Redmine-core) PM sync adapter for Otaman.

Implements ``PmSyncAdapter`` against the Easy8 REST API at
es.sunflowers.online.  All HTTP is done via the stdlib ``urllib.request``
so no external dependencies are required.

Capabilities were probed live on es.sunflowers.online (2026-06 audit).
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Any, Optional

try:
    from otaman_core.pm_sync import (
        PmSyncAdapter,
        PmAdapterCapabilities,
        PmSyncConfig,
        PmProject,
        PmIssue,
        PmIssueFilters,
        PmStatus,
        PmPriority,
        PmInboundEvent,
        WebhookRegistration,
        SpecChange,
        SpecState,
        register_pm_adapter,
    )
except ImportError:
    # otaman-core not yet installed in this environment
    PmSyncAdapter = object
    register_pm_adapter = lambda *a, **kw: None  # noqa: E731

    # -----------------------------------------------------------------------
    # Minimal stand-ins so the module is importable and testable without
    # otaman-core installed.  These are replaced at runtime when the real
    # package is present.
    # -----------------------------------------------------------------------

    from dataclasses import dataclass as _dc, field as _field

    @_dc
    class PmAdapterCapabilities:
        issue_comments: bool = False
        custom_fields: bool = False
        custom_workflow: bool = False
        webhook_inbound: bool = False
        webhook_registration_api: bool = False
        user_creation_api: bool = False
        agent_identity_user: bool = False
        agent_identity_group: bool = False
        agent_identity_system_user: bool = False
        mcp_support: bool = False
        rest_api: bool = False
        native_assignee_metrics: bool = False
        project_hierarchy: bool = False
        github_url_field: Optional[str] = None
        project_custom_fields_api: bool = False

    @_dc
    class PmSyncConfig:
        program_key: str = ""
        program_name: str = ""

    @_dc
    class PmProject:
        id: int = 0
        name: str = ""
        identifier: str = ""
        parent_id: Optional[int] = None

    @_dc
    class PmIssue:
        id: int = 0
        subject: str = ""
        project_id: int = 0
        status: str = ""
        priority: str = ""
        assignee: Optional[str] = None
        custom_fields: dict = _field(default_factory=dict)

    @_dc
    class PmIssueFilters:
        project_id: Optional[int] = None
        status_id: Optional[str] = None

    @_dc
    class PmStatus:
        id: int = 0
        name: str = ""

    @_dc
    class PmPriority:
        id: int = 0
        name: str = ""

    @_dc
    class PmInboundEvent:
        event_type: str = ""
        project_id: Optional[int] = None
        issue_id: Optional[int] = None
        payload: dict = _field(default_factory=dict)

    @_dc
    class WebhookRegistration:
        id: int = 0
        url: str = ""
        active: bool = False

    @_dc
    class SpecChange:
        title: str = ""
        agent_name: str = ""
        project_id: Optional[int] = None
        jtbd_id: Optional[str] = None
        spec_path: Optional[str] = None
        description: str = ""

    class SpecState:
        DECLARED = "declared"
        IN_PROGRESS = "in_progress"
        BLOCKED = "blocked"
        DONE = "done"


# ---------------------------------------------------------------------------
# Capabilities (probed 2026-06, es.sunflowers.online)
# ---------------------------------------------------------------------------

EASY8_CAPABILITIES = PmAdapterCapabilities(
    issue_comments=True,
    custom_fields=True,
    custom_workflow=True,
    webhook_inbound=True,
    webhook_registration_api=True,
    user_creation_api=True,
    agent_identity_user=True,
    agent_identity_group=False,
    agent_identity_system_user=True,
    mcp_support=True,
    rest_api=True,
    native_assignee_metrics=True,
    project_hierarchy=True,
    github_url_field="homepage",
    project_custom_fields_api=False,
)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class Easy8Error(Exception):
    """Raised when the Easy8 API returns a non-2xx response."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Easy8 HTTP {status}: {body}")
        self.status = status
        self.body = body


class Easy8Client:
    """Thin, dependency-free HTTP wrapper for the Easy8 / Redmine REST API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        return {
            "X-Redmine-API-Key": self._api_key,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; otaman/1.0)",
        }

    def _do_request(
        self,
        method: str,
        path: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        url = f"{self._base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        body_bytes: Optional[bytes] = None
        if data is not None:
            body_bytes = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=self._build_headers(),
            method=method,
        )

        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise Easy8Error(exc.code, body) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET *path* and return parsed JSON body."""
        return self._do_request("GET", path, params=params)

    def post(self, path: str, data: dict) -> dict:
        """POST *data* as JSON to *path* and return parsed JSON body."""
        return self._do_request("POST", path, data=data)

    def put(self, path: str, data: dict) -> dict:
        """PUT *data* as JSON to *path*; returns ``{}`` on 204 No Content."""
        return self._do_request("PUT", path, data=data)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

# Default Otaman state → Easy8/Redmine status name mapping (standard Redmine install)
_DEFAULT_STATUS_MAP: dict[str, str] = {
    "declared": "New",
    "in_progress": "In Progress",
    "blocked": "Feedback",
    "done": "Closed",
}


class Easy8Adapter(PmSyncAdapter):  # type: ignore[misc]
    """PmSyncAdapter implementation for Easy8 (Redmine-core)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        tracker: str = "Task",
        status_map: Optional[dict] = None,
        platform_custom_fields: Optional[dict] = None,
    ) -> None:
        self._client = Easy8Client(base_url, api_key)
        self._project_map: dict[str, int] = {}
        self._status_cache: dict[str, int] = {}
        self._tracker_cache: dict[str, int] = {}
        self._priority_cache: dict[str, int] = {}
        self._custom_field_cache: dict[str, int] = {}
        self._platform_custom_fields: dict[str, int] = platform_custom_fields or {}
        self._root_project_id: int | None = None
        self._tracker_name = tracker
        self._status_map: dict[str, str] = dict(_DEFAULT_STATUS_MAP)
        if status_map:
            self._status_map.update(status_map)

    # ------------------------------------------------------------------
    # Protocol: capabilities
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> PmAdapterCapabilities:
        return EASY8_CAPABILITIES

    # ------------------------------------------------------------------
    # Project management
    # ------------------------------------------------------------------

    def provision_project(self, config: Any) -> PmProject:
        """Ensure a top-level project exists for *config.program_key*.

        Returns the existing project if already present, otherwise creates it.
        """
        existing = self._find_project_by_name(config.program_name)
        if existing is not None:
            self._project_map[config.program_key] = existing.id
            return existing

        resp = self._client.post(
            "/projects.json",
            {
                "project": {
                    "name": config.program_name,
                    "identifier": config.program_key,
                }
            },
        )
        project = _parse_project(resp["project"])
        self._project_map[config.program_key] = project.id
        self._root_project_id = project.id
        return project

    def create_subproject(
        self,
        name: str,
        identifier: str,
        parent_id: int,
        github_url: str = "",
    ) -> PmProject:
        """Create a child project under *parent_id*.

        Silently returns the existing project if *identifier* is already taken.
        """
        existing = self._find_project_by_name(name)
        if existing is not None:
            self._project_map[identifier] = existing.id
            return existing

        resp = self._client.post(
            "/projects.json",
            {
                "project": {
                    "name": name,
                    "identifier": identifier,
                    "parent_id": parent_id,
                    "homepage": github_url,
                    "description": (
                        f"# Otaman metadata\nprogram-key: {identifier}"
                    ),
                }
            },
        )
        project = _parse_project(resp["project"])
        self._project_map[identifier] = project.id
        return project

    # ------------------------------------------------------------------
    # Issue management
    # ------------------------------------------------------------------

    def create_issue(self, spec_change: Any) -> PmIssue:
        """Create a Redmine issue from a *SpecChange*."""
        subject = f"[{spec_change.agent_name}] {spec_change.title}"

        payload: dict[str, Any] = {"subject": subject}
        tracker_id = self._resolve_tracker_id(self._tracker_name)
        if tracker_id is not None:
            payload["tracker_id"] = tracker_id

        priority_id = self._resolve_priority_id("normal")
        if priority_id is not None:
            payload["priority_id"] = priority_id

        project_id = getattr(spec_change, "project_id", None)
        if project_id is None and spec_change.agent_name in self._project_map:
            project_id = self._project_map[spec_change.agent_name]
        if project_id is not None:
            payload["project_id"] = project_id

        if getattr(spec_change, "description", ""):
            payload["description"] = spec_change.description

        cf_map = self._resolve_custom_field_ids()
        _FIELD_MAP = {
            "jtbd-id":      str(getattr(spec_change, "jtbd_id", "") or ""),
            "otaman-agent": str(getattr(spec_change, "agent_name", "") or ""),
            "spec-path":    str(getattr(spec_change, "spec_path", "") or ""),
        }
        custom_field_values: dict[str, str] = {}
        for field_name, value in _FIELD_MAP.items():
            cf_id = cf_map.get(field_name.lower())
            if cf_id is not None and value:
                custom_field_values[str(cf_id)] = value
        if custom_field_values:
            payload["custom_field_values"] = custom_field_values

        resp = self._client.post("/issues.json", {"issue": payload})
        return _parse_issue(resp["issue"])

    def update_issue(self, issue_id: int, state: Any) -> PmIssue:
        """Update the status of *issue_id* to match *state*."""
        state_key = str(getattr(state, "status", state)).lower().replace(" ", "_").replace("-", "_")
        status_name = self._status_map.get(state_key, str(state))
        status_id = self._resolve_status_id(status_name)

        self._client.put(
            f"/issues/{issue_id}.json",
            {"issue": {"status_id": status_id}},
        )
        # Fetch the updated issue to return current state
        resp = self._client.get(f"/issues/{issue_id}.json")
        return _parse_issue(resp["issue"])

    def add_comment(self, issue_id: int, body: str) -> None:
        """Append a journal note to *issue_id* via PUT (Redmine notes field)."""
        self._client.put(
            f"/issues/{issue_id}.json",
            {"issue": {"notes": body}},
        )

    def list_issues(self, filters: Any) -> list:
        """Return issues matching *filters*."""
        params: dict[str, Any] = {}
        project_id = getattr(filters, "project_id", None)
        status_id = getattr(filters, "status_id", None)
        if project_id is not None:
            params["project_id"] = project_id
        if status_id is not None:
            params["status_id"] = status_id

        resp = self._client.get("/issues.json", params=params or None)
        return [_parse_issue(i) for i in resp.get("issues", [])]

    # ------------------------------------------------------------------
    # Webhook management
    # ------------------------------------------------------------------

    def register_webhook(self, url: str, events: list) -> WebhookRegistration:
        """Register *url* for each event in *events* and activate each hook.

        Easy8 uses ``/easy_web_hooks.json`` (underscore path).
        Each event is exactly 2 HTTP calls: POST to create (inactive) + PUT to activate.

        Returns the WebhookRegistration for the last registered webhook.
        """
        last_id: int = 0
        for event in events:
            resp = self._client.post(
                "/easy_web_hooks.json",
                {
                    "easy_web_hook": {
                        "url": url,
                        "name": f"otaman-issue-{event}",
                        "entity_type": "Issue",
                        "action": str(event),
                        **({"project_id": self._root_project_id} if self._root_project_id else {}),
                    }
                },
            )
            hook_id: int = resp.get("easy_web_hook", {}).get("id", 0)
            self._client.put(
                f"/easy_web_hooks/{hook_id}.json",
                {"easy_web_hook": {"status": "active"}},
            )
            last_id = hook_id

        return WebhookRegistration(id=last_id, url=url, active=True)

    def ensure_custom_field(self, name: str, field_format: str = "string") -> int:
        """Create an IssueCustomField with *name* if it doesn't already exist.

        Easy8 extension: POST /custom_fields.json?type=IssueCustomField.
        Returns the field id (existing or newly created).
        """
        # Check if already exists
        try:
            resp = self._client.get("/custom_fields.json")
            for cf in resp.get("custom_fields", []):
                if cf.get("name") == name:
                    return int(cf["id"])
        except Exception:
            pass

        # Easy8 requires ?type=IssueCustomField — call _do_request directly
        resp = self._client._do_request(
            "POST",
            "/custom_fields.json",
            data={"custom_field": {"name": name, "field_format": field_format}},
            params={"type": "IssueCustomField"},
        )
        cf = resp.get("custom_field", {})
        return int(cf.get("id", 0))

    # ------------------------------------------------------------------
    # Inbound event handling
    # ------------------------------------------------------------------

    def handle_inbound_event(self, payload: dict) -> PmInboundEvent:
        """Parse a raw Easy8 webhook payload into a *PmInboundEvent*."""
        project_id: Optional[int] = None
        issue_id: Optional[int] = None

        # Redmine webhook payload shapes vary; try common keys
        raw_project = payload.get("project") or {}
        if isinstance(raw_project, dict):
            project_id = raw_project.get("id")
        elif isinstance(raw_project, int):
            project_id = raw_project

        raw_issue = payload.get("issue") or {}
        if isinstance(raw_issue, dict):
            issue_id = raw_issue.get("id")
            if project_id is None:
                nested = raw_issue.get("project") or {}
                project_id = nested.get("id") if isinstance(nested, dict) else None

        # Determine event type from action / object_kind
        action = payload.get("action") or payload.get("object_kind") or "unknown"

        return PmInboundEvent(
            event_type=str(action),
            project_id=project_id,
            issue_id=issue_id,
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Enumeration helpers
    # ------------------------------------------------------------------

    def list_statuses(self) -> list:
        """Return all issue statuses defined in Easy8."""
        resp = self._client.get("/issue_statuses.json")
        return [
            PmStatus(id=s["id"], name=s["name"])
            for s in resp.get("issue_statuses", [])
        ]

    def list_priorities(self) -> list:
        """Return all issue priorities defined in Easy8."""
        resp = self._client.get("/enumerations/issue_priorities.json")
        return [
            PmPriority(id=p["id"], name=p["name"])
            for p in resp.get("issue_priorities", [])
        ]

    def get_users(self) -> list[dict]:
        """Return all users from Easy8 as raw dicts.

        Each dict contains at least ``id`` (int), ``name`` (str), and
        ``mail`` (str, Redmine's email field key).
        Raises ``Easy8Error`` on HTTP failure.
        """
        resp = self._client.get("/users.json")
        return resp.get("users", [])

    # ------------------------------------------------------------------
    # Project map (injected externally for multi-repo setups)
    # ------------------------------------------------------------------

    def set_project_map(self, project_map: dict[str, int]) -> None:
        """Inject an externally-built ``{identifier: project_id}`` mapping."""
        self._project_map.update(project_map)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_project_by_name(self, name: str) -> Optional[PmProject]:
        """Scan paginated project list for a project with *name*; return None if absent.

        Easy8 ignores the ``identifier`` field in POST /projects.json and assigns
        the numeric project id as identifier, so lookup must use the name field.
        """
        offset = 0
        limit = 100
        while True:
            resp = self._client.get(
                "/projects.json",
                params={"offset": offset, "limit": limit},
            )
            projects = resp.get("projects", [])
            for p in projects:
                if p.get("name") == name:
                    return _parse_project(p)
            total_count = resp.get("total_count", 0)
            offset += limit
            if offset >= total_count or not projects:
                break
        return None

    def _resolve_status_id(self, status_name: str) -> int:
        """Return the integer id for *status_name* (case-insensitive), fetching if not cached."""
        if not self._status_cache:
            for s in self.list_statuses():
                self._status_cache[s.name.lower()] = s.id
        return self._status_cache.get(status_name.lower(), 1)

    def _resolve_tracker_id(self, tracker_name: str) -> Optional[int]:
        """Return tracker id for *tracker_name* (case-insensitive), or None if not found."""
        if not self._tracker_cache:
            try:
                resp = self._client.get("/trackers.json")
                for t in resp.get("trackers", []):
                    self._tracker_cache[t["name"].lower()] = int(t["id"])
            except Exception:
                return None
        return self._tracker_cache.get(tracker_name.lower())

    def _resolve_priority_id(self, priority_name: str) -> Optional[int]:
        """Return priority id for *priority_name* (case-insensitive), or None if not found."""
        if not self._priority_cache:
            try:
                resp = self._client.get("/enumerations/issue_priorities.json")
                for p in resp.get("issue_priorities", []):
                    self._priority_cache[p["name"].lower()] = int(p["id"])
            except Exception:
                return None
        return self._priority_cache.get(priority_name.lower())

    def _resolve_custom_field_ids(self) -> dict[str, int]:
        """Return {name.lower(): id} for all issue custom fields. Cached.

        Resolution order:
        1. Already-populated cache → return immediately.
        2. ``platform_custom_fields`` injected at construction → use as-is.
        3. ``GET /custom_fields.json`` → filter to ``customized_type == 'issue'``.
        Falls back to empty dict on any HTTP error so callers can proceed without
        custom field support.
        """
        if self._custom_field_cache:
            return self._custom_field_cache
        if self._platform_custom_fields:
            self._custom_field_cache = {k.lower(): int(v) for k, v in self._platform_custom_fields.items()}
            return self._custom_field_cache
        try:
            resp = self._client.get("/custom_fields.json")
            for cf in resp.get("custom_fields", []):
                if cf.get("customized_type") == "issue":
                    self._custom_field_cache[cf["name"].lower()] = int(cf["id"])
        except Exception:
            pass
        return self._custom_field_cache

    def _build_custom_fields(self, spec_change: Any) -> list[dict]:
        """Build custom_fields array for known field names (skip unknowns).

        Field IDs are deployment-specific; we only attach if the spec_change
        carries them explicitly.  Callers may sub-class and override.
        """
        # Without known integer field IDs we cannot attach custom fields safely.
        # Intentionally left as a no-op skeleton for callers to extend once
        # they know their Easy8 instance's custom-field ID scheme.
        return []


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_project(data: dict) -> PmProject:
    parent = data.get("parent")
    parent_id = parent.get("id") if isinstance(parent, dict) else None
    return PmProject(
        id=data["id"],
        name=data["name"],
        identifier=data["identifier"],
        parent_id=parent_id,
    )


def _parse_issue(data: dict) -> PmIssue:
    status_obj = data.get("status") or {}
    status_name = status_obj.get("name", "") if isinstance(status_obj, dict) else ""
    project_id = (data.get("project") or {}).get("id", 0)
    cf_map = {
        cf["name"]: cf.get("value")
        for cf in data.get("custom_fields", [])
        if isinstance(cf, dict)
    }
    # Try core PmIssue fields first (id, project_id, subject, status, agent_name, spec_path, jtbd_id)
    try:
        return PmIssue(
            id=data["id"],
            project_id=project_id,
            subject=data.get("subject", ""),
            status=status_name,
            agent_name=cf_map.get("otaman-agent"),
            spec_path=cf_map.get("spec-path"),
            jtbd_id=cf_map.get("jtbd-id"),
        )
    except TypeError:
        pass
    # Fallback: local stub PmIssue (id, subject, project_id, status, priority, assignee, custom_fields)
    priority_obj = data.get("priority") or {}
    assignee_obj = data.get("assigned_to") or {}
    return PmIssue(
        id=data["id"],
        subject=data.get("subject", ""),
        project_id=project_id,
        status=status_name,
        priority=priority_obj.get("name", "") if isinstance(priority_obj, dict) else "",
        assignee=assignee_obj.get("name") if isinstance(assignee_obj, dict) else None,
        custom_fields=cf_map,
    )


# ---------------------------------------------------------------------------
# Human roster helpers (task 4.3)
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _roster_dc


@_roster_dc
class HumanRosterEntry:
    """Minimal representation of a platform.yaml human-roster entry.

    Mirrors the fields from the human-roster spec. ``pm_user_id`` is None
    until resolved by ``resolve_pm_user_id()``.
    """

    name: str
    email: str
    roles: list
    pm_user_id: Optional[int] = None


def resolve_pm_user_id(
    adapter: "Easy8Adapter",
    roster_entry: HumanRosterEntry,
) -> Optional[int]:
    """Resolve the PM user id for *roster_entry* against Easy8's user list.

    Matching strategy (in order):
    1. Exact ``email`` match against the ``mail`` field.
    2. Case-insensitive ``name`` match against the ``name`` field.

    Returns the integer user id on the first match, or ``None`` if no user
    matches. Never raises — caller decides what to do on no-match.
    """
    try:
        users = adapter.get_users()
    except Exception:
        return None

    email_lower = roster_entry.email.lower()
    name_lower = roster_entry.name.lower()

    name_match: Optional[int] = None
    for user in users:
        # Redmine stores email under "mail" key
        if user.get("mail", "").lower() == email_lower:
            return int(user["id"])
        if name_match is None and user.get("name", "").lower() == name_lower:
            name_match = int(user["id"])

    return name_match


# ---------------------------------------------------------------------------
# MCP Tier 2 client (task 9.2)
# ---------------------------------------------------------------------------

class Easy8McpClient:
    """HTTP transport wrapper for the Easy8 MCP server endpoint.

    Used by bridge-agent for complex agent-initiated operations (fleet summaries,
    bulk transitions) that benefit from MCP tooling. NOT used in the bus-driven
    hot path — REST Tier 1 is used there.

    Auth: ``X-Redmine-API-Key`` header (same credential as REST client).
    Endpoint: ``{base_url}/mcp``
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def call_tool(self, name: str, arguments: dict) -> Any:
        """POST to ``{base_url}/mcp`` with tool name + arguments.

        Raises ``Easy8Error`` on HTTP error.
        """
        url = f"{self._base_url}/mcp"
        body = json.dumps({"tool": name, "arguments": arguments}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "X-Redmine-API-Key": self._api_key,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; otaman/1.0)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            body_str = exc.read().decode("utf-8", errors="replace")
            raise Easy8Error(exc.code, body_str) from exc


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

try:
    register_pm_adapter("easy8", Easy8Adapter)
except Exception:
    pass
