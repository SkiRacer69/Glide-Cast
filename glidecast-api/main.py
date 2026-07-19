from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from auth import create_access_token, decode_token, hash_password, verify_password
from calculator import list_venues, run_calculation
from db import create_user, get_user_by_id, get_user_by_username, init_db, user_has_access

app = FastAPI(title="GlideCast API", version="1.0.0")

cors_origins = os.environ.get("GLIDECAST_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


class SignupBody(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=128)
    email: str = ""


class LoginBody(BaseModel):
    username: str
    password: str


class CalculateBody(BaseModel):
    venue: str
    discipline: str
    race_date: str
    run1_time: str
    run2_time: str
    snow_mode: str = "Auto"
    dirty_abrasive: bool = False
    wind_coeff: float = 0.12
    solar_coeff: float = 2.0
    clear_night_coeff: float = 1.4
    longwave_coeff: float = -0.25
    latent_coeff: float = 0.06
    restore_coeff: float = 0.05
    deep_auto_relax_coeff: float = 0.02
    slope_deg: float = 19.0
    aspect_deg: float = 20.0
    lapse_cap_f_per_1000ft: float = 4.5
    cloud_attenuation: float = 0.75
    diffuse_floor_frac: float = 0.35
    albedo: float = 0.75
    wet_lock_band_f: float = 0.3
    wet_refreeze_strength: float = 3.5
    wet_deep_relax_scale: float = 0.4


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "glidecast-api"}


@app.post("/api/auth/signup")
def signup(body: SignupBody):
    if get_user_by_username(body.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    user = create_user(body.username, body.email, hash_password(body.password))
    token = create_access_token(user["id"], user["username"])
    return {"token": token, "user": _public_user(user)}


@app.post("/api/auth/login")
def login(body: LoginBody):
    user = get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user["id"], user["username"])
    return {"token": token, "user": _public_user(user)}


@app.get("/api/auth/me")
def me(user: Annotated[dict, Depends(get_current_user)]):
    return _public_user(user)


@app.get("/api/venues")
def venues(user: Annotated[dict, Depends(get_current_user)]):
    if not user_has_access(user):
        raise HTTPException(status_code=402, detail="Trial expired. Subscribe to continue.")
    return {"venues": list_venues(user)}


@app.post("/api/calculate")
def calculate(body: CalculateBody, user: Annotated[dict, Depends(get_current_user)]):
    if not user_has_access(user):
        raise HTTPException(status_code=402, detail="Trial expired. Subscribe to continue.")
    try:
        return run_calculation(user, body.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid input: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not compute recommendation: {exc}") from exc


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email") or "",
        "plan_tier": user.get("plan_tier") or "basic",
        "trial_ends_at": user.get("trial_ends_at"),
        "has_access": user_has_access(user),
    }
