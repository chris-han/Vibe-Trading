#!/usr/bin/env python3
"""semantier API Server - RESTful API for finance research and backtesting.

V5: ReAct Agent + async /run + CORS env + SSE tool events.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac as _hmac
import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import BackgroundTasks, Body, Depends, FastAPI, File, Form, HTTPException, Query, Request, Security, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rich.console import Console
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from runtime_env import ensure_runtime_env, get_data_root, get_hermes_home, get_runs_dir, get_sessions_dir, get_swarm_runs_dir, get_uploads_dir
from src.adapters.factory import get_feishu_visualization_adapter
from src.auth.store import AuthStore, AuthUser
from src.auth.workspace import WorkspacePaths, ensure_workspace, workspace_swarm_runs_dir
from src.upload_capabilities import (
    build_upload_capabilities_payload,
    get_upload_extension,
    is_supported_upload_filename,
    supported_upload_extensions,
)
from src.ui_services import build_run_analysis, load_run_context, load_run_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# UTF-8 on Windows
import sys as _sys
for _s in ("stdout", "stderr"):
    _r = getattr(getattr(_sys, _s, None), "reconfigure", None)
    if callable(_r):
        _r(encoding="utf-8", errors="replace")

ensure_runtime_env()

from hermes_constants import reset_active_hermes_home, set_active_hermes_home

# ---------------------------------------------------------------------------
# Data root: unauthenticated runtime files live under the shared public
# workspace root at workspaces/public. Authenticated users are routed to
# workspaces/<user_id> via ensure_workspace().
# ---------------------------------------------------------------------------
_AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _AGENT_DIR.parent
_CONTAINER_FRONTEND_ROOT = Path("/app/frontend")
DATA_ROOT = get_data_root()
WORKSPACES_DIR = REPO_ROOT / "workspaces"
AUTH_CONTROL_DIR = _AGENT_DIR / ".auth"
AUTH_SESSION_COOKIE = "vt_session"
_TEMPLATE_HERMES_HOME = _AGENT_DIR / ".hermes"

RUNS_DIR = get_runs_dir(DATA_ROOT)
SESSIONS_DIR = get_sessions_dir(DATA_ROOT)
UPLOADS_DIR = get_uploads_dir(DATA_ROOT)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


def _candidate_runs_dirs(runs_dir: Optional[Path] = None) -> List[Path]:
    """Return run roots in lookup order.

    The canonical root lives under workspaces/<workspace_id>/runs.
    """
    if runs_dir is not None:
        return [runs_dir]

    return [RUNS_DIR]


def _session_run_roots(sessions_dir: Optional[Path] = None) -> List[Path]:
    """Yield runs/ subdirectories for all existing sessions (nested hierarchy)."""
    current_sessions = sessions_dir or SESSIONS_DIR
    if not current_sessions.exists():
        return []
    roots: List[Path] = []
    for session_dir in current_sessions.iterdir():
        if not session_dir.is_dir():
            continue
        runs_subdir = session_dir / "runs"
        if runs_subdir.is_dir():
            roots.append(runs_subdir)
    return roots


def _resolve_run_dir(
    run_id: str,
    *,
    runs_dir: Optional[Path] = None,
    sessions_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve a run directory across all known run roots.

    Checks the configured run root first, then falls back to scanning nested
    session run directories.
    """
    for root in _candidate_runs_dirs(runs_dir=runs_dir):
        run_dir = root / run_id
        if run_dir.exists():
            return run_dir
    for root in _session_run_roots(sessions_dir=sessions_dir):
        run_dir = root / run_id
        if run_dir.exists():
            return run_dir
    return None


def _collect_run_dirs(
    *,
    runs_dir: Optional[Path] = None,
    sessions_dir: Optional[Path] = None,
) -> List[Path]:
    """Collect unique run directories from all run roots."""
    by_id: Dict[str, Path] = {}
    all_roots = list(_candidate_runs_dirs(runs_dir=runs_dir)) + _session_run_roots(sessions_dir=sessions_dir)
    for root in all_roots:
        if not root.exists():
            continue
        for d in root.iterdir():
            if not d.is_dir() or d.name in by_id:
                continue
            by_id[d.name] = d
    return sorted(by_id.values(), key=lambda x: x.name, reverse=True)


def _resolve_upload_dir(
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    *,
    runs_dir: Optional[Path] = None,
    sessions_dir: Optional[Path] = None,
) -> Path:
    """Store user uploads under the most specific artifact scope available."""
    if run_id:
        return (runs_dir or RUNS_DIR) / run_id / "artifacts" / "uploads"

    if session_id:
        session_dir = (sessions_dir or SESSIONS_DIR) / session_id
        return session_dir / "uploads"

    raise HTTPException(status_code=400, detail="session_id or run_id is required for uploads")


console = Console()

_SPA_EXCLUDED_PREFIXES = (
    "api",
    "docs",
    "health",
    "openapi.json",
    "redoc",
    "run",
    "runs",
    "sessions",
    "skills",
    "swarm",
    "system",
    "upload",
)


class SPAStaticFiles(StaticFiles):
    """Serve SPA assets and fall back to index.html for client-side routes."""

    @staticmethod
    def _apply_html_cache_headers(response: FileResponse, path: str) -> FileResponse:
        normalized = path.strip("/")
        if normalized == "" or normalized.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
            response.headers["Vary"] = "Accept"
        return response

    async def get_response(self, path: str, scope: Any):  # pragma: no cover - exercised through ASGI mount
        try:
            response = await super().get_response(path, scope)
            return self._apply_html_cache_headers(response, path)
        except StarletteHTTPException as exc:
            normalized = path.strip("/")
            first_segment = normalized.split("/", 1)[0] if normalized else ""
            looks_like_asset = "." in Path(normalized).name if normalized else False
            if (
                exc.status_code != 404
                or scope["method"] not in {"GET", "HEAD"}
                or looks_like_asset
                or first_segment in _SPA_EXCLUDED_PREFIXES
            ):
                raise
            response = await super().get_response("index.html", scope)
            return self._apply_html_cache_headers(response, "index.html")


def _resolve_frontend_paths(current_file: Path | None = None) -> tuple[Path, Path]:
    """Prefer container-baked frontend assets over host checkout paths."""
    resolved_file = (current_file or Path(__file__)).resolve()
    inferred_repo_root = resolved_file.parent.parent
    inferred_frontend_root = inferred_repo_root / "frontend"

    configured_root = (os.getenv("VIBE_TRADING_FRONTEND_ROOT") or "").strip()
    configured_dist = (os.getenv("VIBE_TRADING_FRONTEND_DIST") or "").strip()

    frontend_root_candidates: list[Path] = []
    if configured_root:
        frontend_root_candidates.append(Path(configured_root))
    frontend_root_candidates.extend((_CONTAINER_FRONTEND_ROOT, inferred_frontend_root))

    frontend_dist_candidates: list[Path] = []
    if configured_dist:
        frontend_dist_candidates.append(Path(configured_dist))
    if configured_root:
        frontend_dist_candidates.append(Path(configured_root) / "dist")
    frontend_dist_candidates.extend((_CONTAINER_FRONTEND_ROOT / "dist", inferred_frontend_root / "dist"))

    frontend_root = next((path for path in frontend_root_candidates if path.exists()), frontend_root_candidates[0])
    frontend_dist = next((path for path in frontend_dist_candidates if path.exists()), frontend_dist_candidates[0])
    return frontend_root, frontend_dist


class Artifact(BaseModel):
    """Artifact file metadata."""

    name: str = Field(..., description="File name")
    path: str = Field(..., description="File path")
    type: str = Field(..., description="File type: csv, json, txt, etc.")
    size: int = Field(..., description="Size in bytes")
    exists: bool = Field(..., description="Whether the file exists")


class BacktestMetrics(BaseModel):
    """Backtest summary metrics."""

    model_config = {"extra": "allow"}

    final_value: float = Field(..., description="Ending portfolio value")
    total_return: float = Field(..., description="Total return")
    annual_return: float = Field(..., description="Annualized return")
    max_drawdown: float = Field(..., description="Max drawdown")
    sharpe: float = Field(..., description="Sharpe ratio")
    win_rate: float = Field(..., description="Win rate")
    trade_count: int = Field(..., description="Number of trades")


class RAGSelection(BaseModel):
    """RAG routing result."""
    selected_api: str = Field(..., description="Selected API code")
    selected_name: str = Field(..., description="Selected API name")
    selected_score: float = Field(..., description="Match score")


class RunInfo(BaseModel):
    """Compact run row for list views."""
    run_id: str
    status: str
    created_at: str
    prompt: Optional[str] = None
    total_return: Optional[float] = None
    sharpe: Optional[float] = None
    codes: List[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class RunResponse(BaseModel):
    """API response payload for a single run."""

    status: str = Field(..., description="Run status: success, failed, aborted")
    run_id: str = Field(..., description="Run identifier")
    elapsed_seconds: float = Field(..., description="Execution time in seconds")
    reason: Optional[str] = Field(None, description="Failure reason when available")
    prompt: Optional[str] = Field(None, description="Original user prompt")

    planner_output: Optional[Dict[str, Any]] = Field(None, description="Planner output")
    strategy_spec: Optional[Dict[str, Any]] = Field(None, description="Strategy specification")
    rag_selection: Optional[RAGSelection] = Field(None, description="Selected RAG metadata")

    metrics: Optional[BacktestMetrics] = Field(None, description="Backtest metrics")
    artifacts: List[Artifact] = Field(default_factory=list, description="Run artifacts")

    equity_curve: Optional[List[Dict[str, Any]]] = Field(None, description="Equity preview")
    trade_log: Optional[List[Dict[str, Any]]] = Field(None, description="Trade preview")

    artifacts_equity_csv: Optional[List[Dict[str, Any]]] = Field(None, description="Full equity rows")
    artifacts_metrics_csv: Optional[List[Dict[str, Any]]] = Field(None, description="Full metrics rows")
    artifacts_trades_csv: Optional[List[Dict[str, Any]]] = Field(None, description="Full trade rows")

    run_directory: str = Field(..., description="Run directory path")
    run_stage: Optional[str] = Field(None, description="UI-facing run stage")
    run_context: Optional[Dict[str, Any]] = Field(None, description="Normalized request context")
    price_series: Optional[Dict[str, List[Dict[str, Any]]]] = Field(None, description="Grouped OHLC series")
    indicator_series: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]] = Field(
        None,
        description="Grouped indicator overlays",
    )
    trade_markers: Optional[List[Dict[str, Any]]] = Field(None, description="Trade markers for charts")
    run_logs: Optional[List[Dict[str, Any]]] = Field(None, description="Structured stdout/stderr lines")
    report_markdown: Optional[str] = Field(None, description="Saved narrative report for research-only runs")


class HealthResponse(BaseModel):
    """Health check payload."""
    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    timestamp: str = Field(..., description="Server timestamp")


# ---- V4 Session Models ----

class CreateSessionRequest(BaseModel):
    """Create session request body."""
    title: str = Field("", description="Session title")
    config: Optional[Dict[str, Any]] = Field(None, description="Session config")


class SessionResponse(BaseModel):
    """Session record."""
    session_id: str
    title: str
    status: str
    channel: Optional[str] = None
    created_at: str
    updated_at: str
    last_attempt_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    """Send chat message: natural-language strategy description."""
    content: str = Field(..., description="Natural language strategy description", min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    """Stored chat message."""
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str
    linked_attempt_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SessionEventResponse(BaseModel):
    """Canonical session event."""
    event_id: str
    session_id: str
    attempt_id: Optional[str] = None
    event_type: str
    timestamp: str
    role: Optional[str] = None
    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool: Optional[str] = None
    tool_call_id: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TrajectoryConversationItem(BaseModel):
    """One ShareGPT-style conversation item."""
    from_: str = Field(..., alias="from")
    value: str

    model_config = {"populate_by_name": True}


class SessionTrajectoryResponse(BaseModel):
    """Training-ready Atropos trajectory export."""
    session_id: str
    title: str
    source_file: str
    trajectory: Dict[str, Any]


class BatchDeleteSessionsRequest(BaseModel):
    """Delete multiple sessions in one request."""
    session_ids: List[str] = Field(..., min_length=1)



# ============================================================================
# FastAPI Application
# ============================================================================

class ForwardedHeadersMiddleware(BaseHTTPMiddleware):
    """Handle X-Forwarded-Proto and X-Forwarded-Host for proxy environments."""
    async def dispatch(self, request: Request, call_next):
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        forwarded_host = request.headers.get("X-Forwarded-Host")
        if forwarded_proto:
            request.scope["scheme"] = forwarded_proto
        if forwarded_host:
            # Reconstruct host and port from header
            host_parts = forwarded_host.split(":", 1)
            host = host_parts[0]
            port = int(host_parts[1]) if len(host_parts) > 1 else (443 if forwarded_proto == "https" else 80)
            request.scope["server"] = (host, port)
            # Update headers to keep things consistent
            request.scope["headers"] = [
                (b"host", forwarded_host.encode("latin-1")) if k == b"host" else (k, v)
                for k, v in request.scope.get("headers", [])
            ]
        return await call_next(request)


app = FastAPI(
    title="semantier API",
    description="semantier API: natural-language finance research, backtesting, and agents workflows",
    version="5.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(ForwardedHeadersMiddleware)

# CORS: override with CORS_ORIGINS (comma-separated)
_CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8000,"
    "http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:8000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API Key Authentication
# ============================================================================

_security = HTTPBearer(auto_error=False)
_API_KEY = os.getenv("API_AUTH_KEY")
_auth_store: AuthStore | None = None
_auth_store_path: Path | None = None
_DEFAULT_FEISHU_OAUTH_REDIRECT_URI = "https://app.semantier.com/auth/feishu/callback"


@dataclass
class RequestContext:
    authenticated: bool
    user: AuthUser | None
    workspace: WorkspacePaths


def _get_env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean env var with tolerant support for common truthy values."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


def _feishu_oauth_enabled() -> bool:
    configured = os.getenv("FEISHU_OAUTH_ENABLED")
    if configured is not None and configured.strip():
        return _get_env_bool("FEISHU_OAUTH_ENABLED")
    # Fallback to checking mandatory variables: app_id, secret, session_secret.
    # redirect_uri is also usually required but can sometimes be inferred.
    app_id = (os.getenv("FEISHU_OAUTH_APP_ID") or os.getenv("FEISHU_APP_ID") or "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    session_secret = os.getenv("FEISHU_SESSION_SECRET", "").strip()
    redirect_uri = _get_feishu_oauth_redirect_uri()
    return all([app_id, app_secret, session_secret, redirect_uri])


def _get_feishu_oauth_redirect_uri() -> str:
    """Return the configured Feishu OAuth redirect URI or the production default."""
    return (os.getenv("FEISHU_OAUTH_REDIRECT_URI") or "").strip() or _DEFAULT_FEISHU_OAUTH_REDIRECT_URI


def _get_auth_store() -> AuthStore:
    global _auth_store, _auth_store_path
    db_path = AUTH_CONTROL_DIR / "auth.sqlite3"
    if _auth_store is None or _auth_store_path != db_path:
        _auth_store = AuthStore(db_path)
        _auth_store_path = db_path
    return _auth_store


def _get_public_workspace() -> WorkspacePaths:
    slug = (os.getenv("DEFAULT_WORKSPACE_SLUG") or "public").strip() or "public"
    return ensure_workspace(WORKSPACES_DIR, slug, _TEMPLATE_HERMES_HOME, workspace_slug=slug)


def _b64url_encode(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    import base64

    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _sign_auth_session(user: AuthUser) -> str:
    secret = os.getenv("FEISHU_SESSION_SECRET", "").encode("utf-8")
    if not secret:
        raise RuntimeError("FEISHU_SESSION_SECRET is required when Feishu OAuth is enabled")
    payload = json.dumps(
        {"user_id": user.user_id, "workspace_slug": user.workspace_slug},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = _b64url_encode(_hmac.new(secret, payload, hashlib.sha256).digest())
    return f"{_b64url_encode(payload)}.{signature}"


def _read_auth_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    secret = os.getenv("FEISHU_SESSION_SECRET", "").encode("utf-8")
    if not secret:
        return None
    payload_b64, signature = token.split(".", 1)
    try:
        payload = _b64url_decode(payload_b64)
    except Exception:
        return None
    expected = _b64url_encode(_hmac.new(secret, payload, hashlib.sha256).digest())
    if not _hmac.compare_digest(signature, expected):
        return None
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except Exception:
        return None
    return decoded if isinstance(decoded, dict) else None


def _resolve_request_context(request: Request, *, require_login: bool = False) -> RequestContext:
    if _feishu_oauth_enabled():
        session_payload = _read_auth_session(request.cookies.get(AUTH_SESSION_COOKIE))
        if session_payload:
            user = _get_auth_store().get_user_by_id(str(session_payload.get("user_id") or ""))
            if user is not None:
                workspace = ensure_workspace(
                    WORKSPACES_DIR,
                    user.user_id,
                    _TEMPLATE_HERMES_HOME,
                    workspace_slug=user.workspace_slug,
                )
                return RequestContext(authenticated=True, user=user, workspace=workspace)
        if require_login:
            raise HTTPException(status_code=401, detail="Authentication required")
    return RequestContext(authenticated=False, user=None, workspace=_get_public_workspace())


async def require_auth(
    request: Request,
    cred: HTTPAuthorizationCredentials = Security(_security),
) -> None:
    """Validate Bearer token against API_AUTH_KEY environment variable.

    If API_AUTH_KEY is not set, authentication is skipped (dev mode).
    Only write endpoints (POST/PUT/DELETE/PATCH) use this dependency.

    Args:
        cred: HTTP Bearer credentials extracted from the Authorization header.

    Raises:
        HTTPException: 401 when API_AUTH_KEY is set but the token is missing or wrong.
    """
    if _feishu_oauth_enabled():
        _resolve_request_context(request, require_login=True)
        return
    if not _API_KEY:
        return
    if not cred or cred.credentials != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ============================================================================
# Workflow Factory
# ============================================================================

# ============================================================================
# Helper Functions
# ============================================================================

def _load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON from disk if present."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _load_csv_to_dict(path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load CSV rows into a list of dictionaries."""
    try:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
        if limit is not None:
            rows = rows[:limit]
        return rows
    except Exception:
        return []


def _get_env_float(name: str, default: float) -> float:
    """Parse a float env var while tolerating empty or invalid values."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value.strip() or default)
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "Invalid float for %s=%r; using default %s",
            name,
            raw_value,
            default,
        )
        return default


_SKILL_SCAN_EXCLUDED_DIRS = frozenset({".git", ".github", ".hub"})


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_skill_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        raw = str(item).strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        normalized.append(raw)
    return normalized


def _parse_skill_frontmatter(skill_file: Path) -> tuple[dict[str, Any], str]:
    text = skill_file.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        _, rest = text.split("---\n", 1)
        if "\n---\n" in rest:
            frontmatter_text, body = rest.split("\n---\n", 1)
            try:
                parsed = yaml.safe_load(frontmatter_text) or {}
            except Exception:
                parsed = {}
            return parsed if isinstance(parsed, dict) else {}, body
    return {}, text


def _first_skill_body_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _load_workspace_skill_settings(hermes_home: Path) -> tuple[list[Path], set[str]]:
    config = _load_yaml_mapping(hermes_home / "config.yaml")
    skills_cfg = config.get("skills")
    if not isinstance(skills_cfg, dict):
        return [], set()

    external_dirs: list[Path] = []
    seen_dirs: set[Path] = set()
    for entry in _normalize_skill_string_list(skills_cfg.get("external_dirs")):
        expanded = Path(os.path.expandvars(os.path.expanduser(entry))).resolve()
        if expanded in seen_dirs or not expanded.is_dir():
            continue
        seen_dirs.add(expanded)
        external_dirs.append(expanded)

    disabled = set(_normalize_skill_string_list(skills_cfg.get("disabled")))
    return external_dirs, disabled


def _skill_source_metadata(skill_dir: Path, workspace_skills_dir: Path) -> dict[str, Any]:
    hermes_builtin_root = (REPO_ROOT / "hermes-agent" / "skills").resolve()
    app_shared_root = (REPO_ROOT / "agent" / "src" / "skills").resolve()

    if _path_is_within(skill_dir, workspace_skills_dir):
        return {
            "sourceTier": "workspace",
            "sourceLabel": "Workspace",
            "author": "Workspace",
            "icon": "✍️",
            "builtin": False,
            "canEdit": True,
            "canUninstall": True,
            "canModify": True,
        }

    if _path_is_within(skill_dir, app_shared_root):
        return {
            "sourceTier": "application",
            "sourceLabel": "Application Shared",
            "author": "Semantier",
            "icon": "🧩",
            "builtin": False,
            "canEdit": False,
            "canUninstall": False,
            "canModify": False,
        }

    if _path_is_within(skill_dir, hermes_builtin_root):
        return {
            "sourceTier": "builtin",
            "sourceLabel": "Hermes Built-in",
            "author": "Hermes",
            "icon": "🛠️",
            "builtin": True,
            "canEdit": False,
            "canUninstall": False,
            "canModify": False,
        }

    return {
        "sourceTier": "external",
        "sourceLabel": "External Shared",
        "author": "External",
        "icon": "🧩",
        "builtin": False,
        "canEdit": False,
        "canUninstall": False,
        "canModify": False,
    }


def _infer_skill_category(frontmatter: dict[str, Any], skill_dir: Path, source_root: Path) -> str:
    direct = str(frontmatter.get("category") or "").strip()
    if direct:
        return direct
    try:
        relative_parts = skill_dir.relative_to(source_root).parts
    except ValueError:
        return "Productivity"
    if len(relative_parts) >= 2:
        return relative_parts[-2].replace("-", " ").title()
    if relative_parts:
        return relative_parts[0].replace("-", " ").title()
    return "Productivity"


def _build_workspace_skill_inventory(workspace: WorkspacePaths) -> list[dict[str, Any]]:
    workspace_skills_dir = (workspace.hermes_home / "skills").resolve()
    external_dirs, disabled = _load_workspace_skill_settings(workspace.hermes_home)

    scan_roots: list[Path] = []
    if workspace_skills_dir.exists():
        scan_roots.append(workspace_skills_dir)
    scan_roots.extend(external_dirs)

    inventory: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for scan_root in scan_roots:
        for skill_file in sorted(scan_root.rglob("SKILL.md")):
            if any(part in _SKILL_SCAN_EXCLUDED_DIRS for part in skill_file.parts):
                continue

            skill_dir = skill_file.parent
            try:
                frontmatter, body = _parse_skill_frontmatter(skill_file)
            except Exception:
                continue

            name = str(frontmatter.get("name") or skill_dir.name).strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            description = str(frontmatter.get("description") or "").strip() or _first_skill_body_line(body)
            tags = _normalize_skill_string_list(frontmatter.get("tags"))
            triggers = _normalize_skill_string_list(frontmatter.get("triggers"))
            metadata = _skill_source_metadata(skill_dir, workspace_skills_dir)

            file_count = 0
            try:
                file_count = sum(1 for child in skill_dir.rglob("*") if child.is_file())
            except Exception:
                file_count = 1

            inventory.append(
                {
                    "id": name,
                    "slug": name,
                    "name": name,
                    "description": description,
                    "author": str(frontmatter.get("author") or metadata["author"]),
                    "triggers": triggers,
                    "tags": tags,
                    "homepage": None,
                    "category": _infer_skill_category(frontmatter, skill_dir, scan_root),
                    "icon": metadata["icon"],
                    "content": "",
                    "fileCount": file_count,
                    "sourcePath": str(skill_dir),
                    "installed": True,
                    "enabled": name not in disabled,
                    "builtin": metadata["builtin"],
                    "sourceTier": metadata["sourceTier"],
                    "sourceLabel": metadata["sourceLabel"],
                    "canEdit": metadata["canEdit"],
                    "canUninstall": metadata["canUninstall"],
                    "canModify": metadata["canModify"],
                    "security": {
                        "level": "safe",
                        "flags": [],
                        "score": 0,
                    },
                }
            )

    source_order = {"workspace": 0, "application": 1, "builtin": 2, "external": 3}
    inventory.sort(key=lambda item: (source_order.get(str(item.get("sourceTier")), 99), str(item.get("name") or "")))
    return inventory


def _build_workspace_tool_inventory() -> list[dict[str, Any]]:
    from hermes_cli.tools_config import _get_effective_configurable_toolsets, _get_platform_tools, _toolset_has_keys
    from hermes_cli.web_server import load_config
    from toolsets import resolve_toolset

    config = load_config()
    enabled_toolsets = _get_platform_tools(
        config,
        "cli",
        include_default_mcp_servers=False,
    )

    inventory: list[dict[str, Any]] = []
    for name, label, description in _get_effective_configurable_toolsets():
        try:
            tools = sorted(set(resolve_toolset(name)))
        except Exception:
            tools = []

        source_tier = "application" if name == "vibe_trading" else "builtin"
        source_label = "Application Shared" if source_tier == "application" else "Hermes Built-in"
        inventory.append(
            {
                "id": name,
                "name": name,
                "label": label,
                "description": description,
                "tools": tools,
                "enabled": name in enabled_toolsets,
                "available": name in enabled_toolsets,
                "configured": _toolset_has_keys(name, config),
                "sourceTier": source_tier,
                "sourceLabel": source_label,
                "builtin": source_tier == "builtin",
                "canModify": False,
            }
        )

    source_order = {"application": 0, "builtin": 1}
    inventory.sort(key=lambda item: (source_order.get(str(item.get("sourceTier")), 99), str(item.get("label") or item.get("name") or "")))
    return inventory


def _install_skill_into_workspace(
    workspace: WorkspacePaths,
    *,
    identifier: str,
    category: str = "",
    force: bool = False,
) -> dict[str, Any]:
    from hermes_cli.web_server import _install_skill_from_hub

    token = set_active_hermes_home(workspace.hermes_home)
    try:
        result = _install_skill_from_hub(
            identifier,
            category=category,
            force=force,
            invalidate_cache=True,
        )
    finally:
        reset_active_hermes_home(token)

    install_path = str(result.get("install_path") or "").strip()
    if install_path:
        result["absolute_install_path"] = str((workspace.hermes_home / "skills" / install_path).resolve())
    result["sourceTier"] = "workspace"
    result["sourceLabel"] = "Workspace"
    return result


def _toggle_workspace_skill(
    workspace: WorkspacePaths,
    *,
    name: str,
    enabled: bool,
) -> dict[str, Any]:
    from hermes_cli.skills_config import get_disabled_skills, save_disabled_skills
    from hermes_cli.web_server import load_config

    token = set_active_hermes_home(workspace.hermes_home)
    try:
        config = load_config()
        disabled = get_disabled_skills(config)
        if enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        save_disabled_skills(config, disabled)
    finally:
        reset_active_hermes_home(token)

    return {"ok": True, "name": name, "enabled": enabled}


def _uninstall_workspace_skill(
    workspace: WorkspacePaths,
    *,
    name: str,
) -> dict[str, Any]:
    from hermes_cli.web_server import _uninstall_skill_from_hub

    token = set_active_hermes_home(workspace.hermes_home)
    try:
        return _uninstall_skill_from_hub(name, invalidate_cache=True)
    finally:
        reset_active_hermes_home(token)



def _build_response_from_run_dir(run_dir: Path, elapsed: float, *, include_analysis: bool = False) -> RunResponse:
    """Build a run response from a persisted run directory."""
    run_id = run_dir.name

    response = RunResponse(
        status="unknown",
        run_id=run_id,
        elapsed_seconds=elapsed,
        run_directory=str(run_dir),
    )

    request_data = _load_json_file(run_dir / "req.json") or {}
    prompt = str(request_data.get("prompt") or "").strip()
    if prompt:
        response.prompt = prompt

    report_markdown = load_run_report(run_dir)
    if report_markdown:
        response.report_markdown = report_markdown

    state_data = _load_json_file(run_dir / "state.json")
    if state_data:
        state_status = str(state_data.get("status") or "").lower()
        if state_status == "success":
            response.status = "success"
        elif state_status == "failed":
            response.status = "failed"
            response.reason = state_data.get("reason", "")
        else:
            response.status = state_status or "unknown"
    else:
        response.status = "unknown"

    planner_path = run_dir / "planner_output.json"
    response.planner_output = _load_json_file(planner_path)

    design_path = run_dir / "design_spec.json"
    response.strategy_spec = _load_json_file(design_path)

    rag_path = run_dir / "rag_metadata.json"
    rag_data = _load_json_file(rag_path)
    if rag_data:
        response.rag_selection = RAGSelection(
            selected_api=rag_data.get("selected_api") or rag_data.get("api_code", ""),
            selected_name=rag_data.get("selected_name") or rag_data.get("api_name", ""),
            selected_score=float(rag_data.get("selected_score") or rag_data.get("score", 0.0)),
        )

    metrics_path = run_dir / "artifacts" / "metrics.csv"
    if metrics_path.exists():
        metrics_dict_list = _load_csv_to_dict(metrics_path, limit=1)
        if metrics_dict_list:
            row = metrics_dict_list[0]
            try:
                # Pass ALL CSV columns to BacktestMetrics (extra="allow")
                parsed: dict = {}
                for k, v in row.items():
                    if not k or not v:
                        continue
                    try:
                        parsed[k] = int(float(v)) if k == "trade_count" or k == "max_consecutive_loss" else float(v)
                    except (ValueError, TypeError):
                        continue
                if "final_value" in parsed:
                    response.metrics = BacktestMetrics(**parsed)
            except (ValueError, TypeError):
                pass


    artifacts_dir = run_dir / "artifacts"
    if artifacts_dir.exists():
        for file_path in artifacts_dir.iterdir():
            if file_path.is_file():
                file_type = file_path.suffix.lstrip(".")
                response.artifacts.append(
                    Artifact(
                        name=file_path.name,
                        path=str(file_path),
                        type=file_type if file_type else "unknown",
                        size=file_path.stat().st_size,
                        exists=True,
                    )
                )

    equity_path = run_dir / "artifacts" / "equity.csv"
    if equity_path.exists():
        response.artifacts_equity_csv = _load_csv_to_dict(equity_path)

    metrics_csv_path = run_dir / "artifacts" / "metrics.csv"
    if metrics_csv_path.exists():
        response.artifacts_metrics_csv = _load_csv_to_dict(metrics_csv_path)

    trades_path = run_dir / "artifacts" / "trades.csv"
    if trades_path.exists():
        response.artifacts_trades_csv = _load_csv_to_dict(trades_path)

    if response.artifacts_equity_csv:
        filtered_equity = []
        for row in response.artifacts_equity_csv[:1000]:
            filtered_row: Dict[str, Any] = {}
            if "timestamp" in row:
                filtered_row["time"] = row["timestamp"]
            if "equity" in row:
                filtered_row["equity"] = row["equity"]
            if "drawdown" in row:
                filtered_row["drawdown"] = row["drawdown"]
            filtered_equity.append(filtered_row)
        response.equity_curve = filtered_equity

    if response.artifacts_trades_csv:
        response.trade_log = response.artifacts_trades_csv[:500]

    if include_analysis:
        analysis = build_run_analysis(run_dir)
        response.run_stage = analysis.get("run_stage")
        response.run_context = analysis.get("run_context")
        response.price_series = analysis.get("price_series")
        response.indicator_series = analysis.get("indicator_series")
        response.trade_markers = analysis.get("trade_markers")
        response.run_logs = analysis.get("run_logs")

    return response


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/runs/{run_id}/code")
async def get_run_code(run_id: str, request: Request):
    """Return strategy source files for a run.

    Args:
        run_id: Run identifier.

    Returns:
        Map filename -> source text.
    """
    ctx = _resolve_request_context(request, require_login=False)
    resolved_run_dir = _resolve_run_dir(
        run_id,
        runs_dir=ctx.workspace.runs_dir,
        sessions_dir=ctx.workspace.sessions_dir,
    )
    run_dir = resolved_run_dir / "code" if resolved_run_dir else None
    if run_dir is None or not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Code directory for run {run_id} not found")
    result = {}
    for f in ["signal_engine.py"]:
        p = run_dir / f
        if p.exists():
            result[f] = p.read_text(encoding="utf-8")
    return result


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run_result(run_id: str, request: Request):
    """Fetch full details for a historical run by ``run_id``."""
    # Browser page-refresh sends Accept: text/html — serve the SPA instead of JSON
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept and _FRONTEND_DIST is not None:
        resp = FileResponse(_FRONTEND_DIST / "index.html")
        resp.headers["Vary"] = "Accept"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    ctx = _resolve_request_context(request, require_login=False)
    run_dir = _resolve_run_dir(
        run_id,
        runs_dir=ctx.workspace.runs_dir,
        sessions_dir=ctx.workspace.sessions_dir,
    )

    if run_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found"
        )

    response = _build_response_from_run_dir(run_dir, elapsed=0.0, include_analysis=True)

    return response


@app.get("/runs", response_model=List[RunInfo])
async def list_runs(request: Request, limit: int = 20):
    """List recent runs with summary fields."""
    limit = min(max(1, limit), 100)
    ctx = _resolve_request_context(request, require_login=False)
    run_dirs = _collect_run_dirs(
        runs_dir=ctx.workspace.runs_dir,
        sessions_dir=ctx.workspace.sessions_dir,
    )

    if not run_dirs:
        return []
    
    results = []
    for d in run_dirs[:limit]:
        run_id = d.name
        
        # Status from state.json or artifacts
        status_val = "unknown"
        state_file = _load_json_file(d / "state.json")
        if state_file:
            status_val = str(state_file.get("status") or "unknown").lower()
        elif (d / "artifacts" / "equity.csv").exists():
            status_val = "success"
        elif (d / "review_report.json").exists():
            status_val = "success"
        
        # Parse created_at from run_id (YYYYMMDD_HHMMSS or run_YYYYMMDD_HHMMSS)
        created_at = "Unknown"
        if run_id.startswith("run_"):
            parts = run_id.split('_')
            if len(parts) >= 3:
                d_str, t_str = parts[1], parts[2]
                if len(d_str) == 8 and len(t_str) == 6:
                    created_at = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]} {t_str[:2]}:{t_str[2:4]}:{t_str[4:6]}"
        elif "_" in run_id:
            parts = run_id.split('_')
            if len(parts) >= 2:
                d_str, t_str = parts[0], parts[1]
                if len(d_str) == 8 and len(t_str) == 6:
                    created_at = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]} {t_str[:2]}:{t_str[2:4]}:{t_str[4:6]}"
        
        if created_at == "Unknown":
            mtime = datetime.fromtimestamp(d.stat().st_mtime)
            created_at = mtime.strftime("%Y-%m-%d %H:%M:%S")
        
        prompt = None
        req_file = d / "req.json"
        planner_file = d / "planner_output.json"
        if req_file.exists():
            try:
                req_data = json.loads(req_file.read_text(encoding="utf-8"))
                prompt = req_data.get("prompt")
            except: pass
        
        if not prompt and planner_file.exists():
            try:
                planner_data = json.loads(planner_file.read_text(encoding="utf-8"))
                prompt = planner_data.get("user_goal") or planner_data.get("goal")
            except: pass
            
        if not prompt:
            prompt_file = d / "user_prompt.txt"
            if prompt_file.exists():
                prompt = prompt_file.read_text(encoding="utf-8").strip()
        
        total_return = None
        sharpe = None
        metrics_file = d / "artifacts" / "metrics.csv"
        if metrics_file.exists():
            try:
                import csv
                with open(metrics_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        total_return = float(row.get('total_return', 0) or 0)
                        sharpe = float(row.get('sharpe', 0) or 0)
                        break
            except:
                pass
        
        run_context = load_run_context(d)
        results.append(RunInfo(
            run_id=run_id,
            status=status_val,
            created_at=created_at,
            prompt=prompt or "Manual Analysis",
            total_return=total_return,
            sharpe=sharpe,
            codes=run_context.get("codes") or [],
            start_date=run_context.get("start_date"),
            end_date=run_context.get("end_date"),
        ))
        
    return results


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Liveness probe."""
    return HealthResponse(
        status="healthy",
        service="semantier API",
        timestamp=datetime.now().isoformat()
    )


def _terminate_current_process() -> None:
    """Stop the current API process after the response has been sent."""
    time.sleep(0.25)
    os.kill(os.getpid(), signal.SIGTERM)


@app.post("/system/shutdown", dependencies=[Depends(require_auth)])
async def shutdown_local_api(background_tasks: BackgroundTasks, request: Request):
    """Shut down the local API server when requested from loopback clients."""
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")

    background_tasks.add_task(_terminate_current_process)
    return {
        "status": "shutting-down",
        "service": "semantier API",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/skills")
async def list_skills():
    """List registered skills (name and description)."""
    import re as _re
    skills_dir = Path(__file__).resolve().parent / "src" / "skills"
    result = []
    if skills_dir.exists():
        for p in sorted(skills_dir.iterdir()):
            if not p.is_dir():
                continue
            md = p / "SKILL.md"
            if not md.exists():
                continue
            text = md.read_text(encoding="utf-8", errors="ignore")
            m = _re.search(r"^description:\s*(.+)$", text, _re.MULTILINE)
            desc = m.group(1).strip().strip('"') if m else ""
            result.append({"name": p.name, "description": desc})
    return result


@app.get("/api")
async def api_info():
    """Service metadata."""
    return {
        "service": "semantier API",
        "version": "5.0.0",
        "docs": "/docs",
        "health": "/health",
    }


class SystemSkillInstallRequest(BaseModel):
    identifier: str = Field(..., min_length=1)
    category: str = Field(default="")
    force: bool = Field(default=False)


class SystemSkillToggleRequest(BaseModel):
    name: str = Field(..., min_length=1)
    enabled: bool


class SystemSkillUninstallRequest(BaseModel):
    name: str = Field(..., min_length=1)


@app.get("/system/paths")
async def system_paths(request: Request):
    """Return backend-owned runtime paths used by this API process."""
    hermes_home = get_hermes_home()
    ctx = _resolve_request_context(request, require_login=False)
    return {
        "hermesHome": str(hermes_home),
        "dataRoot": str(DATA_ROOT),
        "sessionsDir": str(SESSIONS_DIR),
        "runsDir": str(RUNS_DIR),
        "uploadsDir": str(UPLOADS_DIR),
        "authenticated": ctx.authenticated,
        "currentWorkspaceId": ctx.workspace.workspace_id,
        "currentWorkspaceSlug": ctx.workspace.workspace_slug,
        "currentWorkspaceRoot": str(ctx.workspace.workspace_root),
        "currentHermesHome": str(ctx.workspace.hermes_home),
        "currentSessionsDir": str(ctx.workspace.sessions_dir),
        "currentRunsDir": str(ctx.workspace.runs_dir),
        "currentUploadsDir": str(ctx.workspace.uploads_dir),
    }


@app.get("/system/skills")
async def system_skills(request: Request):
    """Return the installed skill inventory for the active workspace.

    This endpoint is Semantier-owned and augments Hermes skill discovery with
    source-tier and mutability metadata for the workspace UI.
    """
    ctx = _resolve_request_context(request, require_login=False)
    skills = _build_workspace_skill_inventory(ctx.workspace)
    categories = sorted({str(skill.get("category") or "") for skill in skills if skill.get("category")})
    return {
        "skills": skills,
        "total": len(skills),
        "page": 1,
        "categories": categories,
        "workspaceId": ctx.workspace.workspace_id,
        "workspaceSlug": ctx.workspace.workspace_slug,
    }


@app.post("/system/skills/install", dependencies=[Depends(require_auth)])
async def system_install_skill(request: Request, body: SystemSkillInstallRequest = Body(...)):
    """Install a marketplace skill directly into the active workspace Hermes home."""
    ctx = _resolve_request_context(request, require_login=_feishu_oauth_enabled())
    return _install_skill_into_workspace(
        ctx.workspace,
        identifier=body.identifier.strip(),
        category=body.category.strip(),
        force=body.force,
    )


@app.put("/system/skills/toggle", dependencies=[Depends(require_auth)])
async def system_toggle_skill(request: Request, body: SystemSkillToggleRequest = Body(...)):
    """Toggle skill enabled state inside the active workspace Hermes home."""
    ctx = _resolve_request_context(request, require_login=_feishu_oauth_enabled())
    return _toggle_workspace_skill(
        ctx.workspace,
        name=body.name.strip(),
        enabled=body.enabled,
    )


@app.post("/system/skills/uninstall", dependencies=[Depends(require_auth)])
async def system_uninstall_skill(request: Request, body: SystemSkillUninstallRequest = Body(...)):
    """Uninstall a hub-installed workspace skill from the active workspace Hermes home."""
    ctx = _resolve_request_context(request, require_login=_feishu_oauth_enabled())
    return _uninstall_workspace_skill(
        ctx.workspace,
        name=body.name.strip(),
    )


@app.get("/system/tools")
async def system_tools(request: Request):
    """Return toolset inventory with Semantier source-tier metadata."""
    ctx = _resolve_request_context(request, require_login=False)
    tools = _build_workspace_tool_inventory()
    return {
        "tools": tools,
        "total": len(tools),
        "workspaceId": ctx.workspace.workspace_id,
        "workspaceSlug": ctx.workspace.workspace_slug,
    }


class AuthUserResponse(BaseModel):
    user_id: str
    name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    feishu_open_id: str
    workspace_slug: str


class AuthMeResponse(BaseModel):
    authenticated: bool
    feishu_oauth_enabled: bool
    user: Optional[AuthUserResponse] = None
    workspace_slug: Optional[str] = None


class UploadCapabilitiesResponse(BaseModel):
    allowed_extensions: List[str]
    accept: str
    max_upload_size_bytes: int
    max_upload_size_mb: int
    types_summary: str


class UploadBatchResponse(BaseModel):
    status: str
    files: List[Dict[str, str]]


def _resolve_effective_upload_scope(
    request: Request,
    session_id: Optional[str],
    run_id: Optional[str],
) -> tuple[Optional[str], Optional[str], Path, Path]:
    effective_session_id = (
        session_id
        or request.query_params.get("session_id")
        or request.headers.get("x-session-id")
    )
    effective_run_id = (
        run_id
        or request.query_params.get("run_id")
        or request.headers.get("x-run-id")
    )
    ctx = _resolve_request_context(request, require_login=False)
    active_runs_dir = ctx.workspace.runs_dir if _feishu_oauth_enabled() else RUNS_DIR
    active_sessions_dir = ctx.workspace.sessions_dir if _feishu_oauth_enabled() else SESSIONS_DIR
    return effective_session_id, effective_run_id, active_runs_dir, active_sessions_dir


def _resolve_upload_target_dir(
    *,
    request: Request,
    session_id: Optional[str],
    run_id: Optional[str],
) -> tuple[Path, Optional[str], Optional[str], Path, Path]:
    effective_session_id, effective_run_id, active_runs_dir, active_sessions_dir = _resolve_effective_upload_scope(
        request,
        session_id,
        run_id,
    )

    try:
        target_dir = _resolve_upload_dir(
            session_id=effective_session_id,
            run_id=effective_run_id,
            runs_dir=active_runs_dir,
            sessions_dir=active_sessions_dir,
        )
    except HTTPException as exc:
        if exc.status_code == 400 and "session_id or run_id" in str(exc.detail):
            raise HTTPException(
                status_code=400,
                detail=(
                    "session_id or run_id is required for uploads. "
                    "Provide one via multipart form field, query param, or "
                    "x-session-id/x-run-id header."
                ),
            )
        raise

    if _feishu_oauth_enabled() and effective_session_id and not (active_sessions_dir / effective_session_id).exists():
        raise HTTPException(status_code=404, detail=f"Session {effective_session_id} not found")
    if _feishu_oauth_enabled() and effective_run_id and _resolve_run_dir(
        effective_run_id,
        runs_dir=active_runs_dir,
        sessions_dir=active_sessions_dir,
    ) is None:
        raise HTTPException(status_code=404, detail=f"Run {effective_run_id} not found")

    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir, effective_session_id, effective_run_id, active_runs_dir, active_sessions_dir


async def _store_uploaded_file(file: UploadFile, target_dir: Path) -> Dict[str, str]:
    file_extension = get_upload_extension(file.filename)
    if not is_supported_upload_filename(file.filename) or not file_extension:
        supported_list = ", ".join(supported_upload_extensions())
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed extensions: {supported_list}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (limit {MAX_UPLOAD_SIZE // (1024 * 1024)} MB)",
        )

    safe_name = f"{uuid.uuid4().hex}{file_extension}"
    dest = target_dir / safe_name
    dest.write_bytes(content)
    return {
        "status": "ok",
        "file_path": str(dest.resolve()),
        "filename": file.filename or safe_name,
    }


@app.get("/auth/me", response_model=AuthMeResponse)
async def auth_me(request: Request):
    ctx = _resolve_request_context(request, require_login=False)
    if not ctx.authenticated or ctx.user is None:
        return AuthMeResponse(
            authenticated=False,
            feishu_oauth_enabled=_feishu_oauth_enabled(),
            workspace_slug=ctx.workspace.workspace_slug,
        )
    return AuthMeResponse(
        authenticated=True,
        feishu_oauth_enabled=_feishu_oauth_enabled(),
        workspace_slug=ctx.workspace.workspace_slug,
        user=AuthUserResponse(
            user_id=ctx.user.user_id,
            name=ctx.user.name,
            email=ctx.user.email,
            avatar_url=ctx.user.avatar_url,
            feishu_open_id=ctx.user.feishu_open_id,
            workspace_slug=ctx.user.workspace_slug,
        ),
    )


@app.get("/capabilities/uploads", response_model=UploadCapabilitiesResponse)
async def upload_capabilities():
    return UploadCapabilitiesResponse(**build_upload_capabilities_payload(MAX_UPLOAD_SIZE))


@app.get("/auth/feishu/login")
async def auth_feishu_login(request: Request):
    if not _feishu_oauth_enabled():
        raise HTTPException(status_code=404, detail="Feishu OAuth is not enabled")
    app_id = (os.getenv("FEISHU_OAUTH_APP_ID") or os.getenv("FEISHU_APP_ID") or "").strip()
    redirect_uri = _get_feishu_oauth_redirect_uri()

    if not app_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="Feishu OAuth is not fully configured")
    state = uuid.uuid4().hex
    url = (
        f"{_FEISHU_BASE_URL}/open-apis/authen/v1/authorize"
        f"?app_id={app_id}&redirect_uri={redirect_uri}&response_type=code&state={state}"
    )
    return RedirectResponse(url=url, status_code=307)


@app.get("/auth/feishu/callback")
async def auth_feishu_callback(request: Request, code: str, state: Optional[str] = None):
    if not _feishu_oauth_enabled():
        raise HTTPException(status_code=404, detail="Feishu OAuth is not enabled")

    redirect_uri = _get_feishu_oauth_redirect_uri()

    token_data = _feishu_exchange_oauth_code(code, redirect_uri=redirect_uri)
    profile = _feishu_fetch_user_profile(str(token_data.get("access_token") or ""))
    user = _get_auth_store().upsert_feishu_user(
        open_id=str(profile.get("open_id") or ""),
        union_id=profile.get("union_id"),
        name=str(profile.get("name") or profile.get("en_name") or profile.get("email") or profile.get("open_id") or "user"),
        email=profile.get("email"),
        avatar_url=profile.get("avatar_url"),
    )
    ensure_workspace(
        WORKSPACES_DIR,
        user.user_id,
        _TEMPLATE_HERMES_HOME,
        workspace_slug=user.workspace_slug,
    )
    response = RedirectResponse(url="/", status_code=307)
    response.set_cookie(
        AUTH_SESSION_COOKIE,
        _sign_auth_session(user),
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return response


@app.post("/auth/logout")
async def auth_logout():
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(AUTH_SESSION_COOKIE, path="/")
    return response


# ============================================================================
# Session API
# ============================================================================

_session_service = None
_session_service_by_workspace: Dict[str, Any] = {}


def _get_session_service(workspace: Optional[WorkspacePaths] = None):
    """Lazy-init session service when ENABLE_SESSION_RUNTIME=true."""
    if not _get_env_bool("ENABLE_SESSION_RUNTIME", default=True):
        return None

    import asyncio
    from src.session.store import SessionStore
    from src.session.events import EventBus
    from src.session.service import SessionService

    if workspace is not None:
        key = workspace.workspace_id
        if key in _session_service_by_workspace:
            return _session_service_by_workspace[key]
        store = SessionStore(base_dir=workspace.sessions_dir)
        runs_dir = workspace.runs_dir
        swarm_dir = workspace.swarm_dir
    else:
        global _session_service
        if _session_service is not None:
            return _session_service
        store = SessionStore(base_dir=SESSIONS_DIR)
        runs_dir = RUNS_DIR
        swarm_dir = None
    event_bus = EventBus()

    try:
        loop = asyncio.get_event_loop()
        event_bus.set_loop(loop)
    except RuntimeError:
        pass

    svc = SessionService(
        store=store,
        event_bus=event_bus,
        runs_dir=runs_dir,
        swarm_dir=swarm_dir,
    )
    if workspace is not None:
        _session_service_by_workspace[workspace.workspace_id] = svc
        return svc
    _session_service = svc
    return svc


def _feishu_exchange_oauth_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    import requests

    app_id = (os.getenv("FEISHU_OAUTH_APP_ID") or os.getenv("FEISHU_APP_ID") or "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret or not redirect_uri:
        raise HTTPException(status_code=500, detail="Feishu OAuth is not fully configured")

    response = requests.post(
        f"{_FEISHU_BASE_URL}/open-apis/authen/v2/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or payload
    if not isinstance(data, dict) or not data.get("access_token"):
        raise HTTPException(status_code=502, detail="Feishu OAuth token exchange failed")
    return data


def _feishu_fetch_user_profile(access_token: str) -> Dict[str, Any]:
    import requests

    response = requests.get(
        f"{_FEISHU_BASE_URL}/open-apis/authen/v1/user_info",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or payload
    if not isinstance(data, dict) or not data.get("open_id"):
        raise HTTPException(status_code=502, detail="Feishu user info fetch failed")
    return data


@app.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth)])
async def create_session(request: CreateSessionRequest, http_request: Request):
    """Create a chat session."""
    ctx = _resolve_request_context(http_request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    session = svc.create_session(title=request.title, config=request.config)
    return SessionResponse(
        session_id=session.session_id,
        title=session.title,
        status=session.status.value,
        channel=(session.config or {}).get("channel"),
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_attempt_id=session.last_attempt_id,
    )


@app.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(request: Request, limit: int = Query(50, ge=1, le=200)):
    """List sessions."""
    ctx = _resolve_request_context(request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    sessions = svc.list_sessions(limit=limit)
    return [
        SessionResponse(
            session_id=s.session_id,
            title=s.title,
            status=s.status.value,
            channel=(s.config or {}).get("channel"),
            created_at=s.created_at,
            updated_at=s.updated_at,
            last_attempt_id=s.last_attempt_id,
        )
        for s in sessions
    ]


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request):
    """Get one session by id."""
    ctx = _resolve_request_context(request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    session = svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return SessionResponse(
        session_id=session.session_id,
        title=session.title,
        status=session.status.value,
        channel=(session.config or {}).get("channel"),
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_attempt_id=session.last_attempt_id,
    )

@app.post("/sessions/batch-delete", dependencies=[Depends(require_auth)])
async def batch_delete_sessions(request: BatchDeleteSessionsRequest, http_request: Request):
    """Delete multiple sessions."""
    ctx = _resolve_request_context(http_request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    result = svc.delete_sessions(request.session_ids)
    return {
        "status": "ok",
        "deleted": result["deleted"],
        "missing": result["missing"],
    }


class UpdateSessionRequest(BaseModel):
    """Session update fields."""
    title: Optional[str] = None


@app.patch("/sessions/{session_id}", dependencies=[Depends(require_auth)])
async def update_session(session_id: str, req: UpdateSessionRequest, request: Request):
    """Update session fields (e.g. title)."""
    ctx = _resolve_request_context(request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    session = svc.store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if req.title is not None:
        session.title = req.title
    from datetime import datetime
    session.updated_at = datetime.now().isoformat()
    svc.store.update_session(session)
    return {"status": "updated", "session_id": session_id}


@app.post("/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
async def send_message(session_id: str, request: SendMessageRequest, http_request: Request):
    """Send a user message and start the agent loop (natural language strategy)."""
    ctx = _resolve_request_context(http_request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    try:
        result = await svc.send_message(session_id=session_id, content=request.content)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/sessions/{session_id}/cancel", dependencies=[Depends(require_auth)])
async def cancel_session(session_id: str, request: Request):
    """Cancel the in-flight agent loop for this session."""
    ctx = _resolve_request_context(request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    cancelled = svc.cancel_current(session_id)
    if not cancelled:
        return {"status": "no_active_loop"}
    return {"status": "cancelled"}


@app.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def get_messages(session_id: str, request: Request, limit: int = Query(100, ge=1, le=1000)):
    """List messages for a session."""
    ctx = _resolve_request_context(request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    messages = svc.get_messages(session_id, limit=limit)
    return [
        MessageResponse(
            message_id=m.message_id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            linked_attempt_id=m.linked_attempt_id,
            metadata=m.metadata if m.metadata else None,
        )
        for m in messages
    ]


@app.get("/sessions/{session_id}/event-log", response_model=List[SessionEventResponse])
async def get_event_log(session_id: str, request: Request, limit: int = Query(1000, ge=1, le=20000)):
    """List canonical session events."""
    ctx = _resolve_request_context(request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    session = svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    events = svc.get_events(session_id, limit=limit)
    return [
        SessionEventResponse(
            event_id=e.event_id,
            session_id=e.session_id,
            attempt_id=e.attempt_id,
            event_type=e.event_type,
            timestamp=e.timestamp,
            role=e.role,
            content=e.content,
            reasoning=e.reasoning,
            tool=e.tool,
            tool_call_id=e.tool_call_id,
            args=e.args,
            status=e.status,
            metadata=e.metadata if e.metadata else None,
        )
        for e in events
    ]


@app.get("/sessions/{session_id}/trajectory", response_model=SessionTrajectoryResponse)
async def get_session_trajectory(session_id: str, request: Request):
    """Export a session as an Atropos/Hermes trajectory entry."""
    ctx = _resolve_request_context(request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    try:
        export = svc.export_atropos_trajectory(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return SessionTrajectoryResponse(**export)


@app.get("/sessions/{session_id}/events")
async def session_events(
    session_id: str,
    request: Request,
    last_event_id: Optional[str] = Query(None, alias="Last-Event-ID"),
    replay_existing: bool = Query(False),
):
    """SSE stream for agent events."""
    ctx = _resolve_request_context(request, require_login=False)
    svc = _get_session_service(ctx.workspace)
    if not svc:
        raise HTTPException(status_code=501, detail="Session runtime not enabled")
    session = svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    header_id = request.headers.get("Last-Event-ID")
    event_id = header_id or last_event_id

    async def event_generator():
        async for event in svc.event_bus.subscribe(
            session_id,
            last_event_id=event_id,
            replay_existing=replay_existing,
        ):
            if await request.is_disconnected():
                break
            yield event.to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================================
# File Upload
# ============================================================================

@app.post("/upload", dependencies=[Depends(require_auth)])
async def upload_file(
    request: Request,
    file: UploadFile,
    session_id: Optional[str] = Form(None),
    run_id: Optional[str] = Form(None),
):
    """Upload a supported document into the scoped session/run artifact folder."""
    target_dir, _, _, _, _ = _resolve_upload_target_dir(request=request, session_id=session_id, run_id=run_id)
    return await _store_uploaded_file(file, target_dir)


@app.post("/upload/batch", response_model=UploadBatchResponse, dependencies=[Depends(require_auth)])
async def upload_files(
    request: Request,
    files: Optional[List[UploadFile]] = File(default=None),
    session_id: Optional[str] = Form(None),
    run_id: Optional[str] = Form(None),
):
    """Upload multiple supported documents into the scoped session/run artifact folder."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    target_dir, _, _, _, _ = _resolve_upload_target_dir(request=request, session_id=session_id, run_id=run_id)
    stored_files: List[Dict[str, str]] = []
    for file in files:
        stored_files.append(await _store_uploaded_file(file, target_dir))
    return UploadBatchResponse(status="ok", files=stored_files)


# ============================================================================
# Feishu Integration (WebSocket long-connection + HTTP webhook fallback)
# ============================================================================
#
# Set FEISHU_CONNECTION_MODE=websocket (default) to use the lark SDK's
# outbound WebSocket connection — no public URL needed.
# Set FEISHU_CONNECTION_MODE=webhook to receive HTTP POST events instead.
# Both modes share the same _feishu_route_message / _feishu_send_reply helpers.
# The WebSocket client starts automatically at server startup when the mode is
# "websocket" and app credentials are configured.
# ============================================================================

_FEISHU_CONNECTION_MODE = os.getenv("FEISHU_CONNECTION_MODE", "websocket").strip().lower()

# Credentials needed by both WS and webhook sections — define once here.
_FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
_FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
_FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")
_FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
_FEISHU_DOMAIN = os.getenv("FEISHU_DOMAIN", "feishu")
_FEISHU_BASE_URL = (
    "https://open.larksuite.com"
    if _FEISHU_DOMAIN == "lark"
    else "https://open.feishu.cn"
)
_FEISHU_SESSION_MAP_FILE = DATA_ROOT / ".feishu_sessions.json"
_FEISHU_STREAM_UPDATE_INTERVAL_SECONDS = max(
    0.2,
    _get_env_float("FEISHU_STREAM_UPDATE_INTERVAL_SECONDS", 0.35),
)
_FEISHU_TOKEN_CACHE: Dict[str, Any] = {"token": "", "expires_at": 0.0}
_feishu_logger = logging.getLogger("feishu.webhook")
_FEISHU_VISUALIZATION_ADAPTER = get_feishu_visualization_adapter()

# ---------------------------------------------------------------------------
# Markdown helpers — reuse hermes-agent's battle-tested implementation.
# Falls back to an inline copy when hermes-agent is not on sys.path.
# ---------------------------------------------------------------------------
import re as _re
import sys as _sys

_hermes_agent_dir = str(Path(__file__).resolve().parent.parent / "hermes-agent")
if _hermes_agent_dir not in _sys.path:
    _sys.path.insert(0, _hermes_agent_dir)

try:
    from gateway.platforms.feishu import (  # type: ignore[import]
        _build_markdown_post_payload as _feishu_build_markdown_post,
        _MARKDOWN_HINT_RE as _FEISHU_MARKDOWN_HINT_RE,
    )
    _feishu_logger.debug("[Feishu] Loaded markdown helpers from hermes-agent")
except Exception:
    _feishu_logger.debug("[Feishu] hermes-agent unavailable; using inline markdown helpers")
    _FEISHU_MARKDOWN_HINT_RE = _re.compile(
        r"(^#{1,6}\s)|(^\s*[-*]\s)|(^\s*\d+\.\s)|(^\s*---+\s*$)|(```)|(`[^`\n]+`)"
        r"|(\*\*[^*\n].+?\*\*)|(~~[^~\n].+?~~)|(<u>.+?</u>)|(\*[^*\n]+\*)"
        r"|(\[[^\]]+\]\([^)]+\))|(^>\s)",
        _re.MULTILINE,
    )

    def _feishu_build_markdown_post(content: str) -> str:  # type: ignore[misc]
        return json.dumps(
            {"zh_cn": {"content": [[{"tag": "md", "text": content}]]}},
            ensure_ascii=False,
        )

async def _feishu_patch_card_body(
    card_ctx: Dict[str, Any],
    title: str,
    elements: List[Dict[str, Any]],
    *,
    template: str = "blue",
) -> None:
    """Replace the full card body with a new element list via the CardKit update API.

    Must be called AFTER _feishu_set_card_streaming_mode(enabled=False) because
    Feishu ignores structural card updates while streaming mode is active.
    Uses PUT /open-apis/cardkit/v1/cards/{card_id} which replaces the card JSON
    in-place.  This is the only endpoint that supports Card v2 chart elements.
    """
    from urllib.parse import quote

    card_id = str(card_ctx.get("card_id") or "")
    if not card_id:
        _feishu_logger.warning("[Feishu] Cannot patch card body: card_id missing from card_ctx")
        return

    await _feishu_openapi_request(
        "PUT",
        f"/open-apis/cardkit/v1/cards/{quote(card_id, safe='')}",
        {
            "card": {
                "type": "card_json",
                "data": _FEISHU_VISUALIZATION_ADAPTER.build_card_payload_from_elements(
                    title,
                    elements,
                    template=template,
                ),
            },
            "uuid": uuid.uuid4().hex,
            "sequence": _feishu_take_card_sequence(card_ctx),
        },
    )


def _feishu_lookup_attempt_reply(svc: Any, session_id: str, attempt_id: str) -> str:
    """Return the stored assistant message for an attempt when available."""
    messages = svc.get_messages(session_id, limit=20)
    for msg in reversed(messages):
        if msg.role == "assistant" and msg.linked_attempt_id == attempt_id:
            return msg.content or ""
    return ""


def _feishu_snapshot_attempt_state(svc: Any, session_id: str, attempt_id: str) -> tuple[str, str]:
    """Best-effort reconstruction of current text and status from persisted events."""
    text_parts: List[str] = []
    status_text = ""
    try:
        events = svc.get_events(session_id, limit=2000)
    except Exception:
        return "", ""

    for event in events:
        if getattr(event, "attempt_id", None) != attempt_id:
            continue
        if event.event_type == "assistant.delta" and event.content:
            text_parts.append(event.content)
        elif event.event_type == "tool.progress" and event.content:
            status_text = event.content
        elif event.event_type == "tool.call" and event.tool:
            status_text = f"Running `{event.tool}`..."

    return "".join(text_parts).strip(), status_text.strip()


def _feishu_http_json(method: str, url: str, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
    """Send a JSON request to the Feishu OpenAPI and parse the JSON response.

    Retries up to 2 times on transient HTTP errors (502/503/504) and timeouts.
    """
    import urllib.error
    import urllib.request

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    _RETRYABLE_CODES = (502, 503, 504)
    last_exc: Exception | None = None
    for attempt in range(3):
        if attempt > 0:
            time.sleep(min(1.0 * attempt, 3.0))
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            if exc.code in _RETRYABLE_CODES and attempt < 2:
                _feishu_logger.debug("[Feishu] Retrying %s %s after HTTP %s (attempt %d)", method, url, exc.code, attempt + 1)
                last_exc = RuntimeError(f"Feishu HTTP {exc.code}: {response_body}")
                continue
            raise RuntimeError(f"Feishu HTTP {exc.code}: {response_body}") from exc
        except (TimeoutError, OSError) as exc:
            if attempt < 2:
                _feishu_logger.debug("[Feishu] Retrying %s %s after timeout (attempt %d)", method, url, attempt + 1)
                last_exc = exc
                continue
            raise RuntimeError(f"Feishu request timeout: {exc}") from exc
    raise RuntimeError(f"Feishu request failed after retries") from last_exc


async def _feishu_get_tenant_access_token() -> str:
    """Fetch or reuse a tenant access token for Feishu OpenAPI calls."""
    if not _FEISHU_APP_ID or not _FEISHU_APP_SECRET:
        raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET not configured")

    now = time.time()
    cached_token = str(_FEISHU_TOKEN_CACHE.get("token") or "")
    cached_expiry = float(_FEISHU_TOKEN_CACHE.get("expires_at") or 0.0)
    if cached_token and cached_expiry - now > 60:
        return cached_token

    def _fetch_token() -> str:
        response = _feishu_http_json(
            "POST",
            f"{_FEISHU_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
            {"Content-Type": "application/json; charset=utf-8"},
            {"app_id": _FEISHU_APP_ID, "app_secret": _FEISHU_APP_SECRET},
        )
        token = str(response.get("tenant_access_token") or "")
        if not token:
            raise RuntimeError(f"Failed to obtain tenant access token: {response}")
        expires_in = int(response.get("expire") or response.get("expires_in") or 7200)
        _FEISHU_TOKEN_CACHE["token"] = token
        _FEISHU_TOKEN_CACHE["expires_at"] = time.time() + max(expires_in - 120, 60)
        return token

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_token)


async def _feishu_openapi_request(method: str, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Call a Feishu OpenAPI endpoint and return the `data` field on success."""
    headers = {
        "Authorization": f"Bearer {await _feishu_get_tenant_access_token()}",
        "Content-Type": "application/json; charset=utf-8",
    }
    url = f"{_FEISHU_BASE_URL}{path}"
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, _feishu_http_json, method, url, headers, body)
    if int(response.get("code") or 0) != 0:
        raise RuntimeError(f"Feishu API error {response.get('code')}: {response.get('msg')}")
    return response.get("data") or {}


async def _feishu_create_streaming_card_message(chat_id: str, title: str, initial_body: str) -> Dict[str, Any]:
    """Create a CardKit streaming card entity and send it to a chat."""
    create_data = await _feishu_openapi_request(
        "POST",
        "/open-apis/cardkit/v1/cards",
        {
            "type": "card_json",
            "data": _FEISHU_VISUALIZATION_ADAPTER.build_streaming_card_payload(title, initial_body),
        },
    )
    card_id = str(create_data.get("card_id") or "")
    if not card_id:
        raise RuntimeError(f"Missing card_id from create-card response: {create_data}")

    message_data = await _feishu_openapi_request(
        "POST",
        "/open-apis/im/v1/messages?receive_id_type=chat_id",
        {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps({"type": "card", "data": {"card_id": card_id}}, ensure_ascii=False),
        },
    )
    return {
        "card_id": card_id,
        "message_id": str(message_data.get("message_id") or ""),
        "element_id": _FEISHU_VISUALIZATION_ADAPTER.stream_element_id,
        "sequence": 1,
    }


async def _feishu_send_card_message(
    chat_id: str,
    title: str,
    elements: List[Dict[str, Any]],
    *,
    template: str = "blue",
) -> Dict[str, Any]:
    """Create a non-streaming CardKit card entity and send it to a chat."""
    create_data = await _feishu_openapi_request(
        "POST",
        "/open-apis/cardkit/v1/cards",
        {
            "type": "card_json",
            "data": _FEISHU_VISUALIZATION_ADAPTER.build_card_payload_from_elements(
                title,
                elements,
                template=template,
            ),
        },
    )
    card_id = str(create_data.get("card_id") or "")
    if not card_id:
        raise RuntimeError(f"Missing card_id from create-card response: {create_data}")

    message_data = await _feishu_openapi_request(
        "POST",
        "/open-apis/im/v1/messages?receive_id_type=chat_id",
        {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps({"type": "card", "data": {"card_id": card_id}}, ensure_ascii=False),
        },
    )
    return {
        "card_id": card_id,
        "message_id": str(message_data.get("message_id") or ""),
    }


def _feishu_take_card_sequence(card_ctx: Dict[str, Any]) -> int:
    """Return the next strictly increasing sequence number for card operations."""
    sequence = int(card_ctx.get("sequence") or 1)
    card_ctx["sequence"] = sequence + 1
    return sequence


async def _feishu_stream_card_text(card_ctx: Dict[str, Any], content: str) -> None:
    """Push the full markdown content into the streaming card text element."""
    from urllib.parse import quote

    await _feishu_openapi_request(
        "PUT",
        (
            f"/open-apis/cardkit/v1/cards/{quote(str(card_ctx['card_id']), safe='')}"
            f"/elements/{quote(str(card_ctx['element_id']), safe='')}/content"
        ),
        {
            "uuid": uuid.uuid4().hex,
            "sequence": _feishu_take_card_sequence(card_ctx),
            "content": content or " ",
        },
    )


async def _feishu_set_card_streaming_mode(
    card_ctx: Dict[str, Any], *, enabled: bool, summary: Optional[str] = None
) -> None:
    """Update streaming mode for a card entity."""
    from urllib.parse import quote

    settings: Dict[str, Any] = {
        "config": {
            "width_mode": "fill",
            "update_multi": True,
            "streaming_mode": enabled,
        }
    }
    if summary is not None:
        settings["config"]["summary"] = {"content": summary[:100]}

    await _feishu_openapi_request(
        "PATCH",
        f"/open-apis/cardkit/v1/cards/{quote(str(card_ctx['card_id']), safe='')}/settings",
        {
            "uuid": uuid.uuid4().hex,
            "sequence": _feishu_take_card_sequence(card_ctx),
            "settings": json.dumps(settings, ensure_ascii=False),
        },
    )


# ---------------------------------------------------------------------------
# Feishu WebSocket startup (runs in a dedicated daemon thread)
# ---------------------------------------------------------------------------

_feishu_ws_thread: Optional[Any] = None  # threading.Thread, set at startup


async def _feishu_await_and_reply(svc: Any, session_id: str, chat_id: str, attempt_id: str) -> None:
    """Stream session output into a Feishu Card v2, then close streaming mode."""
    card_ctx: Optional[Dict[str, Any]] = None
    streamed_text, latest_status = _feishu_snapshot_attempt_state(svc, session_id, attempt_id)
    last_pushed_body = ""
    last_push_at = 0.0

    try:
        initial_body = _FEISHU_VISUALIZATION_ADAPTER.render_stream_body(
            streamed_text,
            status=latest_status or "Thinking...",
        )
        card_ctx = await _feishu_create_streaming_card_message(chat_id, "semantier", initial_body)
        last_pushed_body = initial_body
        last_push_at = time.monotonic()
    except Exception:
        card_ctx = None
        _feishu_logger.warning(
            "[Feishu WS] Failed to create streaming card for chat=%s; falling back to final reply",
            chat_id,
            exc_info=True,
        )

    try:
        final_text = streamed_text
        final_error = ""

        async def _maybe_push_update() -> None:
            nonlocal last_pushed_body, last_push_at
            if not card_ctx:
                return
            candidate = _FEISHU_VISUALIZATION_ADAPTER.render_stream_body(streamed_text, status=latest_status)
            now = time.monotonic()
            if candidate == last_pushed_body or (now - last_push_at) < _FEISHU_STREAM_UPDATE_INTERVAL_SECONDS:
                return
            await _feishu_stream_card_text(card_ctx, candidate)
            last_pushed_body = candidate
            last_push_at = now

        async def _wait_for_completion() -> tuple[str, str]:
            nonlocal streamed_text, latest_status
            async for sse_event in svc.event_bus.subscribe(session_id):
                event_attempt_id = str((sse_event.data or {}).get("attempt_id") or "")
                if event_attempt_id and event_attempt_id != attempt_id:
                    continue

                if sse_event.event_type == "text_delta":
                    streamed_text += str((sse_event.data or {}).get("content") or "")
                    latest_status = "Generating response..."
                    await _maybe_push_update()
                    continue

                if sse_event.event_type == "tool_call":
                    tool_name = str((sse_event.data or {}).get("tool") or "tool")
                    latest_status = f"Running `{tool_name}`..."
                    await _maybe_push_update()
                    continue

                if sse_event.event_type == "tool_progress":
                    preview = str((sse_event.data or {}).get("preview") or "").strip()
                    if preview:
                        latest_status = preview
                        await _maybe_push_update()
                    continue

                if sse_event.event_type == "attempt.completed":
                    reply = _feishu_lookup_attempt_reply(svc, session_id, attempt_id)
                    final_reply = reply or str((sse_event.data or {}).get("summary") or streamed_text or "")
                    return final_reply, ""

                if sse_event.event_type == "attempt.failed":
                    error_text = str((sse_event.data or {}).get("error") or "Execution failed")
                    reply = _feishu_lookup_attempt_reply(svc, session_id, attempt_id)
                    final_reply = reply or streamed_text or error_text
                    return final_reply, error_text

            return streamed_text, ""

        final_text, final_error = await asyncio.wait_for(_wait_for_completion(), timeout=600.0)

        if card_ctx:
            streaming_closed = False
            try:
                has_charts = _FEISHU_VISUALIZATION_ADAPTER.has_chart_elements(final_text)
                if has_charts:
                    # Push prose-only text to the streaming element so vchart
                    # fences never appear as code blocks in the live stream view.
                    prose_text = _FEISHU_VISUALIZATION_ADAPTER.strip_chart_fences(final_text)
                    prose_body = _FEISHU_VISUALIZATION_ADAPTER.render_stream_body(
                        prose_text or " ",
                        error=final_error,
                    )
                    if prose_body != last_pushed_body:
                        await _feishu_stream_card_text(card_ctx, prose_body)
                else:
                    final_body = _FEISHU_VISUALIZATION_ADAPTER.render_stream_body(final_text, error=final_error)
                    if final_body != last_pushed_body:
                        await _feishu_stream_card_text(card_ctx, final_body)

                # Close streaming mode first — Feishu ignores structural card
                # updates (body element replacement) while streaming is active.
                await _feishu_set_card_streaming_mode(
                    card_ctx,
                    enabled=False,
                    summary="Failed" if final_error else "Complete",
                )
                streaming_closed = True

                # After streaming is closed, replace the card body with proper
                # chart elements via the IM message update endpoint.
                if has_charts:
                    final_elements = _FEISHU_VISUALIZATION_ADAPTER.split_card_elements(
                        final_text,
                        enforce_chart_limit=False,
                    )
                    if final_error:
                        final_elements.append({"tag": "markdown", "content": f"\n\n---\n\n**Error:** {final_error}"})
                    final_batches = _FEISHU_VISUALIZATION_ADAPTER.chunk_card_elements(final_elements)
                    try:
                        await _feishu_patch_card_body(card_ctx, "semantier", final_batches[0])
                        for extra_batch in final_batches[1:]:
                            await _feishu_send_card_message(chat_id, "semantier", extra_batch)
                    except Exception:
                        _feishu_logger.warning(
                            "[Feishu WS] Chart card patch failed after streaming close; preserving markdown card for chat=%s attempt=%s",
                            chat_id,
                            attempt_id,
                            exc_info=True,
                        )
                        return
                _feishu_logger.info("[Feishu WS] Streamed card reply to chat=%s (attempt=%s)", chat_id, attempt_id)
                return
            except Exception:
                _feishu_logger.warning(
                    "[Feishu WS] Streaming card finalization failed for chat=%s attempt=%s",
                    chat_id,
                    attempt_id,
                    exc_info=True,
                )
                if streaming_closed:
                    return

        if final_text:
            await _feishu_send_reply(chat_id, final_text if not final_error else f"{final_text}\n\nError: {final_error}")
            _feishu_logger.info("[Feishu WS] Sent fallback reply to chat=%s (attempt=%s)", chat_id, attempt_id)
    except asyncio.TimeoutError:
        _feishu_logger.warning("[Feishu WS] Timed out waiting for reply to chat=%s attempt=%s", chat_id, attempt_id)
    except Exception:
        _feishu_logger.warning("[Feishu WS] Error sending Feishu reply", exc_info=True)


def _feishu_ws_event_handler_factory(main_loop: asyncio.AbstractEventLoop) -> Any:
    """Build a lark EventDispatcherHandler routing im.message.receive_v1 and card.action.trigger."""
    try:
        import lark_oapi as lark  # noqa: F401 — side-effect: registers SDK
        from lark_oapi import EventDispatcherHandler
    except ImportError:
        _feishu_logger.error("[Feishu WS] lark-oapi not installed. Run: uv add 'lark-oapi[websocket]'")
        return None

    def _on_message(data: Any) -> None:
        try:
            event = getattr(data, "event", None) or {}
            message = getattr(event, "message", None) or {}
            sender = getattr(event, "sender", None) or {}
            sender_id = getattr(sender, "sender_id", None) or {}
            if getattr(sender, "sender_type", "") == "bot":
                return
            chat_id = getattr(message, "chat_id", "") or ""
            message_id = getattr(message, "message_id", "") or ""
            msg_dict: Dict[str, Any] = {
                "message_type": getattr(message, "message_type", "text") or "text",
                "content": getattr(message, "content", "") or "",
                "mentions": [
                    {"name": getattr(m, "name", "") or ""}
                    for m in (getattr(message, "mentions", None) or [])
                ],
            }
            text = _extract_feishu_text(msg_dict)
            if not chat_id or not text:
                return
            svc = _get_session_service()
            if svc is None:
                _feishu_logger.warning("[Feishu WS] Session service not available, dropping message %s", message_id)
                return
            future = asyncio.run_coroutine_threadsafe(
                _feishu_route_message(
                    svc,
                    chat_id,
                    text,
                    sender_open_id=str(getattr(sender_id, "open_id", "") or ""),
                    sender_union_id=str(getattr(sender_id, "union_id", "") or ""),
                ),
                main_loop,
            )
            future.add_done_callback(
                lambda f: _feishu_logger.warning("[Feishu WS] Route error: %s", f.exception())
                if f.exception() else None
            )
            _feishu_logger.info("[Feishu WS] Queued message from chat=%s id=%s: %.80s", chat_id, message_id, text)
        except Exception:
            _feishu_logger.warning("[Feishu WS] Error in message handler", exc_info=True)

    def _on_card_action(data: Any) -> None:
        """Log card action triggers (button clicks). Extend here for interactive flows."""
        try:
            event = getattr(data, "event", None) or {}
            action = getattr(event, "action", None) or {}
            action_value = getattr(action, "value", {}) or {}
            context = getattr(event, "context", None) or {}
            chat_id = getattr(context, "open_chat_id", "") or ""
            _feishu_logger.info("[Feishu WS] Card action from chat=%s value=%s", chat_id, action_value)
        except Exception:
            _feishu_logger.warning("[Feishu WS] Error in card action handler", exc_info=True)

    try:
        handler = (
            EventDispatcherHandler
            .builder(_FEISHU_ENCRYPT_KEY, _FEISHU_VERIFICATION_TOKEN)
            .register_p2_im_message_receive_v1(_on_message)
            .register_p2_card_action_trigger(_on_card_action)
            .build()
        )
        return handler
    except Exception:
        _feishu_logger.error("[Feishu WS] Failed to build event handler", exc_info=True)
        return None


def _run_feishu_ws_client(ws_client: Any) -> None:
    """Run the lark WS client in its own thread-local event loop (blocking)."""
    import lark_oapi.ws.client as _ws_mod

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Inject thread-local loop so the lark SDK's internal asyncio calls use it
    _ws_mod.loop = loop  # type: ignore[attr-defined]
    try:
        ws_client.start()
    except Exception:
        _feishu_logger.error("[Feishu WS] WebSocket client crashed", exc_info=True)
    finally:
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        try:
            loop.stop()
            loop.close()
        except Exception:
            pass
        _feishu_logger.info("[Feishu WS] WebSocket client thread exited")


def _start_feishu_websocket(main_loop: asyncio.AbstractEventLoop) -> None:
    """Start the Feishu WebSocket long-connection client in a background daemon thread."""
    global _feishu_ws_thread

    if _FEISHU_CONNECTION_MODE != "websocket":
        return
    if not _FEISHU_APP_ID or not _FEISHU_APP_SECRET:
        _feishu_logger.warning("[Feishu WS] FEISHU_APP_ID / FEISHU_APP_SECRET not set — skipping WS startup")
        return

    try:
        import lark_oapi as lark
        from lark_oapi.ws.client import Client as FeishuWSClient
    except ImportError:
        _feishu_logger.error("[Feishu WS] lark-oapi not installed. Run: uv add 'lark-oapi[websocket]'")
        return

    event_handler = _feishu_ws_event_handler_factory(main_loop)
    if event_handler is None:
        return

    domain = lark.LARK_DOMAIN if _FEISHU_DOMAIN == "lark" else lark.FEISHU_DOMAIN
    ws_client = FeishuWSClient(
        app_id=_FEISHU_APP_ID,
        app_secret=_FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    import threading
    _feishu_ws_thread = threading.Thread(
        target=_run_feishu_ws_client,
        args=(ws_client,),
        daemon=True,
        name="feishu-ws",
    )
    _feishu_ws_thread.start()
    _feishu_logger.info("[Feishu WS] WebSocket client started (thread=%s)", _feishu_ws_thread.name)


@app.on_event("startup")
async def _feishu_ws_startup() -> None:
    """Launch Feishu WebSocket long-connection client alongside the WebUI at startup."""
    if _FEISHU_CONNECTION_MODE == "websocket" and _FEISHU_APP_ID:
        loop = asyncio.get_running_loop()
        _start_feishu_websocket(loop)


# ============================================================================
# Feishu Webhook Integration (HTTP mode, kept for compatibility)
# ============================================================================
# Note: credentials (_FEISHU_APP_ID etc.) are defined in the WS section above.


def _load_feishu_session_map() -> Dict[str, str]:
    """Load the Feishu chat_id → session_id mapping from disk."""
    try:
        if _FEISHU_SESSION_MAP_FILE.exists():
            return json.loads(_FEISHU_SESSION_MAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_feishu_session_map(mapping: Dict[str, str]) -> None:
    """Persist the Feishu chat_id → session_id mapping to disk."""
    try:
        _FEISHU_SESSION_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _FEISHU_SESSION_MAP_FILE.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        _feishu_logger.warning("Failed to save Feishu session map", exc_info=True)


def _feishu_session_map_key(chat_id: str, user: Optional[AuthUser] = None) -> str:
    if user is None:
        return chat_id
    return f"{user.user_id}:{chat_id}"


def _resolve_feishu_auth_user(*, open_id: str = "", union_id: str = "") -> Optional[AuthUser]:
    if not _feishu_oauth_enabled():
        return None
    store = _get_auth_store()
    if open_id:
        user = store.get_user_by_feishu_open_id(open_id)
        if user is not None:
            return user
    if union_id:
        return store.get_user_by_feishu_union_id(union_id)
    return None


def _feishu_login_required_message() -> str:
    import urllib.parse

    redirect_uri = _get_feishu_oauth_redirect_uri()
    login_url = "/auth/feishu/login"
    if redirect_uri:
        parsed = urllib.parse.urlsplit(redirect_uri)
        if parsed.scheme and parsed.netloc:
            login_url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, "/auth/feishu/login", "", "")
            )
    return (
        "Your Feishu account is not linked yet. "
        f"Sign in first: {login_url}"
    )


def _feishu_verify_signature(headers: Any, body_bytes: bytes) -> bool:
    """Verify Feishu webhook signature: SHA256(timestamp + nonce + encrypt_key + body)."""
    timestamp = str(headers.get("x-lark-request-timestamp", "") or "")
    nonce = str(headers.get("x-lark-request-nonce", "") or "")
    signature = str(headers.get("x-lark-signature", "") or "")
    if not timestamp or not nonce or not signature:
        return False
    body_str = body_bytes.decode("utf-8", errors="replace")
    content = f"{timestamp}{nonce}{_FEISHU_ENCRYPT_KEY}{body_str}"
    computed = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return _hmac.compare_digest(computed, signature)


def _extract_feishu_text(message: Dict[str, Any]) -> str:
    """Extract plain text content from a Feishu message object."""
    msg_type = message.get("message_type", "")
    raw_content = message.get("content", "")
    try:
        content_obj = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except Exception:
        return raw_content or ""
    if msg_type == "text":
        return str(content_obj.get("text", "")).strip()
    if msg_type in ("post", "rich_text"):
        # Extract text nodes from the post format
        parts: List[str] = []
        post_body = content_obj.get("content") or []
        for line in post_body:
            if isinstance(line, list):
                for block in line:
                    if isinstance(block, dict) and block.get("tag") == "text":
                        parts.append(str(block.get("text", "")))
        return " ".join(parts).strip()
    return ""


async def _feishu_send_reply(chat_id: str, text: str) -> None:
    """Send a reply to a Feishu chat using the tenant access token.

    Automatically selects the outbound message format:
    - ``post``  when markdown formatting is detected (rendered via the ``md`` tag).
      Uses hermes-agent's ``_build_markdown_post_payload`` / ``_MARKDOWN_HINT_RE``.
    - ``text``  for plain text content.

    Falls back to plain-text if Feishu rejects the post payload (two-stage
    delivery, same as hermes-agent's behaviour described in the Feishu docs).
    """
    if not _FEISHU_APP_ID or not _FEISHU_APP_SECRET:
        return
    import urllib.request
    import urllib.error

    # Choose format based on markdown detection (reuses hermes-agent regex)
    if _FEISHU_MARKDOWN_HINT_RE.search(text):
        msg_type = "post"
        content = _feishu_build_markdown_post(text)
    else:
        msg_type = "text"
        content = json.dumps({"text": text})

    def _get_token() -> str:
        url = f"{_FEISHU_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal"
        body = json.dumps({"app_id": _FEISHU_APP_ID, "app_secret": _FEISHU_APP_SECRET}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("tenant_access_token", "")

    def _send(token: str, mt: str, ct: str) -> Dict[str, Any]:
        url = f"{_FEISHU_BASE_URL}/open-apis/im/v1/messages?receive_id_type=chat_id"
        body = json.dumps({
            "receive_id": chat_id,
            "msg_type": mt,
            "content": ct,
        }).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    try:
        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, _get_token)
        if not token:
            return
        result = await loop.run_in_executor(None, _send, token, msg_type, content)
        # Two-stage fallback: if Feishu rejects the post payload, retry as plain text
        if msg_type == "post" and isinstance(result, dict) and result.get("code") != 0:
            _feishu_logger.debug(
                "[Feishu] post payload rejected (code=%s), falling back to plain text",
                result.get("code"),
            )
            plain_content = json.dumps({"text": text})
            await loop.run_in_executor(None, _send, token, "text", plain_content)
    except Exception:
        _feishu_logger.warning("Failed to send Feishu reply to %s", chat_id, exc_info=True)


async def _feishu_route_message(
    svc: Any,
    chat_id: str,
    text: str,
    *,
    sender_open_id: str = "",
    sender_union_id: str = "",
) -> None:
    """Find or create a session for this Feishu chat and dispatch the message."""
    resolved_user = _resolve_feishu_auth_user(open_id=sender_open_id, union_id=sender_union_id)
    resolved_workspace: Optional[WorkspacePaths] = None
    if _feishu_oauth_enabled():
        if resolved_user is None:
            _feishu_logger.info(
                "Ignoring Feishu message from unlinked sender open_id=%s union_id=%s chat=%s",
                sender_open_id,
                sender_union_id,
                chat_id,
            )
            await _feishu_send_reply(chat_id, _feishu_login_required_message())
            return
        resolved_workspace = ensure_workspace(
            WORKSPACES_DIR,
            resolved_user.user_id,
            _TEMPLATE_HERMES_HOME,
            workspace_slug=resolved_user.workspace_slug,
        )
        svc = _get_session_service(resolved_workspace)

    mapping = _load_feishu_session_map()
    session_key = _feishu_session_map_key(chat_id, resolved_user)
    session_id = mapping.get(session_key)

    # Validate the cached session still exists
    if session_id and not svc.get_session(session_id):
        session_id = None

    if not session_id:
        title_prefix = f"Feishu:{resolved_user.name}" if resolved_user is not None else "Feishu"
        session = svc.create_session(title=f"{title_prefix}:{chat_id[:30]}", config={"channel": "feishu"})
        session_id = session.session_id
        mapping[session_key] = session_id
        _save_feishu_session_map(mapping)
        if resolved_workspace is not None:
            _feishu_logger.info(
                "Created new session %s for Feishu chat %s in workspace %s",
                session_id,
                chat_id,
                resolved_workspace.workspace_slug,
            )
        else:
            _feishu_logger.info("Created new session %s for Feishu chat %s", session_id, chat_id)

    try:
        result = await svc.send_message(session_id=session_id, content=text)
        attempt_id = result.get("attempt_id") if isinstance(result, dict) else None
        if attempt_id:
            # Send the agent's reply back to Feishu when the attempt finishes
            asyncio.create_task(_feishu_await_and_reply(svc, session_id, chat_id, attempt_id))
    except Exception:
        _feishu_logger.warning("Failed to route Feishu message to session %s", session_id, exc_info=True)


@app.post("/feishu/webhook")
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    """Feishu webhook endpoint: receive events and route messages to the agent.

    Handles:
    - URL verification challenge (subscription setup in Feishu developer console)
    - Signature verification via FEISHU_ENCRYPT_KEY when configured
    - Verification token check via FEISHU_VERIFICATION_TOKEN when configured
    - im.message.receive_v1 → session service routing
    """
    body_bytes = await request.body()

    # Signature verification (skip when FEISHU_ENCRYPT_KEY is not configured)
    if _FEISHU_ENCRYPT_KEY and not _feishu_verify_signature(request.headers, body_bytes):
        _feishu_logger.warning("Feishu webhook rejected: invalid signature from %s", request.client)
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload: Dict[str, Any] = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # URL verification challenge — must respond before other security checks
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    # Verification token check
    if _FEISHU_VERIFICATION_TOKEN:
        header = payload.get("header") or {}
        incoming_token = str(header.get("token") or payload.get("token") or "")
        if not incoming_token or not _hmac.compare_digest(incoming_token, _FEISHU_VERIFICATION_TOKEN):
            _feishu_logger.warning("Feishu webhook rejected: invalid verification token from %s", request.client)
            raise HTTPException(status_code=401, detail="Invalid verification token")

    event_type = str((payload.get("header") or {}).get("event_type") or "")

    if event_type == "im.message.receive_v1":
        event = payload.get("event") or {}
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}

        # Ignore bot-originated messages to prevent feedback loops
        if sender.get("sender_type") == "bot":
            return {"code": 0, "msg": "ok"}

        chat_id = message.get("chat_id", "")
        message_id = message.get("message_id", "")
        if not chat_id or not message_id:
            return {"code": 0, "msg": "ok"}

        text = _extract_feishu_text(message)

        # Strip @mentions (e.g. group chats)
        for mention in (message.get("mentions") or []):
            name = mention.get("name") or ""
            if name:
                text = text.replace(f"@{name}", "").strip()
        text = text.strip()

        if not text:
            return {"code": 0, "msg": "ok"}

        svc = _get_session_service()
        if svc:
            background_tasks.add_task(
                _feishu_route_message,
                svc,
                chat_id,
                text,
                sender_open_id=str(sender_id.get("open_id") or ""),
                sender_union_id=str(sender_id.get("union_id") or ""),
            )
            _feishu_logger.info(
                "Queued Feishu message from chat %s (message_id=%s): %.80s",
                chat_id, message_id, text,
            )
    else:
        _feishu_logger.debug("Ignoring Feishu event type: %s", event_type or "(unknown)")

    return {"code": 0, "msg": "ok"}


# ============================================================================
# Swarm API
# ============================================================================

_swarm_runtime = None
_swarm_runtime_by_workspace: Dict[str, Any] = {}
_FRONTEND_DIST: Optional[Path] = None  # set during startup when SPA is mounted


def _get_swarm_runtime(workspace: Optional[WorkspacePaths] = None):
    """Lazy-init SwarmRuntime singleton."""
    from src.swarm.store import SwarmStore
    from src.swarm.runtime import WorkflowRuntime
    if workspace is not None:
        key = workspace.workspace_id
        if key in _swarm_runtime_by_workspace:
            return _swarm_runtime_by_workspace[key]
        swarm_dir = workspace_swarm_runs_dir(workspace.agent_root)
        store = SwarmStore(base_dir=swarm_dir)
        runtime = WorkflowRuntime(store=store)
        _swarm_runtime_by_workspace[key] = runtime
        return runtime
    global _swarm_runtime
    if _swarm_runtime is not None:
        return _swarm_runtime
    swarm_dir = get_swarm_runs_dir(DATA_ROOT)
    store = SwarmStore(base_dir=swarm_dir)
    _swarm_runtime = WorkflowRuntime(store=store)
    return _swarm_runtime


@app.get("/swarm/presets")
async def list_swarm_presets():
    """List Swarm YAML presets."""
    from src.swarm.presets import list_presets
    return list_presets()


@app.post("/swarm/runs", dependencies=[Depends(require_auth)])
async def create_swarm_run(request: dict, http_request: Request):
    """Start a swarm run: body must include preset_name and user_vars."""
    ctx = _resolve_request_context(http_request, require_login=True)
    runtime = _get_swarm_runtime(ctx.workspace)
    preset_name = request.get("preset_name", "")
    user_vars = request.get("user_vars", {})
    try:
        run = runtime.start_run(preset_name, user_vars)
        return {"id": run.id, "status": run.status.value, "preset_name": run.preset_name}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/swarm/runs")
async def list_swarm_runs(request: Request, limit: int = Query(20, ge=1, le=100)):
    """List swarm runs (newest first)."""
    ctx = _resolve_request_context(request, require_login=True)
    runtime = _get_swarm_runtime(ctx.workspace)
    runs = runtime._store.list_runs(limit=limit)
    return [
        {
            "id": r.id,
            "preset_name": r.preset_name,
            "status": r.status.value,
            "created_at": r.created_at,
            "task_count": len(r.tasks),
            "completed_count": sum(1 for t in r.tasks if t.status.value == "completed"),
        }
        for r in runs
    ]


@app.get("/swarm/runs/{run_id}")
async def get_swarm_run(run_id: str, request: Request):
    """Swarm run detail including task statuses."""
    from src.swarm.task_store import TaskStore

    ctx = _resolve_request_context(request, require_login=True)
    runtime = _get_swarm_runtime(ctx.workspace)
    run = runtime._store.load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Merge real-time task statuses from task_store (updated during execution)
    run_dir = runtime._store.run_dir(run_id)
    tasks_dir = run_dir / "tasks"
    if tasks_dir.exists():
        task_store = TaskStore(run_dir)
        live_tasks = task_store.load_all()
        if live_tasks:
            run.tasks = live_tasks

    return {
        "id": run.id,
        "preset_name": run.preset_name,
        "status": run.status.value,
        "user_vars": run.user_vars,
        "agents": [a.model_dump() for a in run.agents],
        "tasks": [t.model_dump() for t in run.tasks],
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "final_report": run.final_report,
    }


@app.get("/swarm/runs/{run_id}/events")
async def swarm_run_events(run_id: str, request: Request, last_index: int = Query(0, ge=0)):
    """SSE stream for a swarm run."""
    import asyncio
    ctx = _resolve_request_context(request, require_login=True)
    runtime = _get_swarm_runtime(ctx.workspace)

    async def event_stream():
        idx = last_index
        while True:
            if await request.is_disconnected():
                break
            events = runtime._store.read_events(run_id, after_index=idx)
            for evt in events:
                idx += 1
                yield f"id: {idx}\nevent: {evt.type}\ndata: {json.dumps(evt.model_dump(), ensure_ascii=False)}\n\n"
            run = runtime._store.load_run(run_id)
            if run and run.status.value in ("completed", "failed", "cancelled"):
                yield f"event: done\ndata: {{\"status\": \"{run.status.value}\"}}\n\n"
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/swarm/runs/{run_id}/cancel", dependencies=[Depends(require_auth)])
async def cancel_swarm_run(run_id: str, request: Request):
    """Cancel an active swarm run."""
    ctx = _resolve_request_context(request, require_login=True)
    runtime = _get_swarm_runtime(ctx.workspace)
    ok = runtime.cancel_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"No active run {run_id}")
    return {"status": "cancelled"}


# ============================================================================
# Main Entry Point
# ============================================================================

def _pid_exists(pid: int) -> bool:
    """Return True when the process id still exists."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_process_on_port(port: int) -> None:
    """Best-effort: terminate any process listening on the requested TCP port."""
    import shutil
    import subprocess

    if port <= 0:
        return

    pids: list[int] = []
    try:
        if shutil.which("lsof"):
            result = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True,
                text=True,
                check=False,
            )
            pids = [
                int(line.strip())
                for line in result.stdout.splitlines()
                if line.strip().isdigit() and int(line.strip()) != os.getpid()
            ]
        elif shutil.which("fuser"):
            result = subprocess.run(
                ["fuser", f"{port}/tcp"],
                capture_output=True,
                text=True,
                check=False,
            )
            pids = [
                int(token)
                for token in result.stdout.split()
                if token.strip().isdigit() and int(token.strip()) != os.getpid()
            ]
    except Exception as exc:
        print(f"[warn] Failed to inspect port {port}: {exc}")
        return

    if not pids:
        return

    print(f"[info] Port {port} is busy; stopping PID(s): {', '.join(str(pid) for pid in pids)}")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    deadline = time.time() + 3.0
    while time.time() < deadline:
        alive = [pid for pid in pids if _pid_exists(pid)]
        if not alive:
            print(f"[info] Freed TCP port {port}")
            return
        time.sleep(0.1)

    for pid in [pid for pid in pids if _pid_exists(pid)]:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    time.sleep(0.1)
    print(f"[info] Freed TCP port {port}")


def serve_main(argv: list[str] | None = None) -> int:
    """Start the API server from CLI-style arguments."""
    import argparse
    import subprocess
    import uvicorn
    parser = argparse.ArgumentParser(description="semantier Server")
    parser.add_argument("--port", type=int, default=8899, help="Listen port (default 8899)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--dev", action="store_true", help="Dev mode: spawn Vite on :5173")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    frontend_root, frontend_dist = _resolve_frontend_paths()

    vite_proc = None
    if args.dev and frontend_root.exists():
        print("[dev] Starting Vite dev server on :5173 ...")
        vite_proc = subprocess.Popen(
            ["npx", "vite", "--host", "0.0.0.0"],
            cwd=str(frontend_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[dev] Vite PID={vite_proc.pid}")
        print("[dev] Frontend: http://localhost:5173")
        print(f"[dev] API: http://localhost:{args.port}")
    elif frontend_dist.exists():
        if not any(route.path == "/" for route in app.routes):
            global _FRONTEND_DIST
            _FRONTEND_DIST = frontend_dist
            app.mount("/", SPAStaticFiles(directory=str(frontend_dist), html=True), name="frontend")
        print(f"[prod] Frontend served from {frontend_dist}")
    else:
        print(f"[warn] No frontend build found at {frontend_dist}")
        print("[warn] Run: cd frontend && bun run build")

    _kill_process_on_port(args.port)

    print("=" * 50)
    print("  semantier Server")
    print(f"  http://127.0.0.1:{args.port}")
    print("=" * 50)

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        if vite_proc:
            vite_proc.terminate()
            print("[dev] Vite stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_main())
