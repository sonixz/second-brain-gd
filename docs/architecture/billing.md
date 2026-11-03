# Real costs (OpenAI billing)

The owner wants the amounts OpenAI actually bills, not estimates. The app stores none of it: OpenAI
already keeps every request, token and dollar. The engine asks OpenAI when the dashboard opens.

## Why a second key

A project key (`sk-proj-…`) cannot read usage or costs at any permission level. Measured 2026-11-03:
`GET /v1/organization/costs` returned HTTP 403 with "Missing scopes: api.usage.read". These endpoints need
an **admin key**. It is created by an organization owner, under Settings → Organization → Admin keys,
with permissions **Restricted** and **Usage API: Read**, and everything else left at None.

Such a key can read usage and costs. It cannot call models or change anything. It is stored like the
regular key:
- in the OS keyring, as provider `openai_admin`;
- in a private file when there is no keyring;
- or in `OPENAI_ADMIN_KEY` for developers using `dotenvx run`.

## What is read (`engine/billing.py`)

- **`GET /v1/organization/costs`** with `bucket_width=1d` and `group_by=line_item`, from the earlier of
  the month start or 30 days ago. It gives billed amounts per UTC day and per line item, for example
  `gpt-4o-…, input`.
- **`GET /v1/organization/usage/{completions,embeddings,audio_speeches,audio_transcriptions}`** with
  `group_by=model`, month to date. It gives requests and tokens, and characters or seconds for audio.
- **The chart.** Line items are grouped by product (the text before the comma), ranked by spend. The top
  5 get the fixed categorical colours, and the rest fold into "Other".
- **Caching.** An in-memory cache keeps results for 5 minutes, and **Refresh** bypasses it. Nothing is
  written to disk.
- **Daily buckets.** OpenAI fills in today's amount as it updates billing, so the app has no live
  per-second meter.

## Routes

| Route | Purpose |
|---|---|
| `GET /billing/status` | Whether an admin key is configured, plus its last 4 characters |
| `GET /billing?days=30&refresh=` | The figures, or `{configured: false}` |
| `PUT /billing/key` | Checks the key with one cheap costs call. A 401 or 403 is refused with a clear message, then the key is stored |
| `DELETE /billing/key` | Removes the key |

## Tests

`SBGD_BILLING_PROVIDER=fake` serves canned pages in OpenAI's exact shapes. The tests use it, the Godot
end-to-end run uses it, and the screenshots use it. The parsing and paging code is the same as for the
real API.
