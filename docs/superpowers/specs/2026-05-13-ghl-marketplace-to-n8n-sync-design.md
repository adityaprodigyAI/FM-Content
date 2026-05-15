# Design: FirstMovers GoHighLevel → n8n Sync

**Date:** 2026-05-13
**Owner:** Aditya Singh (aditya@calldental.ai)
**Status:** v1 SHIPPED & VERIFIED — INSTALL + ContactCreate webhooks confirmed live
**Related n8n workflow:** `FMGHL` (id `0djIDmctSK1vm9A9`) at https://n8n.callreceptionist.com
**GHL app:** `FM-Webhook` (id `6a044f181ec5bf79ae2e5e73`) — Private, Sub-Account, installed on FirstMovers location `FHkXd7nR6YPRBpswDWgf` / company `t1aFfE9Z2lKoCIEDYO5k`
**OAuth Client ID:** `6a044f181ec5bf79ae2e5e73-mp4d6zkn` (Client Secret stored separately; rotate after Session 1 per security note)
**Install URL (canonical):** `https://marketplace.gohighlevel.com/oauth/chooselocation?response_type=code&redirect_uri=https%3A%2F%2Fn8n.callreceptionist.com%2Frest%2Foauth2-credential%2Fcallback&client_id=6a044f181ec5bf79ae2e5e73-mp4d6zkn&scope=contacts.readonly+contacts.write+opportunities.readonly+opportunities.write+locations.readonly&version_id=6a044f181ec5bf79ae2e5e73`

## Goal

Push contact, opportunity, pipeline, and stage events from the FirstMovers GoHighLevel sub-account into n8n in real time, where downstream automation can act on them.

## Decisions locked

| Parameter | Choice | Why |
|---|---|---|
| GHL app type | **Private Marketplace App** | Production-quality OAuth + webhooks without the public-listing review |
| Distribution | **Sub-account** | Only FirstMovers' own location installs it |
| Locations served | **One** (FirstMovers main) | Single-tenant — no token-broker DB needed |
| Bridge | **Direct: GHL → n8n Webhook node** | n8n has no HighLevel Trigger; webhook is the cleanest path |
| n8n host | Self-hosted at `n8n.callreceptionist.com` (MCP-connected) | Already provisioned |
| Workflow shape | **Intake + sub-workflows per event** (target) | Per-event versioning + clean logs; v1 ships intake with placeholder routing, sub-workflows added in iteration 2 |
| Destination | Stay in n8n only, downstream actions per event | No persistent event log required |

## Events subscribed (v1)

App lifecycle (auto): `INSTALL`, `UNINSTALL`.

Contact: `ContactCreate`, `ContactUpdate`, `ContactDelete`, `ContactTagUpdate`, `ContactDndUpdate`.

Opportunity: `OpportunityCreate`, `OpportunityUpdate`, `OpportunityDelete`, `OpportunityStageUpdate`, `OpportunityStatusUpdate`.

## OAuth scopes

`contacts.readonly`, `contacts.write`, `opportunities.readonly`, `opportunities.write`, `opportunities/leadValue.readonly`, `locations.readonly`.

## Endpoints in play

- Authorization: `https://marketplace.leadconnectorhq.com/oauth/chooselocation`
- Token exchange: `POST https://services.leadconnectorhq.com/oauth/token`
- API base: `https://services.leadconnectorhq.com` (always include header `Version: 2021-07-28`)

## n8n intake workflow (current state, v1)

```
Webhook (POST) ──► Parse Event ──┬──► Respond 200
                                 └──► Route by event type (Switch, 11 named outputs + unhandled)
```

Production webhook URL (paste this into GHL): `https://n8n.callreceptionist.com/webhook/5bee003e-28e1-4215-b89a-572b79242941`

Nodes:
- **Webhook (GHL events)** — POST, `responseMode: responseNode`
- **Parse Event** — Code node, extracts `type`, `webhookId`, `locationId`, `id`, `timestamp`, both signature headers, and the raw payload
- **Respond 200** — `Respond to Webhook`, returns `{ ok: true, received: <type>, webhookId: <id> }` immediately
- **Route by event type** — Switch v3.2 with 11 named outputs and a fallback "unhandled" branch; outputs to be wired to per-event sub-workflows in iteration 2

## Webhook signature verification (iteration 2)

GHL signs every webhook with `X-GHL-Signature` (Ed25519, preferred) and the legacy `X-WH-Signature` (RSA-SHA256). The current Parse Event node captures both headers into the payload but does not yet verify. Verification will be added as a dedicated Code node between Webhook and Parse Event, using GHL's published public keys.

Public keys:
- GHL (Ed25519): `MCowBQYDK2VwAyEAi2HR1srL4o18O8BRa7gVJY7G7bupbN3H9AwJrHCDiOg=` (PEM body)
- Legacy (RSA): published in the GHL Webhook Integration Guide

## Idempotency (iteration 2)

`webhookId` is unique per delivery. The dedupe layer will keep the last ~500 IDs in workflow `staticData` and short-circuit duplicates with a 200 response and `{"status":"duplicate"}` body.

## Error handling rules

- **Always respond 200 once signature passes and event isn't a duplicate** — GHL retries on non-200 within ~30s.
- **Bad signature → 401** (no retry storm; GHL surfaces this in the developer portal).
- **Duplicate `webhookId` → 200 with body `{"status":"duplicate"}`**.
- **Sub-workflow failure** uses n8n's built-in retry (3 attempts, exponential backoff); final failure alerts via the workflow's error workflow.

## Testing plan

1. **Install smoke test** — when FirstMovers installs the private app, GHL fires `INSTALL` automatically. Expect a successful execution in n8n with `type: "INSTALL"` and a valid `locationId`. ✅ **VERIFIED 2026-05-13 18:04** — exec `481963`, locationId `FHkXd7nR6YPRBpswDWgf`, companyName "First Movers", both signature headers present, 38ms duration.
2. **Contact lifecycle** — create a test contact in FirstMovers → expect `ContactCreate`. Add a tag → expect `ContactTagUpdate`. Toggle DND → expect `ContactDndUpdate`. Delete → expect `ContactDelete`. ✅ **`ContactCreate` VERIFIED 2026-05-13 18:08** — exec `481976`, contact `1wIhmk0i2Z1b8RHXV5Qp`, both signatures present, 22ms duration.
3. **Opportunity lifecycle** — create a test opportunity → `OpportunityCreate`. Move to next stage → `OpportunityStageUpdate`. Mark won → `OpportunityStatusUpdate`. Delete → `OpportunityDelete`. (Pending — to be exercised next session.)
4. **Idempotency check** (after iteration 2) — re-fire the same `webhookId` from the GHL developer portal; expect the second to hit the dedupe branch.

## Lessons learned during install (worth keeping)

- The "v2" install URL shown in the dev portal Auth page Install-link panel uses `version_id=...` but **does not include `appId=...`** in its query string. The chooselocation page's first API call (`backend.leadconnectorhq.com/marketplace/app/installationDetails?appId=&versionId=...`) returns **400** with `appId` empty, so the page renders blank. This is a Draft-private-app bug in the v2 install flow — at minimum it's a UX trap.
- The **v1 install URL** (`/oauth/chooselocation` without the `/v2/` prefix) works, but for Draft apps it requires **both** `client_id` *and* `version_id`. Using only `client_id` returns `error.noAppVersionIdFound`.
- The Client ID for a marketplace app lives on **`Manage → Secrets`** in the dev portal (sidebar nav). Format is `<app_id>-mp<8-char-suffix>`. The Client Secret on the same page is displayed only on creation and at-rest as `*************`.
- `marketplace.gohighlevel.com` (developer portal) and `app.gohighlevel.com` (agency app) maintain **independent sessions**. The Login button on chooselocation uses a popup-based SSO bridge that `postMessage`s back to the parent window. In Playwright that bridge can fail because the new tab/popup is opened as a separate top-level page; the workaround is to open the URL once with the developer-portal session live and let GHL auto-select the (only matching) location.

## Out of scope (explicit YAGNI)

- Multi-location token resolution
- Persistent event log to a database
- Pipeline structure caching (pull on demand via `GET /opportunities/pipelines?locationId=...` when a handler needs it)
- Public marketplace listing / GHL review
- Bridge service in front of n8n
- Specific downstream actions inside each sub-workflow (per-event editing task)

## Iteration 2 (not in v1)

1. Add Ed25519 signature verification node between Webhook and Parse Event.
2. Add dedupe node using workflow `staticData`.
3. Create 11 sub-workflows (`ghl.app.installed`, `ghl.contact.created`, `ghl.contact.updated`, `ghl.contact.deleted`, `ghl.contact.tag`, `ghl.contact.dnd`, `ghl.opp.created`, `ghl.opp.updated`, `ghl.opp.deleted`, `ghl.opp.stage`, `ghl.opp.status`) — each a thin `Execute Workflow Trigger → downstream actions` shape.
4. Wire each Switch output to its corresponding sub-workflow via `Execute Workflow` node in the intake.
5. Create an `n8n.errorWorkflow` workflow and reference it in the intake workflow settings.
