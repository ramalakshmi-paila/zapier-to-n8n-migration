# Zapier to n8n migration plan

## Summary

- Zaps to migrate: 5
- Simple: 2, medium: 3, complex: 0
- Zapier tasks used per month (estimate): 4,752
- n8n executions per month after migration: 1,674

Zapier bills per task (each action step). n8n counts one execution per
workflow run, and a self-hosted instance has no per-execution charge.

## Suggested order

Move simple Zaps first, then medium, then complex. Within each group, move
the Zaps that use the most tasks first.

| # | Zap | Complexity | Steps | Tasks per month | Manual API steps |
|---|-----|------------|-------|-----------------|------------------|
| 1 | Invoice paid to sheet | simple | 3 | 500 | 0 |
| 2 | New lead alert | simple | 4 | 400 | 0 |
| 3 | Support ticket triage | medium | 6 | 3,600 | 0 |
| 4 | Course signup sync | medium | 3 | 240 | 1 |
| 5 | Weekly report | medium | 4 | 12 | 0 |

## Node mapping

### Invoice paid to sheet

| Step | Zapier app | n8n node | Note |
|------|------------|----------|------|
| Trigger | Stripe | Stripe Trigger |  |
| Action 1 | Google Sheets | Google Sheets |  |
| Action 2 | Gmail | Gmail |  |

### New lead alert

| Step | Zapier app | n8n node | Note |
|------|------------|----------|------|
| Trigger | Webhooks by Zapier | Webhook |  |
| Action 1 | Formatter by Zapier | Edit Fields (Set) |  |
| Action 2 | Filter by Zapier | Filter |  |
| Action 3 | Slack | Slack |  |

### Support ticket triage

| Step | Zapier app | n8n node | Note |
|------|------------|----------|------|
| Trigger | Zendesk | Zendesk Trigger |  |
| Action 1 | OpenAI | OpenAI |  |
| Action 2 | Paths by Zapier | Switch |  |
| Action 3 | Slack | Slack |  |
| Action 4 | Asana | Asana |  |
| Action 5 | Gmail | Gmail |  |

### Course signup sync

| Step | Zapier app | n8n node | Note |
|------|------------|----------|------|
| Trigger | Teachable | Webhook or Schedule Trigger + HTTP Request | No direct mapping here. Check the app's API. |
| Action 1 | Mailchimp | Mailchimp |  |
| Action 2 | Google Sheets | Google Sheets |  |

### Weekly report

| Step | Zapier app | n8n node | Note |
|------|------------|----------|------|
| Trigger | Schedule by Zapier | Schedule Trigger |  |
| Action 1 | Google Sheets | Google Sheets |  |
| Action 2 | Code by Zapier | Code |  |
| Action 3 | Email by Zapier | Send Email |  |

## Cut-over checklist (per Zap)

1. Build the n8n workflow and connect credentials.
2. Test with real sample data copied from the Zap history.
3. Add an error workflow so failures send an alert.
4. Turn the n8n workflow on and the Zap off at the same time.
5. Compare results for one week before deleting the Zap.

