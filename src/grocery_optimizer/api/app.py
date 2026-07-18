import hmac
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from ..assistant import build_meal_assistant_response
from ..geo_discovery import discover_food_places
from ..live_pricing import get_live_price_history, get_live_pricing_engine, reload_live_pricing_engine
from ..observability import (
    configure_json_logging,
    record_request,
    request_metrics_snapshot,
    reset_request_id,
    set_request_id,
)
from ..retailer_research import load_retailer_research, summarize_retailer_research
from .schemas import CreateUserRequest, LoginRequest, OptimizeRequest, SavePlanRequest
from .service import optimize_from_request
from .storage import backup_database, database_strategy, get_schema_version
from .users import (
    create_user_profile,
    delete_saved_plan,
    get_saved_plan,
    get_saved_plans_secure_paginated,
    login_user,
    logout_all_user_sessions,
    logout_user,
    refresh_user_token,
    rename_saved_plan,
    run_token_cleanup,
    save_optimized_plan,
)

api_version = os.getenv("GROCERY_API_VERSION", "0.3.0-beta")
configure_json_logging()
logger = logging.getLogger("grocery_optimizer.api")
app = FastAPI(title="Grocery Optimizer API", version=api_version)
cors_origins = os.getenv("GROCERY_API_CORS_ORIGINS", "*")
allowed_origins = [item.strip() for item in cors_origins.split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


_pricing_scheduler_thread: threading.Thread | None = None
_pricing_scheduler_stop = threading.Event()
_pricing_scheduler_running = False
_pricing_scheduler_interval_seconds = 900
_pricing_scheduler_last_run_utc = ""
_pricing_scheduler_last_error = ""
_pricing_scheduler_watchlist: list[dict[str, Any]] = []
_rate_limit_state: dict[tuple[str, str], list[float]] = {}
_rate_limit_lock = threading.Lock()


def _security_headers() -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Cache-Control": "no-store",
    }
    if _is_production():
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


def _rate_limit_for_path(path: str) -> tuple[int, int] | None:
    if path.startswith(("/auth", "/users")):
        return 60, 60
    if path.startswith(("/optimize", "/pricing/live", "/area/scan", "/assistant/chat", "/route/road")):
        return 120, 60
    return None


def _client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_rate_limited(request: Request) -> tuple[bool, int]:
    if os.getenv("GROCERY_RATE_LIMIT_ENABLED", "true").strip().lower() in {"0", "false", "no"}:
        return False, 0

    policy = _rate_limit_for_path(request.url.path)
    if policy is None:
        return False, 0

    limit, window_seconds = policy
    now = time.monotonic()
    key = (_client_identifier(request), request.url.path)
    cutoff = now - window_seconds

    with _rate_limit_lock:
        timestamps = [ts for ts in _rate_limit_state.get(key, []) if ts > cutoff]
        if len(timestamps) >= limit:
            oldest = min(timestamps)
            retry_after = max(1, int(window_seconds - (now - oldest)))
            _rate_limit_state[key] = timestamps
            return True, retry_after
        timestamps.append(now)
        _rate_limit_state[key] = timestamps
    return False, 0


@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip() or str(uuid.uuid4())
    request_token = set_request_id(request_id)
    start = time.perf_counter()
    status_code = 500
    response = None
    try:
        limited, retry_after = _is_rate_limited(request)
        if limited:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please wait and try again."},
                headers={"Retry-After": str(retry_after)},
            )
        else:
            response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        record_request(request.method, request.url.path, status_code, duration_ms)
        logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client": _client_identifier(request),
            },
        )
        if response is not None:
            response.headers.setdefault("X-Request-ID", request_id)
            for key, value in _security_headers().items():
                response.headers.setdefault(key, value)
        reset_request_id(request_token)


def _close_http_error(error: HTTPError) -> None:
    try:
        error.close()
        return
    except Exception:
        pass

    response_body = getattr(error, "fp", None)
    if response_body and hasattr(response_body, "close"):
        try:
            response_body.close()
        except Exception:
            pass


def _resolve_auth_token(auth_token: str = "", authorization: str = "") -> str:
    if auth_token:
        return auth_token
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _default_watchlist() -> list[dict[str, Any]]:
    path = Path("config/live_pricing/watchlist.json")
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    requests = payload.get("requests", [])
    if isinstance(requests, list):
        return [cast(dict[str, Any], r) for r in requests if isinstance(r, dict)]
    return []


def _run_scheduler_cycle() -> None:
    global _pricing_scheduler_last_error
    global _pricing_scheduler_last_run_utc

    watchlist = _pricing_scheduler_watchlist or _default_watchlist()
    for item in watchlist:
        payload = OptimizeRequest(
            budget=float(item.get("budget", 50.0)),
            max_items=int(item.get("max_items", 8)),
            strategy=str(item.get("strategy", "knapsack")),
            location=str(item.get("location", "montreal")),
            postal_code=str(item.get("postal_code", "")),
            required_categories=list(item.get("required_categories", [])),
            excluded_categories=list(item.get("excluded_categories", [])),
        )
        optimize_from_request(payload)

    _pricing_scheduler_last_run_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _pricing_scheduler_last_error = ""


def _pricing_scheduler_loop() -> None:
    global _pricing_scheduler_running
    global _pricing_scheduler_last_error
    while not _pricing_scheduler_stop.is_set():
        try:
            _run_scheduler_cycle()
        except Exception as exc:
            _pricing_scheduler_last_error = str(exc)

        # Wait with cancel support
        waited = 0
        while waited < _pricing_scheduler_interval_seconds and not _pricing_scheduler_stop.is_set():
            time.sleep(1)
            waited += 1
    _pricing_scheduler_running = False


def _environment_name() -> str:
    return os.getenv("GROCERY_ENV", "development").strip().lower()


def _is_production() -> bool:
    return _environment_name() in {"prod", "production"}


def _truthy_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def validate_runtime_config() -> dict[str, Any]:
    """Return deployment-readiness checks with production errors separated from warnings."""
    env_name = _environment_name()
    origins = [item.strip() for item in os.getenv("GROCERY_API_CORS_ORIGINS", "*").split(",") if item.strip()]
    admin_token = os.getenv("GROCERY_ADMIN_TOKEN", "")
    public_base_url = os.getenv("GROCERY_PUBLIC_BASE_URL", "").strip()
    db_strategy = database_strategy()
    errors: list[str] = []
    warnings: list[str] = []

    if _is_production():
        if not origins or "*" in origins:
            errors.append("Set GROCERY_API_CORS_ORIGINS to explicit production frontend origins; wildcard CORS is blocked.")
        if not admin_token:
            errors.append("Set GROCERY_ADMIN_TOKEN before enabling production maintenance endpoints.")
        elif len(admin_token) < 24:
            warnings.append("GROCERY_ADMIN_TOKEN should be at least 24 random characters.")
        if not public_base_url.startswith("https://"):
            errors.append("Set GROCERY_PUBLIC_BASE_URL to the public HTTPS URL served by the deployment.")
        if db_strategy["driver"] == "sqlite" and not _truthy_env("GROCERY_ALLOW_SQLITE_IN_PRODUCTION"):
            errors.append("Use GROCERY_DATABASE_URL with PostgreSQL for production, or explicitly set GROCERY_ALLOW_SQLITE_IN_PRODUCTION=true for a single-instance pilot.")
        if db_strategy["driver"] == "postgresql" and not _truthy_env("GROCERY_MANAGED_BACKUPS_ENABLED"):
            errors.append("Enable managed PostgreSQL backups and set GROCERY_MANAGED_BACKUPS_ENABLED=true.")
        if db_strategy["driver"] == "sqlite" and not os.getenv("GROCERY_BACKUP_DIR", "").strip():
            warnings.append("Set GROCERY_BACKUP_DIR and schedule /maintenance/backup-database for SQLite pilot backups.")
    else:
        if "*" in origins:
            warnings.append("Wildcard CORS is fine locally but must be replaced before production.")
        if db_strategy["driver"] == "sqlite":
            warnings.append("SQLite is suitable for local/dev and single-instance pilots only; use PostgreSQL for production.")

    return {
        "environment": env_name,
        "production": _is_production(),
        "database": db_strategy,
        "cors_origins": origins,
        "https_configured": public_base_url.startswith("https://"),
        "admin_token_configured": bool(admin_token),
        "managed_backups_enabled": _truthy_env("GROCERY_MANAGED_BACKUPS_ENABLED"),
        "errors": errors,
        "warnings": warnings,
        "ready": not errors,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    db_path = os.getenv("GROCERY_DB_PATH", "data/grocery_optimizer.db")
    try:
        schema_version = get_schema_version(db_path=db_path)
        db_ok = True
    except Exception:
        schema_version = None
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "grocery-optimizer-api",
        "version": api_version,
        "database": {
            "path": db_path,
            "ok": db_ok,
            "schema_version": schema_version,
            "strategy": database_strategy(),
        },
    }


@app.get("/ready")
def ready() -> dict[str, Any]:
    db_path = os.getenv("GROCERY_DB_PATH", "data/grocery_optimizer.db")
    try:
        schema_version = get_schema_version(db_path=db_path)
        config = validate_runtime_config()
        if _is_production() and config["errors"]:
            raise HTTPException(status_code=503, detail={"message": "Production configuration is not ready", **config})
        return {
            "ready": True,
            "version": api_version,
            "schema_version": schema_version,
            "deployment": config,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Readiness failed: {exc}") from exc


def _service_metadata() -> dict[str, Any]:
    return {
        "service": "grocery-optimizer-api",
        "status": "ok",
        "version": api_version,
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
        "web_ui": "http://127.0.0.1:8080",
        "area_scan": "/area/scan?postal_code=H3A1A1",
        "pricing_live": "/pricing/live",
        "pricing_providers": "/pricing/providers",
        "pricing_history": "/pricing/history?postal_code=H3A1A1",
        "pricing_scheduler_status": "/pricing/scheduler/status",
        "observability_metrics": "/observability/metrics",
        "deployment_status": "/deployment/status",
        "retailer_research": "/retailer-research/montreal",
    }


@app.get("/")
def root() -> Any:
    if os.getenv("VERCEL", "").strip().lower() in {"1", "true", "yes"}:
        return RedirectResponse(url="/index.html", status_code=307)
    return _service_metadata()


@app.get("/api")
def api_root() -> dict[str, Any]:
    return _service_metadata()


@app.get("/locations")
def locations() -> dict[str, Any]:
    """List available locations with their details."""
    from ..location import list_available_locations, load_location_profile

    location_ids = list_available_locations()
    details = []

    for loc_id in location_ids:
        try:
            profile = load_location_profile(loc_id)
            details.append({
                "location_id": profile.location_id,
                "display_name": profile.display_name,
                "currency": profile.currency,
                "price_multiplier": profile.price_multiplier,
                "category_price_multipliers": profile.category_price_multipliers,
                "supported_postal_prefixes": profile.supported_postal_prefixes,
                "store_chains": profile.stores,
                "retailer_research": summarize_retailer_research(profile.location_id),
            })
        except Exception:
            pass

    return {"locations": details}


@app.get("/retailer-research/{location_id}")
def retailer_research(location_id: str) -> dict[str, Any]:
    """Return market-specific retailer research imported from planning workbooks."""
    research = load_retailer_research(location_id)
    if not research:
        raise HTTPException(status_code=404, detail="Retailer research is not available for this location")
    return {"research": research, "summary": summarize_retailer_research(location_id)}


@app.get("/stores")
def get_stores(
    postal_code: str = "",
    location: str = "",
    max_distance: float = Query(default=20.0, gt=0, le=100),
) -> dict[str, Any]:
    """Get stores near a postal code or all stores in a location."""
    from ..stores import find_nearby_stores, load_postal_codes, load_stores

    all_stores = load_stores()

    if postal_code:
        postal_codes = load_postal_codes()
        nearby = find_nearby_stores(postal_code, all_stores, postal_codes, max_distance_km=max_distance)

        stores_data = [
            {
                "store_id": store.store_id,
                "name": store.name,
                "chain": store.chain,
                "address": store.address,
                "postal_code": store.postal_code,
                "latitude": store.latitude,
                "longitude": store.longitude,
                "distance_km": distance,
                "price_tier": store.price_tier,
                "quality_rating": store.quality_rating,
                "location_id": store.location_id,
            }
            for store, distance in nearby
        ]

        return {
            "postal_code": postal_code,
            "max_distance_km": max_distance,
            "stores": stores_data,
            "count": len(stores_data),
        }

    elif location:
        filtered = [s for s in all_stores if s.location_id == location]
        stores_data = [
            {
                "store_id": store.store_id,
                "name": store.name,
                "chain": store.chain,
                "address": store.address,
                "postal_code": store.postal_code,
                "latitude": store.latitude,
                "longitude": store.longitude,
                "price_tier": store.price_tier,
                "quality_rating": store.quality_rating,
                "location_id": store.location_id,
            }
            for store in filtered
        ]

        return {
            "location": location,
            "stores": stores_data,
            "count": len(stores_data),
        }

    else:
        raise HTTPException(status_code=400, detail="Provide postal_code or location parameter")


@app.get("/area/scan")
def area_scan(
    postal_code: str,
    radius_km: float = Query(default=12.0, gt=0, le=100),
    country_hint: str = "",
) -> dict[str, Any]:
    """Automatically scan nearby food places for a postal code using public map data."""
    if not postal_code:
        raise HTTPException(status_code=400, detail="postal_code is required")
    return discover_food_places(postal_code=postal_code, radius_km=radius_km, country_hint=country_hint)


@app.get("/postal-codes")
def get_postal_codes(country: str = "") -> dict[str, Any]:
    """Get supported postal codes, optionally filtered by country."""
    from ..stores import load_postal_codes

    all_postal_codes = load_postal_codes()

    if country:
        filtered = {
            pc: info for pc, info in all_postal_codes.items()
            if info.country.upper() == country.upper()
        }
    else:
        filtered = all_postal_codes

    postal_data = [
        {
            "postal_code": info.postal_code,
            "city": info.city,
            "province_state": info.province_state,
            "country": info.country,
            "latitude": info.latitude,
            "longitude": info.longitude,
        }
        for info in filtered.values()
    ]

    return {
        "postal_codes": postal_data,
        "count": len(postal_data),
        "countries": sorted(set(info.country for info in all_postal_codes.values())),
    }


ADMIN_OPEN_ENVIRONMENTS = {"", "dev", "development", "local", "test", "testing"}


@app.post("/optimize")
def optimize(request: OptimizeRequest) -> dict[str, Any]:
    return optimize_from_request(request)


class AssistantChatRequest(BaseModel):
    message: str = ""
    plan_items: list[dict[str, Any]] = []
    likes: list[str] = []
    dislikes: list[str] = []
    health_goals: list[str] = []


class RoutePoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RoadRouteRequest(BaseModel):
    points: list[RoutePoint] = Field(min_length=2, max_length=8)


def _fetch_osrm_route(points: list[RoutePoint]) -> dict[str, Any]:
    base_url = os.getenv("GROCERY_OSRM_ROUTE_URL", "https://router.project-osrm.org").rstrip("/")
    coords = ";".join(f"{point.longitude:.6f},{point.latitude:.6f}" for point in points)
    url = f"{base_url}/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=false"
    req = UrlRequest(
        url=url,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "grocery-planner/0.3"},
    )

    try:
        with urlopen(req, timeout=8) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
    except HTTPError as error:
        _close_http_error(error)
        raise HTTPException(status_code=502, detail="Road routing service rejected the route request.") from error
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Road routing service is unavailable.") from exc

    route = (data.get("routes") or [{}])[0]
    raw_coordinates = route.get("geometry", {}).get("coordinates", [])
    if not isinstance(raw_coordinates, list) or len(raw_coordinates) < 2:
        raise HTTPException(status_code=502, detail="Road routing service returned no usable route.")

    coordinates = [
        {"latitude": float(coord[1]), "longitude": float(coord[0])}
        for coord in raw_coordinates
        if isinstance(coord, (list, tuple)) and len(coord) >= 2
    ]
    if len(coordinates) < 2:
        raise HTTPException(status_code=502, detail="Road routing service returned invalid coordinates.")

    return {
        "coordinates": coordinates,
        "distance_km": round(float(route.get("distance", 0.0)) / 1000, 2),
        "duration_minutes": round(float(route.get("duration", 0.0)) / 60, 1),
        "provider": "osrm",
    }


@app.post("/assistant/chat")
def assistant_chat(request: AssistantChatRequest) -> dict[str, Any]:
    """Return meal suggestions based on planned groceries and user preferences/goals."""
    result = build_meal_assistant_response(
        user_message=request.message,
        plan_items=request.plan_items,
        likes=request.likes,
        dislikes=request.dislikes,
        health_goals=request.health_goals,
    )
    return result


@app.post("/route/road")
def road_route(request: RoadRouteRequest) -> dict[str, Any]:
    """Return road-following route geometry for the selected shopping path."""
    return {"route": _fetch_osrm_route(request.points)}


@app.get("/assistant/status")
def assistant_status() -> dict[str, Any]:
    mode = os.getenv("GROCERY_ASSISTANT_MODE", "hybrid").strip().lower()
    model = os.getenv("GROCERY_ASSISTANT_OLLAMA_MODEL", "llama3.2:3b")
    base_url = os.getenv("GROCERY_ASSISTANT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

    ollama_reachable = False
    if mode in {"hybrid", "ollama"}:
        try:
            req = UrlRequest(url=f"{base_url}/api/tags", method="GET")
            with urlopen(req, timeout=2):
                ollama_reachable = True
        except HTTPError as error:
            _close_http_error(error)
            ollama_reachable = False
        except (URLError, TimeoutError, ValueError):
            ollama_reachable = False

    return {
        "assistant_mode": mode,
        "ollama": {
            "base_url": base_url,
            "model": model,
            "reachable": ollama_reachable,
        },
    }


@app.get("/pricing/live")
def live_pricing(
    location: str = "montreal",
    postal_code: str = "",
    address: str = "",
    budget: float = Query(default=50.0, gt=0),
    max_items: int = Query(default=8, ge=1, le=100),
    strategy: Literal["greedy", "knapsack"] = "knapsack",
    transportation_mode: Literal["walk", "transit", "drive"] = "transit",
    country_hint: str = "",
) -> dict[str, Any]:
    """Return a live pricing snapshot for nearby stores and optimized route."""
    payload = OptimizeRequest(
        budget=budget,
        max_items=max_items,
        strategy=strategy,
        location=location,
        postal_code=postal_code,
        address=address,
        transportation_mode=transportation_mode,
        country_hint=country_hint,
        include_live_pricing=True,
    )
    result = optimize_from_request(payload)
    return {
        "location": result.get("location", {}),
        "summary": result.get("summary", {}),
        "stores": result.get("stores", {}),
        "route": result.get("route"),
    }


@app.get("/pricing/providers")
def pricing_providers() -> dict[str, Any]:
    """Return health/config status of third-party live pricing providers."""
    engine = get_live_pricing_engine()
    health = engine.provider_health()
    return {
        "providers": health,
        "enabled_count": sum(1 for p in health if p.get("enabled")),
        "configured_count": sum(1 for p in health if p.get("configured")),
    }


@app.get("/pricing/history")
def pricing_history(postal_code: str, limit: int = Query(default=200, ge=1, le=2000)) -> dict[str, Any]:
    """Get historical live price quotes for a postal code."""
    if not postal_code:
        raise HTTPException(status_code=400, detail="postal_code is required")
    rows = get_live_price_history(postal_code=postal_code, limit=limit)
    return {
        "postal_code": postal_code.upper().replace(" ", ""),
        "count": len(rows),
        "quotes": rows,
    }


@app.post("/pricing/providers/reload")
def pricing_providers_reload(authorization: str = Header(default="")) -> dict[str, Any]:
    """Reload live pricing provider config from disk without restarting API."""
    _verify_admin_token(authorization)
    engine = reload_live_pricing_engine()
    health = engine.provider_health()
    return {
        "reloaded": True,
        "providers": health,
        "enabled_count": sum(1 for p in health if p.get("enabled")),
        "configured_count": sum(1 for p in health if p.get("configured")),
    }


@app.get("/pricing/scheduler/status")
def pricing_scheduler_status() -> dict[str, Any]:
    watchlist = _pricing_scheduler_watchlist or _default_watchlist()
    return {
        "running": _pricing_scheduler_running,
        "interval_seconds": _pricing_scheduler_interval_seconds,
        "watchlist_count": len(watchlist),
        "last_run_utc": _pricing_scheduler_last_run_utc,
        "last_error": _pricing_scheduler_last_error,
    }


@app.post("/pricing/scheduler/start")
def pricing_scheduler_start(request: dict[str, Any] | None = None, authorization: str = Header(default="")) -> dict[str, Any]:
    _verify_admin_token(authorization)
    global _pricing_scheduler_running
    global _pricing_scheduler_interval_seconds
    global _pricing_scheduler_watchlist
    global _pricing_scheduler_thread

    if _pricing_scheduler_running:
        return {
            "started": False,
            "detail": "Scheduler already running",
            "running": True,
        }

    payload = request or {}
    interval_seconds = int(payload.get("interval_seconds", 900))
    _pricing_scheduler_interval_seconds = max(60, min(interval_seconds, 86400))

    watchlist = payload.get("watchlist", [])
    if isinstance(watchlist, list) and watchlist:
        _pricing_scheduler_watchlist = [cast(dict[str, Any], item) for item in watchlist if isinstance(item, dict)]
    else:
        _pricing_scheduler_watchlist = []

    _pricing_scheduler_stop.clear()
    _pricing_scheduler_running = True
    _pricing_scheduler_thread = threading.Thread(target=_pricing_scheduler_loop, daemon=True)
    _pricing_scheduler_thread.start()

    return {
        "started": True,
        "running": True,
        "interval_seconds": _pricing_scheduler_interval_seconds,
        "watchlist_count": len(_pricing_scheduler_watchlist or _default_watchlist()),
    }


@app.post("/pricing/scheduler/stop")
def pricing_scheduler_stop(authorization: str = Header(default="")) -> dict[str, Any]:
    _verify_admin_token(authorization)
    global _pricing_scheduler_running
    if not _pricing_scheduler_running:
        return {
            "stopped": False,
            "detail": "Scheduler is not running",
            "running": False,
        }

    _pricing_scheduler_stop.set()
    _pricing_scheduler_running = False
    return {
        "stopped": True,
        "running": False,
    }


@app.get("/observability/metrics")
def observability_metrics(authorization: str = Header(default="")) -> dict[str, Any]:
    """Return in-process request/provider metrics. Protected in production."""
    _verify_admin_token(authorization)
    return request_metrics_snapshot()


@app.get("/deployment/status")
def deployment_status(authorization: str = Header(default="")) -> dict[str, Any]:
    """Return production hardening status and actionable config checks."""
    _verify_admin_token(authorization)
    return validate_runtime_config()


@app.post("/maintenance/backup-database")
def backup_database_endpoint(authorization: str = Header(default="")) -> dict[str, Any]:
    """Create a timestamped local SQLite backup for single-instance/pilot deployments."""
    _verify_admin_token(authorization)
    backup_dir = os.getenv("GROCERY_BACKUP_DIR", "data/backups")
    try:
        return backup_database(db_path=os.getenv("GROCERY_DB_PATH", "data/grocery_optimizer.db"), backup_dir=backup_dir)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/sample-request")
def sample_request() -> dict[str, Any]:
    return OptimizeRequest().model_dump()


@app.post("/users")
def create_user(request: CreateUserRequest) -> dict[str, Any]:
    try:
        return create_user_profile(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/auth/login")
def login(request: LoginRequest) -> dict[str, Any]:
    try:
        return login_user(request)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


class AuthTokenRequest(BaseModel):
    user_id: str = ""
    auth_token: str = ""


@app.post("/auth/refresh")
def refresh_token(request: AuthTokenRequest, authorization: str = Header(default="")) -> dict[str, Any]:
    token = _resolve_auth_token(auth_token=request.auth_token, authorization=authorization)
    try:
        return refresh_user_token(request.user_id, token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/auth/logout")
def logout(request: AuthTokenRequest, authorization: str = Header(default="")) -> dict[str, Any]:
    token = _resolve_auth_token(auth_token=request.auth_token, authorization=authorization)
    try:
        return logout_user(request.user_id, token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/auth/logout-all")
def logout_all(request: AuthTokenRequest, authorization: str = Header(default="")) -> dict[str, Any]:
    token = _resolve_auth_token(auth_token=request.auth_token, authorization=authorization)
    try:
        return logout_all_user_sessions(request.user_id, token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


class SavePlanForUserRequest(BaseModel):
    label: str = "Untitled Plan"
    optimize_request: dict[str, Any] = Field(default_factory=dict)
    optimization_result: dict[str, Any] | None = None
    auth_token: str = ""


@app.post("/users/{user_id}/plans")
def save_plan_for_user(
    user_id: str,
    request: SavePlanForUserRequest,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    optimize_payload = OptimizeRequest(**request.optimize_request)
    payload = SavePlanRequest(
        label=request.label,
        optimize_request=optimize_payload,
        optimization_result=request.optimization_result,
    )
    token = _resolve_auth_token(auth_token=request.auth_token, authorization=authorization)
    try:
        return save_optimized_plan(user_id, payload, auth_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/users/{user_id}/plans")
def list_plans_for_user(
    user_id: str,
    auth_token: str = "",
    authorization: str = Header(default=""),
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    token = _resolve_auth_token(auth_token=auth_token, authorization=authorization)
    try:
        return get_saved_plans_secure_paginated(user_id, auth_token=token, limit=limit, offset=offset)
    except ValueError as exc:
        message = str(exc)
        if message.lower().startswith("invalid pagination"):
            raise HTTPException(status_code=400, detail=message) from exc
        raise HTTPException(status_code=401, detail=message) from exc


@app.get("/users/{user_id}/plans/{plan_id}")
def get_plan_for_user(
    user_id: str,
    plan_id: str,
    auth_token: str = "",
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    token = _resolve_auth_token(auth_token=auth_token, authorization=authorization)
    try:
        return get_saved_plan(user_id=user_id, plan_id=plan_id, auth_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/users/{user_id}/plans/{plan_id}")
def delete_plan_for_user(
    user_id: str,
    plan_id: str,
    auth_token: str = "",
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    token = _resolve_auth_token(auth_token=auth_token, authorization=authorization)
    try:
        return delete_saved_plan(user_id=user_id, plan_id=plan_id, auth_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class RenamePlanRequest(BaseModel):
    label: str = ""
    auth_token: str = ""


@app.patch("/users/{user_id}/plans/{plan_id}")
def rename_plan_for_user(
    user_id: str,
    plan_id: str,
    request: RenamePlanRequest,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    token = _resolve_auth_token(auth_token=request.auth_token, authorization=authorization)
    try:
        return rename_saved_plan(
            user_id=user_id,
            plan_id=plan_id,
            label=request.label,
            auth_token=token,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "Label is required":
            raise HTTPException(status_code=400, detail=message) from exc
        raise HTTPException(status_code=404, detail=message) from exc


def _verify_admin_token(authorization: str = Header(default="")) -> None:
    """Verify admin token for protected maintenance endpoints."""
    admin_token = os.getenv("GROCERY_ADMIN_TOKEN", "")
    env_name = os.getenv("GROCERY_ENV", "development").strip().lower()
    if not admin_token:
        if env_name in ADMIN_OPEN_ENVIRONMENTS:
            return
        raise HTTPException(status_code=503, detail="Admin token is not configured")
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not hmac.compare_digest(token, admin_token):
        raise HTTPException(status_code=403, detail="Admin access required")


@app.post("/maintenance/cleanup-tokens")
def cleanup_auth_tokens(authorization: str = Header(default="")) -> dict[str, Any]:
    _verify_admin_token(authorization)
    return run_token_cleanup()
