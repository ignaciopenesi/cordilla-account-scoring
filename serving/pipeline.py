"""
Cordilla account scoring — the serving pipeline.

A stateful graph. One State object is passed node to node; each node adds to it and
returns it. Nothing writes to Salesforce without passing the HITL node.

    INGEST -> VALIDATE -> SCORE -> {BASELINES, FLAGS, CONVERSATION_INTENT, CALIBRATE_VENDOR}
           -> RECONCILE -> {ALLOCATE, HYGIENE, VERDICT} -> PRESCRIBE -> HITL -> EMIT
           -> (day 90) READOUT

Why a graph and not a script: the audit concluded the model's ranking is noise-level
(audit/01_model_audit.ipynb §2). So the model cannot BE the decision -- it is one voice
of three in RECONCILE, and the system's job is to produce the data Cordilla has never
had: a control group, the rep's knowledge, and the prospect's own words.

Nodes whose inputs do not exist yet are BYPASSED, not faked. Each bypass records what it
would have produced and what unblocks it; `--map` prints the result. That distinction is
the point: what runs today is real, and what doesn't is declared.

Usage:
    python serving/pipeline.py                  # dry run, writes nothing outside serving/out
    python serving/pipeline.py --approve        # simulate the manager signing off
    python serving/pipeline.py --llm live       # make the real LLM calls (needs ANTHROPIC_API_KEY)
    python serving/pipeline.py --map            # print the node map and exit
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "out"
TODAY = pd.Timestamp("2026-08-01")          # the packet's "today", never the system clock

FEATURES = ["account_type", "employee_count", "industry", "intent_score", "mql_count_90d",
            "trial_started", "trial_active_users", "web_touchpoints_90d", "sales_contacts_90d"]


# ─────────────────────────────────────────────────────────────────────────────
# Findings: every detector emits these, never free text.
# A finding without an owner and an action is a report, and Cordilla already has reports.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Finding:
    what: str                  # the defect, in one line
    evidence: str              # the number that shows it
    severity: str              # blocking | high | medium | low
    owner: str                 # crm | vendor | pipeline | model | process
    action: str                # what to actually do about it
    cost: str = "unknown"      # rough effort
    expect: str = ""           # what changes if it is done
    source: str = ""           # which node found it

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Bypass:
    node: str
    reason: str                # why it cannot run on today's inputs
    unblocked_by: str          # what would have to exist
    would_produce: str         # the contract it would fulfil
    still_computed: str = ""   # the part that DOES run today, if any

    def as_dict(self) -> dict:
        return self.__dict__.copy()


# ─────────────────────────────────────────────────────────────────────────────
# State: the folder that travels the graph.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class State:
    accounts: pd.DataFrame = field(default_factory=pd.DataFrame)
    training: pd.DataFrame = field(default_factory=pd.DataFrame)
    quarantine: pd.DataFrame = field(default_factory=pd.DataFrame)
    model: object = None
    findings: list[Finding] = field(default_factory=list)
    bypassed: list[Bypass] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    capabilities: set[str] = field(default_factory=set)
    approvals: dict = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    args: argparse.Namespace = None

    # -- capabilities: what data sources are actually wired up right now ------
    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def find(self, **kw) -> None:
        self.findings.append(Finding(**kw))

    def bypass(self, **kw) -> None:
        self.bypassed.append(Bypass(**kw))
        self.say(f"  ⛔ BYPASSED — {kw['reason']}")

    def say(self, msg: str) -> None:
        self.log.append(msg)
        print(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
NODE_MAP = [
    ("INGEST",              "runs",    "loads the CSVs, the pickle, and declares capabilities"),
    ("VALIDATE",            "runs",    "gate: nulls, ranges, unseen categories, label window, staleness"),
    ("SCORE",               "runs",    "the pickle scores the 300 — one voice, not the decision"),
    ("BASELINES",           "runs",    "ORDER BY contacts, random, and what the team does today"),
    ("FLAGS",               "runs",    "per account: the reasons to distrust its score"),
    ("CONVERSATION_INTENT", "partial", "the 4 coverage quadrants run; intent extraction needs transcripts"),
    ("CALIBRATE_VENDOR",    "bypass",  "needs conversation intent to contrast the vendor against"),
    ("RECONCILE",           "partial", "model vs effort runs; the conversation voice is missing"),
    ("ALLOCATE",            "runs",    "three matched arms: exploit / explore / rep's choice (control)"),
    ("HYGIENE",             "runs",    "CRM contradictions, as proposals with evidence"),
    ("VERDICT",             "runs",    "is this run worth anything? PSI, drift vs last run, concentration"),
    ("PRESCRIBE",           "runs",    "findings -> prioritised actions with an owner"),
    ("HITL",                "runs",    "the manager approves actions; nothing reaches the CRM before this"),
    ("EMIT",                "runs",    "writes what the rep, the manager and Salesforce each get"),
    ("READOUT",             "bypass",  "needs 90-day outcomes that do not exist yet"),
]


def print_map() -> None:
    icon = {"runs": "✅", "partial": "🟡", "bypass": "⛔"}
    print("\nNODE MAP — what runs on today's data and what does not\n" + "─" * 78)
    for name, status, desc in NODE_MAP:
        print(f"  {icon[status]} {name:<20} {desc}")
    n = {k: sum(1 for _, s, _ in NODE_MAP if s == k) for k in icon}
    print("─" * 78)
    print(f"  {n['runs']} run · {n['partial']} partial · {n['bypass']} bypassed "
          f"— every bypass records what unblocks it (see serving/out/run.json)\n")


def run(args) -> State:
    from nodes import (INGEST, VALIDATE, SCORE, BASELINES, FLAGS, CONVERSATION_INTENT,
                       CALIBRATE_VENDOR, RECONCILE, ALLOCATE, HYGIENE, VERDICT,
                       PRESCRIBE, HITL, EMIT, READOUT)

    state = State(args=args)
    graph = [INGEST, VALIDATE, SCORE, BASELINES, FLAGS, CONVERSATION_INTENT,
             CALIBRATE_VENDOR, RECONCILE, ALLOCATE, HYGIENE, VERDICT,
             PRESCRIBE, HITL, EMIT, READOUT]

    print(f"\nCordilla serving pipeline — reference date {TODAY:%Y-%m-%d}")
    print("=" * 78)
    for node in graph:
        state.say(f"\n▸ {node.__name__}")
        state = node(state)
    print("\n" + "=" * 78)

    OUT.mkdir(exist_ok=True)
    (OUT / "run.json").write_text(json.dumps({
        "generated_at_reference_date": str(TODAY.date()),
        "accounts_scored": int(len(state.accounts)),
        "findings": [f.as_dict() for f in state.findings],
        "bypassed": [b.as_dict() for b in state.bypassed],
        "artifacts": {k: v for k, v in state.artifacts.items() if not isinstance(v, pd.DataFrame)},
        "approvals": state.approvals,
    }, indent=2, default=str))
    print(f"state written to {(OUT / 'run.json').relative_to(ROOT)}")
    return state


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--approve", action="store_true",
                   help="simulate the SDR manager approving the proposed actions")
    p.add_argument("--llm", choices=["template", "live"], default="template",
                   help="'template' renders the prompt and a worked example (the packet judges "
                        "this the same as a live call); 'live' calls the API if a key is set")
    p.add_argument("--map", action="store_true", help="print the node map and exit")
    args = p.parse_args()

    if args.map:
        print_map()
        return
    run(args)
    print_map()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
