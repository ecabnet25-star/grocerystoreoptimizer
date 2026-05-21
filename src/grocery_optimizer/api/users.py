from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from .schemas import CreateUserRequest, LoginRequest, SavePlanRequest
from .service import optimize_from_request
from .storage import (
    DEFAULT_DB_PATH,
    cleanup_tokens,
    count_user_plans,
    create_user,
    create_user_token,
    delete_user_plan,
    get_user,
    get_user_auth_by_email,
    get_user_plan,
    list_user_plans,
    revoke_all_user_tokens,
    revoke_user_token,
    save_plan,
    update_user_plan_label,
    validate_user_token,
)

PASSWORD_HASH_ITERATIONS = 260_000


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def _verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        algorithm, iterations_text, salt, expected = stored_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256" or iterations < 100_000:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(actual, expected)


def _default_db_path_str() -> str:
    return str(Path(DEFAULT_DB_PATH))


def verify_user_access(user_id: str, auth_token: str, db_path: str = "") -> None:
    if not auth_token:
        raise ValueError("Auth token is required")
    db = db_path or _default_db_path_str()
    if not validate_user_token(user_id, auth_token, db_path=db):
        raise ValueError("Invalid auth token")


def create_user_profile(request: CreateUserRequest, db_path: str = "") -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    if not request.name.strip() or not request.email.strip():
        raise ValueError("Name and email are required")
    if len(request.password) < 8:
        raise ValueError("Password must be at least 8 characters")

    try:
        user = create_user(
            name=request.name.strip(),
            email=request.email.strip(),
            password_hash=_hash_password(request.password),
            db_path=db,
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("Email already exists") from exc

    token = create_user_token(user["id"], db_path=db)
    return {"user": user, "auth_token": token}


def login_user(request: LoginRequest, db_path: str = "") -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    email = request.email.strip().lower()
    if not email:
        raise ValueError("Email is required")

    user = get_user_auth_by_email(email, db_path=db)
    if user is None:
        raise ValueError("User not found")
    if not _verify_password(request.password, user.get("password_hash")):
        raise ValueError("Invalid email or password")

    token = create_user_token(user["id"], db_path=db)
    user.pop("password_hash", None)
    return {"user": user, "auth_token": token}


def refresh_user_token(user_id: str, auth_token: str, db_path: str = "") -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    revoked = revoke_user_token(user_id, auth_token, db_path=db)
    if not revoked:
        raise ValueError("Invalid auth token")
    new_token = create_user_token(user_id, db_path=db)
    return {"user_id": user_id, "auth_token": new_token}


def logout_user(user_id: str, auth_token: str, db_path: str = "") -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    revoked = revoke_user_token(user_id, auth_token, db_path=db)
    if not revoked:
        raise ValueError("Invalid auth token")
    return {"user_id": user_id, "revoked": True}


def logout_all_user_sessions(user_id: str, auth_token: str, db_path: str = "") -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    count = revoke_all_user_tokens(user_id, db_path=db)
    return {"user_id": user_id, "revoked_count": count}


def delete_saved_plan(
    user_id: str, plan_id: str, auth_token: str, db_path: str = ""
) -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    deleted = delete_user_plan(user_id=user_id, plan_id=plan_id, db_path=db)
    if not deleted:
        raise ValueError("Plan not found")
    return {"user_id": user_id, "plan_id": plan_id, "deleted": True}


def rename_saved_plan(
    user_id: str, plan_id: str, label: str, auth_token: str, db_path: str = ""
) -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    next_label = label.strip()
    if not next_label:
        raise ValueError("Label is required")
    renamed = update_user_plan_label(
        user_id=user_id, plan_id=plan_id, label=next_label, db_path=db
    )
    if not renamed:
        raise ValueError("Plan not found")
    return {"user_id": user_id, "plan_id": plan_id, "label": next_label, "updated": True}


def run_token_cleanup(db_path: str = "") -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    removed = cleanup_tokens(db_path=db)
    return {"removed_tokens": removed}


def save_optimized_plan(
    user_id: str, request: SavePlanRequest, auth_token: str, db_path: str = ""
) -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    user = get_user(user_id, db_path=db)
    if user is None:
        raise ValueError("User not found")

    optimization_result = optimize_from_request(request.optimize_request)
    saved = save_plan(
        user_id=user_id,
        label=request.label,
        request_payload={
            "label": request.label,
            "optimize_request": request.optimize_request.model_dump(),
        },
        result_payload=optimization_result,
        db_path=db,
    )

    return {"saved": saved, "result": optimization_result}


def get_saved_plans_secure(user_id: str, auth_token: str, db_path: str = "") -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    user = get_user(user_id, db_path=db)
    if user is None:
        raise ValueError("User not found")

    return {"user": user, "plans": list_user_plans(user_id, db_path=db)}


def get_saved_plans_secure_paginated(
    user_id: str,
    auth_token: str,
    limit: int = 20,
    offset: int = 0,
    db_path: str = "",
) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise ValueError("Invalid pagination: limit must be between 1 and 100")
    if offset < 0:
        raise ValueError("Invalid pagination: offset must be >= 0")

    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    user = get_user(user_id, db_path=db)
    if user is None:
        raise ValueError("User not found")

    plans = list_user_plans(user_id, limit=limit, offset=offset, db_path=db)
    total = count_user_plans(user_id, db_path=db)
    return {
        "user": user,
        "plans": plans,
        "pagination": {"limit": limit, "offset": offset, "total": total},
    }


def get_saved_plan(
    user_id: str, plan_id: str, auth_token: str, db_path: str = ""
) -> dict[str, Any]:
    db = db_path or _default_db_path_str()
    verify_user_access(user_id, auth_token, db_path=db)
    plan = get_user_plan(user_id=user_id, plan_id=plan_id, db_path=db)
    if plan is None:
        raise ValueError("Plan not found")
    return {"plan": plan}


# ---------------------------------------------------------------------------
# Backwards-compatible aliases for the former ``_with_db`` variants.
# Tests and other callers that imported these names will continue to work
# because every public function now accepts an optional ``db_path`` keyword.
# ---------------------------------------------------------------------------
create_user_profile_with_db = create_user_profile
login_user_with_db = login_user
refresh_user_token_with_db = refresh_user_token
logout_user_with_db = logout_user
delete_saved_plan_with_db = delete_saved_plan
rename_saved_plan_with_db = rename_saved_plan
save_optimized_plan_with_db = save_optimized_plan
get_saved_plans_with_db = get_saved_plans_secure
get_saved_plans_paginated_with_db = get_saved_plans_secure_paginated
get_saved_plan_with_db = get_saved_plan
