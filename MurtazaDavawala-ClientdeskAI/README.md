# Clientdesk AI — Desktop Application
**AICA Level 2 Capstone Project**  
*Developed by Murtaza Davawala*  
*Firm Branding: XYZ and Co (Professional Workflow v1.1)*

Clientdesk AI is a modern, offline-first Windows desktop application for managing clients, professional service engagements, statutory document checklists, compliance verification, and senior quality reviews for Chartered Accountancy and corporate compliance practices.

---

## Key Features

- **Modern Desktop UI & High DPI Scaling:** Responsive dark sidebar navigation, PassThrough High DPI scaling, minimum resolution preservation (1280x800), and crisp layout across all display scalings.
- **Multi-Row Selection & Batch Processing:** Shift+Click, Ctrl+Click, or drag-select multiple checklist rows to batch mark received, batch verify/accept, or apply statutory waivers and deficiency remarks across documents with a single confirmation.
- **Initial Service Scope (v1.1):** Exactly six user-facing professional service categories:
  1. **GST** (GST Registration across 8 entity variants, GST Annual Return GSTR-9 & 9C)
  2. **ITR** (Individual Salaried & Business/Professional)
  3. **Company Formation** (Company Incorporation Pvt Ltd / OPC)
  4. **Partnership Registration** (Partnership Firm Registration)
  5. **LLP Incorporation** (LLP Incorporation)
  6. **MCA Annual Compliance** (ROC / MCA Annual Compliance)
- **Immutable Checklist Snapshots:** Engagements capture an immutable snapshot of template items at creation time to maintain statutory audit trails.
- **Readiness vs. Collection Metrics:** Clearly distinguishes between documents received and documents verified/accepted against mandatory statutory gates.
- **Segregation of Duties (4-Eyes Principle):** Operators/Staff cannot approve their own engagements; independent Senior Review / Partner sign-off is strictly enforced.
- **Document Management:** Managed local storage, path-traversal protection, permitted file types, and SHA-256 duplicate content detection.
- **Offline SOP Knowledge Search:** Fast, local full-text search powered by SQLite FTS5 for statutory guidelines and standard operating procedures.
- **Reporting & Excel Exports:** One-click formatted Excel (.xlsx) export for client checklists and engagement portfolios.
- **100% Offline & Private:** Zero external cloud calls, zero telemetry, local AES/PBKDF2 security, and Aadhaar/PAN data masking.

---

## How to Run on Your PC

You can launch the application in two ways:

1. **One-Click Batch Launcher:**
   Double-click `scripts\run_app.bat`

2. **PowerShell / Terminal Command:**
   ```powershell
   .\.venv\Scripts\python.exe run_app.py
   ```

### Running Automated Verification Tests

```powershell
# Run the complete test suite (persistence, workflows, security, and UI)
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"

# Run the production architectural verification suite (12/12 PASS)
.\.venv\Scripts\python.exe verify_clientdesk_ai.py

# Build and run the standalone verification test bundle (16/16 PASS)
.\.venv\Scripts\python.exe make_zip.py
.\.venv\Scripts\python.exe clientdesk_ai_verification\clientdesk_verification.py
```

### Standalone Executable Build (Windows .exe)

To bundle the application into a standalone Windows binary without Python dependencies:
```cmd
scripts\build_windows_exe.bat
```
The output executable will be created at `dist\Clientdesk_AI\Clientdesk_AI.exe`.

---

## User & Operator Guide

For the complete guide on dispatching WhatsApp/Email requirement checklists, document collection, verification, readiness gates, and senior sign-off, see:
- [User Guide](docs/user_guide/README.md)

---

## Default Administrator & Staff Credentials

On first launch, the local database automatically initializes with the master administrative account:
- **Default Admin Username:** `admin`
- **Default Admin Password:** `admin`

### Staff & Operator Management
- The Administrator has sole authority to create staff operator accounts and assign their secure passwords.
- Staff members cannot modify passwords or access firm configuration panels.
- Work assignments follow the statutory **4-Eyes Principle**: operators cannot approve their own filings, ensuring segregation of duties before senior sign-off.

### 14-Day Evaluation Trial
- Clientdesk AI includes a tamper-resistant 14-day evaluation trial counter starting on first activation.
- Trial days remaining are displayed continuously in the top status bar.
- Upon trial expiration, administrative access locks to ensure authorized licensing.

---

## Project Structure

```text
capstone project/
├── .venv/                         # Local Python 3.15 virtual environment
├── src/
│   └── clientdesk_ai/
│       ├── config/settings.py     # Local filesystem and app configuration
│       ├── domain/models.py       # Domain entities, dataclasses, and status enums
│       ├── security/crypto.py     # PBKDF2 password hashing & identifier masking
│       ├── persistence/           # SQLite database schema, seed data, and typed repositories
│       ├── application/services.py# Core business logic, readiness rules & workflows
│       ├── reporting/             # Excel workbook generator (openpyxl)
│       └── ui/                    # Modern desktop UI (PyQt6 / PySide6)
│           ├── theme.py           # Modern QSS stylesheet & status badges
│           ├── qt_compat.py       # Unified Qt compatibility wrapper
│           ├── main_window.py     # Main window with sidebar navigation
│           └── views/             # 8 coordinated views (Dashboard, Clients, Workspace, Review, etc.)
├── data/
│   ├── database/                  # Local SQLite database (clientdesk.db)
│   ├── filestore/                 # Managed document attachments
│   └── backups/                   # Full offline zip backups
├── tests/                         # Complete automated test suite
├── docs/                          # Architecture records (ADR) and Traceability Matrix
└── run_app.py                     # Application entry point
```
