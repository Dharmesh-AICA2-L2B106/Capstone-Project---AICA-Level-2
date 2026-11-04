# Deploy the AuditSmart engine to Render (development, dummy data only)

Stage 5, step 1. This guide puts the calculation engine on the internet so the Lovable app can
call it. It is written for a non-developer: follow the steps in order and copy the commands
exactly. Decisions: plans/DECISIONS.md D46-D49.

> **DUMMY DATA ONLY.** This is a free development set-up. Files can disappear at any time, the
> database is deleted after 30 days, and nothing here has been reviewed for real client data.
> Never upload a real client's ledger, trial balance or TRN list.

> **Keys and secrets never go into files, GitHub or chat.** You type them only into the Render
> dashboard (step 4). If a key is ever pasted somewhere else, treat it as leaked and replace it.

---

## 1. What you will end up with

| Thing | Name on Render | Cost | Notes |
|---|---|---|---|
| Web service (the engine, from `engine/Dockerfile`) | `auditsmart-engine` | Free | Frankfurt; sleeps after 15 min without visits; about 1 minute to wake |
| PostgreSQL database | `auditsmart-db` | Free | Frankfurt; 1 GB; **expires 30 days after creation** |
| Weekly FTA monitor (cron job) | *(not created)* | Paid only | Left switched off in `render.yaml` (section 9) |

Everything is described in one file, `render.yaml`, at the top of the repository. Render calls
this a **Blueprint**.

When the engine starts it automatically (a) updates the database tables (`alembic upgrade
head`) and (b) loads the shared default rules and the watched FTA sources. Starting again is
safe: nothing is loaded twice.

---

## 2. Put the new files on GitHub (PowerShell, on your PC)

You received `auditsmart_stage5_step1.zip`. It holds every file added or changed since commit
`c062f7b` (the last one on GitHub), at the same folder positions as in the repository, plus a
`patches` folder and `COPY_LIST.txt` (the list of files, each marked `added` or `modified`).
You do not copy `patches` or `COPY_LIST.txt` into the project.

1. Save the zip to your **Downloads** folder.
2. Open **PowerShell** (Start menu, type `PowerShell`, press Enter).
3. Paste these lines one at a time and press Enter after each:

```powershell
cd C:\Projects\auditsmart
git status
```

   `git status` should say `nothing to commit, working tree clean` (or list only files you know
   about). If it lists changes you did not make, stop and ask before continuing.

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\auditsmart_stage5_step1.zip" -DestinationPath "$env:USERPROFILE\Downloads\auditsmart_stage5_step1" -Force
robocopy "$env:USERPROFILE\Downloads\auditsmart_stage5_step1" "C:\Projects\auditsmart" /E /XD patches /XF COPY_LIST.txt
```

   robocopy prints a summary table. That is normal (its "exit code" 1 means "files copied").

```powershell
git status
```

   You should see the files from `COPY_LIST.txt` (for example `render.yaml`,
   `docs/DEPLOY_DEV.md`, `engine/scripts/start.sh`). Nothing else should appear - in particular
   no `.env` file and no file with real client data.

```powershell
git add render.yaml .gitattributes docs plans engine
git commit -m "Stage 4 prompt pack + Stage 5 step 1: Render dev deployment, approval and firm-claim fixes"
git push
```

4. Open https://github.com/Savio2358/AuditSmart in your browser. `render.yaml` should now be
   in the file list at the top level.

---

## 3. Create the Render account

1. Go to https://dashboard.render.com and choose **Sign up** (or **Sign in**).
2. Choose **GitHub** and approve the request. Render can now see your repositories.
3. Render may ask for a workspace name: `AuditSmart` is fine. No card is needed for free plans.

---

## 4. Create the Blueprint

1. In the Render dashboard click **New** (top right) and choose **Blueprint**.
2. Under *Connect a repository*, pick **Savio2358/AuditSmart**.
   - Not in the list? Click **Configure GitHub** (or *Configure account*), allow Render access to
     the `AuditSmart` repository, then come back.
3. **Blueprint Name**: `auditsmart-dev`. **Branch**: the branch you pushed to (normally `main`).
4. Render reads `render.yaml` and shows two items: `auditsmart-engine` (web service) and
   `auditsmart-db` (database). Both should say **Free**.
5. Render now asks for the values marked *sync: false*. Fill them from the table in section 5.
   Leave a box empty where the table says "leave empty".
6. Click **Deploy Blueprint** (the button may say **Apply**).
7. The first build takes about 5-10 minutes. Click `auditsmart-engine` and open **Logs** to
   watch. Success looks like:
   ```
   start.sh: alembic upgrade head
   ... Application startup complete.
   ... Uvicorn running on http://0.0.0.0:10000
   ```

---

## 5. The settings (environment variables)

You type only the rows marked **you type it**. The others are already in `render.yaml`.

| Setting | Value | Where it comes from |
|---|---|---|
| `ENVIRONMENT` | `development` | Already set. Makes the engine load the default rules at start-up |
| `DATABASE_URL` | *(automatic)* | Already set. Render links it to `auditsmart-db` |
| `AUTH_PROVIDER` | `supabase` | Already set. Lovable Cloud sign-in is Supabase Auth |
| `AUTH_ISSUER` | **you type it**: `https://<project-ref>.supabase.co/auth/v1` | Your Lovable Cloud project URL **plus `/auth/v1`**, no slash at the end. See 5.1 |
| `AUTH_AUDIENCE` | `authenticated` | Already set. Supabase puts this in every signed-in user's token |
| `AUTH_JWKS_URL` | **leave empty** | Optional. Empty means `<AUTH_ISSUER>/.well-known/jwks.json`. See 5.2 |
| `AUTH_HS256_SECRET` | **leave empty** unless 5.2 says otherwise | Optional. Only for projects still on the *legacy* JWT secret. See 5.2 |
| `ALLOWED_ORIGINS` | **you type it**: the Lovable preview URL and published URL, comma-separated, no spaces | See 5.3 |
| `AI_PROVIDER` | **leave empty** (or `stub`) | Empty or `stub` = no outside AI service is called. `gemini` only after you decide to use Gemini |
| `AI_MODEL` | **leave empty** | Only used with `gemini` (default `gemini-1.5-pro`) |
| `GEMINI_API_KEY` | **leave empty** | Only with `AI_PROVIDER=gemini`. Typed only here, never in chat or files |
| `RULES_ALLOW_PENDING` | `true` | Already set. Development: unverified seed rules may be used and are flagged |
| `AUTH_FIRM_CLAIM` | `firm_id` | Already set. The firm is read from `app_metadata.firm_id` in the sign-in token |

The AI only writes wording. It never calculates. Every number comes from the engine.

You can change any value later: **auditsmart-engine > Environment > Edit**, then **Save,
rebuild, and deploy**.

### 5.1 Finding the Lovable Cloud project URL (for `AUTH_ISSUER`)

Lovable Cloud runs on Supabase. The project URL looks like `https://abcdefghijklmnop.supabase.co`.
Ways to find it (no credits needed):

- In GitHub, open the Lovable app's repository and the `.env` file at the top. The line
  `VITE_SUPABASE_URL="https://....supabase.co"` is the project URL. (The
  `VITE_SUPABASE_PUBLISHABLE_KEY` next to it is a public key. You do not need it here.)
- Or open the Lovable preview in Chrome, press **F12**, open **Network**, sign in, and look for
  a request to `....supabase.co/auth/v1/token`. The part up to `.supabase.co` is the URL.

Then add `/auth/v1`. Example: `https://abcdefghijklmnop.supabase.co/auth/v1`.

### 5.2 JWKS (signing keys) or the legacy HS256 secret?

Supabase signs each sign-in token in one of two ways:

- **Signing keys (JWKS)** - newer projects. Tokens say `"alg": "ES256"` (or `RS256`). The
  engine downloads the public keys itself from
  `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`. **No secret is needed.**
  Leave `AUTH_JWKS_URL` and `AUTH_HS256_SECRET` empty.
- **Legacy JWT secret** - older projects. Tokens say `"alg": "HS256"`. The engine then needs
  the project's *legacy JWT secret* in `AUTH_HS256_SECRET` (at least 32 characters).

How to tell which one your project uses:

1. Open `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json` in your browser.
   - It shows a key with `"alg":"ES256"` or `"alg":"RS256"` -> the project has signing keys.
   - It shows `{"keys":[]}` -> the project uses only the legacy secret.
2. To be certain which one signs your tokens today: open the Lovable preview, sign in, press
   **F12**, open **Console**, paste this line and press Enter. It shows only the token's header
   (which algorithm signed it). Nothing is sent anywhere:
   ```js
   JSON.parse(atob(JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.endsWith('-auth-token')))).access_token.split('.')[0]))
   ```
   `alg: "ES256"` or `"RS256"` = JWKS (leave the secret empty). `alg: "HS256"` = legacy secret.

If it is HS256: Lovable Cloud may not show you the legacy secret. Do not guess and do not paste
it into chat. Stop and decide with your adviser (section 10, decision 3).

### 5.3 `ALLOWED_ORIGINS` (which websites may call the engine)

Only these browser addresses can call the engine. Use the address bar, **without** any path and
**without** a trailing `/`:

- the Lovable **preview** URL, e.g. `https://id-preview--1234abcd.lovable.app`
- the **published** URL, e.g. `https://auditsmart.lovable.app` (and any custom domain)

Type them comma-separated with no spaces:
`https://id-preview--1234abcd.lovable.app,https://auditsmart.lovable.app`
(A trailing `/` is removed automatically, but other paths are not.)

---

## 6. Check that it works

1. In Render, open `auditsmart-engine`. Copy its address at the top, e.g.
   `https://auditsmart-engine.onrender.com` (Render may add a few letters to the name).
2. Open `<that address>/v1/health` in your browser. You should see:
   ```json
   {"status":"ok","service":"auditsmart-engine","version":"0.2.2","environment":"development","db":"ok","queue":"in-process"}
   ```
   - The first visit after a quiet period takes about a minute (the free service is waking).
   - `"db":"ok"` means the database is connected.
3. `<that address>/docs` shows the list of engine endpoints.
4. `<that address>/v1/rules` should answer `401` ("Sign in required"). That is correct: the
   engine needs a signed-in Lovable user. Connecting Lovable is the next step (Stage 5 step 2).

---

## 7. Free-plan cautions

- **It sleeps.** After 15 minutes with no visits the engine stops. The next visit wakes it in
  about a minute. Render shows a loading page meanwhile.
- **Uploaded files are temporary.** Uploads, parsed datasets and generated workpapers are
  stored on the service's own disk, which is wiped on every restart, redeploy or sleep. The
  database rows stay, but their files may be gone: upload the dummy file again if needed.
- **The free database expires 30 days after it was created.** Render emails you before. After
  that you have 14 days to upgrade it to a paid plan, then it is deleted with all its data. It
  holds at most 1 GB and has no backups. Only one free database is allowed per workspace.
- **512 MB memory.** The engine uses about 160 MB when idle. Very large dummy files may make it
  restart. Keep test files small (a few thousand rows).
- **750 free hours a month** for all free services together (enough for one service).
- **Dummy data only.** See the top of this page.

---

## 8. Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| Build fails in **Logs** | The Docker image could not be built | Open the first red line in Logs. Check that `render.yaml` and `engine/scripts/start.sh` reached GitHub (step 2) |
| Log shows `alembic` error, service restarts | The database could not be updated | Check `auditsmart-db` is *Available*. Use **Manual Deploy > Deploy latest commit** to retry |
| `/v1/health` shows `"db":"error..."` | Engine cannot reach the database | `DATABASE_URL` must come from `auditsmart-db` (it does in `render.yaml`). Both must be in Frankfurt |
| **401** "Your sign-in token is not valid or has expired" | Token was checked and rejected: wrong issuer, wrong audience, or a key mismatch | `AUTH_ISSUER` must be exactly `https://<project-ref>.supabase.co/auth/v1` (no trailing `/`). `AUTH_AUDIENCE` = `authenticated`. Re-check section 5.2: an HS256 token needs `AUTH_HS256_SECRET`; an ES256/RS256 token needs the JWKS address to work. Sign out and in again (tokens expire after about an hour) |
| **401** "Sign in required" | No token was sent | The Lovable app is not sending `Authorization: Bearer <token>` yet (step 2 work) |
| **403** "Only a TaxPartner / Partner ..." or another role message | Signed in, but the token carries no suitable role, or no firm | The engine reads roles **only** from `app_metadata.roles` and the firm **only** from `app_metadata.firm_id`. Values the user typed into their own profile (`user_metadata`) are ignored on purpose. See section 10 |
| Browser console says **CORS** / "blocked by CORS policy" | The page's address is not in `ALLOWED_ORIGINS` | Add the exact address from the browser bar (no path, no `/` at the end) and redeploy. Note the preview and published addresses are different |
| Health page slow, then fine | The free service was asleep | Normal (section 7) |
| Everything stopped after ~30 days | The free database expired | Upgrade it, or delete it and recreate the Blueprint for a new 30 days (all data is lost) |

---

## 9. Later: paid plans and the weekly FTA monitor (not now)

- To stop the sleeping: change `plan: free` to a paid plan (for example `0.5c-512mb`) in
  `render.yaml` for the web service, or in **Settings > Instance Type**.
- The weekly FTA monitor is written in `render.yaml` but commented out (lines starting with
  `#`). Render cron jobs have no free plan (smallest is `0.5c-512mb`). A cron job also runs in
  its own container, so it would not see files kept by the free web service. Until then,
  a TaxPartner or Admin runs the check by hand: `POST /v1/rules-monitor/check` (the Rules
  monitor screen in the Lovable app, once it is connected). Running the check proposes rule
  changes only; approving them stays with the TaxPartner / Partner.
- A paid database (with backups) is needed before any non-dummy use.

---

## 10. Role and firm claims - the risk to settle in step 2

The engine trusts only what is in the **signed** token, in `app_metadata`:

```json
{ "sub": "...", "aud": "authenticated", "role": "authenticated",
  "app_metadata": { "roles": ["Partner"], "firm_id": "firm-cla-emirates" } }
```

- `app_metadata` can only be written by the server (Supabase admin side). A user cannot change
  it, so it is safe to base approvals on.
- `user_metadata` **can** be changed by the user from the browser, so the engine never reads it
  (D48). The top-level `role` claim is always `authenticated` in Supabase and is not an
  AuditSmart role.
- **Risk:** Lovable apps usually keep roles in a database table (e.g. `user_roles`), not in
  `app_metadata`. If so, every user reaches the engine with no role and gets **403** on
  role-gated actions such as approvals. Never "fix" this by having the browser send a role, or
  by reading `user_metadata` - that would let any user make themselves a TaxPartner.

Safe ways to put roles and the firm into `app_metadata` (decide before step 2):

1. **Custom Access Token Hook** (Supabase Auth hook): a small database function copies the
   user's roles and firm from the `user_roles` table into `app_metadata` each time a token is
   issued. Recommended - one source of truth.
2. **Set `app_metadata` from a server-side function** (Supabase admin API, service-role key kept
   on the server) whenever an admin changes a user's role.

Both need changes in the Lovable Cloud project. Ask before using Lovable credits.

Approval rules the engine enforces (D43, D47): **TaxPartner** approves tax rules (VAT, Input
VAT, CT, TRN, legal references); **Partner** approves methodology rules (sampling, JE tests,
Benford, data validation). **Admin never approves rules** - neither a firm Admin nor the
platform Admin. A user who should approve both kinds needs both roles.
