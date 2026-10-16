"""Model adapters for the agent loop: the live Gemini adapter and a scripted adapter for replay/tests.

The agent talks to a small neutral interface (ModelRequest -> ModelTurn). The Gemini adapter follows the
documented generate_content multi-turn function-calling protocol: the model's returned Content is appended to
history unchanged (this preserves thought signatures), and all function responses for one step are sent together
in one user turn, after the calls. Thought parts are never surfaced or logged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

ToolMode = Literal["auto", "none"]
ProviderErrorKind = Literal["missing_credentials", "auth", "quota", "model_unavailable", "invalid_request",
                            "timeout", "network", "server", "empty_response", "sdk_missing", "script_exhausted"]
# Quota (429) is deliberately NOT retried: an immediate retry has no backoff, spends another request, and cannot
# help with daily or per-minute limits inside one bounded run. The case stops with provider_quota instead.
RETRYABLE = {"timeout", "network", "server"}


class ProviderError(RuntimeError):
    def __init__(self, kind: ProviderErrorKind, detail: str = ""):
        super().__init__(f"{kind}: {detail}"[:300])
        self.kind, self.detail = kind, detail[:300]

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE


@dataclass
class Message:
    """Neutral history entry. role: user | model | tool. `native` holds the provider's own turn object."""
    role: Literal["user", "model", "tool"]
    text: str = ""
    function_calls: list[dict] = field(default_factory=list)      # model: [{"id", "name", "args"}]
    function_responses: list[dict] = field(default_factory=list)  # tool: [{"id", "name", "response"}]
    native: Any = None


@dataclass
class ModelRequest:
    kind: Literal["investigate", "finalize", "revise", "review"]
    system: str
    history: list[Message]
    tools: list[dict] | None            # agent-facing JSON specs, or None for no tools at all
    tool_mode: ToolMode
    response_schema: dict | None
    max_output_tokens: int
    timeout_s: float


@dataclass
class ModelTurn:
    function_calls: list[dict]           # [{"id", "name", "args"}]
    text: str                            # visible (non-thought) text only
    native: Any = None
    usage: dict = field(default_factory=dict)
    finish_reason: str | None = None


# --------------------------------------------------------------------------- scripted adapter

ScriptStep = Callable[[ModelRequest], "ModelTurn | ProviderError"] | ModelTurn | ProviderError


class ScriptedAdapter:
    """Deterministic adapter for replay demonstrations and tests. It never contacts a provider."""
    provider, model = "scripted", "scripted-replay"

    def __init__(self, steps: list[ScriptStep], name: str = "script"):
        self.steps, self.name, self.requests = list(steps), name, []

    def generate(self, req: ModelRequest) -> ModelTurn:
        self.requests.append(req)
        if not self.steps:
            raise ProviderError("script_exhausted", f"{self.name}: no scripted step for a '{req.kind}' request")
        step = self.steps.pop(0)
        out = step(req) if callable(step) else step
        if isinstance(out, ProviderError):
            raise out
        return out


def call(name: str, **args) -> dict:
    return {"id": None, "name": name, "args": args}


def calls(*items: dict) -> ModelTurn:
    return ModelTurn(function_calls=[dict(c, id=c["id"] or f"call-{i}") for i, c in enumerate(items)], text="")


def text(s: str | dict) -> ModelTurn:
    return ModelTurn(function_calls=[], text=s if isinstance(s, str) else json.dumps(s))


# --------------------------------------------------------------------------- Gemini adapter

class GeminiAdapter:
    """Live adapter over the official google-genai SDK. SDK retries are disabled (attempts=1); the agent loop
    owns retries so they count against its request budget and deadline."""
    provider = "gemini"

    def __init__(self, model: str, api_key: str | None, client=None):
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise ProviderError("sdk_missing", "pip install google-genai") from e
        if client is None and not api_key:
            raise ProviderError("missing_credentials", "GEMINI_API_KEY not available")
        self.model, self.types = model, types
        self.client = client or genai.Client(api_key=api_key, http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1)))

    def _content(self, m: Message):
        t = self.types
        if m.role == "user":
            return t.Content(role="user", parts=[t.Part.from_text(text=m.text)])
        if m.role == "model":
            if m.native is not None:
                return m.native                                   # unchanged: keeps thought signatures
            return t.Content(role="model", parts=[t.Part.from_text(text=m.text or "")])
        return t.Content(role="user", parts=[t.Part(function_response=t.FunctionResponse(
            id=r.get("id"), name=r["name"], response=r["response"])) for r in m.function_responses])

    def contents(self, history: list[Message]) -> list:
        """Native contents; adjacent user turns (function responses + an instruction) are merged into one turn,
        keeping all function responses of a step together and after the calls."""
        out = []
        for m in history:
            c = self._content(m)
            if out and m.role in ("user", "tool") and out[-1].role == "user":
                out[-1] = self.types.Content(role="user", parts=list(out[-1].parts) + list(c.parts))
            else:
                out.append(c)
        return out

    def generate(self, req: ModelRequest) -> ModelTurn:
        t = self.types
        from google.genai import errors
        cfg = dict(system_instruction=req.system, temperature=0, max_output_tokens=req.max_output_tokens,
                   automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True),
                   http_options=t.HttpOptions(timeout=max(1000, int(req.timeout_s * 1000)),
                                              retry_options=t.HttpRetryOptions(attempts=1)))
        if req.tools:
            cfg["tools"] = [t.Tool(function_declarations=[t.FunctionDeclaration(
                name=s["name"], description=s["description"], parameters_json_schema=s["parameters"])
                for s in req.tools])]
            cfg["tool_config"] = t.ToolConfig(function_calling_config=t.FunctionCallingConfig(
                mode=t.FunctionCallingConfigMode.AUTO if req.tool_mode == "auto" else t.FunctionCallingConfigMode.NONE))
        if req.response_schema:
            cfg["response_mime_type"] = "application/json"
            cfg["response_json_schema"] = req.response_schema
        try:
            resp = self.client.models.generate_content(model=self.model, contents=self.contents(req.history),
                                                       config=t.GenerateContentConfig(**cfg))
        except errors.APIError as e:
            code = getattr(e, "code", None)
            kind = {401: "auth", 403: "auth", 404: "model_unavailable", 429: "quota", 400: "invalid_request"}.get(
                code, "server" if code and code >= 500 else "invalid_request")
            raise ProviderError(kind, f"HTTP {code}: {getattr(e, 'message', '')}") from None
        except Exception as e:
            name = type(e).__name__
            kind = "timeout" if "Timeout" in name else "network" if any(k in name for k in ("Connect", "Network",
                                                                                          "Transport")) else "server"
            raise ProviderError(kind, name) from None
        cand = (resp.candidates or [None])[0]
        if cand is None or cand.content is None:
            raise ProviderError("empty_response", "no candidate content returned")
        parts = cand.content.parts or []
        fcs = [{"id": p.function_call.id, "name": p.function_call.name, "args": dict(p.function_call.args or {})}
               for p in parts if p.function_call is not None]
        visible = "".join(p.text for p in parts if p.text and not p.thought)
        u = resp.usage_metadata
        usage = {k: getattr(u, k, None) or 0 for k in ("prompt_token_count", "candidates_token_count",
                                                       "thoughts_token_count")} if u else {}
        return ModelTurn(function_calls=fcs, text=visible, native=cand.content, usage=usage,
                         finish_reason=str(cand.finish_reason) if cand.finish_reason else None)
