# Stage 4 status (Lovable front end)

**Started 1 Nov 2026.** The prompt pack is ready, and Stage 4 is now **waiting on Savio to paste prompt 4.1 into a new Lovable project.**

**Done (no Lovable credits used):**
- Re-exported the engine contract (auditsmart-engine 0.2.0, 67 operations, including `/v1/firm/...` and `/v1/firms...`) to `docs/lovable/engine_openapi.json`.
- Rewrote the prompt pack in `docs/lovable/` for the multi-firm model (D42 to D45):
  - Partner Review page, firm badge and the Dashboard pending-rules card (4.1).
  - Firms, `firm_id` and firm-scoped RLS through `app_metadata.firm_id`, plus 7 test users including a Firm B manager (4.2).
  - Corrected approvers: Tax Partner for tax domains, Partner for methodology, Admin never (4.2, 4.5).
- Lean 4.4 and 4.5. 4.3 is combined with the B3 batch-fix list.
- Removed the old 30 Oct `4.1_master_prompt_with_engine_contract.md`.

**Deferred by the scope decision:**
- 4.6 and 4.7.
- 4.4: the Excel calendar upload and copy-to-next-year.
- 4.5: Update Alerts with AI summaries, Watched sources and "Check FTA now".

**Waiting on the user:** the Lovable project, the Supabase project `auditsmart-dev`, the new GitHub repository for the web app, a test password, and logging credits after each prompt.

Engine code is unchanged in this step. See docs/lovable/README.md for the order and checks.
