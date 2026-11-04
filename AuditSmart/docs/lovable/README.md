# Stage 4 Lovable prompt pack (multi-firm, lean)

Prepared 1 Nov 2026. Sources: Build Guide v2.0 (prompts 4.1 to 4.5, Appendix A), Stage-by-Stage Workbook (Stage 4, Part B3), and docs/MULTI_FIRM_APPROVAL.md with D42 to D45.
- **Scope:** 4.1 to 4.5 plus Partner Review. 4.6 (jobs, large tables) and 4.7 (Input VAT tab) are deferred.
- **Budget:** about 100 credits.
- **Rule:** the front end does no audit calculations, and AI never calculates.

## Files
| File | What it is |
|---|---|
| 4.1_master_prompt.md | Master build, multi-firm roles, Partner Review page, and the engine contract |
| 4.2_data_security.md | Supabase tables (Appendix A plus firms), firm-scoped RLS, test users |
| 4.4_calendar.md | Working Calendar (lean) |
| 4.5_rules_library.md | Rules Library (lean, manual mode, corrected roles) |
| 4.3_ux_and_fixes.md | UX pass plus the B3 batch-fix list, one message |
| 5.2_engine_connect.md | **Stage 5.2**: engine-proxy edge function, remove mocks, roles/firm into the token, engagement sync (`PUT /v1/engagements/{id}`), Engine status card. Paste after the engine 0.2.1 is deployed (~8–12 credits) |
| engine_openapi.json | Full OpenAPI contract, exported from the committed engine 0.2.2 |
| engine_endpoints.txt / engine_endpoints_compact.txt | Endpoint lists (long and compact). The compact list is inside 4.1 |
| export_contract.py | Regenerates the three files above: `engine/.venv/bin/python docs/lovable/export_contract.py` |

`4.1_master_prompt_with_engine_contract.md` (30 Oct) was removed. It came before the multi-firm work: it had no `/v1/firm` endpoints and said Admin approves rules.

## Starting the Lovable project (step by step)
1. Go to lovable.dev and sign in. Check that your plan shows **Pro**, and note the start date and credit balance in the Credit Budget workbook.
2. In Account settings, check that AI training on your data is off (Workbook step 4.0).
3. From the Lovable home page, start a **new project** by using the main chat box ("What do you want to build?") or the New project button. Do not type anything else first.
4. Open `4.1_master_prompt.md` and copy **only** the text between the two dashed lines. Paste it into the chat box as **one message** and send it.
5. Wait until Lovable finishes, which takes several minutes. The preview appears on the right.
6. Click through every page with the mock data. **Write problems in a list. Do not fix them one at a time.** Log the credits used.
7. Connect Supabase (Supabase button, then Connect, then create the project `auditsmart-dev`), then paste 4.2. Approve the migrations when Lovable asks.
8. Connect GitHub (GitHub icon, then Connect, then Create repository, for example `auditsmart-web`). This must be a **new** repository. Do not point it at the engine repo `Savio2358/AuditSmart`.
9. Paste 4.4, then 4.5, then 4.3 with your problem list, checking after each one (see below).

## Order, credits and what to check
| # | Prompt | Workbook planned | Lean target | What you should see |
|---|---|---|---|---|
| 1 | 4.1 Master build | 40 | ~42 | Every page opens with mock data: Dashboard (including the "Rules pending verification for your firm" card), Engagements, workspace tabs, Review Queue, Calendar, Rules Library, Jobs, Audit Trail, Admin, **Partner Review**. A firm name badge in the header. The footer has the engine version |
| 2 | 4.2 Data and security | 8 | ~10 | Tables created, including `firms` and `firm_rule_approvals`. The 7 test users log in |
| 3 | 4.4 Calendar | 13 | ~10 | Work Week editor (Mon to Sun boxes, half-day times, dated periods that refuse overlaps) and month preview colours. Test data: Client A has Sat/Sun off with a Friday half day to 12:00; Client B has Friday only off; the 2025 holidays are typed in by hand |
| 4 | 4.5 Rules Library | 13 | ~10 | Current Rules, version history, Upload FTA PDF, verification checklist, and the "Review for my firm" link to Partner Review |
| 5 | 4.3 plus fixes | 12 + 19 | ~15 | AED 1,234,567.89, dates like 26-Oct-2026, a Help panel on every tab, empty states, and your list fixed |
| | **Total** | **105** | **~87** | Keep about 8–12 for Stage 5.2 (`5.2_engine_connect.md`) and a small buffer |

### Multi-firm checks (log in as each test user)
- **senior@test.local:** sees only own engagements; **no** Approve, Override or Reject buttons anywhere.
- **manager@test.local:** can propose an Override on Partner Review; no Approve or Reject.
- **taxpartner@test.local:** Approve and Reject only on VAT, INPUT_VAT, CT, TRN and LEGAL_REF rows.
- **partner@test.local:** Approve and Reject only on methodology rows (SAMPLING, JE, BENFORD, VALIDATION).
- **admin@test.local (Firm Admin):** users and roles, plus firm settings; **no** approve buttons.
- **platform.admin@test.local:** Firms and Client assignment on Admin; no approve buttons.
- **manager.b@test.local (Firm B):** sees **nothing** of Firm A (no clients, engagements, rule decisions or audit log). The badge shows Firm B.
- Every Approve, Override or Reject, and the firm settings toggle, refuses to submit without a comment of at least 10 characters.

### If credits run low
- **Below about 25 credits:** batch fixes only.
- **Code bugs:** fix them in Antigravity (they sync through GitHub at no Lovable cost).
- **A broken page:** restore it from Lovable's history rather than asking again.
- **Stage 5.2 not done:** keep the mock data for the demo.
