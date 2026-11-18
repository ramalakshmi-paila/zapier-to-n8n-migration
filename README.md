# Zapier to n8n migration example

A worked example of moving automations from Zapier to n8n: a planning tool
that turns a list of Zaps into a migration plan, and one Zap rebuilt as an
n8n workflow.

## Why migrate

Zapier bills per task, and each action step in a Zap uses a task. n8n counts
one execution per workflow run, however many steps it has, and a self-hosted
instance has no per-execution charge. For multi-step automations that run
often, the difference adds up. See the cost comparisons by
[Flowmondo](https://www.flowmondo.com/article/n8n-vs-zapier-vs-make) and an
[n8n community member](https://community.n8n.io/t/n8n-vs-zapier-my-honest-cost-breakdown-after-1-year-of-self-hosting/286907).

Migration is not always the right call. Self-hosting means someone has to
update and back up the server.

## 1. Plan the migration

List your Zaps in a CSV, one row each:

```csv
name,trigger_app,action_apps,runs_per_month
New lead alert,Webhooks by Zapier,Formatter by Zapier;Filter by Zapier;Slack,400
Invoice paid to sheet,Stripe,Google Sheets;Gmail,250
```

Then run:

```bash
python migration_plan.py examples/zaps.csv > plan.md
```

The report ([examples/plan.md](examples/plan.md)) gives:

- the n8n node that replaces each Zapier step
- a complexity rating per Zap and a suggested order
- steps with no direct mapping, which need API work
- an estimate of Zapier tasks used per month
- a cut-over checklist

Example summary for the five sample Zaps:

```text
Zaps to migrate: 5
Simple: 2, medium: 3, complex: 0
Zapier tasks used per month (estimate): 4,752
n8n executions per month after migration: 1,674
```

The task count is an estimate. It assumes Filter, Formatter, Paths and Delay
steps use no tasks. Check your Zapier task history for exact numbers.

## 2. One Zap, before and after

### Before: the Zap

| Step | App | What it does |
|---|---|---|
| Trigger | Webhooks by Zapier | Catches a POST from the website contact form |
| Action 1 | Formatter by Zapier | Trims the name, lower-cases the email |
| Action 2 | Filter by Zapier | Continues only if there is an email and the budget is 1000 or more |
| Action 3 | Slack | Posts the lead to a sales channel |

### After: the n8n workflow

[n8n/new-lead-alert.json](n8n/new-lead-alert.json)

```text
New lead webhook -> Clean lead fields -> Has email and budget of 1000 or more?
                                            | yes -> Send Slack alert
                                            | no  -> Ignore lead
```

Changes made during the move:

- The webhook needs a secret header. The original Zap URL was open to anyone
  who knew it.
- Missing fields no longer break the run. An empty name or budget gets a safe
  default.
- The Slack call retries three times before failing.

### Test result

Run on n8n Cloud with four sample leads. The webhook input and the Slack call
were simulated, and the other nodes ran for real.

| Lead sent | Cleaned to | Result |
|---|---|---|
| name `"  Ada Example "`, email `" ADA@Example.com "`, budget `"2500"` | `Ada Example`, `ada@example.com`, `2500` | Slack alert |
| budget `200` | budget `200` | Ignored |
| no email, budget `"5000"` | email empty | Ignored |
| no name, budget `"not a number"` | budget `0` | Ignored |

### Import it

1. In n8n choose **Create workflow**, then **Import from file**, and pick
   `n8n/new-lead-alert.json`.
2. On the webhook node create a **Header Auth** credential.
3. On the Slack node replace the URL with your Slack incoming webhook URL.
4. Send a test request:

```bash
curl -X POST "https://YOUR-N8N/webhook-test/new-lead" -H "X-Api-Key: YOUR-SECRET" -H "Content-Type: application/json" -d '{"name":" Ada ","email":"ADA@Example.com","budget":"2500"}'
```

## Tests

```bash
pip install -r requirements.txt
python -m pytest
```

The tests cover the planning tool and check the workflow file is well formed.

## Limits

- The app mapping covers common apps. Others fall back to the HTTP Request
  node and are flagged for manual work.
- The tool plans a migration. It does not convert Zaps automatically.

## Licence

MIT
