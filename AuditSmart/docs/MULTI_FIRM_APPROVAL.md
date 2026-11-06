# Multi-firm rule approval (D42–D45)

AuditSmart can be used by any audit firm. This page explains how the shipped
**default best-practice rules** stay `pending_verification`, and how each firm's audit
partner reviews them inside the tool. The partner can **approve** a default for the firm or
**override** it for the firm or for one engagement. No firm's decision ever reaches another
firm.

AI is not part of any of this. Rule values are typed by people, rules are resolved by plain
code, and calculations never use AI.

## 1. The model

| Layer | Stored as | Who creates it | Who sees it |
|---|---|---|---|
| **Shared default** | `rule_versions` row with `firm_id IS NULL` (the seed, Appendix D) | Platform (seed / Rules Library) | Every firm (read-only for firm users) |
| **Firm adoption** | `firm_rule_approvals` row (firm, default version, approver, comment) | The firm's partner | That firm only |
| **Firm override** | `rule_versions` row with `firm_id = <firm>` and `engagement_id IS NULL` | Proposed by a firm Manager/Partner/TaxPartner, approved by the firm's partner | That firm only |
| **Engagement override** | `rule_versions` row with `firm_id = <firm>` and `engagement_id = <engagement>` | Same as above, by members of that engagement | That engagement only |

- **Shared defaults are never edited by a firm.** When a firm approves a default, AuditSmart
  adds a `firm_rule_approvals` row. The shared row keeps its status, `pending_verification`,
  for everyone else.
- Overrides use the normal Rules Library workflow (`proposed` → `approved` or `rejected`,
  with closing, superseding and STALE marking). Every step is limited to the firm or
  engagement that owns the row.
- Version numbers stay global per `rule_key`. Every `key@vN` ref is therefore unique across
  firms, and existing refs such as the golden `@v1` refs are unchanged. An override records
  `based_on_id`, the default version it replaces.
- A client belongs to at most one firm (`clients.firm_id`). An engagement's firm is the firm
  of its client.

## 2. Resolution order

Every calculation resolves a rule for one date, inside a **rule scope** (firm, engagement).
Background jobs and the synchronous endpoints set the scope from the engagement, so a
calculation always uses the firm of the engagement's client.

1. An **approved engagement override** for this engagement.
2. An **approved firm override** for this firm.
3. The **shared default**. An approved global version beats a `pending_verification` one.
   - If this firm has adopted that version, it is used with status `approved`
     (`firm_approved = true`).
   - If not, it is used as `pending_verification`, but only when pending rules are allowed
     (see §3). Otherwise the call fails with "… awaits approval by the firm's audit partner".

`proposed`, `rejected` and `superseded` rows are never used. Rows of other firms are never
candidates.

Without a firm scope (legacy clients with no firm, or platform users), resolution is
**unchanged** from Stage 3 and uses global rows only. The golden and answer-key results are
therefore identical.

## 3. Pending defaults: `RULES_ALLOW_PENDING`

- The default stays **`RULES_ALLOW_PENDING=true`** (D24, D44). A new firm can start at once:
  every default it has not approved resolves as `pending_verification`. That status is
  recorded on every result and shown in the working paper.
- Each firm can **tighten** this setting with `PATCH /v1/firm/settings`
  `{"require_approved_rules": true, "comment": "..."}`. After that, the firm's calculations
  stop on any rule its partner has not approved or overridden.
- A firm can never relax the **platform-wide** `RULES_ALLOW_PENDING` flag. If the platform
  sets it to `false`, no firm can turn pending rules back on. A firm can switch its *own*
  `require_approved_rules` on and off (`PATCH /v1/firm/settings`, Partner / TaxPartner /
  Admin of the firm, comment required and audit-logged):
  `pending allowed = RULES_ALLOW_PENDING AND NOT firm.require_approved_rules`.
- `GET /v1/firm` shows both flags and the result (`pending_rules_resolve`).

## 4. Endpoints

Firm users are identified by a **firm claim** in their token. The claim name is set by
`AUTH_FIRM_CLAIM` (default `firm_id`) and its value must equal `firms.id`.
- **Entra ID:** a top-level claim (add it as an optional claim or app role mapping).
- **Supabase:** `app_metadata.firm_id`, which only the server can set. `user_metadata` is
  never read, and neither is a top-level `firm_id` claim (D48).

Every decision needs a non-empty `comment` and is written to `audit_log`.

| Method and path | Purpose | Roles |
|---|---|---|
| `GET /v1/firm` | The caller's firm and its rule settings | Any firm user |
| `PATCH /v1/firm/settings` | Set `require_approved_rules` (tighten or relax the firm's own setting) | Partner, TaxPartner, Admin of the firm |
| `GET /v1/firm/rules/review?on=&domain=&status=&engagement_id=` | **One list of every default rule**, showing the firm's position on each: the default version, the firm's approval, any firm or engagement override, open proposals, the value that would be used now (`effective`), and who may approve it. `status` filters by `approved_by_firm`, `overridden`, `awaiting_firm_approval` or `not_effective`. `engagement_id` shows that engagement's view (membership required) | Any firm user |
| `POST /v1/firm/rules/{rule_key}/approve` | `{"comment": "...", "on"?: date}` approves the shared default effective on `on` (default today) for the firm. `{"comment": "...", "version_id": "<firm proposal>"}` approves a pending firm or engagement override instead | **TaxPartner** for tax domains (VAT, INPUT_VAT, CT, TRN, LEGAL_REF). **Partner** for methodology domains. For an engagement override the approver must also be a member of the engagement |
| `POST /v1/firm/rules/{rule_key}/override` | Propose the firm's own value: `value`, `effective_from`, optional `effective_to`, optional `engagement_id`, `source_ref`, optional `source_url`, `unit`, `comment`. Returns 201 with the `proposed` version | Manager, Partner, TaxPartner (members only, for an engagement override) |
| `POST /v1/firm/rules/{rule_key}/reject` | `{"version_id": "...", "comment": "..."}` rejects one of the firm's proposals | Same approver roles as approve |
| `POST /v1/firms` | Register a firm (`id`, `name`, `require_approved_rules`) | Platform Admin (Admin role, **no** firm claim) |
| `PUT /v1/firms/{firm_id}/clients/{client_id}` | Link an unassigned client to a firm. Repeating it is harmless; moving a client to another firm returns 409 | Platform Admin |

The **Admin role never approves rules**. This applies to firm Admins and to the platform
Admin. Platform users (no firm claim) approving or rejecting a **shared default** through
`POST /v1/rules/{id}/approve|reject` follow the same domain split: TaxPartner for tax domains,
Partner for methodology domains (D47).

### What changes in the existing `/v1/rules` endpoints for firm users
- `GET /v1/rules` lists the shared defaults plus the caller's own firm's rows only.
- `GET /v1/rules/resolve` uses the firm scope. It takes an optional `engagement_id`, which
  needs membership.
- `POST /v1/rules/proposals` (propose a shared version), and `POST /v1/rules/{id}/approve` or
  `POST /v1/rules/{id}/reject` on a shared default, return **403**: "Default rules are shared by every firm; approve one for your firm with …".
  Firm users act through the `/v1/firm/rules/...` endpoints instead.
- Another firm's rows return **404**. Platform approvers cannot approve firm rows (also 404).
- The rules monitor (3.9) only ever sends shared defaults to the AI extraction prompt. Firm
  rows are never included.

## 5. Partner workflow

1. A platform Admin registers the firm (`POST /v1/firms`) and links its clients
   (`PUT /v1/firms/{id}/clients/{client}`). The firm's users get the `firm_id` claim.
2. The firm starts working immediately. Unapproved defaults resolve as
   `pending_verification`, and results and working papers say so.
3. The Tax Partner and the audit Partner open `GET /v1/firm/rules/review?status=awaiting_firm_approval`.
   For each rule, they do one of three things:
   - **Approve** it (`POST …/approve` with a comment). From then on the firm's results use
     it as `approved`. The default's value does not change, so no result becomes STALE.
   - **Override** it (`POST …/override`). Then **approve** the proposal (`POST …/approve`
     with `version_id`). Approving closes or supersedes only the firm's (or the engagement's)
     own earlier rows, and marks STALE only results of that firm's (or engagement's)
     engagements whose period lost coverage.
   - **Leave it pending**, or **reject** a proposal (`POST …/reject`).
4. When everything needed is approved, the firm can set `require_approved_rules=true`.
5. If the platform later publishes a new default version, each firm sees it as
   `awaiting_firm_approval` again. An adoption applies to one specific version.

## 6. Isolation guarantees (tested)

- Firm A's approval, override or proposal never changes what firm B resolves, lists or
  reviews. This is tested, including against the golden data (161 / 3.00 for firm B
  unchanged).
- Another firm's rows and proposals return 404. Another firm's engagements return 403
  ("This engagement belongs to another firm.") on every engagement-scoped endpoint. Firm
  users cannot list or act on them.
- STALE marking after a firm or engagement override is limited to that firm's or
  engagement's results.
- Jobs (parse, validate, JE tests, sampling, evaluation, input-VAT, working paper) run in the
  scope of their engagement's firm.

## 7. Audit trail

| Action | `audit_log.action` |
|---|---|
| Register a firm | `firm_create` |
| Link a client to a firm | `client_firm` |
| Change firm settings | `firm_settings` (old and new values, comment) |
| Approve a default for the firm | `firm_rule_approve` (default ref, firm, comment) |
| Propose an override | `rule_propose` + `firm_rule_override` |
| Approve an override | `rule_approve` (+ `rule_close` for each closed or superseded own row) |
| Reject a proposal | `rule_reject` |
| Results affected | `stale` (one row per result) |
| Engagement sync (§10) | `client_sync_create` / `client_sync_update`, `engagement_sync_create` / `engagement_sync_update` (old and new values, members, firm_id) |

## 8. Database

Migration **`0008_multi_firm_rules.py`** (revision `0008`, after `0007`):
- adds a `firms` table;
- adds `clients.firm_id`;
- adds `rule_versions.firm_id`, `engagement_id` and `based_on_id`;
- adds a `firm_rule_approvals` table (unique per firm and version).

It has a full downgrade. Existing rows keep `firm_id = NULL`, so an existing installation
behaves exactly as before until a firm is registered.

## 9. Not in scope yet / to confirm

- There is no endpoint yet to revoke a firm adoption. A firm can override instead.
- The same partner may both propose and approve (no four-eyes rule is enforced).
- Clients cannot move between firms.
- A Lovable screen for the review list is Stage 4.

## 10. Engagement sync from the front end (Stage 5.2, D50–D55)

Lovable keeps clients, engagements and teams in Supabase. The engine needs the same rows,
because every engagement call checks membership and the firm boundary. The front end
therefore sends each engagement to the engine whenever it or its team is created or edited:

```
PUT /v1/engagements/{engagement uuid}
{"client": {"id": "<client uuid>", "client_code": "C001", "name": "…", "emirate": "Dubai",
            "entity_type": "LLC"},
 "fye": "2025-12-31", "framework": "IFRS", "materiality": "1500000.00",
 "perf_materiality": "1125000.00", "trivial": "75000.00", "status": "planning",
 "members": [{"user_id": "<auth user uuid = token sub>", "role": "Manager"}, …]}
→ 201 {created: true, engagement, client, members, stale: []}   (first time)
→ 200 {created: false, …}                                         (every later call)
```

- **Firm:** always the caller's token firm (`app_metadata.firm_id`). It must already be
  registered with `POST /v1/firms` by the platform Admin; otherwise 403. The body has no
  firm field.
- **Who:** create needs app role Manager, Partner, TaxPartner or the firm's Admin. Update
  needs a team member whose engagement role is Manager, Partner or TaxPartner, or the
  firm's Admin. Seniors and Staff can never change a team.
- **Isolation:** another firm's engagement id → 403; another firm's client id → 404;
  a legacy client or engagement with no firm → 409 (the platform Admin links it first,
  §4); an engagement cannot move to another client (409). `client_code` is unique per
  firm (migration 0010).
- **Team:** `members` replaces the whole team. It needs at least one Manager or Partner;
  `user_id` must be the Supabase auth user id (the token `sub`).
- **STALE:** a new year end marks all current samples, JE runs and input-VAT runs of the
  engagement STALE; a new emirate re-checks the client's JE runs against the calendar.
  Other changes are audit-only.
- **Read back:** `GET /v1/engagements/{id}` (team members, or the firm's Admin).
