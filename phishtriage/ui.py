"""Notebook interface: reusable session logic, safe HTML rendering, and a thin ipywidgets front end.

All logic lives in TriageSession (testable without widgets). build_interface() only wires widgets to it.
Nothing here renders email HTML, loads remote content, creates clickable links, fetches URLs or opens attachments:
every piece of email-derived or model-written text is HTML-escaped before display.
"""
from __future__ import annotations

import hashlib
import html
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import agent as A
from . import agent_replays as AR
from . import email_input as EI
from .export import disagreement, report_export, verification_record

SOURCES = ("pasted", "eml", "synthetic")
MODES = ("evidence_only", "replay", "live")
STATUS_LABELS = {"approved": "Completed: reviewer approved", "evidence_only": "Completed: evidence only (no LLM)",
                 "needs_human_review": "Needs human review", "failed": "Failed"}
PARTIAL_TERMINATIONS = {"budget_exhausted", "deadline_exceeded"}
LIVE_NOTICE = ("Live mode sends the email's subject and body, plus tool results derived from it, to the configured "
               "API provider ({provider}, model {model}). Use synthetic or non-sensitive content.")


class InputError(ValueError):
    """A user-correctable problem: shown to the user, nothing is run."""


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


@dataclass
class Attempt:
    attempt_id: str
    case_id: str
    started_at_utc: str
    input_source: str
    synthetic_case: str | None
    fingerprint: str
    mode: str
    model: str | None
    result: object | None = None
    error: str | None = None

    def meta(self) -> dict:
        return {"attempt_id": self.attempt_id, "started_at_utc": self.started_at_utc, "input_source": self.input_source,
                "synthetic_case": self.synthetic_case, "mode": self.mode, "model": self.model}


def input_fingerprint(source, subject="", body="", eml_bytes=None, synthetic_name=None) -> str:
    h = hashlib.sha256()
    for part in (source, subject or "", body or "", synthetic_name or ""):
        h.update(str(part).encode("utf-8", "replace") + b"\x00")
    h.update(hashlib.sha256(bytes(eml_bytes or b"")).digest())
    return h.hexdigest()


class TriageSession:
    """Session-memory state for the interface. Submitted cases stay in memory; nothing is written to Git."""

    def __init__(self, tools, *, settings=None, preflights=None, config=None, run_info=None,
                 live_adapter_factory=A.make_live_adapter, replay_factory=AR.replay_adapter, runner=A.run_triage):
        self.tools, self.store = tools, tools.store
        self.settings, self.preflights = settings, preflights
        self.config, self.run_info = config or A.AgentConfig(), run_info or {}
        self.live_adapter_factory, self.replay_factory, self.runner = live_adapter_factory, replay_factory, runner
        self.busy, self.attempts = False, []

    # -- gating
    def live_status(self) -> tuple[bool, str]:
        if self.settings is None or self.preflights is None:
            return False, "live mode is not configured in this runtime"
        approval = self.preflights.approval_for(self.settings)
        if approval is None:
            latest = self.preflights.latest_for(self.settings)
            why = f"last preflight status: {latest['status']}" if latest else "no preflight for this model yet"
            return False, f"model {self.settings.model}: {why} (run section 21 with RUN_LLM_PREFLIGHT = True)"
        return True, f"model {self.settings.model}: preflight ok (google-genai {approval.get('sdk_version')})"

    def live_notice(self) -> str:
        model = self.settings.model if self.settings else "not configured"
        return LIVE_NOTICE.format(provider=getattr(self.settings, "provider", "gemini"), model=model)

    # -- input
    def build_case(self, source, subject="", body="", eml_bytes=None, synthetic_name=None, case_id=None):
        if source not in SOURCES:
            raise InputError(f"choose an input source: {', '.join(SOURCES)}")
        try:
            if source == "pasted":
                if eml_bytes:
                    raise InputError("an .eml file is uploaded; choose 'Upload .eml' or clear the upload")
                return EI.from_pasted(subject, body, case_id=case_id)
            if source == "eml":
                if not eml_bytes:
                    raise InputError("upload an .eml file first")
                if len(eml_bytes) > EI.MAX_EML_BYTES:
                    raise InputError(f".eml is larger than {EI.MAX_EML_BYTES:,} bytes")
                return EI.parse_eml(bytes(eml_bytes), case_id=case_id)
            if synthetic_name not in AR.DEMO_CASES:
                raise InputError("choose one of the listed synthetic examples")
            return AR.build_demo_case(synthetic_name, case_id)
        except EI.EmailInputError as e:
            raise InputError(str(e)) from None

    # -- analysis
    def analyze(self, *, source, mode, subject="", body="", eml_bytes=None, synthetic_name=None,
                live_acknowledged=False) -> Attempt:
        if self.busy:
            raise InputError("an analysis is already running; wait for it to finish")
        self.busy = True
        try:
            if mode not in MODES:
                raise InputError(f"unknown mode {mode!r}")
            if mode == "replay" and source != "synthetic":
                raise InputError("scripted replay only works for its predefined synthetic examples")
            approval = None
            if mode == "live":
                ok, why = self.live_status()
                if not ok:
                    raise InputError(f"live mode unavailable: {why}")
                if not live_acknowledged:
                    raise InputError("tick the acknowledgement before sending content to the API provider")
                approval = self.preflights.approval_for(self.settings)
            n = len(self.attempts) + 1
            attempt_id = f"attempt-{n:03d}-{uuid.uuid4().hex[:6]}"
            case_id = f"ui-{attempt_id}"
            case = self.build_case(source, subject, body, eml_bytes, synthetic_name, case_id=case_id)
            adapter = None
            if mode == "live":
                adapter, reason = self.live_adapter_factory(approval, self.settings)
                if adapter is None:
                    raise InputError(f"live mode unavailable: {reason}")
            elif mode == "replay":
                adapter = self.replay_factory(synthetic_name)
            self.store.add(case)
            attempt = Attempt(attempt_id=attempt_id, case_id=case_id,
                              started_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                              input_source=source if source != "synthetic" else f"synthetic:{synthetic_name}",
                              synthetic_case=synthetic_name if source == "synthetic" else None,
                              fingerprint=input_fingerprint(source, subject, body, eml_bytes, synthetic_name),
                              mode=mode, model=getattr(adapter, "model", None) if mode == "live" else None)
            self.attempts.append(attempt)               # recorded before running: failures stay in history
            try:
                attempt.result = self.runner(self.tools, case_id, mode=mode, adapter=adapter, config=self.config,
                                             preflight=approval)
            except Exception as e:                      # unexpected: recorded honestly, never shown as success
                attempt.error = f"internal error: {type(e).__name__}"
            return attempt
        finally:
            self.busy = False

    def is_stale(self, attempt: Attempt, **current_inputs) -> bool:
        return attempt.fingerprint != input_fingerprint(**current_inputs)

    def export(self, attempt: Attempt, detailed: bool = False) -> dict:
        if attempt.result is None:
            raise InputError("this attempt has no report to export")
        return report_export(attempt.result.report, attempt.result.trace, self.store, detailed=detailed,
                             attempt=attempt.meta(), run_info=self.run_info)

    def verification_records(self) -> list[dict]:
        return [verification_record(a.result.report, a.meta(), self.run_info)
                for a in self.attempts if a.synthetic_case and a.result is not None]


# --------------------------------------------------------------------------- rendering (escaped HTML only)

_CSS = ("<style>.pt{font-family:system-ui,sans-serif;font-size:13px;line-height:1.45;max-width:980px}"
        ".pt h4{margin:10px 0 4px}.pt .b{padding:6px 10px;border-radius:6px;margin:6px 0;border:1px solid #8884}"
        ".pt .warn{border-color:#d9822b}.pt .bad{border-color:#d0453f}.pt .ok{border-color:#3a9a5b}"
        ".pt table{border-collapse:collapse}.pt td,.pt th{border:1px solid #8884;padding:2px 6px;font-size:12px}"
        ".pt code{font-size:12px}.pt .muted{opacity:.75}</style>")


def _status_line(report) -> tuple[str, str]:
    label = STATUS_LABELS.get(report.status, report.status)
    if report.status == "needs_human_review" and report.termination_reason in PARTIAL_TERMINATIONS:
        label = "Partial result: needs human review"
    cls = {"approved": "ok", "evidence_only": "ok", "failed": "bad"}.get(report.status, "warn")
    return label, cls


def render_attempt_html(attempt: Attempt, store, stale: bool = False) -> str:
    parts = [_CSS, '<div class="pt">']
    if stale:
        parts.append('<div class="b warn"><b>Input changed since this result was produced.</b> This result is for '
                     'the earlier input; run Analyze again before relying on or exporting it.</div>')
    parts.append(f"<div class='muted'>{esc(attempt.attempt_id)} · {esc(attempt.started_at_utc)} · "
                 f"input: {esc(attempt.input_source)}</div>")
    if attempt.synthetic_case:
        parts.append(f"<div class='b'>{esc(AR.SYNTHETIC_LABEL)}</div>")
    if attempt.result is None:
        parts.append(f"<div class='b bad'><b>Failed:</b> {esc(attempt.error or 'no result')}</div></div>")
        return "".join(parts)
    r = attempt.result.report
    label, cls = _status_line(r)
    model = r.provider.get("model") or "none (no language model)"
    sdk = f", google-genai {r.provider['sdk_version']}" if r.provider.get("sdk_version") else ""
    parts.append(f"<div class='b {cls}'><b>{esc(label)}</b> · termination: <code>{esc(r.termination_reason)}</code>"
                 + (f"<br><span class='muted'>{esc(r.termination_detail)}</span>" if r.termination_detail else "")
                 + "</div>")
    parts.append(f"<div class='b'><b>Mode:</b> {esc(r.mode_notice)}<br><b>Model used:</b> {esc(model)}{esc(sdk)}</div>")
    c = r.classifier or {}
    score = "n/a" if c.get("score") is None else f"{c['score']:.3f}"
    thr = "n/a" if c.get("threshold") is None else f"{c['threshold']:.3f}"
    parts.append("<h4>Classifier (unchanged by the agent)</h4>"
                 f"<div>{esc(c.get('model_id'))}: <b>{esc(c.get('predicted_label'))}</b>, score {esc(score)} "
                 f"(uncalibrated model estimate, threshold {esc(thr)}). Trained on a source-confounded benchmark; "
                 "not real-world accuracy.</div>")
    if r.assessment:
        note = " (not proof that the email is safe)" if r.assessment == "no_strong_indicators" else ""
        parts.append(f"<h4>Agent assessment</h4><div><b>{esc(r.assessment)}</b>{esc(note)}</div>")
    if disagreement(r):
        parts.append("<div class='b warn'><b>Disagreement:</b> the classifier label and the agent assessment differ. "
                     "Both are shown unchanged for a human to weigh.</div>")
    evidence = store.evidence(r.case_id) if store.has(r.case_id) else {}
    if r.findings:
        rows = []
        for f in r.findings:
            cites = "<br>".join(f"<code>{esc(e.split('/')[-1])}</code> {esc(evidence[e].evidence_type)} "
                                f"[{esc(evidence[e].status)}] {esc(evidence[e].excerpt[:120])}"
                                for e in f["evidence_ids"] if e in evidence) or "<i>no valid citation</i>"
            bad = (f"<br><span class='muted'>rejected citations: {esc(', '.join(f['rejected_citations']))}</span>"
                   if f["rejected_citations"] else "")
            rows.append(f"<tr><td>{esc(f['statement'])}{bad}</td><td>{cites}</td></tr>")
        parts.append("<h4>Findings and supporting evidence</h4><table><tr><th>Finding</th><th>Evidence</th></tr>"
                     + "".join(rows) + "</table>")
    if r.missing_information:
        parts.append("<h4>Missing information (unknown, not evidence of safety)</h4><ul>"
                     + "".join(f"<li>{esc(m['item'])}{' <i>(agent)</i>' if m['source'] == 'agent' else ''}</li>"
                               for m in r.missing_information[:10]) + "</ul>")
    if r.playbook_refs:
        parts.append("<h4>Example playbook guidance (EXAMPLE POLICY, not proof)</h4><ul>"
                     + "".join(f"<li>{esc(p['doc_id'])} v{esc(p['version'])} {esc(p['title'] or '')}: {esc(p['reason'])}"
                               + ("" if p["verified_retrieved"] else " <b>[not verified]</b>") + "</li>"
                               for p in r.playbook_refs) + "</ul>")
    if r.recommended_actions:
        parts.append("<h4>Recommended human actions</h4><ul>"
                     + "".join(f"<li>{esc(a['action'])}</li>" for a in r.recommended_actions) + "</ul>")
    rv = r.review
    issues = "".join(f"<li>[{esc(i['severity'])}] {esc(i['code'])}: {esc(i['detail'])}</li>"
                     for i in rv.get("validation_issues", []))
    objections = "".join(f"<li>{esc(o['issue_type'])}: {esc(o['detail'])}</li>"
                         for o in rv.get("unresolved_objections", []))
    parts.append(f"<h4>Reviewer outcome</h4><div>{esc(rv.get('reviewer_status'))} after {esc(rv.get('rounds'))} "
                 "review(s). Approval is a second check, not a guarantee of correctness.</div>"
                 + (f"<ul>{objections}{issues}</ul>" if objections or issues else ""))
    u = r.usage
    counters = ", ".join(f"{esc(k)}={esc(u.get(k))}" for k in ("model_requests", "tool_rounds", "tool_executions",
                                                               "rejected_tool_calls", "provider_retries",
                                                               "retry_wait_s", "elapsed_s"))
    trace_rows = "".join(f"<tr><td>{esc(t['step'])}</td><td>{esc(t['kind'])}</td><td>{esc(t['name'])}</td>"
                         f"<td>{esc(t['status'])}</td><td>{esc(t['ms'])}</td><td>{esc(t['code'] or '')}</td>"
                         f"<td>{esc(', '.join(e.split('/')[-1] for e in t['evidence_ids']))}</td></tr>"
                         for t in attempt.result.trace)
    parts.append("<details><summary>Observable tool trace and counters (no model reasoning)</summary>"
                 f"<div class='muted'>{counters}</div><table><tr><th>#</th><th>kind</th><th>name</th><th>status</th>"
                 f"<th>ms</th><th>code</th><th>evidence</th></tr>{trace_rows}</table></details>")
    parts.append("<div class='muted'>Limitations: " + " ".join(esc(x) for x in r.limitations[:3]) + "</div></div>")
    return "".join(parts)


# --------------------------------------------------------------------------- ipywidgets front end

def uploaded_bytes(upload) -> bytes | None:
    """Read FileUpload content for ipywidgets 8 (tuple of dicts) or 7 (dict of dicts), with a size check first."""
    value = upload.value
    items = list(value.values()) if isinstance(value, dict) else list(value or [])
    if not items:
        return None
    item = items[0]
    size = item.get("size") or (item.get("metadata") or {}).get("size") or len(item.get("content", b""))
    if size > EI.MAX_EML_BYTES:
        raise InputError(f".eml is larger than {EI.MAX_EML_BYTES:,} bytes")
    return bytes(item["content"])


def build_interface(session: TriageSession, export_dir=None, download=None):
    """Return the widget tree. Callbacks are thin: they collect inputs, call the session, and render escaped HTML.
    Displaying the widgets never runs an analysis or calls an API."""
    import ipywidgets as W
    from .export import write_json

    source = W.ToggleButtons(options=[("Paste text", "pasted"), ("Upload .eml", "eml"),
                                      ("Synthetic example", "synthetic")], value="pasted", description="Input")
    subject = W.Text(description="Subject", layout=W.Layout(width="95%"))
    body = W.Textarea(description="Body", layout=W.Layout(width="95%", height="140px"))
    upload = W.FileUpload(accept=".eml", multiple=False, description="Upload .eml")
    synthetic = W.Dropdown(options=[(f"SYNTHETIC: {spec['title']}", name) for name, spec in AR.DEMO_CASES.items()],
                           description="Example", layout=W.Layout(width="95%"))
    mode = W.Dropdown(options=[("Evidence only (no LLM)", "evidence_only"),
                               ("Scripted replay (synthetic examples only; NOT live)", "replay"),
                               ("Live agent (configured API provider)", "live")],
                      value="evidence_only", description="Mode", layout=W.Layout(width="95%"))
    live_info = W.HTML()
    ack = W.Checkbox(value=False, description="I understand the content is sent to the API provider",
                     layout=W.Layout(width="95%"))
    analyze = W.Button(description="Analyze", button_style="primary")
    clear = W.Button(description="Clear")
    detailed = W.Checkbox(value=False, description="Detailed export (includes model text and excerpts)")
    export = W.Button(description="Export JSON", disabled=True)
    message = W.HTML()
    result = W.HTML()
    state = {"attempt": None}

    def inputs() -> dict:
        eml = uploaded_bytes(upload) if source.value == "eml" else None
        return {"source": source.value, "subject": subject.value if source.value == "pasted" else "",
                "body": body.value if source.value == "pasted" else "", "eml_bytes": eml,
                "synthetic_name": synthetic.value if source.value == "synthetic" else None}

    def refresh(*_):
        pasted, is_eml, synth = source.value == "pasted", source.value == "eml", source.value == "synthetic"
        subject.layout.display = body.layout.display = None if pasted else "none"
        upload.layout.display = None if is_eml else "none"
        synthetic.layout.display = None if synth else "none"
        ok, why = session.live_status()
        live = mode.value == "live"
        ack.layout.display = None if live else "none"
        live_info.value = (f"<div class='pt'><div class='b {'ok' if ok else 'warn'}'>{esc(why)}<br>"
                           f"{esc(session.live_notice())}</div></div>" if live else "")
        a = state["attempt"]
        if a is not None:
            try:
                stale = session.is_stale(a, **inputs())
            except InputError:
                stale = True
            result.value = render_attempt_html(a, session.store, stale=stale)
            export.disabled = stale or a.result is None

    def on_analyze(_):
        analyze.disabled = True
        message.value = "<i>Running…</i>"
        try:
            state["attempt"] = session.analyze(mode=mode.value, live_acknowledged=ack.value, **inputs())
            message.value = ""
        except InputError as e:
            message.value = f"<div class='pt'><div class='b warn'>{esc(e)}</div></div>"
        except Exception as e:                       # never leave the interface stuck
            message.value = f"<div class='pt'><div class='b bad'>Unexpected error: {esc(type(e).__name__)}</div></div>"
        finally:
            analyze.disabled = False
            refresh()

    def on_clear(_):
        subject.value = body.value = ""
        try:
            upload.value = ()
        except Exception:
            upload.value = {}
        state["attempt"] = None
        result.value = message.value = ""
        export.disabled = True
        ack.value = False
        refresh()

    def on_export(_):
        a = state["attempt"]
        try:
            if a is None or session.is_stale(a, **inputs()):
                raise InputError("nothing current to export; run Analyze on the current input first")
            data = session.export(a, detailed=detailed.value)
            if export_dir is None:
                message.value = "<i>No export directory configured.</i>"
                return
            path = write_json(data, export_dir, f"phishtriage_{a.attempt_id}_{data['export_kind']}")
            if download is not None:
                download(str(path))
            message.value = f"<div class='pt'><div class='b ok'>Exported {esc(data['export_kind'])} JSON: {esc(path.name)}</div></div>"
        except InputError as e:
            message.value = f"<div class='pt'><div class='b warn'>{esc(e)}</div></div>"

    for w in (source, mode, subject, body, synthetic, upload):
        w.observe(refresh, names="value")
    analyze.on_click(on_analyze)
    clear.on_click(on_clear)
    export.on_click(on_export)
    refresh()
    box = W.VBox([source, subject, body, upload, synthetic, mode, live_info, ack,
                  W.HBox([analyze, clear]), W.HBox([detailed, export]), message, result])
    box._phishtriage = {"source": source, "subject": subject, "body": body, "upload": upload, "synthetic": synthetic,
                        "mode": mode, "ack": ack, "analyze": analyze, "clear": clear, "detailed": detailed,
                        "export": export, "message": message, "result": result, "state": state}
    return box
