"""Optional, opt-in runtime check that the Gemini API is reachable and returns function calls.

Credentials come from Colab Secrets (GEMINI_API_KEY) or the environment. They are never printed, logged,
returned or written to disk. The request uses synthetic, non-sensitive text only.
"""
from __future__ import annotations

import os
import re

DEFAULT_MODEL = "gemini-3.8-flash"     # stable ID listed on ai.google.dev/gemini-api/docs/models (checked 2026-10-15)
MODEL_ENV = "PHISHTRIAGE_GEMINI_MODEL"
KEY_NAME = "GEMINI_API_KEY"
SDK_VERIFIED = "2.31.0"               # google-genai version whose interface this module was checked against
TIMEOUT_MS = 30_000
MAX_OUTPUT_TOKENS = 1024
EXPECTED_TOKEN = "preflight-ok"

SETUP_STEPS = [
    "Create a Gemini API key in Google AI Studio (aistudio.google.com) with your own Google account.",
    "In Colab, open the key icon (Secrets) in the left sidebar and add a secret named GEMINI_API_KEY.",
    "Enable 'Notebook access' for that secret in this notebook. Never paste the key into a cell or chat.",
    "Set RUN_LLM_PREFLIGHT = True in the preflight cell and run it.",
]
_NO_RETRY_CODES = {400, 401, 403, 404, 429}


def _redact(message: str, secret: str | None) -> str:
    message = str(message)
    if secret:
        message = message.replace(secret, "[REDACTED]")
    return re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[REDACTED]", message)[:500]


def get_api_key() -> str | None:
    """Colab Secrets first (if running in Colab), then the environment. Returns None when unavailable."""
    try:
        from google.colab import userdata  # type: ignore
        try:
            key = userdata.get(KEY_NAME)
            if key:
                return key
        except Exception:      # SecretNotFoundError / NotebookAccessError: fall through to the environment
            pass
    except ImportError:
        pass
    return os.environ.get(KEY_NAME) or None


def preflight(enable_network: bool = False, model: str | None = None, api_key: str | None = None,
              client_factory=None) -> dict:
    """Return a status dict; never raises for expected failures and never includes the key.

    status: skipped_opt_in_required | missing_credentials | sdk_missing | model_unavailable | auth_error |
            quota_exceeded | api_error | tool_call_missing | ok
    """
    model = model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL
    result = {"status": None, "model": model, "sdk_version": None, "checks": [], "error": None,
              "setup_steps": None, "network_calls": 0}
    if not enable_network:
        result.update(status="skipped_opt_in_required",
                      error="External calls are opt-in: set RUN_LLM_PREFLIGHT = True to run the live check.")
        return result
    key = api_key if api_key is not None else get_api_key()
    if not key:
        result.update(status="missing_credentials", error=f"{KEY_NAME} not found in Colab Secrets or the environment.",
                      setup_steps=SETUP_STEPS)
        return result
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError:
        result.update(status="sdk_missing", error="google-genai is not installed; run: pip install -q google-genai")
        return result
    result["sdk_version"] = getattr(genai, "__version__", "unknown")

    retry = types.HttpRetryOptions(attempts=2, http_status_codes=[500, 502, 503, 504])   # never retry 429 quota
    http = types.HttpOptions(timeout=TIMEOUT_MS, retry_options=retry)
    client = (client_factory or genai.Client)(api_key=key, http_options=http)

    def fail(e, step):
        code = getattr(e, "code", None)
        status = ("model_unavailable" if code == 404 and step == "model_lookup" else
                  "auth_error" if code in (401, 403) else "quota_exceeded" if code == 429 else "api_error")
        hint = {"model_unavailable": f"Model '{model}' was not found. Check the current list at "
                                     f"ai.google.dev/gemini-api/docs/models and set {MODEL_ENV}.",
                "auth_error": "The key was rejected or lacks access. Check the secret value and API enablement.",
                "quota_exceeded": "The account's quota or rate limit for this model is exhausted. Check usage limits "
                                  "in Google AI Studio, wait for the limit to reset, or set "
                                  f"{MODEL_ENV} to a model with available quota."}
        result.update(status=status, error=_redact(f"{step}: {type(e).__name__} {code or ''}: "
                                                   f"{getattr(e, 'message', None) or e}", key)
                      + (f" | {hint[status]}" if status in hint else ""))
        result["checks"].append({"step": step, "ok": False, "retryable": code not in _NO_RETRY_CODES})
        return result

    # 1. model lookup: rejects an invalid model ID before any generation request
    try:
        result["network_calls"] += 1
        info = client.models.get(model=model)
        actions = list(getattr(info, "supported_actions", None) or [])
        result["checks"].append({"step": "model_lookup", "ok": True, "supported_actions": actions[:10]})
    except errors.APIError as e:
        return fail(e, "model_lookup")
    except Exception as e:
        return fail(e, "model_lookup")

    # 2. one tiny synthetic request that must come back as a forced function call
    declaration = types.FunctionDeclaration(
        name="record_check", description="Record the preflight token.",
        parameters_json_schema={"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]})
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[declaration])],
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
            mode=types.FunctionCallingConfigMode.ANY, allowed_function_names=["record_check"])),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0, max_output_tokens=MAX_OUTPUT_TOKENS)
    try:
        result["network_calls"] += 1
        response = client.models.generate_content(
            model=model, config=config,
            contents=f"Synthetic connectivity test. Call record_check with token '{EXPECTED_TOKEN}'.")
    except errors.APIError as e:
        return fail(e, "generate_content")
    except Exception as e:
        return fail(e, "generate_content")

    calls = list(getattr(response, "function_calls", None) or [])
    ok = bool(calls) and calls[0].name == "record_check" and (calls[0].args or {}).get("token") == EXPECTED_TOKEN
    result["checks"].append({"step": "function_call", "ok": ok,
                             "returned_calls": [c.name for c in calls][:3]})
    result.update(status="ok" if ok else "tool_call_missing",
                  error=None if ok else "The model did not return the expected function call.")
    return result
