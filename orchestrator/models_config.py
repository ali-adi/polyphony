"""Configuration models and resolvers for agent models, thinking levels, and subagents."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field


def map_thinking_to_tokens(thinking_level: Optional[Union[str, int]]) -> Optional[int]:
    """Map human-friendly thinking levels or raw numbers to token limits for Claude/extended thinking."""
    if thinking_level is None:
        return None
    if isinstance(thinking_level, int):
        return thinking_level
    
    val = str(thinking_level).strip().lower()
    if val.isdigit():
        return int(val)
    
    mapping = {
        "low": 2048,
        "medium": 8192,
        "high": 16384,
        "max": 32768,
    }
    return mapping.get(val, 8192)


def map_thinking_to_effort(thinking_level: Optional[Union[str, int]]) -> Optional[str]:
    """Map thinking level to CLI effort string (low, medium, high) for AGY."""
    if thinking_level is None:
        return None
    if isinstance(thinking_level, int):
        if thinking_level <= 4096:
            return "low"
        elif thinking_level <= 16384:
            return "medium"
        else:
            return "high"

    val = str(thinking_level).strip().lower()
    if val in ("low", "medium", "high"):
        return val
    if val == "max":
        return "high"
    return "medium"


class AgentModelProfile(BaseModel):
    """Configuration profile for a specific agent/executor."""
    model: Optional[str] = None
    thinking_level: Optional[Union[str, int]] = None
    fallback_model: Optional[str] = None


class SubagentRoleProfile(BaseModel):
    """Profile for a specific subagent role."""
    model: Optional[str] = None
    thinking_level: Optional[Union[str, int]] = None
    description: Optional[str] = None
    prompt: Optional[str] = None


class SubagentsPolicy(BaseModel):
    """Configuration policy governing spawned subagents and workflows."""
    default_model: Optional[str] = None
    default_thinking_level: Optional[Union[str, int]] = None
    roles: Dict[str, SubagentRoleProfile] = Field(default_factory=dict)

    def to_claude_agents_json(self) -> Optional[str]:
        """Convert roles into JSON structure expected by claude CLI `--agents` flag."""
        if not self.roles:
            return None
        agents_dict = {}
        for role_name, role_cfg in self.roles.items():
            agent_def: Dict[str, Any] = {}
            if role_cfg.description:
                agent_def["description"] = role_cfg.description
            if role_cfg.model:
                agent_def["model"] = role_cfg.model
            if role_cfg.prompt:
                agent_def["prompt"] = role_cfg.prompt
            agents_dict[role_name] = agent_def
        return json.dumps(agents_dict) if agents_dict else None


class ModelsHierarchyConfig(BaseModel):
    """Resolved model and thinking configuration across all layers."""
    lead: Dict[str, AgentModelProfile] = Field(default_factory=dict)
    executors: Dict[str, AgentModelProfile] = Field(default_factory=dict)
    subagents: SubagentsPolicy = Field(default_factory=SubagentsPolicy)


def is_model_compatible(engine: str, model_name: Optional[str]) -> bool:
    """Check if a model name is compatible with a given engine to prevent cross-contamination."""
    if not model_name:
        return True
    m = model_name.lower().strip()
    claude_keywords = ("claude", "sonnet", "haiku", "opus")
    gemini_keywords = ("gemini",)

    if engine == "agy":
        if any(k in m for k in claude_keywords):
            return False
        return True
    elif engine in ("claude", "cursor"):
        if any(k in m for k in gemini_keywords):
            return False
        return True
    elif engine == "python":
        return False
    return True


def resolve_models_config(
    global_cfg: Dict[str, Any],
    project_cfg: Optional[Dict[str, Any]] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> ModelsHierarchyConfig:
    """Resolve model and thinking configuration cascading from:
    CLI Overrides -> Project Config -> Global Defaults
    """
    project_cfg = project_cfg or {}
    cli_overrides = cli_overrides or {}

    global_models = global_cfg.get("models", {})
    project_models = project_cfg.get("models", {})

    # 1. Resolve Lead Profiles
    lead_profiles: Dict[str, AgentModelProfile] = {}
    all_lead_keys = set(global_models.get("lead", {}).keys()) | set(project_models.get("lead", {}).keys()) | {"claude", "agy"}
    for lead_key in all_lead_keys:
        g_prof = global_models.get("lead", {}).get(lead_key, {})
        p_prof = project_models.get("lead", {}).get(lead_key, {})

        model = p_prof.get("model") or g_prof.get("model")
        thinking = p_prof.get("thinking_level") or g_prof.get("thinking_level")
        fallback = p_prof.get("fallback_model") or g_prof.get("fallback_model")

        # CLI overrides for lead (only override compatible engines)
        if cli_overrides.get("lead_model"):
            override_model = cli_overrides["lead_model"]
            if is_model_compatible(lead_key, override_model):
                model = override_model
        if cli_overrides.get("lead_thinking"):
            thinking = cli_overrides["lead_thinking"]

        lead_profiles[lead_key] = AgentModelProfile(
            model=model,
            thinking_level=thinking,
            fallback_model=fallback,
        )

    # 2. Resolve Executor Profiles
    executor_profiles: Dict[str, AgentModelProfile] = {}
    all_exec_keys = set(global_models.get("executors", {}).keys()) | set(project_models.get("executors", {}).keys()) | {"claude", "agy", "cursor", "python"}
    for exec_key in all_exec_keys:
        g_prof = global_models.get("executors", {}).get(exec_key, {})
        p_prof = project_models.get("executors", {}).get(exec_key, {})

        model = p_prof.get("model") or g_prof.get("model")
        thinking = p_prof.get("thinking_level") or g_prof.get("thinking_level")
        fallback = p_prof.get("fallback_model") or g_prof.get("fallback_model")

        # CLI overrides for executor (only override compatible engines)
        if cli_overrides.get("executor_model"):
            override_model = cli_overrides["executor_model"]
            if is_model_compatible(exec_key, override_model):
                model = override_model
        if cli_overrides.get("executor_thinking"):
            thinking = cli_overrides["executor_thinking"]

        executor_profiles[exec_key] = AgentModelProfile(
            model=model,
            thinking_level=thinking,
            fallback_model=fallback,
        )

    # 3. Resolve Subagents Policy
    g_sub = global_models.get("subagents", {})
    p_sub = project_models.get("subagents", {})

    default_model = p_sub.get("default_model") or g_sub.get("default_model")
    default_thinking = p_sub.get("default_thinking_level") or g_sub.get("default_thinking_level")

    if cli_overrides.get("subagent_model"):
        default_model = cli_overrides["subagent_model"]
    if cli_overrides.get("subagent_thinking"):
        default_thinking = cli_overrides["subagent_thinking"]

    merged_roles: Dict[str, SubagentRoleProfile] = {}
    all_roles = set(g_sub.get("roles", {}).keys()) | set(p_sub.get("roles", {}).keys())
    for r_key in all_roles:
        gr = g_sub.get("roles", {}).get(r_key, {})
        pr = p_sub.get("roles", {}).get(r_key, {})
        merged_roles[r_key] = SubagentRoleProfile(
            model=pr.get("model") or gr.get("model") or default_model,
            thinking_level=pr.get("thinking_level") or gr.get("thinking_level") or default_thinking,
            description=pr.get("description") or gr.get("description"),
            prompt=pr.get("prompt") or gr.get("prompt"),
        )

    subagents_policy = SubagentsPolicy(
        default_model=default_model,
        default_thinking_level=default_thinking,
        roles=merged_roles,
    )

    return ModelsHierarchyConfig(
        lead=lead_profiles,
        executors=executor_profiles,
        subagents=subagents_policy,
    )
