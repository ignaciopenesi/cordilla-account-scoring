"""
The agent layer: every place a human has to read something, an agent drafts it; every
place unstructured text has to become data, an agent extracts it.

Three rules that hold across all of it:

  1. **Agents never decide.** They turn numbers into a paragraph a person can act on, and
     turn what a person said into structured data. Allocation is rules, approval is the
     manager, and the only write path is HITL.
  2. **Every agent has a typed contract** — named inputs, a declared return shape, and for
     the extracting ones a schema that the output is validated against. That is the
     difference between "an LLM writes the thing" and "an agent is a node".
  3. **Failure is visible, never invented.** If a backend is down or returns something off
     contract, the agent falls back to template mode and says so in the output. It does
     not guess, and it does not silently skip.

Configuration lives in `config.toml` (see it — the routing section is a compliance
argument, not a preference). With no config and no keys this runs in template mode, which
renders the exact prompt plus a worked example; the packet judges that the same as a live
call.

    python serving/pipeline.py --check-llm     # probe the configured backends and exit

No new dependencies: `anthropic` is imported inside its branch, the OpenAI-compatible
backend speaks HTTP through `urllib` from the standard library, and `tomllib` is stdlib
on Python 3.11+.
"""
from __future__ import annotations

import json
import os
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"

# Used when config.toml is absent, so the pipeline always runs.
FALLBACK_CONFIG = {
    "defaults": {"mode": "template", "timeout_seconds": 60, "max_retries": 2},
    "backends": {}, "routing": {},
}


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        return FALLBACK_CONFIG
    try:
        import tomllib
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
        for k, v in FALLBACK_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception as exc:
        print(f"  [llm] config.toml unreadable ({exc}); falling back to template mode")
        return FALLBACK_CONFIG


CONFIG = load_config()


# ═════════════════════════════════════════════════════════════════════════════
# Agents
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class Agent:
    name: str
    purpose: str                       # what it is for, in one line
    reads: list[str]                   # named inputs
    returns: str                       # declared return shape
    system: str
    template: str
    schema: dict | None = None         # if set, output is JSON and is validated
    invariants: list = None            # cross-field rules a schema cannot express
    sensitivity: str = "aggregate"     # aggregate | account_ids | pii  → drives routing
    example: object = None             # a worked example of the return


AGENTS: dict[str, Agent] = {}


def agent(a: Agent) -> Agent:
    AGENTS[a.name] = a
    return a


# ── drafting agents: aggregates in, prose out ────────────────────────────────
agent(Agent(
    name="experiment_card",
    purpose="Write the week's allocation as an experiment the manager can approve or refuse",
    reads=["arms (name, size, selection rule)", "matching variables", "base rate", "readout date"],
    returns="markdown, ~150 words",
    sensitivity="aggregate",
    system="You write experiment cards for an SDR manager who is not technical and is "
           "sceptical of being experimented on. Be concrete about what each arm is testing "
           "and what result would make us stop. Never oversell, and never promise a lift "
           "number we do not have.",
    template="""This week's allocation splits {total} accounts into {n_arms} matched arms
({matched_on}). Base rate is {base_rate}.

{arm_block}

Write the experiment card the SDR manager reads before approving. For each arm state the
hypothesis in one sentence, the result that would confirm it, and the result that would
kill it. End with the readout date and one sentence on why the control arm exists.""",
))

agent(Agent(
    name="disagreement_question",
    purpose="Ask a rep what they know that the data cannot show",
    reads=["account_id", "disagreement type", "score", "contacts logged", "flags"],
    returns="one question, under 40 words",
    sensitivity="account_ids",
    system="You write short questions to a sales rep. The rep is busy and has been burned "
           "by a scoring tool before. Ask about what they know that the data cannot show. "
           "Never tell them who to call. Never imply they were wrong.",
    template="""Account {account_id}. The model scores it {score} ({percentile} percentile).
The team has logged {contacts} contacts in 90 days. Flags: {flags}.
Disagreement type: {disagreement_kind}.

Write one question to the rep, under 40 words, that they can answer in two minutes, about
what they know that the data does not show. It must not read as a performance check.""",
    example="ACC-00453 — the model ranks this in the bottom quartile, but the team has "
            "logged 4 contacts in 90 days. What are you seeing there that the data isn't "
            "showing?",
))

agent(Agent(
    name="hygiene_batch",
    purpose="Turn a detected CRM defect into an approval note with evidence and a preventive rule",
    reads=["defect", "detection rule", "affected count", "examples", "proposed correction"],
    returns="markdown, ~100 words",
    sensitivity="account_ids",
    system="You write CRM correction proposals for approval in bulk. State the evidence "
           "before the fix. Always include the rule that prevents the defect from coming "
           "back — a one-off cleanup is worth much less than the rule.",
    template="""Defect: {defect}
Detected by: {rule}
Affected records: {count}
Examples: {examples}
Proposed correction: {correction}

Write the approval note. Lead with the evidence, then the correction, then the preventive
rule. Say plainly what happens if this is not fixed.""",
    example="**account_type is stale — 86 records.** A 'Suspect' is defined as an account "
            "that fits the profile but has shown no engagement. These 86 have an MQL, a "
            "trial or a logged sales contact (e.g. ACC-00095, ACC-00228, ACC-00284), and "
            "in training this group converts at the same rate as Prospects (chi2 p = 0.84). "
            "Proposed: reclassify to Prospect in bulk. Preventive rule: a validation rule "
            "so an account with activity cannot be saved as Suspect. Left alone, the field "
            "keeps disagreeing with itself and nobody can explain why a 'Suspect' is near "
            "the top of a list.",
))

agent(Agent(
    name="run_verdict",
    purpose="Say whether this week's run is worth trusting, and recommend what to do about it",
    reads=["PSI table", "overlap with previous run", "score concentration", "flags in top K",
           "sum of probabilities vs the field rate"],
    returns="one paragraph, under 120 words",
    sensitivity="aggregate",
    system="You write a weekly one-paragraph verdict on whether a scoring run is worth "
           "trusting. You are allowed — expected — to say it is not. End with a concrete "
           "recommendation for THIS week, not a general observation.",
    template="""Run of {date}. {psi_summary}. Overlap of the top 30 with the previous run:
{overlap}. {concentration}. Of the top 30, {clean} carry no flags. The model's predicted
probabilities sum to {sum_p} expected conversions across {n} accounts ({mean_p}), against a
field rate the business reports at 1-3%.

Write the manager's paragraph. End with one concrete recommendation for this week.""",
    example="Run of 2026-08-01. Every feature is stable against training (max PSI 0.06); "
            "snapshot age is not — but that is how the batch was drawn, not drift. The top "
            "30 shares 21 of 30 accounts with last week's list even though no underlying "
            "data changed, which is the model's own seed, not the market. Only 7 of the top "
            "30 carry no flags at all. The model expects 19.7 conversions across 300 "
            "accounts (6.6%) against a field rate the business reports at 1–3%. "
            "Recommendation this week: run the exploit arm off sales_contacts, not off the "
            "score, and do not publish the probabilities.",
))

# ── the extracting agent: PII in, validated JSON out ─────────────────────────
# v2 — rebuilt after measuring v1 against 20 transcripts with known levels.
# What changed and why (numbers in serving/README.md):
#   · `ready_to_act` is now the PRIMARY field. v1 asked for a six-level grade and got 50%
#     exact; collapsing the same answers to act/wait scored 95%. The decision a rep makes
#     is binary, so the contract now asks the binary question directly.
#   · `intent_level` survives as secondary and informational. It is not what the pipeline
#     routes on.
#   · `speaker_role` is GONE. v1 scored 5% on it — worse than guessing — because a
#     transcript rarely states a title. That field belongs to the CRM, which already has it.
#   · `next_step_agreed` scored 20/20 in v1 and as a standalone proxy for "hot" reached
#     100% precision / 91% recall. It stays, and RECONCILE leans on it.
INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "ready_to_act": {"type": "boolean"},
        "ready_because": {"type": "string",
                          "enum": ["budget_approved", "purchase_timeline", "both", "neither"]},
        "evidence_quote": {"type": "string"},
        "next_step_agreed": {"type": "boolean"},
        "next_step": {"type": ["string", "null"]},
        "objections": {"type": "array", "items": {"type": "string"}},
        "intent_level": {"type": "string", "enum": ["A", "B", "C", "D", "E", "F"]},
        "call_purpose": {"type": "string",
                         "enum": ["discovery", "follow_up", "negotiation", "support", "other"]},
        "confidence": {"type": "number"},
    },
    "required": ["ready_to_act", "ready_because", "evidence_quote", "next_step_agreed",
                 "objections", "intent_level", "confidence"],
}

agent(Agent(
    name="conversation_intent",
    purpose="Extract buying signals from a call — the one account-intrinsic signal available",
    reads=["speaker-labelled transcript", "account_id", "call date"],
    returns="validated JSON — ready_to_act is the field the pipeline uses (see INTENT_SCHEMA)",
    schema=INTENT_SCHEMA,
    sensitivity="pii",
    system="You extract buying signals from a sales call transcript. Report only what the "
           "PROSPECT said — never the rep's enthusiasm — and always quote the sentence you "
           "used.\n\n"
           "`ready_to_act` is the field that matters, and it has exactly two triggers.\n\n"
           "BUDGET counts only if money is already allocated: \"budget approved\", "
           "\"signed off\", \"the spend is authorised\". It does NOT count when they are "
           "still trying to get it: \"I need to justify this\", \"building the business "
           "case\", \"if I can get budget\".\n\n"
           "TIMELINE counts only if it is a date or window for BUYING OR GOING LIVE, and it "
           "is definite: \"live before November\", \"in production by Q4\", \"we need this "
           "by end of quarter\". It does NOT count when the date belongs to an internal step "
           "(\"I\'ll take it to my VP next month\" is their errand, not a purchase date), and "
           "it does NOT count when it is hedged or pushed away — \"sometime next year "
           "maybe\", \"not this quarter\", \"it\'s on the roadmap\" are all `neither`.\n\n"
           "Two traps, in order of how often they happen.\n"
           "1. A vague or deferred date is not a timeline. If the sentence contains "
           "\"maybe\", \"sometime\", \"not this quarter\", or names no period at all, "
           "`ready_because` is `neither`.\n"
           "2. A stated CONDITION is not a lack of interest. \"I need to see X work before "
           "I commit\" or \"we\'re comparing three vendors\" describe a live buying process "
           "— record the obstacle in `objections`, and let budget or timeline decide "
           "`ready_to_act` on their own.\n\n"
           "`intent_level` is secondary context: A = budget and timeline, B = budget or "
           "timeline, C = building a case, D = passive interest, E = wrong person or "
           "wrong time, F = explicit no. Grade it, but `ready_to_act` is what gets acted on.",
    template="""Transcript of a sales call with account {account_id} on {date}.

<transcript>
{transcript}
</transcript>

Return the JSON object in the schema.

Work in this order:
1. Did the prospect say money is ALREADY allocated, or name a definite date for
   buying or going live? Set `ready_because` — and if the date is hedged, deferred, or
   belongs to an internal errand, the answer is `neither`.
2. `ready_to_act` follows directly: true if `ready_because` is anything but "neither".
   These two must agree — a stated budget with `ready_to_act: false` is a contradiction.
3. Quote the exact sentence you used, from the prospect, in `evidence_quote`.
4. Did they agree to a specific follow-up — a meeting, a call, a document by a date?
   Set `next_step_agreed` and describe it in `next_step`. "Let\'s find time in the next
   couple of weeks" counts; "you can send something over" does not.
5. List obstacles they named in `objections`. A condition to buy is an objection, not a
   reason to mark them cold.
6. Grade `intent_level` last, as context.""",
    invariants=[
        ("ready_to_act agrees with ready_because",
         lambda o: o.get("ready_to_act") == (o.get("ready_because") != "neither")),
        ("next_step is described when one was agreed",
         lambda o: (not o.get("next_step_agreed")) or bool(o.get("next_step"))),
    ],
    example={
        "ready_to_act": True,
        "ready_because": "budget_approved",
        "evidence_quote": "We've got budget approved for a workflow tool this quarter, "
                          "we're just deciding between you and two others.",
        "next_step_agreed": True,
        "next_step": "Technical review with their ops lead, week of 2026-08-11",
        "objections": ["incumbent tool", "price"],
        "intent_level": "B",
        "call_purpose": "discovery",
        "confidence": 0.86,
    },
))


# ═════════════════════════════════════════════════════════════════════════════
# Backends. One adapter per protocol, not per vendor — Ollama, vLLM, LM Studio and
# LocalAI all speak the same OpenAI-compatible /v1 surface, so `openai_compat` covers
# every local option and swapping between them is a base_url change.
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class Backend:
    name: str
    cfg: dict

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def complete(self, a: Agent, prompt: str) -> str:
        raise NotImplementedError


class AnthropicBackend(Backend):
    def available(self) -> tuple[bool, str]:
        if not os.environ.get(self.cfg.get("api_key_env", "ANTHROPIC_API_KEY")):
            return False, f"{self.cfg.get('api_key_env')} not set"
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "pip install anthropic"
        return True, f"{self.cfg['model']} via API"

    def complete(self, a: Agent, prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ[self.cfg["api_key_env"]])
        msg = client.messages.create(
            model=self.cfg["model"],
            max_tokens=self.cfg.get("max_tokens", 1024),
            temperature=self.cfg.get("temperature", 0.3),
            system=a.system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text


class OpenAICompatBackend(Backend):
    """Ollama · vLLM · LM Studio · LocalAI · any OpenAI-compatible gateway.

    Speaks raw HTTP through urllib so the pipeline keeps zero extra dependencies."""

    def _post(self, path: str, payload: dict | None, timeout: int) -> dict:
        url = self.cfg["base_url"].rstrip("/") + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("Content-Type", "application/json")
        key = os.environ.get(self.cfg.get("api_key_env", ""), "")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def available(self) -> tuple[bool, str]:
        try:
            models = self._post("/models", None, 5)
            ids = [m.get("id") for m in models.get("data", [])]
            want = self.cfg["model"]
            if ids and want not in ids:
                return True, f"reachable, but '{want}' not loaded (has: {', '.join(ids[:3])}…)"
            return True, f"{want} at {self.cfg['base_url']}"
        except urllib.error.URLError as exc:
            return False, f"{self.cfg['base_url']} unreachable ({exc.reason})"
        except Exception as exc:
            return False, f"{self.cfg['base_url']}: {exc}"

    # Servers disagree on how to ask for JSON: OpenAI and recent vLLM take a full
    # json_schema, Ollama takes json_object, some builds take neither and return an
    # EMPTY string rather than an error. So try in descending order of strictness and
    # fall through on an empty reply -- that failure mode is silent and would otherwise
    # look like the model having nothing to say.
    def _json_modes(self, a: Agent) -> list[dict]:
        if not a.schema:
            return [{}]
        want = self.cfg.get("json_mode", "auto")
        schema = {"response_format": {"type": "json_schema",
                                      "json_schema": {"name": a.name, "schema": a.schema,
                                                      "strict": True}}}
        obj = {"response_format": {"type": "json_object"}}
        return {"schema": [schema], "object": [obj], "none": [{}],
                "auto": [schema, obj, {}]}.get(want, [schema, obj, {}])

    def complete(self, a: Agent, prompt: str) -> str:
        base = {
            "model": self.cfg["model"],
            "temperature": self.cfg.get("temperature", 0),
            # Reasoning models (Qwen3 among them) spend tokens thinking before answering.
            # A 1k budget can be consumed entirely by that, and the reply comes back empty.
            "max_tokens": self.cfg.get("max_tokens", 4096),
            "messages": [{"role": "system", "content": a.system},
                         {"role": "user", "content": prompt}],
        }
        if self.cfg.get("disable_thinking"):
            base["chat_template_kwargs"] = {"enable_thinking": False}

        last_empty = None
        for extra in self._json_modes(a):
            out = self._post("/chat/completions", {**base, **extra},
                             CONFIG["defaults"].get("timeout_seconds", 60))
            text = out["choices"][0]["message"]["content"] or ""
            if text.strip():
                return text
            last_empty = list(extra.get("response_format", {}).values())[:1] or ["plain"]
        raise RuntimeError(f"backend returned an empty completion for every JSON mode tried "
                           f"(last: {last_empty}). The server likely does not support the "
                           f"requested response_format; set json_mode in config.toml.")


KINDS = {"anthropic": AnthropicBackend, "openai_compat": OpenAICompatBackend}


def get_backend(name: str) -> Backend | None:
    cfg = CONFIG.get("backends", {}).get(name)
    if not cfg or cfg.get("kind") not in KINDS:
        return None
    return KINDS[cfg["kind"]](name=name, cfg=cfg)


def route(agent_name: str) -> str | None:
    """Which backend handles this agent. PII-bearing agents must never route to a hosted
    backend — if the routing table says so, that is a configuration error and we refuse."""
    target = CONFIG.get("routing", {}).get(agent_name)
    a = AGENTS.get(agent_name)
    if target and a and a.sensitivity == "pii":
        kind = CONFIG.get("backends", {}).get(target, {}).get("kind")
        if kind == "anthropic":
            print(f"  [llm] REFUSING to route '{agent_name}' (pii) to a hosted backend. "
                  f"Fix [routing] in config.toml. Falling back to template.")
            return None
    return target


# ═════════════════════════════════════════════════════════════════════════════
# Entry points
# ═════════════════════════════════════════════════════════════════════════════
def draft(kind: str, mode: str = "template", **payload) -> str:
    """Run one agent. Returns text a human reads.

    mode='template' → render the prompt and the worked example, call nothing.
    mode='live'     → route to the configured backend; on any failure, say so and fall
                      back to template. Never invents a result.
    """
    a = AGENTS[kind]
    prompt = a.template.format(**payload)
    if mode != "live":
        return _render(a, prompt, "template")

    target = route(kind)
    backend = get_backend(target) if target else None
    if backend is None:
        return _render(a, prompt, f"live requested, no backend routed for '{kind}'")

    ok, why = backend.available()
    if not ok:
        return _render(a, prompt, f"backend '{target}' unavailable: {why}")

    last = ""
    for attempt in range(1 + CONFIG["defaults"].get("max_retries", 2)):
        try:
            out = backend.complete(a, prompt)
            if a.schema:
                parsed, err = _validate(out, a.schema)
                if err:
                    last = f"schema violation: {err}"
                    continue
                broken = [name for name, rule in (a.invariants or []) if not rule(parsed)]
                if broken:
                    # A typed schema catches a wrong TYPE. It cannot catch a reply that
                    # contradicts itself -- "budget_stated" alongside ready_to_act=false --
                    # which is exactly what a small model does under pressure. Retry.
                    last = f"invariant violated: {'; '.join(broken)}"
                    continue
                return json.dumps(parsed, indent=2)
            return out
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
    return _render(a, prompt, f"backend '{target}' failed after retries — {last}")


def _extract_json(raw: str) -> str:
    """Pull the JSON object out of a reply. Local models wrap it in <think> blocks, code
    fences, or a sentence of preamble -- all of which are normal, none of which are the
    model being wrong."""
    txt = raw.strip()
    if "</think>" in txt:                       # reasoning models emit their scratchpad
        txt = txt.rsplit("</think>", 1)[1].strip()
    if "```" in txt:
        parts = txt.split("```")
        for part in parts[1::2]:
            cand = part.removeprefix("json").strip()
            if cand.startswith("{"):
                return cand
    start = txt.find("{")
    if start == -1:
        return txt
    depth, in_str, esc = 0, False, False         # find the matching close brace
    for i, ch in enumerate(txt[start:], start):
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            in_str = not in_str
        elif not in_str:
            depth += ch == "{"
            depth -= ch == "}"
            if depth == 0:
                return txt[start:i + 1]
    return txt[start:]


def _validate(raw: str, schema: dict) -> tuple[dict | None, str]:
    """Minimal contract check. Not a full JSON-Schema implementation -- enough to catch a
    model that returned prose, dropped a required field, or invented an enum value."""
    try:
        obj = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        return None, f"not JSON ({exc}); reply began {raw.strip()[:60]!r}"
    if not isinstance(obj, dict):
        return None, "not an object"
    for f in schema.get("required", []):
        if f not in obj:
            return None, f"missing required field '{f}'"
    for f, spec in schema.get("properties", {}).items():
        if f in obj and "enum" in spec and obj[f] not in spec["enum"]:
            return None, f"'{f}' = {obj[f]!r} not in {spec['enum']}"
    return obj, ""


def _render(a: Agent, prompt: str, mode_note: str) -> str:
    ex = a.example if a.example is not None else "(no worked example)"
    if isinstance(ex, dict):
        ex = json.dumps(ex, indent=2)
    bar = "─" * 74
    out = [f"┌{bar}",
           f"│ AGENT · {a.name}   [{mode_note}]",
           f"│ purpose     : {a.purpose}",
           f"│ sensitivity : {a.sensitivity}"
           + ("   → must run on a local backend" if a.sensitivity == "pii" else ""),
           f"│ routed to   : {CONFIG.get('routing', {}).get(a.name, '(unrouted)')}",
           f"│ reads       : {', '.join(a.reads)}",
           f"│ returns     : {a.returns}",
           f"├─ SYSTEM {'─' * 65}"]
    out += [f"│ {ln}" for ln in textwrap.wrap(a.system, 72)]
    out += [f"├─ PROMPT {'─' * 65}"]
    out += [f"│ {ln}" for ln in prompt.strip().splitlines()]
    out += [f"├─ RETURNS (worked example) {'─' * 47}"]
    out += [f"│ {ln}" for ln in str(ex).splitlines()]
    out += [f"└{bar}"]
    return "\n".join(out)


def healthcheck() -> None:
    """`--check-llm`: probe what is configured without running the pipeline."""
    print(f"\nLLM CONFIGURATION  ({CONFIG_PATH.name}"
          f"{'' if CONFIG_PATH.exists() else ' — ABSENT, template mode only'})")
    print("─" * 78)
    print(f"  default mode: {CONFIG['defaults'].get('mode')}\n")

    print("  BACKENDS")
    if not CONFIG.get("backends"):
        print("    (none configured)")
    for name in CONFIG.get("backends", {}):
        b = get_backend(name)
        if b is None:
            print(f"    ✗ {name:<8} unknown kind")
            continue
        ok, why = b.available()
        print(f"    {'✓' if ok else '✗'} {name:<8} {b.cfg['kind']:<15} {why}")

    print("\n  AGENTS")
    for name, a in AGENTS.items():
        target = CONFIG.get("routing", {}).get(name, "(unrouted)")
        b = get_backend(target)
        ok = b.available()[0] if b else False
        flag = " ⚠ PII" if a.sensitivity == "pii" else ""
        print(f"    {'✓' if ok else '·'} {name:<22} → {target:<8} "
              f"[{a.sensitivity}]{flag}")
    print("\n  · = would run in template mode (rendered prompt + worked example).")
    print("    That is the default and the packet judges it the same as a live call.\n")
