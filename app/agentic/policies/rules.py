from __future__ import annotations

import re
from typing import Any

FORBIDDEN_ACTIONS = frozenset(
    {
        "approve_campaign",
        "reject_campaign",
        "publish_campaign",
        "delete_campaign",
        "delete_workflow_history",
        "modify_actor_role",
        "modify_roles",
        "modify_permissions",
        "access_secrets",
        "execute_sql",
        "execute_shell",
        "call_arbitrary_url",
        "disable_audit",
        "change_policy_rules",
    }
)
GENERIC_ACTIONS = frozenset(
    {
        "update_anything",
        "modify_record",
        "execute_command",
        "run_query",
        "call_url",
        "patch_resource",
    }
)
DANGEROUS_ARGUMENT_KEYS = frozenset(
    {
        "action",
        "action_name",
        "command",
        "sql",
        "query",
        "url",
        "authorization",
        "api_key",
        "password",
        "secret",
        "token",
    }
)


def canonical_action_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def is_forbidden_alias(value: str) -> bool:
    canonical = canonical_action_name(value)
    return canonical in FORBIDDEN_ACTIONS or canonical in GENERIC_ACTIONS


def contains_nested_danger(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            canonical_key = canonical_action_name(str(key))
            if canonical_key in DANGEROUS_ARGUMENT_KEYS:
                return True
            if contains_nested_danger(item):
                return True
        return False
    if isinstance(value, list):
        return any(contains_nested_danger(item) for item in value)
    if isinstance(value, str):
        return is_forbidden_alias(value) or value.lower().startswith(
            ("http://", "https://")
        )
    return False
