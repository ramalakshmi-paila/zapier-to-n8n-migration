"""Tests for migration_plan.py and the example workflow. Run with: python -m pytest"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import migration_plan as mp  # noqa: E402


def row(**overrides) -> dict[str, str]:
    base = {"name": "Zap", "trigger_app": "Typeform", "action_apps": "Slack", "runs_per_month": "10"}
    return {**base, **overrides}


# --- mapping ----------------------------------------------------------------


def test_known_apps_map_to_n8n_nodes_ignoring_case():
    assert mp.map_trigger("TYPEFORM") == mp.Step("TYPEFORM", "Typeform Trigger", True)
    assert mp.map_action("google sheets") == mp.Step("google sheets", "Google Sheets", True)


def test_unknown_apps_fall_back_to_http_and_are_flagged():
    assert mp.map_action("Teachable") == mp.Step("Teachable", "HTTP Request", False)
    assert mp.map_trigger("Teachable").mapped is False


# --- task counting ----------------------------------------------------------


def test_tasks_are_runs_times_billable_actions():
    plan = mp.plan_zap(row(action_apps="Google Sheets;Gmail", runs_per_month="250"), 2)
    assert plan.tasks_per_month == 500


def test_filter_formatter_paths_and_delay_do_not_count_as_tasks():
    apps = "Formatter by Zapier;Filter by Zapier;Paths by Zapier;Delay by Zapier;Slack"
    plan = mp.plan_zap(row(action_apps=apps, runs_per_month="400"), 2)
    assert plan.tasks_per_month == 400


# --- complexity -------------------------------------------------------------


@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        ("Slack", "simple"),
        ("Slack;Gmail;Google Sheets", "simple"),
        ("Slack;Gmail;Google Sheets;Notion", "medium"),
        ("Paths by Zapier;Slack", "medium"),
        ("Code by Zapier", "medium"),
        ("Teachable", "medium"),
        (";".join(["Slack"] * 8), "complex"),
        ("AppOne;AppTwo;AppThree", "complex"),
    ],
)
def test_complexity(actions, expected):
    assert mp.plan_zap(row(action_apps=actions), 2).complexity == expected


# --- input validation -------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"name": ""},
        {"trigger_app": " "},
        {"action_apps": " ; "},
        {"runs_per_month": "many"},
        {"runs_per_month": "-5"},
        {"runs_per_month": ""},
    ],
)
def test_bad_rows_raise_with_line_number(bad):
    with pytest.raises(mp.InputError, match="line 7"):
        mp.plan_zap(row(**bad), 7)


def test_missing_column_is_reported(tmp_path):
    path = tmp_path / "zaps.csv"
    path.write_text("name,trigger_app\nA,B\n", encoding="utf-8")
    with pytest.raises(mp.InputError, match="action_apps, runs_per_month"):
        mp.load_plans(path)


def test_csv_saved_by_excel_with_bom_loads(tmp_path):
    path = tmp_path / "zaps.csv"
    path.write_text("name,trigger_app,action_apps,runs_per_month\nA,Stripe,Slack,3\n", encoding="utf-8-sig")
    assert mp.load_plans(path)[0].name == "A"


# --- report and command line ------------------------------------------------


def test_example_report_totals_and_order(capsys):
    assert mp.main([str(ROOT / "examples" / "zaps.csv")]) == 0
    report = capsys.readouterr().out

    # 400*1 + 250*2 + 900*4 + 4*3 + 120*2
    assert "Zapier tasks used per month (estimate): 4,752" in report
    assert "n8n executions per month after migration: 1,674" in report
    assert "Simple: 2, medium: 3, complex: 0" in report

    table = [line for line in report.splitlines() if line.startswith("| 1 |") or line.startswith("| 5 |")]
    assert "Invoice paid to sheet" in table[0]  # simple, most tasks
    assert "Weekly report" in table[1]  # medium, fewest tasks
    assert "| Trigger | Teachable | Webhook or Schedule Trigger + HTTP Request | No direct mapping" in report


def test_main_returns_2_for_missing_file_and_empty_csv(tmp_path, capsys):
    assert mp.main([str(tmp_path / "nope.csv")]) == 2

    empty = tmp_path / "empty.csv"
    empty.write_text("name,trigger_app,action_apps,runs_per_month\n", encoding="utf-8")
    assert mp.main([str(empty)]) == 2
    assert "no Zaps" in capsys.readouterr().err


# --- the example n8n workflow -----------------------------------------------


@pytest.fixture()
def workflow() -> dict:
    return json.loads((ROOT / "n8n" / "new-lead-alert.json").read_text(encoding="utf-8"))


def test_workflow_node_names_and_ids_are_unique(workflow):
    names = [n["name"] for n in workflow["nodes"]]
    ids = [n["id"] for n in workflow["nodes"]]
    assert len(set(names)) == len(names)
    assert len(set(ids)) == len(ids)


def test_workflow_connections_point_at_real_nodes(workflow):
    names = {n["name"] for n in workflow["nodes"]}
    for source, outputs in workflow["connections"].items():
        assert source in names
        for branch in outputs["main"]:
            for link in branch:
                assert link["node"] in names


def test_every_node_except_the_note_is_reachable_from_the_trigger(workflow):
    reachable, queue = set(), ["New lead webhook"]
    while queue:
        name = queue.pop()
        if name in reachable:
            continue
        reachable.add(name)
        for branch in workflow["connections"].get(name, {}).get("main", []):
            queue.extend(link["node"] for link in branch)

    expected = {n["name"] for n in workflow["nodes"] if n["type"] != "n8n-nodes-base.stickyNote"}
    assert reachable == expected


def test_workflow_ships_without_credentials_or_real_urls(workflow):
    assert all("credentials" not in n for n in workflow["nodes"])
    slack = next(n for n in workflow["nodes"] if n["name"] == "Send Slack alert")
    assert "REPLACE" in slack["parameters"]["url"]


def test_webhook_requires_authentication(workflow):
    webhook = next(n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.webhook")
    assert webhook["parameters"]["authentication"] != "none"
