# Clientdesk AI — User & Operator Guide (v1.1)

Welcome to **Clientdesk AI**, the 100% offline-first, generic desktop application engineered for Chartered Accountants, Tax Practitioners, Company Secretaries, and professional accounting firms to track client engagements, enforce document compliance checklists, and execute tamper-proof review workflows.

---

## 🚀 Quick Launch

You can launch Clientdesk AI on your Windows PC using either of the following:

1. **One-Click Batch Launcher:**
   Double-click `scripts\run_app.bat` in the project root.

2. **PowerShell / Terminal Command:**
   ```powershell
   .\.venv\Scripts\python.exe run_app.py
   ```

3. **Standalone Portable Executable (Build):**
   Run `scripts\build_windows_exe.bat` to package the full app into `dist\Clientdesk_AI\Clientdesk_AI.exe`.

---

## 📋 Standard Workflow

Clientdesk AI provides a continuous, audited workflow from engagement creation through to senior sign-off.

```
[1. Client Master]  ───>  [2. New Engagement]  ───>  [3. Dispatch Checklist]
      Create Client           Pick Service & FY           WhatsApp / Email format
                                                                │
                                                                ▼
[6. Review & Approval] <── [5. Readiness Gate]  <─── [4. Document Collection]
  Independent Sign-Off        100% Mandatory Check        Attach Files (SHA-256)
  Segregation of Duties       Exclude Not Applicable      Verify & Mark Accepted
```

### Step 1: Create or Select a Client
- Navigate to the **Client Master** tab (`Ctrl+2` or click sidebar).
- Click **+ Register New Client**.
- Enter Client Code (e.g. `CLT-0001`), Entity Type (`Sole Proprietorship`, `Private Limited`, `LLP`, etc.), Legal Name, Trade Name, PAN, and GSTIN.
- *Security Note:* PAN and GSTIN identifiers are automatically masked in views (e.g., `AB*******F` and `27*********1Z5`) to ensure client confidentiality.

### Step 2: Create an Engagement
- Navigate to **Workspaces & Checklists** and click **+ New Engagement**.
- Select the client, financial year, priority, target filing due date, staff assignee, and senior reviewer.
- **Smart Service Recommendation Assistant:** If unsure which statutory service to select, type the client inquiry into the natural language box (e.g., *"Client wants to register new private limited company with MCA"*). The offline classifier recommends the exact service code with a confidence score.
- **Master Checklist Snapshot:** Upon creation, the master service checklist items are copied into an immutable snapshot for that engagement. Even if master checklists are modified later, existing engagements retain their snapshot.

### Step 3: Dispatch Requirements Checklist to Client
- From the **Dashboard** or **Workspaces & Checklists**, click **📤 Send Requirements** on any active engagement.
- The **Send Requirements Checklist to Client** dialog will open:
  - Displays the client's contact phone and email.
  - Generates ready-to-send statutory checklists with clear instructions.
  - **WhatsApp Ready:** Click **Copy WhatsApp Format** and paste directly into WhatsApp Web or Desktop.
  - **Email Ready:** Click **Copy Email Format** with formal subject line, itemized tables, and accepted formats (`.pdf`, `.xlsx`, `.jpg`).
  - **Mark as Requested & Record Follow-up:** Automatically advances checklist items from `NOT_REQUESTED` to `REQUESTED` and logs an audited follow-up entry in the activity timeline.

### Step 4: Document Collection & Verification
- When the client delivers documents (scanned PDFs, spreadsheets, or images):
  - In **Workspaces & Checklists**, select the checklist row.
  - Click **Attach File**: The system computes the file's SHA-256 cryptographic hash, stores it in the local filestore (`data/filestore/`), and records an attachment entry.
  - *Duplicate Protection:* If an identical file is uploaded again to the same requirement, the database blocks duplicate storage.
  - Click **Verify & Accept** once the document is reviewed and deemed valid.
  - If a document is defective (e.g., blurry stamp, unsigned), click **Report Deficiency** and provide notes. The item is marked `DEFICIENT`, preventing submission until resolved.
  - If a requirement is not relevant (e.g., an export turnover declaration for a domestic-only trader), select `NOT_APPLICABLE`. The statutory readiness engine excludes it from the mandatory denominator.

### Step 5: Statutory Readiness Gate
- The system continuously calculates two metrics:
  - **Collection Progress:** Percentage of total documents physically received.
  - **Statutory Readiness:** Percentage of applicable mandatory documents verified as `ACCEPTED` or authorized as `WAIVED_WITH_APPROVAL`.
- **Database Trigger Enforcement:** The database trigger `trg_enforce_readiness_on_status_change` blocks the engagement from moving to `SUBMITTED_FOR_REVIEW` or `APPROVED` unless Statutory Readiness is exactly 100% and zero deficiencies exist.

### Step 6: Senior Review Queue & Segregation of Duties
- Once at 100% readiness, the staff member clicks **Submit for Senior Review →**.
- A partner or senior reviewer navigates to **Senior Review Queue**.
- **Segregation of Duties Enforcement:**
  - Database schema constraint `CHECK (assigned_to <> reviewer_id)` and Trigger `trg_enforce_segregation_on_review` strictly prevent staff members from reviewing or approving their own engagements.
  - Approvals must be signed off by a user with role `SENIOR`, `PARTNER`, or `ADMIN`.
- The reviewer enters review notes and clicks **Approve Engagement** or **Return for Correction**.

---

## 🔒 Security & Offline Guarantees

1. **Zero Cloud Dependencies:**
   All application logic, SQLite database, FTS5 index, and attachment files reside entirely inside `d:\AICA\AICA L2\capstone project\`. No data leaves your machine.

2. **OWASP Cryptographic Standards:**
   User passwords are encrypted with PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte cryptographically secure random salt, and verified using constant-time comparison. Iteration downgrades are blocked.

3. **Service Scope Lock (v1.1):**
   Database constraints restrict initial release services to exactly 6 service groups and 8 approved services:
   - GST (Registration with 8 entity variants + Annual Return)
   - ITR (Salaried Individuals + Business / Profession)
   - Company Formation (Pvt Ltd / OPC)
   - Partnership Registration
   - LLP Incorporation
   - MCA Annual Compliance (ROC)

---

## 📊 Reports & Offline Knowledge Search

- **Excel Reports:** Generate professionally formatted compliance workbooks (`.xlsx`) via OpenPyXL with color-coded status badges, readiness gauges, and client breakdown sheets.
- **SOP Search:** Full-text instant search across firm SOPs, compliance checklists, and statutory circulars using SQLite FTS5 with automatic trigger synchronization.

---
*Clientdesk AI v1.1 — Secure Local Practice Management*
