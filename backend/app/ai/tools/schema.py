"""ToolSpec -> OpenAI function schema (the input Call B needs).

Schemas are built by introspecting the tool function's own signature, so a tool
can never drift from its advertised contract — there is no second place to edit.

Two things are deliberately never emitted:
  * `ctx` and `db` — injected by the registry, not by the model;
  * anything in IDENTITY_ARGS — RBAC Layer 3 strips those at invoke time, and
    omitting them here means the model is never even shown a `student_id` field
    to hallucinate a value into. Layer 3 stays as the enforcing check; this is
    just the cheaper first line.
"""
from __future__ import annotations

import inspect
import types
import typing
from typing import Any

from app.auth.context import Role
from app.ai.tools.registry import IDENTITY_ARGS, REGISTRY, ToolSpec

INJECTED = frozenset({"ctx", "db", "confirmed"})

_JSON_TYPES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _unwrap_optional(annotation: Any) -> Any:
    """`str | None` -> `str`. Optional-ness is carried by `required`, not by type."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _json_type(annotation: Any) -> str:
    annotation = _unwrap_optional(annotation)
    base = typing.get_origin(annotation) or annotation
    return _JSON_TYPES.get(base, "string")


def function_schema(spec: ToolSpec) -> dict[str, Any]:
    """One tool in OpenAI wire format, ready to hand to `provider.chat(tools=...)`."""
    try:
        hints = typing.get_type_hints(spec.fn)
    except Exception:  # a tool with an unresolvable annotation must not kill the turn
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in inspect.signature(spec.fn).parameters.items():
        if name in INJECTED or name in IDENTITY_ARGS:
            continue
        if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue  # the `**_` catch-all every tool carries

        properties[name] = {"type": _json_type(hints.get(name, param.annotation))}
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def schemas_for(names: list[str] | tuple[str, ...], role: Role) -> list[dict[str, Any]]:
    """Schemas for `names`, silently dropping any the role may not see (Layer 1).

    Call A picks the names, and Call A is an LLM: an unknown or off-limits name
    is an expected input here, not an error.
    """
    out = []
    for name in names:
        if name not in REGISTRY:
            continue
        spec = REGISTRY.get(name)
        if spec.visible_to(role):
            out.append(function_schema(spec))
    return out


def required_params(spec: ToolSpec) -> list[str]:
    """Params the model must supply — used to spot the no-argument fast path."""
    return function_schema(spec)["function"]["parameters"]["required"]
