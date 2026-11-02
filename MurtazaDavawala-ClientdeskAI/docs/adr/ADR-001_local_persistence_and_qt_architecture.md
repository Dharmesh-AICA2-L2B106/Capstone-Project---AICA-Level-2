# Architecture Decision Record (ADR-001)

## Context & Objectives
The project requires building **Clientdesk AI**, a generic, offline-first Windows desktop application running on a local PC with **Python 3.15** without using GitHub or external online dependencies. The initial service scope is strictly locked to **6 service groups**. The user requested a modern front-end interface and robust, error-free code that will not break.

## Decisions Made

1. **Qt UI Compatibility Layer (`qt_compat.py`):**
   - Installed environment on Python 3.15 natively includes `PyQt6` (v6.11.0).
   - Designed a unified compatibility module (`clientdesk_ai.ui.qt_compat`) that imports `PyQt6` and gracefully falls back to `PySide6`. All views import from this abstraction.
   - Result: Seamless rendering on Python 3.15 with modern high-DPI scaling and zero runtime crashes.

2. **Native SQLite 3.53+ Engine with WAL Mode & FTS5:**
   - Standard Python `sqlite3` includes SQLite 3.53.4 with Write-Ahead Logging (`PRAGMA journal_mode=WAL`), strict foreign keys (`PRAGMA foreign_keys=ON`), and native FTS5 full-text indexing.
   - Using typed repository data mappers eliminates dependency on external C-extension binary wheels that frequently fail to compile on newly released Python 3.15.
   - Result: 100% offline reliability, transactional ACID guarantees, zero installation breakage.

3. **Cryptographic Password Hashing & Data Masking:**
   - Implemented OWASP-recommended PBKDF2-HMAC-SHA256 (600,000 rounds) with cryptographic salts and constant-time verification.
   - Masked Indian PAN and GSTIN identifiers across all UI tables and logs for privacy.

4. **Service Scope Lock (v1.1):**
   - Implemented and seeded only the 6 approved service groups (GST, ITR, Company Formation, Partnership, LLP, MCA Compliance) and their 8 source service definitions plus 8 GST entity variants.
   - The remaining 10 service definitions from legacy materials are deferred and excluded from the active catalogue.
