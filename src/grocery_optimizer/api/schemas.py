from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    budget: float = Field(default=50.0, gt=0)
    max_items: int = Field(default=10, ge=1, le=100)
    strategy: Literal["greedy", "knapsack"] = "greedy"
    transportation_mode: Literal["walk", "transit", "drive"] = "transit"
    country_hint: str = ""
    required_categories: list[str] = Field(default_factory=list)
    must_have_items: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)
    nutrition_weight: float = Field(default=1.0, ge=0)
    shelf_life_weight: float = Field(default=0.25, ge=0)
    cost_weight: float = Field(default=1.0, ge=0)
    location: str = "montreal"
    postal_code: str = ""
    address: str = ""
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    health_goals: list[str] = Field(default_factory=list)
    catalog_path: str = "config/catalog.json"
    include_live_pricing: bool = False


class CreateUserRequest(BaseModel):
    name: str
    email: str
    password: str = Field(min_length=8, max_length=256)


class SavePlanRequest(BaseModel):
    label: str = "Untitled Plan"
    optimize_request: OptimizeRequest = Field(default_factory=OptimizeRequest)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)
