# PDF Play Station 2.0

*by CA Aditya Mundada* — **100% Offline | Stay safe from DPDP Implications**

One Windows desktop tool for:

- **PDF & Document Utilities**: Merge, Split, Extract, Page Numbering, Rearrange, Rotate (all / selected / odd / even / sideways), PDF ↔ Images, Password Protect / Remove, Markdown ↔ PDF.
- **Convert to Excel / Word**: tables and text to editable Office files, plus balance-checked **Bank Statement to Excel**.
- **Secure Redaction**: Manual, Find, Smart detection of 13 types of personal data (PAN, Aadhaar, GSTIN, TAN, CIN, DIN, bank account, IFSC, passport, voter ID, mobile, e-mail, date of birth), Review, Apply and Verify, including scanned PDFs via OCR.

All processing happens on your computer. No document is ever uploaded.

> Internal testing build — please do not share outside the firm.

---

## Setting up on a new computer (one time)

### 1. Install Python
1. Download **Python 3.13 or 3.14 (64-bit)** from <https://www.python.org/downloads/windows/>.
2. While installing, tick **"Add python.exe to PATH"** and keep the **py launcher** option ticked.

### 2. Install Tesseract OCR (for scanned PDFs)
1. Download the Windows installer from <https://github.com/UB-Mannheim/tesseract/wiki>.
2. While installing, open **Additional language data** and tick **Hindi** and **Marathi**. English and the orientation data are included by default.
3. Keep the default folder `C:\Program Files\Tesseract-OCR`.

The tool still opens without Tesseract, but scanned pages cannot be read until it is installed.

### 3. Get the program
1. On the GitHub page, click **Code ▸ Download ZIP**.
2. Unzip it to a normal folder, for example `D:\PDF Play Station 2.0`. Avoid OneDrive or other synced folders if you can.

### 4. First start
1. Double-click **`run.bat`**.
2. The first time, it creates a private Python environment and installs the components. This needs internet and takes about 3–5 minutes.
3. Later starts are immediate and fully offline.

If Windows SmartScreen warns about `run.bat`, click **More info ▸ Run anyway**. The file is a plain text launcher; you can open it in Notepad to check.

---

## Using it
1. Pick a tool on the left.
2. Add files by dragging them onto the list or using **Add files**.
3. Choose the options and click the button at the bottom right.

The originals are never changed. Results are saved as new files, for example `name_rotated.pdf`, and an existing file is never overwritten.

## Reporting a problem
Please send:
- the tool you used and what happened (a screenshot helps);
- a sample or anonymised file, if possible;
- the last lines of `logs\pdf_play_station.log`. The log never contains document text or passwords.

## Checking that it works
`.venv\Scripts\python.exe PDF_Play_Station.py --selftest` runs every tool on dummy files for 1–2 minutes and writes `selftest_report.txt`. The result should be "19 of 19 passed". The EXE version has the same check: `Run self-test.bat` next to the EXE.

## Windows program (EXE)
A single-file `PDF Play Station 2.0.exe` with everything built in, including Tesseract, is made in the separate build workspace `E:\PDF Play Station 2.0 - EXE Build` with `Packaging\build.bat`. The EXE writes its log to `%LOCALAPPDATA%\PDF Play Station 2.0\logs`.

## For developers
- Run the tests (optional): `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`, then `.venv\Scripts\python.exe -m pytest tests`.
- How the tool was built: see `PDF Play Station 2.0 - Development Documentation.docx` (rebuilt by `docs\build_dev_document.py`).
