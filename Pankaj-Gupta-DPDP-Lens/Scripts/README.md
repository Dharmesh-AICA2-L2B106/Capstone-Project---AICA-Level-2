# DPDP Lens

**Find it. Decide it. Prove it.** An offline Windows tool that discovers personal data across a person's storage, lets a human decide Keep or Delete, and traces every copy when consent is withdrawn, supporting practical readiness for India's Digital Personal Data Protection Act, 2023.

> Personal learning project built for the AICA Level 2 capstone. It is a discovery and evidence aid, **not legal advice**, and is not an official product of any employer. All sample data in this repository is synthetic.

## Why
Personal data is scattered across laptops, USB backups and cloud-synced folders, hides inside scans and photos, and organisations cannot show that every copy was found when a person withdraws consent. The DPDP Rules were notified in November 2025 with phased commencement and core duties applying after about 18 months (mid-May 2027; verify dates in the Gazette).

## What it does
| Step | Tab | What happens |
|---|---|---|
| 1 Map | Storage Map | Add local, removable, network and cloud-synced folders; each is classified automatically and findings roll up by folder |
| 2 Discover | Storage Map / Dashboard | Finds Aadhaar (Verhoeff checksum), PAN, payment cards (Luhn), IFSC, UPI, and optionally mobile and e-mail, in text, Word, Excel, PowerPoint, PDF and, with offline OCR, photos and scanned PDFs |
| 3 Decide | Review & Decide | Masked preview, KEEP with a lawful reason or DELETE to a reversible quarantine; dry-run by default; files re-verified by SHA-256 before any move; permanent erase needs a typed DELETE |
| 4 Evidence | Consent Revocation | Search all mapped locations by name, e-mail, mobile, PAN or Aadhaar, act on every copy, export a case report |

Also: audit log (CSV), identical-copy detection, a read-only local web dashboard (127.0.0.1, token protected, installable as a PWA) and an offline Ed25519-signed trial licence.

## Privacy by design
Offline only. Only paths, owners, sizes and counts are stored. Matched values are never saved, and consent-case identifiers are kept only as salted one-way fingerprints.

## Licence code for evaluators
The app asks for a licence code when it starts. Use this evaluation code (90 days, one trial per computer, so every evaluator can use it on their own PC). It is also in `EVALUATION_LICENCE.txt` inside the app download.

```
<PASTE EVALUATOR CODE HERE>
```
Activate it before **<ACTIVATE-BY DATE>**. The video, source code and demo data also let you review the project without running the app.

## Quick start
**Windows EXE (no Python needed):** download the app zip (it contains the app, the demo data, a short guide and the evaluation code) from `<ADD DRIVE LINK HERE>`, follow `docs/USER_GUIDE.txt`. Use the evaluation code above.

**From source (Python 3.12, 64-bit):**
```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python dpdp_lens.py
```
Use the evaluation code above.

**Try it with the supplied data:** the `demo_data` folder holds 15 synthetic files. Scanning the three sub-folders with OCR and mobile/e-mail enabled should show 15 files scanned, 13 with personal data (High 6, Medium 4, Low 3) and 5 files found in a consent search for the demo person (see `docs/USER_GUIDE.txt`).

## Testing
- Blind test on an independent 21-file dataset (new seed, mixed formats, look-alike traps): Aadhaar, PAN, card, IFSC, UPI and mobile all 100% precision and recall after tuning. Real-world data is untested.
- Walkthrough video: `<ADD VIDEO LINK HERE>`

## Known limits
PAN, IFSC, UPI and OCR findings need manual review; Aadhaar and cards rely on checksums, and about 1 in 10 random 12-digit numbers passes the Aadhaar checksum. Excel stores 16-digit numbers in scientific form, so numeric card cells cannot be read. `.doc`, `.xls`, archives and password-protected PDFs are not scanned. The EXE is not code-signed, so Windows SmartScreen may warn.

## Repository layout
```
dpdp_lens.py, ocr_worker.py   application and OCR helper
demo_data/                    synthetic test files
docs/                         deck and user guide
```

## Author
CA. Pankaj Gupta. Shared for capstone evaluation; all rights reserved unless a licence file is added.
