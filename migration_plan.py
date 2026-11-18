"""Turn a list of Zaps into a Zapier to n8n migration plan.

Input is a CSV with one row per Zap:

    name,trigger_app,action_apps,runs_per_month
    New lead alert,Typeform,Filter by Zapier;Google Sheets;Slack,400

Output is a Markdown report: which n8n node replaces each step, how hard each
Zap is to move, which steps need manual API work, and a rough count of the
Zapier tasks the Zaps use each month.

Usage:
    python migration_plan.py examples/zaps.csv > plan.md
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_COLUMNS = ("name", "trigger_app", "action_apps", "runs_per_month")

# Zapier app name (lower case) -> n8n node name.
TRIGGER_NODES = {
    "webhooks by zapier": "Webhook",
    "schedule by zapier": "Schedule Trigger",
    "email by zapier": "Email Trigger (IMAP)",
    "rss by zapier": "RSS Feed Trigger",
    "typeform": "Typeform Trigger",
    "calendly": "Calendly Trigger",
    "stripe": "Stripe Trigger",
    "jotform": "Jotform Trigger",
    "gmail": "Gmail Trigger",
    "google sheets": "Google Sheets Trigger",
    "google forms": "Google Sheets Trigger (on the responses sheet)",
    "google calendar": "Google Calendar Trigger",
    "google drive": "Google Drive Trigger",
    "airtable": "Airtable Trigger",
    "hubspot": "HubSpot Trigger",
    "shopify": "Shopify Trigger",
    "woocommerce": "WooCommerce Trigger",
    "slack": "Slack Trigger",
    "telegram": "Telegram Trigger",
    "notion": "Notion Trigger",
    "trello": "Trello Trigger",
    "pipedrive": "Pipedrive Trigger",
    "zendesk": "Zendesk Trigger",
}

ACTION_NODES = {
    "webhooks by zapier": "HTTP Request",
    "filter by zapier": "Filter",
    "paths by zapier": "Switch",
    "formatter by zapier": "Edit Fields (Set)",
    "delay by zapier": "Wait",
    "code by zapier": "Code",
    "email by zapier": "Send Email",
    "looping by zapier": "Loop Over Items",
    "storage by zapier": "Data table",
    "ai by zapier": "Basic LLM Chain",
    "openai": "OpenAI",
    "gmail": "Gmail",
    "google sheets": "Google Sheets",
    "google calendar": "Google Calendar",
    "google drive": "Google Drive",
    "google docs": "Google Docs",
    "slack": "Slack",
    "discord": "Discord",
    "telegram": "Telegram",
    "microsoft teams": "Microsoft Teams",
    "airtable": "Airtable",
    "notion": "Notion",
    "trello": "Trello",
    "asana": "Asana",
    "clickup": "ClickUp",
    "hubspot": "HubSpot",
    "pipedrive": "Pipedrive",
    "salesforce": "Salesforce",
    "mailchimp": "Mailchimp",
    "activecampaign": "ActiveCampaign",
    "stripe": "Stripe",
    "shopify": "Shopify",
    "woocommerce": "WooCommerce",
    "twilio": "Twilio",
    "zendesk": "Zendesk",
    "dropbox": "Dropbox",
}

FALLBACK_TRIGGER = "Webhook or Schedule Trigger + HTTP Request"
FALLBACK_ACTION = "HTTP Request"

# Built-in Zapier steps that do not use a task. Check your own Zapier task
# history for exact numbers: the rules have changed over time.
FREE_STEPS = {"filter by zapier", "paths by zapier", "formatter by zapier", "delay by zapier"}
# Steps that hold logic which has to be rebuilt and tested by hand.
LOGIC_STEPS = {"paths by zapier", "code by zapier", "looping by zapier"}


class InputError(ValueError):
    """The CSV is missing data or holds a value that cannot be used."""


@dataclass(frozen=True)
class Step:
    zapier_app: str
    n8n_node: str
    mapped: bool


@dataclass(frozen=True)
class ZapPlan:
    name: str
    trigger: Step
    actions: list[Step] = field(default_factory=list)
    runs_per_month: int = 0

    @property
    def tasks_per_month(self) -> int:
        billable = [a for a in self.actions if a.zapier_app.lower() not in FREE_STEPS]
        return self.runs_per_month * len(billable)

    @property
    def manual_steps(self) -> list[Step]:
        return [s for s in (self.trigger, *self.actions) if not s.mapped]

    @property
    def complexity(self) -> str:
        has_logic = any(a.zapier_app.lower() in LOGIC_STEPS for a in self.actions)
        count = len(self.actions)
        if count >= 8 or len(self.manual_steps) >= 3:
            return "complex"
        if count >= 4 or has_logic or self.manual_steps:
            return "medium"
        return "simple"


def map_trigger(app: str) -> Step:
    node = TRIGGER_NODES.get(app.lower())
    return Step(app, node or FALLBACK_TRIGGER, mapped=node is not None)


def map_action(app: str) -> Step:
    node = ACTION_NODES.get(app.lower())
    return Step(app, node or FALLBACK_ACTION, mapped=node is not None)


def plan_zap(row: dict[str, str], line: int) -> ZapPlan:
    name = (row.get("name") or "").strip()
    trigger = (row.get("trigger_app") or "").strip()
    if not name or not trigger:
        raise InputError(f"line {line}: name and trigger_app are required")

    raw_runs = (row.get("runs_per_month") or "").strip()
    try:
        runs = int(raw_runs)
    except ValueError:
        raise InputError(f"line {line}: runs_per_month must be a whole number, got '{raw_runs}'") from None
    if runs < 0:
        raise InputError(f"line {line}: runs_per_month cannot be negative")

    actions = [a.strip() for a in (row.get("action_apps") or "").split(";") if a.strip()]
    if not actions:
        raise InputError(f"line {line}: action_apps needs at least one app")

    return ZapPlan(name, map_trigger(trigger), [map_action(a) for a in actions], runs)


def load_plans(path: Path) -> list[ZapPlan]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise InputError(f"missing column(s): {', '.join(missing)}")
        return [plan_zap(row, line) for line, row in enumerate(reader, start=2)]


def render_report(plans: list[ZapPlan]) -> str:
    order = {"simple": 0, "medium": 1, "complex": 2}
    ordered = sorted(plans, key=lambda p: (order[p.complexity], -p.tasks_per_month))
    total_tasks = sum(p.tasks_per_month for p in plans)
    total_runs = sum(p.runs_per_month for p in plans)
    counts = {level: sum(1 for p in plans if p.complexity == level) for level in order}

    lines = [
        "# Zapier to n8n migration plan",
        "",
        "## Summary",
        "",
        f"- Zaps to migrate: {len(plans)}",
        f"- Simple: {counts['simple']}, medium: {counts['medium']}, complex: {counts['complex']}",
        f"- Zapier tasks used per month (estimate): {total_tasks:,}",
        f"- n8n executions per month after migration: {total_runs:,}",
        "",
        "Zapier bills per task (each action step). n8n counts one execution per",
        "workflow run, and a self-hosted instance has no per-execution charge.",
        "",
        "## Suggested order",
        "",
        "Move simple Zaps first, then medium, then complex. Within each group, move",
        "the Zaps that use the most tasks first.",
        "",
        "| # | Zap | Complexity | Steps | Tasks per month | Manual API steps |",
        "|---|-----|------------|-------|-----------------|------------------|",
    ]
    for index, plan in enumerate(ordered, start=1):
        lines.append(
            f"| {index} | {plan.name} | {plan.complexity} | {1 + len(plan.actions)} "
            f"| {plan.tasks_per_month:,} | {len(plan.manual_steps)} |"
        )

    lines += ["", "## Node mapping", ""]
    for plan in ordered:
        lines += [
            f"### {plan.name}",
            "",
            "| Step | Zapier app | n8n node | Note |",
            "|------|------------|----------|------|",
        ]
        for number, step in enumerate((plan.trigger, *plan.actions), start=1):
            role = "Trigger" if number == 1 else f"Action {number - 1}"
            note = "" if step.mapped else "No direct mapping here. Check the app's API."
            lines.append(f"| {role} | {step.zapier_app} | {step.n8n_node} | {note} |")
        lines.append("")

    lines += [
        "## Cut-over checklist (per Zap)",
        "",
        "1. Build the n8n workflow and connect credentials.",
        "2. Test with real sample data copied from the Zap history.",
        "3. Add an error workflow so failures send an alert.",
        "4. Turn the n8n workflow on and the Zap off at the same time.",
        "5. Compare results for one week before deleting the Zap.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv_file", type=Path, help="CSV with one row per Zap")
    args = parser.parse_args(argv)

    try:
        plans = load_plans(args.csv_file)
    except FileNotFoundError:
        print(f"File not found: {args.csv_file}", file=sys.stderr)
        return 2
    except InputError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return 2

    if not plans:
        print("Input error: the CSV has no Zaps", file=sys.stderr)
        return 2

    print(render_report(plans))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
