"""Model adapters for the agent loop: the live Gemini adapter and a scripted adapter for replay/tests.

The agent talks to a small neutral interface (ModelRequest -> ModelTurn). The Gemini adapter follows the
documented generate_content multi-turn function-calling protocol: the model's returned Content is appended to
history unchanged (this preserves thought signatures), and all function responses for one step are sent together
in one user turn, after the calls. Thought parts are never surfaced or logged.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

ToolMode = Literal["auto", "none"]
ProviderErrorKind = Literal["missing_credentials", "auth", "quota", "model_unavailable", "invalid_request",
                            "timeout", "network", "server", "empty_response", "sdk_missing", "script_exhausted"]
# Transient failures that may be retried with bounded, jittered backoff (counted against request and time budgets).
RETRYABLE = {"timeout", "network", "server"}
# Quota (429): retried ONLY when the error body itself classifies it as a short-term rate limit. Daily or
# unclassified quota stops the case (provider_quota), and run_batch_triage stops later submissions.
QUOTA_CATEGORIES = ("rate_limit", "daily", "unclassified")


class ProviderError(RuntimeError):
    def __init__(self, kind: ProviderErrorKind, detail: str = "", *, http_status: int | None = None,
                 provider_status: str | None = None, quota_category: str | None = None,
                 retry_delay_s: float | None = None):
        super().__init__(f"{kind}: {detail}"[:300])
        self.kind, self.detail = kind, detail[:300]
        self.http_status, self.provider_status = http_status, provider_status
        self.quota_category = quota_category if kind == "quota" else None
        if self.kind == "quota" and self.quota_category is None:
            self.quota_category = "unclassified"
        self.retry_delay_s = retry_delay_s

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE or (self.kind == "quota" and self.quota_category == "rate_limit")

    def diagnostics(self) -> dict:
        """Sanitized: status codes, categories and delay only. Never keys, prompts or account identifiers."""
        return {"http_status": self.http_status, "category": self.kind, "provider_status": self.provider_status,
                "quota_category": self.quota_category, "retry_delay_s": self.retry_delay_s}


_ACCOUNT_IDS = re.compile(r"projects/[^\s,'\"]+|\b\d{6,}\b|AIza[0-9A-Za-z_\-]{20,}")


def _sanitize(text: str, limit: int = 160) -> str:
    return _ACCOUNT_IDS.sub("[redacted]", str(text or ""))[:limit]


def _parse_delay(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):                                  # {"seconds": 37, "nanos": ...}
        return float(value.get("seconds", 0)) + float(value.get("nanos", 0)) / 1e9
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", str(value or ""))  # protobuf Duration JSON, e.g. "37s"
    return float(m.group(1)) if m else None


def classify_api_error(code: int | None, status: str | None, body: Any, message: str = "") -> ProviderError:
    """Map an HTTP error to a ProviderError. Quota is classified only from explicit fields in the error body:
    an error code (rate_limit_exceeded / too_many_requests / quota_exceeded) or a QuotaFailure quotaId
    (...PerMinute... / ...PerDay...). Anything else stays 'unclassified'. RetryInfo.retryDelay is honoured."""
    err = body.get("error", body) if isinstance(body, dict) else {}
    details = err.get("details", []) if isinstance(err, dict) else []
    retry_delay, quota_ids = None, []
    for d in details if isinstance(details, list) else []:
        if not isinstance(d, dict):
            continue
        dtype = str(d.get("@type", ""))
        if dtype.endswith("RetryInfo"):
            retry_delay = _parse_delay(d.get("retryDelay"))
        elif dtype.endswith("QuotaFailure"):
            quota_ids += [str(v.get("quotaId", "")) for v in d.get("violations", []) if isinstance(v, dict)]
    err_code = err.get("code") if isinstance(err, dict) and isinstance(err.get("code"), str) else None
    quota_category = None
    if code == 429:
        if err_code == "quota_exceeded" or any("PerDay" in q for q in quota_ids):
            quota_category = "daily"
        elif err_code in ("rate_limit_exceeded", "too_many_requests") or any(
                "PerMinute" in q or "PerSecond" in q for q in quota_ids):
            quota_category = "rate_limit"
        else:
            quota_category = "unclassified"
    kind = ({401: "auth", 403: "auth", 404: "model_unavailable", 429: "quota", 400: "invalid_request",
             408: "timeout"}.get(code) or ("server" if code and code >= 500 else "invalid_request"))
    detail = f"HTTP {code} {status or ''}".strip()
    if quota_category:
        detail += f" (quota: {quota_category})"
    if retry_delay is not None:
        detail += f" retry-after {retry_delay:g}s"
    if message:
        detail += f": {_sanitize(message)}"
    return ProviderError(kind, detail, http_status=code, provider_status=status, quota_category=quota_category,
                         retry_delay_s=retry_delay)


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
        self.sdk_version = getattr(genai, "__version__", "unknown")
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
        # No temperature: Google's Gemini 3 guidance keeps the default, and the Gemini 3.8 Flash guide lists
        # temperature/top_p/top_k as deprecated sampling parameters. Thinking level stays at the model default.
        cfg = dict(system_instruction=req.system, max_output_tokens=req.max_output_tokens,
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
            # Read specific fields only; str(e) embeds the whole response body.
            raise classify_api_error(getattr(e, "code", None), getattr(e, "status", None),
                                     getattr(e, "details", None), getattr(e, "message", "") or "") from None
        except ProviderError:
            raise                                                 # e.g. refused by a request ledger: not sent
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
                         finish_reason=str(getattr(cand.finish_reason, "value", cand.finish_reason))
                         if cand.finish_reason else None)
