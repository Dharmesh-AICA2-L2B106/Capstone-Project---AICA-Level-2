# -*- coding: utf-8 -*-
"""
DPDP Lens - personal-data discovery, storage mapping and consent-revocation tracing (offline Windows tool)
==========================================================================================================
* Discover   - Aadhaar (Verhoeff), PAN, cards (Luhn), IFSC, UPI (+ optional mobile / e-mail) in text, Office,
               PDF and - with the built-in offline OCR - photos and scanned documents.
* Map        - one view of where personal data sits across local folders, other drives, network shares and
               cloud-synced folders, by folder, with risk and identical-copy counts.
* Decide     - review each file (masked preview), mark KEEP (with a lawful reason) or DELETE. DELETE moves the file
               to a recoverable quarantine; permanent erase is a separate typed-confirmation step.
* Trace      - when consent is withdrawn, search every mapped location for the person's identifiers and act on
               every copy; a case report is exported. Identifiers are never stored (one-way fingerprints only).
* Hybrid     - native PyQt5 worker + an offline-first PWA dashboard on 127.0.0.1 (installable from Chrome / Edge).
* Licensing  - offline Ed25519-signed codes, 7-day trial, one trial per computer.
ZERO-PII STORAGE: results hold only path, owner, size and counts.

Run:  open in IDLE -> F5.   Missing libraries are installed automatically on first run.
Manual fallback (one line):   python -m pip install PyQt5 cryptography pypdf rapidocr-onnxruntime
"""

import sys
import os
import subprocess
import importlib
import importlib.util

# ----------------------------------------------------------------------------------------------
# 0. AUTO-INSTALL OF LIBRARIES  (runs before any third-party import)
# ----------------------------------------------------------------------------------------------
REQUIRED = [("PyQt5", "PyQt5"), ("cryptography", "cryptography")]                       # (import name, pip name) - mandatory
OPTIONAL = [("pypdf", "pypdf")]  # nice-to-have (PDF scanning); OCR is installed separately below
MANUAL_CMD = "python -m pip install PyQt5 cryptography pypdf rapidocr-onnxruntime"


def _has(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def _pip_install(pkg):
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--quiet", pkg]
    flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW
    for extra in ([], ["--user"]):
        try:
            cmd = base[:6] + extra + base[6:]
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=flags, timeout=900)
            if r.returncode == 0:
                return True
        except Exception:
            pass
    try:                                                   # last resort: bootstrap pip itself
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags, timeout=300)
        r = subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=flags, timeout=900)
        return r.returncode == 0
    except Exception:
        return False


def ensure_libraries():
    if getattr(sys, "frozen", False):      # packaged .exe already bundles everything
        return
    import site
    missing_fatal = []
    for mod, pkg in REQUIRED + OPTIONAL:
        if _has(mod):
            continue
        print("[setup] Installing %s ... please wait" % pkg)
        ok = _pip_install(pkg)
        importlib.invalidate_caches()
        try:
            us = site.getusersitepackages()
            if us and us not in sys.path and os.path.isdir(us):
                sys.path.append(us)
        except Exception:
            pass
        if ok and _has(mod):
            print("[setup] %s ready" % pkg)
        elif (mod, pkg) in REQUIRED:
            missing_fatal.append(pkg)
        else:
            print("[setup] Optional library %s unavailable - feature will be disabled." % pkg)
    if not (_has("rapidocr_onnxruntime") or _has("rapidocr")):
        print("[setup] Installing OCR engine (large download, one time) ...")
        ok = _pip_install("rapidocr-onnxruntime") or (_pip_install("onnxruntime") and _pip_install("rapidocr"))
        importlib.invalidate_caches()
        print("[setup] OCR engine ready" if ok else "[setup] OCR engine unavailable - image/scanned-PDF scanning disabled.")
    if missing_fatal:
        msg = ("Could not install: %s\n\nPlease run this in Command Prompt, then re-run the tool:\n\n%s"
               % (", ".join(missing_fatal), MANUAL_CMD))
        print(msg)
        try:
            import tkinter
            from tkinter import messagebox
            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror("Missing libraries", msg)
            root.destroy()
        except Exception:
            pass
        raise SystemExit(1)


ensure_libraries()

# OCR engine must be imported BEFORE PyQt5: Qt ships an older C++ runtime DLL and onnxruntime crashes (access
# violation) if it is loaded after Qt. The packaged EXE does not import it at all - it calls ocr_worker.exe instead.
_RapidOCR = None
if not getattr(sys, "frozen", False):
    try:
        from rapidocr_onnxruntime import RapidOCR as _RapidOCR
    except Exception:
        try:
            from rapidocr import RapidOCR as _RapidOCR
        except Exception:
            _RapidOCR = None

# ----------------------------------------------------------------------------------------------
# Standard library + PyQt5 imports (safe now)
# ----------------------------------------------------------------------------------------------
import re
import io
import csv
import json
import time
import shutil
import hashlib
import secrets
import threading
import zipfile
import getpass
import hmac
import html
import base64
import struct
from datetime import datetime, date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRectF, QTimer, QUrl, QBuffer, QIODevice, QDate
from PyQt5.QtGui import (QColor, QPainter, QPen, QFont, QLinearGradient, QBrush, QImage,
                         QPainterPath, QDesktopServices, QGuiApplication)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTabWidget, QFileDialog, QListWidget, QCheckBox, QComboBox, QSpinBox, QProgressBar, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QMessageBox, QInputDialog, QLineEdit, QFrame,
    QHeaderView, QGroupBox, QPlainTextEdit, QAbstractItemView, QProgressDialog, QSizePolicy, QDialog, QDateEdit, QFormLayout)

try:
    import pypdf as _pypdf
except Exception:
    _pypdf = None
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

for _n in ("stdout", "stderr"):                      # windowed (no-console) EXE: stdout/stderr are None
    if getattr(sys, _n) is None:
        setattr(sys, _n, open(os.devnull, "w"))

APP_VERSION = "1.0.1"
# ---- LICENSING SETTINGS (edit TRIAL_URL to your website's trial page) ----
TRIAL_URL = os.environ.get("DPDP_TRIAL_URL", "https://your-website.example/#trial")
LICENSE_PUB_B64 = "m42JqoMXpScG4kj48q/stYuvXdlXiBjf/iXl6n4zhLY="   # public key only - safe to ship
LIC_EPOCH = date(2026, 1, 1)
DEFAULT_NAME = "DPDP Lens"
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
# Data location: %USERPROFILE%\.dpdp_lens by default. PORTABLE MODE: create an empty file named
# "portable.flag" next to the program (or set env EG_DATA_DIR) and all data goes to a "data" folder beside it.
if os.environ.get("EG_DATA_DIR"):
    DATA_DIR = os.path.abspath(os.environ["EG_DATA_DIR"])
elif os.path.exists(os.path.join(APP_DIR, "portable.flag")):
    DATA_DIR = os.path.join(APP_DIR, "data")
else:
    DATA_DIR = os.path.join(os.path.expanduser("~"), ".dpdp_lens")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
AUDIT_FILE = os.path.join(DATA_DIR, "audit_log.csv")
LICENSE_FILE = os.path.join(DATA_DIR, "license.json")
LICENSE_BACKUP = os.path.join(os.path.expanduser("~"), ".dpl_state")
DEFAULT_QDIR = os.path.join(DATA_DIR, "Quarantine")
os.makedirs(DATA_DIR, exist_ok=True)

THEMES = {
    "Indigo Pulse":  {"p": "#6C5CE7", "s": "#00CEC9", "a": "#FD79A8", "w": "#FDCB6E", "g": "#00B894", "bg": "#F3F4FB"},
    "Sunset Blaze":  {"p": "#E8590C", "s": "#AE3EC9", "a": "#F59F00", "w": "#FA5252", "g": "#12B886", "bg": "#FFF6F0"},
    "Ocean Breeze":  {"p": "#0984E3", "s": "#00B894", "a": "#6C5CE7", "w": "#FDCB6E", "g": "#00CEC9", "bg": "#EEF7FF"},
}

# ----------------------------------------------------------------------------------------------
# 1. SETTINGS, AUDIT LOG, SMALL HELPERS
# ----------------------------------------------------------------------------------------------
_cfg_lock = threading.Lock()
_audit_lock = threading.Lock()


def load_config():
    cfg = {"app_name": "", "theme": "Indigo Pulse", "token": secrets.token_urlsafe(12), "port": 8765,
           "pwa": True, "qdir": DEFAULT_QDIR, "salt": secrets.token_hex(16)}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    with _cfg_lock:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass


def clean_name(s):
    s = "".join(ch for ch in (s or "") if ch.isprintable()).strip()
    return s[:40]


def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%d %s" % (n, u)) if u == "B" else ("%.2f %s" % (n, u))
        n /= 1024.0


def csv_safe(v):
    """Neutralise spreadsheet formula injection in exported / logged text."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def audit(action, detail="", path="", count=0, size=0):
    with _audit_lock:
        new = not os.path.exists(AUDIT_FILE)
        try:
            with open(AUDIT_FILE, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["timestamp", "user", "action", "detail", "path", "count", "bytes"])
                w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), getpass.getuser(),
                            csv_safe(action), csv_safe(detail), csv_safe(path), count, size])
        except Exception:
            pass


def read_audit(limit=500):
    rows = []
    try:
        with open(AUDIT_FILE, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))[1:]
    except Exception:
        pass
    return rows[-limit:][::-1]


def file_owner(path):
    """File owner (metadata only). Falls back to 'Unknown' - never raises."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            adv = ctypes.windll.advapi32
            psid, psd = ctypes.c_void_p(), ctypes.c_void_p()
            if adv.GetNamedSecurityInfoW(path, 1, 1, ctypes.byref(psid), None, None, None,
                                         ctypes.byref(psd)) != 0:
                return "Unknown"
            name, dom = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
            n, d, use = wintypes.DWORD(256), wintypes.DWORD(256), wintypes.DWORD()
            ok = adv.LookupAccountSidW(None, psid, name, ctypes.byref(n), dom, ctypes.byref(d),
                                       ctypes.byref(use))
            ctypes.windll.kernel32.LocalFree(psd)
            return ("%s\\%s" % (dom.value, name.value)) if ok else "Unknown"
        import pwd
        return pwd.getpwuid(os.stat(path).st_uid).pw_name
    except Exception:
        return "Unknown"



# ----------------------------------------------------------------------------------------------
# 1b. LICENSING  (offline Ed25519-signed codes; 7-day trial; one trial per computer)
# ----------------------------------------------------------------------------------------------
REG_KEY = r"Software\DPDPLens"


def decode_license(code):
    """Verify signature and return payload dict. Raises ValueError for any invalid code."""
    c = re.sub(r"^\s*(DL|EG)-", "", (code or "").upper())          # brand prefix (EG kept for old codes)
    c = re.sub(r"[^A-Za-z2-7]", "", c)
    try:
        raw = base64.b32decode(c + "=" * (-len(c) % 8))
    except Exception:
        raise ValueError("Licence code format is not valid.")
    if len(raw) != 73:
        raise ValueError("Licence code is incomplete - copy the whole code.")
    payload, sig = raw[:9], raw[9:]
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(LICENSE_PUB_B64)).verify(sig, payload)
    except Exception:
        raise ValueError("Licence code is not genuine.")
    ltype, lid, days, by = struct.unpack(">BIHH", payload)
    return {"type": "trial" if ltype == 1 else "paid", "id": lid, "days": days,
            "activate_by": LIC_EPOCH + timedelta(days=by)}


class LicenseManager:
    """Keeps activation state in 3 places (file, hidden backup, Windows registry) so that deleting one
    does not restart a trial. Local checks deter casual misuse; they cannot stop a determined cracker."""

    def _read_all(self):
        recs = []
        for path in (LICENSE_FILE, LICENSE_BACKUP):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    recs.append(json.load(f))
            except Exception:
                pass
        if os.name == "nt":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
                    recs.append(json.loads(winreg.QueryValueEx(k, "state")[0]))
            except Exception:
                pass
        return [r for r in recs if isinstance(r, dict) and "code" in r and "activated" in r]

    def _write_all(self, rec):
        txt = json.dumps(rec)
        for path in (LICENSE_FILE, LICENSE_BACKUP):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(txt)
            except Exception:
                pass
        if os.name == "nt":
            try:
                import winreg
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
                    winreg.SetValueEx(k, "state", 0, winreg.REG_SZ, txt)
            except Exception:
                pass

    def _best(self):
        recs = self._read_all()
        if not recs:
            return None
        paid = [r for r in recs if r.get("type") == "paid"]
        pool = paid or recs
        rec = min(pool, key=lambda r: r["activated"])          # earliest activation wins (anti-reset)
        try:
            info = decode_license(rec["code"])                 # re-verify signature every time
        except ValueError:
            return None
        rec = dict(rec)
        rec["last_seen"] = max(r.get("last_seen", r["activated"]) for r in recs)   # latest date ever seen
        rec.update(type=info["type"], days=info["days"], id=info["id"])
        return rec

    def status(self):
        rec = self._best()
        today = date.today()
        if rec is None:
            return {"state": "none", "days_left": 0, "text": "No licence activated"}
        last = date.fromisoformat(rec.get("last_seen", rec["activated"]))
        if today < last - timedelta(days=1):
            return {"state": "tampered", "days_left": 0, "type": rec["type"],
                    "text": "System date was moved backwards. Set the correct date to continue."}
        if today > last:
            rec["last_seen"] = today.isoformat()
            self._write_all(rec)
        end = date.fromisoformat(rec["activated"]) + timedelta(days=rec["days"])
        left = (end - today).days
        kind = "Trial" if rec["type"] == "trial" else "Licensed"
        if left <= 0:
            return {"state": "expired", "days_left": 0, "type": rec["type"],
                    "text": "%s expired on %s" % (kind, end.strftime("%d-%b-%Y"))}
        return {"state": "trial" if rec["type"] == "trial" else "licensed", "days_left": left,
                "type": rec["type"], "text": "%s: %d day(s) left (until %s)" % (kind, left, end.strftime("%d-%b-%Y"))}

    def activate(self, code):
        info = decode_license(code)
        today = date.today()
        if today > info["activate_by"]:
            raise ValueError("This code can no longer be activated (it expired on %s). Request a new one." %
                             info["activate_by"].strftime("%d-%b-%Y"))
        existing = self._read_all()
        if info["type"] == "trial" and existing:
            raise ValueError("A trial or licence has already been used on this computer. "
                             "Please enter a paid licence code.")
        self._write_all({"code": code.strip(), "type": info["type"], "activated": today.isoformat(),
                         "last_seen": today.isoformat()})
        return self.status()


LICENSE = LicenseManager()

# ----------------------------------------------------------------------------------------------
# 2. SHARED CRAWLER  (used by the scan and the consent-revocation search)
# ----------------------------------------------------------------------------------------------
def _protected_prefixes():
    p = []
    if os.name == "nt":
        for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            v = os.environ.get(var)
            if v:
                p.append(os.path.normcase(os.path.abspath(v)))
    else:
        p += ["/proc", "/sys", "/dev", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot",
              "/System", "/Library", "/private", "/var/lib", "/run"]
    return tuple(p)


PROTECTED = _protected_prefixes()
SKIP_DIRS = {"$recycle.bin", "system volume information", "windows.old", "node_modules", ".git",
             "__pycache__", "appdata"}


def is_protected(path):
    ap = os.path.normcase(os.path.abspath(path))
    for p in PROTECTED:
        if ap == p or ap.startswith(p + os.sep):
            return True
    return False


def crawl(roots, cancel, skip_hidden=True, min_size=1, max_size=None, exts=None, skip_paths=()):
    """Yield (path, size, mtime) for regular, non-symlink files outside protected folders."""
    skip_paths = tuple(os.path.normcase(os.path.abspath(s)) for s in skip_paths if s)
    for root in roots:
        if is_protected(root):
            continue
        for dp, dn, fn in os.walk(root, followlinks=False):
            if cancel.is_set():
                return
            keep = []
            for d in dn:
                full = os.path.join(dp, d)
                if d.lower() in SKIP_DIRS or is_protected(full) or os.path.islink(full):
                    continue
                if skip_hidden and d.startswith("."):
                    continue
                if any(os.path.normcase(os.path.abspath(full)).startswith(s) for s in skip_paths):
                    continue
                keep.append(d)
            dn[:] = keep
            for f in fn:
                if skip_hidden and f.startswith("."):
                    continue
                full = os.path.join(dp, f)
                try:
                    if os.path.islink(full):
                        continue
                    st = os.stat(full)
                except OSError:
                    continue
                if not os.path.isfile(full) or st.st_size < min_size:
                    continue
                if max_size is not None and st.st_size > max_size:
                    continue
                if exts is not None and os.path.splitext(f)[1].lower() not in exts:
                    continue
                yield full, st.st_size, st.st_mtime


# ----------------------------------------------------------------------------------------------
# 3. STORAGE MAP, DECISION REGISTER, QUARANTINE  (no duplicate-finder: this tool is about personal data)
# ----------------------------------------------------------------------------------------------
HASH_MAX_BYTES = 500 * 1024 * 1024
CLOUD_HINTS = ("onedrive", "google drive", "googledrive", "dropbox", "box sync", "icloud", "my drive", "sharepoint")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.json")
CASES_FILE = os.path.join(DATA_DIR, "cases.json")
LAST_SCAN_FILE = os.path.join(DATA_DIR, "last_scan.json")
_dec_lock = threading.Lock()


def hash_file(path, cancel=None):
    """SHA-256 of a file (used only to recognise identical copies and to detect change before an action)."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                if cancel is not None and cancel.is_set():
                    return None
                b = f.read(1024 * 1024)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception:
        return None


def classify_location(path):
    """Storage type of a path: local disk, network share/drive, cloud-synced folder, removable drive."""
    ap = os.path.abspath(path)
    low = ap.lower().replace("\\", "/")
    if ap.startswith("\\\\") or low.startswith("//"):
        return "Network share"
    if any(h in low for h in CLOUD_HINTS):
        return "Cloud-synced folder"
    if os.name == "nt":
        try:
            import ctypes
            root = os.path.splitdrive(ap)[0] + "\\"
            dt = ctypes.windll.kernel32.GetDriveTypeW(root)
            return {2: "Removable drive", 3: "Local disk", 4: "Network drive", 5: "Optical drive"}.get(dt, "Other")
        except Exception:
            return "Local disk"
    return "Local disk"


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    except Exception:
        pass


def load_decisions():
    with _dec_lock:
        return _read_json(DECISIONS_FILE, {})


def save_decisions(updates):
    """updates: {path: {decision, reason, case}}  -> stored with user and time. Paths only, never content."""
    with _dec_lock:
        d = _read_json(DECISIONS_FILE, {})
        for p, v in updates.items():
            v = dict(v)
            v["by"] = getpass.getuser()
            v["when"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            d[p] = v
        _write_json(DECISIONS_FILE, d)


def term_fingerprint(value, salt):
    """Salted PBKDF2 fingerprint of a searched identifier (never stored raw). Evidence token only: short numeric
    identifiers have low entropy, so treat cases.json + config.json together as confidential."""
    return hashlib.pbkdf2_hmac("sha256", value.strip().lower().encode("utf-8"), salt.encode(), 100000).hex()[:12]


def do_quarantine(path, batch_dir, idx):
    os.makedirs(batch_dir, exist_ok=True)
    stored = os.path.join(batch_dir, "%05d_%s" % (idx, os.path.basename(path)))
    shutil.move(path, stored)
    return stored


def undo_last_quarantine(qdir):
    """Restore the most recent quarantine batch. Returns (restored, skipped, batch_name)."""
    if not os.path.isdir(qdir):
        return 0, 0, None
    batches = sorted(d for d in os.listdir(qdir) if d.startswith("batch_")
                     and os.path.exists(os.path.join(qdir, d, "manifest.json")))
    if not batches:
        return 0, 0, None
    b = batches[-1]
    mf = os.path.join(qdir, b, "manifest.json")
    with open(mf, "r", encoding="utf-8") as f:
        items = json.load(f)
    ok = skip = 0
    for it in items:
        try:
            if os.path.exists(it["stored"]) and not os.path.exists(it["orig"]):
                os.makedirs(os.path.dirname(it["orig"]), exist_ok=True)
                shutil.move(it["stored"], it["orig"])
                ok += 1
            else:
                skip += 1
        except Exception:
            skip += 1
    os.replace(mf, os.path.join(qdir, b, "manifest.restored.json"))
    return ok, skip, b


def quarantine_stats(qdir):
    files = size = 0
    if os.path.isdir(qdir):
        for d in os.listdir(qdir):
            bd = os.path.join(qdir, d)
            if d.startswith("batch_") and os.path.isdir(bd):
                for dp, _, fn in os.walk(bd):
                    for f in fn:
                        if f.startswith("manifest"):
                            continue
                        files += 1
                        try:
                            size += os.path.getsize(os.path.join(dp, f))
                        except OSError:
                            pass
    return files, size


def empty_quarantine(qdir):
    """PERMANENT deletion of everything held in quarantine batches. Returns (files, bytes)."""
    n, sz = quarantine_stats(qdir)
    if os.path.isdir(qdir) and not is_protected(qdir):
        for d in os.listdir(qdir):
            bd = os.path.join(qdir, d)
            if d.startswith("batch_") and os.path.isdir(bd) and not os.path.islink(bd):
                shutil.rmtree(bd, ignore_errors=True)
    return n, sz


# ---- review helpers: masked preview and match context (shown on demand, never stored) ----
def _mask_card(m):
    d = re.sub(r"\D", "", m.group(0))
    return "XXXX XXXX XXXX " + d[-4:] if luhn_ok(d) and CARD_PREFIX.match(d) else m.group(0)


def _mask_aadhaar(m):
    d = m.group(1) + m.group(3) + m.group(5)
    return "XXXX XXXX " + d[-4:] if len(set(d)) > 1 and verhoeff_ok(d) and d[0] in "23456789" else m.group(0)


def mask_text(text):
    text = RX_CARD.sub(_mask_card, text)
    text = RX_AADHAAR.sub(_mask_aadhaar, text)
    text = RX_PAN.sub(lambda m: m.group(0)[:3] + "XXXXXX" + m.group(0)[-1], text)
    text = RX_UPI.sub(lambda m: m.group(0)[:1] + "***@" + m.group(0).split("@")[-1], text)
    text = RX_EMAIL.sub(lambda m: m.group(0)[:1] + "***@" + m.group(0).split("@")[-1], text)
    text = RX_MOBILE.sub(lambda m: "XXXXXX" + re.sub(r"\D", "", m.group(0))[-4:], text)
    return text


def digit_pattern(d, prefix=""):
    body = r"[ \-. ]?".join(re.escape(c) for c in d)
    return re.compile(r"(?<!\d)" + prefix + body + r"(?!\d)")


def term_regex(kind, value):
    v = value.strip()
    if kind == "Mobile":
        d = re.sub(r"\D", "", v)[-10:]
        return digit_pattern(d, r"(?:\+?91[ \-]?|0)?") if len(d) == 10 else None
    if kind == "Aadhaar":
        d = re.sub(r"\D", "", v)
        return digit_pattern(d) if len(d) == 12 else None
    if kind == "PAN":
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(v.upper()) + r"(?![A-Za-z0-9])", re.I) if v else None
    if kind == "Email":
        return re.compile(r"(?<![\w.+\-])" + re.escape(v.lower()) + r"(?![A-Za-z0-9_\-])", re.I) if "@" in v else None
    if kind == "Name":
        words = v.split()
        return re.compile(r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b", re.I) if words else None
    return re.compile(re.escape(v), re.I) if len(v) >= 3 else None


def context_snippets(text, regexes, width=110, limit=12):
    """Snippets around searched identifiers; the searched value is shown inside [[ ]], other PII is masked."""
    out = []
    for kind, rx in regexes:
        for m in rx.finditer(text):
            s, e = max(0, m.start() - width), min(len(text), m.end() + width)
            before, hit, after = text[s:m.start()], m.group(0), text[m.end():e]
            snip = mask_text(before) + "[[" + hit + "]]" + mask_text(after)
            out.append("(%s)  ...%s..." % (kind, " ".join(snip.split())))
            if len(out) >= limit:
                return out
    return out


def summarize_counts(counts):
    return ", ".join("%s %d" % (k, v) for k, v in counts.items() if v)


def folder_key(root, dirpath, depth=3):
    rel = os.path.relpath(dirpath, root)
    if rel == ".":
        return ""
    return os.sep.join(rel.split(os.sep)[:depth])


def _group_copies(items):
    groups = {}
    for it in items:
        if it.get("hash"):
            groups.setdefault(it["hash"], []).append(it)
    for g in groups.values():
        for it in g:
            it["copies"] = len(g) - 1


def run_dpdp(cfg, cancel, progress):
    """Scan every mapped storage location for personal data. Results hold paths, owners, sizes and counts only."""
    t0 = time.time()
    exts = set(TEXT_EXTS) | set(OFFICE_EXTS) | ({".pdf"} if _pypdf is not None else set())
    use_ocr = bool(cfg.get("ocr")) and ocr_available()
    if use_ocr:
        exts |= OCR_EXTS
    mode = cfg.get("aadhaar_mode", AADHAAR_MODES[0])
    limit = cfg["max_mb"] * 1024 * 1024
    unsupported = {}
    stats = {"files": 0, "scanned": 0, "flagged": 0, "skipped": 0, "errors": 0, "no_text": 0, "ocr_files": 0,
             "ocr_on": use_ocr, "unsupported": unsupported, "elapsed": 0.0, "partial": 0,
             "totals": dict.fromkeys(PII_TYPES, 0), "risk": {"High": 0, "Medium": 0, "Low": 0}, "locations": {}}
    findings, folders = [], {}
    progress("Mapping storage locations...", 0)
    for loc in cfg["locations"]:
        label, root = loc["label"], loc["path"]
        ltype = classify_location(root)
        ls = {"type": ltype, "path": root, "scanned": 0, "flagged": 0, "high": 0, "medium": 0, "low": 0, "size": 0}
        stats["locations"][label] = ls
        for path, size, mtime in crawl([root], cancel, cfg["skip_hidden"], 1, None, None, [cfg.get("qdir")]):
            if cancel.is_set():
                return None
            ext = os.path.splitext(path)[1].lower()
            if ext not in exts:
                if ext in UNSUPPORTED_EXTS or (ext == ".pdf" and _pypdf is None) or (ext in OCR_EXTS and not use_ocr):
                    unsupported[ext] = unsupported.get(ext, 0) + 1
                continue
            stats["files"] += 1
            if limit < size <= limit * 4:
                stats["partial"] += 1                        # read only up to the MB limit
            if size > limit * 4:
                stats["skipped"] += 1
                continue
            fk = folder_key(root, os.path.dirname(path))
            fs = folders.setdefault((label, fk), {"files": 0, "flagged": 0, "high": 0, "size": 0,
                                                  "counts": dict.fromkeys(PII_TYPES, 0)})
            ctx = {}
            try:
                if use_ocr and (ext in OCR_EXTS or ext == ".pdf" or ext in OFFICE_EXTS):
                    progress("Reading %s (OCR may take a few seconds)..." % os.path.basename(path), 50)
                text = extract_text(path, limit, use_ocr, ctx)
            except Exception:
                stats["errors"] += 1
                continue
            if ctx.get("ocr"):
                stats["ocr_files"] += 1
            stats["scanned"] += 1
            ls["scanned"] += 1
            fs["files"] += 1
            fs["size"] += size
            if len(text.strip()) < 5:
                stats["no_text"] += 1
            counts = detect_pii(text, cfg["extras"], mode, bool(ctx.get("ocr")))
            del text
            if stats["scanned"] % 20 == 0:
                progress("Scanned %d files - %d with personal data" % (stats["scanned"], stats["flagged"]), 50)
            if sum(counts.values()) == 0:
                continue
            risk, score = risk_of(counts)
            stats["flagged"] += 1
            ls["flagged"] += 1
            fs["flagged"] += 1
            rk = risk if risk in stats["risk"] else "Low"
            stats["risk"][rk] += 1
            ls[rk.lower()] += 1
            ls["size"] += size
            if rk == "High":
                fs["high"] += 1
            for k, v in counts.items():
                stats["totals"][k] += v
                fs["counts"][k] += v
            remark, action = remarks_for(path, counts, risk, bool(ctx.get("ocr")))
            findings.append({"path": path, "location": label, "loc_type": ltype, "owner": file_owner(path),
                             "size": size, "mtime": mtime, "counts": counts, "risk": risk, "score": score,
                             "summary": summarize_counts(counts), "remark": remark, "action": action,
                             "ocr": bool(ctx.get("ocr")), "copies": 0,
                             "hash": hash_file(path, cancel) if size <= HASH_MAX_BYTES else ""})
    findings.sort(key=lambda r: r["score"], reverse=True)
    _group_copies(findings)
    fl = [{"location": k[0], "folder": k[1], **v} for k, v in sorted(folders.items())]
    stats["elapsed"] = time.time() - t0
    progress("Completed.", 100)
    return {"findings": findings, "stats": stats, "folders": fl}


def run_search(cfg, cancel, progress):
    """Consent-revocation trace: find every file in the mapped locations that mentions the given identifiers."""
    t0 = time.time()
    exts = set(TEXT_EXTS) | set(OFFICE_EXTS) | ({".pdf"} if _pypdf is not None else set())
    use_ocr = bool(cfg.get("ocr")) and ocr_available()
    if use_ocr:
        exts |= OCR_EXTS
    limit = cfg["max_mb"] * 1024 * 1024
    terms = [(t["kind"], term_regex(t["kind"], t["value"])) for t in cfg["terms"]]
    terms = [(k, rx) for k, rx in terms if rx is not None]
    stats = {"scanned": 0, "hits": 0, "errors": 0, "elapsed": 0.0, "ocr_on": use_ocr, "locations": {}}
    hits = []
    progress("Searching storage locations...", 0)
    for loc in cfg["locations"]:
        label, root = loc["label"], loc["path"]
        ltype = classify_location(root)
        stats["locations"][label] = {"type": ltype, "scanned": 0, "hits": 0}
        for path, size, mtime in crawl([root], cancel, cfg["skip_hidden"], 1, None, None, [cfg.get("qdir")]):
            if cancel.is_set():
                return None
            ext = os.path.splitext(path)[1].lower()
            if ext not in exts or size > limit * 4:
                continue
            ctx = {}
            try:
                text = extract_text(path, limit, use_ocr, ctx)
            except Exception:
                stats["errors"] += 1
                continue
            stats["scanned"] += 1
            stats["locations"][label]["scanned"] += 1
            if stats["scanned"] % 20 == 0:
                progress("Searched %d files - %d match" % (stats["scanned"], stats["hits"]), 50)
            counts = {}
            for kind, rx in terms:
                n = len(rx.findall(text))
                if n:
                    counts[kind] = counts.get(kind, 0) + n
            del text
            if not counts:
                continue
            stats["hits"] += 1
            stats["locations"][label]["hits"] += 1
            hits.append({"path": path, "location": label, "loc_type": ltype, "owner": file_owner(path), "size": size,
                         "mtime": mtime, "risk": "Match", "score": sum(counts.values()), "counts": counts,
                         "summary": ", ".join("%s x%d" % kv for kv in counts.items()), "ocr": bool(ctx.get("ocr")),
                         "remark": "Contains the searched identifier(s): " + ", ".join(counts) + ".",
                         "action": "Review in context, then Keep (with a lawful reason) or Delete (quarantine).",
                         "copies": 0, "hash": hash_file(path, cancel) if size <= HASH_MAX_BYTES else ""})
    hits.sort(key=lambda r: r["score"], reverse=True)
    _group_copies(hits)
    stats["elapsed"] = time.time() - t0
    progress("Completed.", 100)
    return {"hits": hits, "stats": stats}


# ----------------------------------------------------------------------------------------------
# 4. PHASE 2 - DPDP DISCOVERY ENGINE  (zero-PII storage: counts only)
# ----------------------------------------------------------------------------------------------
_VD = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
       [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
       [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
       [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VP = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
       [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
       [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def verhoeff_ok(num):
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _VD[c][_VP[i % 8][int(ch)]]
    return c == 0


def luhn_ok(num):
    s, alt = 0, False
    for ch in reversed(num):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0


SEP = "[ \\-.\u00a0\u2009\u202f/]"
RX_AADHAAR = re.compile(r"(?<![\d])(\d{4})(%s?)(\d{4})(%s?)(\d{4})(?![\d])" % (SEP, SEP))
RX_AADHAAR_KEY = re.compile(r"aadh?aa?r|adhaa?r|uidai|\buid\b|\bvid\b|आधार", re.I)
RX_PAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3}[PCHABGJLFT][A-Z]\d{4}[A-Z](?![A-Za-z0-9])", re.I)   # re.I: lower-case PAN in typed text
RX_PAN_OCR = re.compile(r"[A-Z]{3}[PCHABGJLFT][A-Z]\d{4}[A-Z](?!\d)", re.I)               # OCR glues words: allow letters on both sides
RX_CARD = re.compile(r"(?<![\d])\d(?:[ -]?\d){12,18}(?![\d])")
RX_IFSC = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Za-z0-9])")
UPI_HANDLES = ("ybl|ibl|axl|okhdfcbank|okicici|oksbi|okaxis|paytm|upi|apl|fbl|sbi|hdfcbank|icici|axisbank|"
               "pnb|boi|cnrb|idfcbank|kotak|aubank|yesbank|rbl|federal|jupiter|slice|ptyes|pthdfc|ptsbi|"
               "ptaxis|waicici|wahdfcbank|wasbi|waaxis|freecharge|airtel|postbank|indus|dbs|jio|ikwik|"
               "abfspay|axisb|barodampay|unionbank|allbank|mahb|idbi|centralbank")
RX_UPI = re.compile(r"(?<![\w.\-])[A-Za-z0-9._\-]{2,64}@(?:%s)(?![\w.])" % UPI_HANDLES, re.I)
RX_MOBILE = re.compile(r"(?<![\d])(?:\+91[ -]?|0)?[6-9]\d{9}(?![\d])")
RX_EMAIL = re.compile(r"(?<![\w.+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+(?![\w])")
CARD_PREFIX = re.compile(r"^(4|5[0-8]|2[2-7]|3[47]|35|6011|65|60|62|63|67|81|82|36|30[0-5])")

PII_TYPES = ["Aadhaar", "Aadhaar?", "PAN", "Card", "IFSC", "UPI", "Mobile", "Email"]
PII_WEIGHT = {"Aadhaar": 10, "Aadhaar?": 4, "PAN": 8, "Card": 10, "IFSC": 2, "UPI": 3, "Mobile": 1, "Email": 1}
PII_COLOR_KEY = {"Aadhaar": "p", "Aadhaar?": "a", "PAN": "s", "Card": "a", "IFSC": "w", "UPI": "g", "Mobile": "p", "Email": "s"}
TEXT_EXTS = {".txt", ".csv", ".tsv", ".json", ".xml", ".log", ".md", ".ini", ".cfg", ".yaml", ".yml", ".sql",
             ".html", ".htm", ".eml", ".py", ".js", ".rtf", ".conf", ".dat"}
OFFICE_EXTS = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm", ".odt", ".ods", ".odp"}
UNSUPPORTED_EXTS = {".xls", ".doc", ".ppt", ".msg", ".pst", ".zip", ".7z", ".rar", ".xlsb"}
AADHAAR_MODES = ["Standard (checksum + keyword hint)", "Strict (checksum only)", "Loose (any 12-digit, for UAT)"]


def _looks_like_timestamp(n):
    """12 digits shaped like YYYYMMDDhhmm (log/order timestamps) are not Aadhaar numbers."""
    try:
        y, mo, d, h, mi = int(n[:4]), int(n[4:6]), int(n[6:8]), int(n[8:10]), int(n[10:12])
    except ValueError:
        return False
    return 1990 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31 and h <= 23 and mi <= 59


def detect_pii(text, extras=False, mode="Standard", ocr=False):
    c = dict.fromkeys(PII_TYPES, 0)
    for m in RX_AADHAAR.finditer(text):
        n = m.group(1) + m.group(3) + m.group(5)
        grouped = bool(m.group(2) or m.group(4))
        if len(set(n)) <= 3 or _looks_like_timestamp(n):      # patterned or timestamp-like: not an Aadhaar
            continue
        if grouped:                                            # part of a longer grouped number (e.g. a 16-digit card)
            if re.match(SEP + r"\d", text[m.end():m.end() + 2]) or re.search(r"\d" + SEP + "$", text[max(0, m.start() - 2):m.start()]):
                continue
        if n[0] in "23456789" and verhoeff_ok(n):
            c["Aadhaar"] += 1
        elif mode.startswith("Loose"):
            c["Aadhaar?"] += 1
        elif mode.startswith("Standard"):
            win = text[max(0, m.start() - 60):m.end() + 60]
            if RX_AADHAAR_KEY.search(win):
                c["Aadhaar?"] += 1
    c["PAN"] = len((RX_PAN_OCR if ocr else RX_PAN).findall(text))      # OCR often glues words together
    for m in RX_CARD.finditer(text):
        n = re.sub(r"[ -]", "", m.group(0))
        if 13 <= len(n) <= 19 and len(set(n)) > 1 and CARD_PREFIX.match(n) and luhn_ok(n):
            c["Card"] += 1
    c["IFSC"] = len(RX_IFSC.findall(text))
    c["UPI"] = len(RX_UPI.findall(text))
    if extras:
        c["Mobile"] = len(RX_MOBILE.findall(text))
        c["Email"] = len(RX_EMAIL.findall(text))
    return c


def decode_bytes(b):
    """Decode text safely: BOMs, UTF-16 (Excel 'Unicode Text'), UTF-8, then Windows-1252."""
    if b.startswith((b"\xff\xfe", b"\xfe\xff")):
        return b.decode("utf-16", "ignore")
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "ignore")
    if b[:4000].count(b"\x00") > max(4, len(b[:4000]) // 5):                           # UTF-16 without BOM
        return b.decode("utf-16-le" if b[1:2] == b"\x00" else "utf-16-be", "ignore")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252", "ignore")


def xml_to_text(data):
    """Office XML -> text. Runs are joined WITHOUT spaces so numbers split by Word/Excel stay whole."""
    import html as _html
    data = re.sub(r"</(?:w:p|a:p|c|si|row|text:p|table:table-row)>|<w:br/>|<text:line-break/>", "\n", data)
    data = re.sub(r"<w:tab/>|<text:tab/>|</table:table-cell>", " ", data)
    return _html.unescape(re.sub(r"<[^>]+>", "", data))


def extract_text(path, limit, ocr=False, ctx=None):
    ctx = ctx if ctx is not None else {}
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXTS:
        with open(path, "rb") as f:
            return decode_bytes(f.read(limit))
    if ext in OFFICE_EXTS:
        parts = []
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith(".xml") and
                     (n.startswith("word/") or n.startswith("xl/") or n.startswith("ppt/slides/") or n == "content.xml")]
            used = 0
            for n in names:
                if used >= limit:
                    break
                data = z.open(n).read(limit - used).decode("utf-8", "ignore")
                used += len(data)
                parts.append(xml_to_text(data))
            if ocr and ocr_available():
                parts.append(ocr_office(z, ctx))
        return "\n".join(parts)
    if ext == ".pdf" and _pypdf is not None:
        r = _pypdf.PdfReader(path)
        if r.is_encrypted:
            return ""
        out = []
        for pg in r.pages[:60]:
            out.append(pg.extract_text() or "")
            if sum(len(x) for x in out) > limit:
                break
        if ocr and ocr_available():
            out.append(ocr_pdf(r, ctx))
        return "\n".join(out)
    if ext in OCR_EXTS and ocr and ocr_available():
        with open(path, "rb") as f:
            data = f.read(OCR_MAX_IMAGE_BYTES + 1)
        ctx["ocr"] = True
        return ocr_image_bytes(data)
    return ""


# ----------------------------------------------------------------------------------------------
# 4b. OPTIONAL OCR  (RapidOCR / ONNX - fully offline; text is used in memory only, never stored)
# ----------------------------------------------------------------------------------------------
OCR_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif", ".webp"}
OCR_MAX_IMAGE_BYTES = 25 * 1024 * 1024
OCR_MAX_PDF_PAGES = 10
OCR_MAX_EMBEDDED = 8
_ocr_engine = None
_ocr_lock = threading.Lock()


def _ocr_helper():
    """Path of the separate OCR program shipped beside the EXE (None if absent)."""
    cands = [os.environ.get("DPDP_OCR_HELPER", ""),
             os.path.join(APP_DIR, "ocr_worker", "ocr_worker.exe"), os.path.join(APP_DIR, "ocr_worker.exe"),
             os.path.join(APP_DIR, "ocr_worker", "ocr_worker")]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def ocr_available():
    return _RapidOCR is not None or _ocr_helper() is not None


def _get_ocr():
    global _ocr_engine
    with _ocr_lock:
        if _ocr_engine is None and _RapidOCR is not None:
            _ocr_engine = _RapidOCR()
        return _ocr_engine


def ocr_image_bytes(data):
    """OCR one image (bytes) -> text. Large pictures are downscaled; multi-page TIFFs use up to 3 frames."""
    if _RapidOCR is None and _ocr_helper():                    # packaged EXE: run OCR in the helper process
        if not data or len(data) > OCR_MAX_IMAGE_BYTES:
            return ""
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".img")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            r = subprocess.run([_ocr_helper(), tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=0x08000000 if os.name == "nt" else 0, timeout=180)
            return r.stdout.decode("utf-8", "ignore") if r.returncode == 0 else ""
        except Exception:
            return ""
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    eng = _get_ocr()
    if eng is None or not data or len(data) > OCR_MAX_IMAGE_BYTES:
        return ""
    from PIL import Image, ImageSequence
    import numpy as np
    Image.MAX_IMAGE_PIXELS = 80000000                          # decompression-bomb guard
    out = []
    with Image.open(io.BytesIO(data)) as im:
        for i, frame in enumerate(ImageSequence.Iterator(im)):
            if i >= 3:
                break
            fr = frame.convert("RGB")
            fr.thumbnail((2600, 2600))
            res = eng(np.array(fr))
            if hasattr(res, "txts"):                           # rapidocr >= 2
                out.extend(res.txts or [])
            else:                                              # rapidocr-onnxruntime
                out.extend(r[1] for r in (res[0] or []))
    return "\n".join(str(x) for x in out)


def ocr_pdf(reader, ctx):
    """OCR the embedded page images of pages that have no text layer (scanned PDFs)."""
    texts, n = [], 0
    for pg in reader.pages[:OCR_MAX_PDF_PAGES]:
        if (pg.extract_text() or "").strip():
            continue
        try:
            for img in list(pg.images)[:3]:
                texts.append(ocr_image_bytes(img.data))
                n += 1
        except Exception:
            continue
        if n >= 20:
            break
    if texts:
        ctx["ocr"] = True
    return "\n".join(texts)


def ocr_office(z, ctx):
    texts, n = [], 0
    for name in z.namelist():
        if "/media/" in name and os.path.splitext(name)[1].lower() in OCR_EXTS:
            try:
                if z.getinfo(name).file_size <= OCR_MAX_IMAGE_BYTES:
                    texts.append(ocr_image_bytes(z.read(name)))
                    n += 1
            except Exception:
                pass
            if n >= OCR_MAX_EMBEDDED:
                break
    if texts:
        ctx["ocr"] = True
    return "\n".join(texts)


def risk_of(counts):
    score = sum(PII_WEIGHT[k] * min(v, 50) for k, v in counts.items())
    sensitive = sum(1 for k in ("Aadhaar", "PAN", "Card") if counts[k])
    if score >= 50 or sensitive >= 2:
        return "High", score
    if sensitive == 1 and score < 10:
        return "Medium", score
    if score >= 10:
        return "Medium", score
    return ("Low", score) if score > 0 else ("None", 0)


def remarks_for(path, counts, risk, ocr=False):
    """Plain-language remark + suggested action for a flagged file (no personal data used)."""
    found, acts = [], []
    c = counts
    if c["Aadhaar"]:
        found.append("%d Aadhaar number(s) - pass the Aadhaar checksum (about 1 in 10 random 12-digit numbers does too), so confirm manually before acting" % c["Aadhaar"])
        acts.append("Aadhaar: mask all but last 4 digits or move to an encrypted, access-controlled store; "
                    "keep only if a lawful purpose exists (Aadhaar Act / UIDAI masking norms)")
    if c["Aadhaar?"]:
        found.append("%d possible Aadhaar number(s) - 12 digits that fail the checksum or sit next to the word Aadhaar; "
                     "may be dummy/test or mistyped numbers" % c["Aadhaar?"])
        acts.append("Possible Aadhaar: verify manually; if real, treat as Aadhaar. If test data, label the file clearly")
    if c["Card"]:
        found.append("%d payment card number(s) - Luhn-verified" % c["Card"])
        acts.append("Cards: do not keep card numbers in files; delete or mask now (PCI-DSS)")
    if c["PAN"]:
        found.append("%d PAN(s) - format match (false positives possible)" % c["PAN"])
        acts.append("PAN: restrict access and mask in reports; retain only for tax/KYC need")
    if c["UPI"] or c["IFSC"]:
        found.append("bank/UPI identifiers (UPI %d, IFSC %d) - pattern match" % (c["UPI"], c["IFSC"]))
        acts.append("Bank/UPI: low risk alone, but high risk if listed with names - review the file")
    if c["Mobile"] or c["Email"]:
        found.append("contact details (mobile %d, e-mail %d)" % (c["Mobile"], c["Email"]))
        acts.append("Contact data: confirm purpose and consent; remove if no longer needed")
    ext = os.path.splitext(path)[1].lower()
    low = path.lower().replace("\\", "/")
    ctx = []
    if sum(c.values()) >= 20 and ext in (".csv", ".xlsx", ".xml", ".json", ".sql", ".tsv"):
        ctx.append("Looks like a bulk data extract/database dump - confirm the owner and authority to hold it")
    if ext in (".log", ".py", ".js", ".html", ".htm", ".conf", ".ini"):
        ctx.append("Found in a log/code/config file - probably accidental exposure; redact or remove")
    if any(x in low for x in ("/downloads/", "/desktop/", "/temp/", "/tmp/", "/recycle")):
        ctx.append("Stored in a personal/temporary folder - move to an approved repository or delete")
    remark = "Contains " + "; ".join(found) + "." if found else "No personal data."
    if ctx:
        remark += " " + " ".join(x + "." for x in ctx)
    if ocr:
        remark += " (Read partly or fully by OCR: digits can be misread, so verify manually.)"
    tail = {"High": "PRIORITY: act within days, record the decision in the audit log.",
            "Medium": "Review this month and record the outcome.",
            "Low": "Review at next periodic audit."}.get(risk, "")
    action = " | ".join(acts) + (" | " + tail if tail else "")
    action += " | Keep a retention/deletion date for data held under the DPDP Act, 2023 (data-minimisation and storage limitation)."
    return remark, action


# ----------------------------------------------------------------------------------------------
# 5. PWA SERVER  (127.0.0.1 only, read-only, token protected, offline-first)
# ----------------------------------------------------------------------------------------------
PWA = {"state": b"{}", "icons": {}, "token": "", "port": 0, "name": DEFAULT_NAME, "theme": THEMES["Indigo Pulse"]}

PWA_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__NAME__</title>
<meta name="theme-color" content="__P__"><link rel="manifest" href="/manifest.webmanifest?k=__K__">
<link rel="icon" href="/icon-192.png?k=__K__"><link rel="apple-touch-icon" href="/icon-192.png?k=__K__">
<style>:root{--p:__P__;--s:__S__;--a:__A__;--w:__W__;--g:__G__;--bg:__BG__}
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Roboto,Arial,sans-serif;background:var(--bg);color:#1e2233}
header{background:linear-gradient(120deg,var(--p),var(--s));color:#fff;padding:22px 20px}
header h1{margin:0;font-size:26px}header p{margin:4px 0 0;opacity:.9;font-size:14px}
#net{display:inline-block;margin-top:8px;padding:3px 12px;border-radius:12px;background:rgba(255,255,255,.25);font-size:12px}
main{padding:16px;max-width:1150px;margin:auto}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.kpi{border-radius:14px;padding:16px;color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.12)}
.kpi b{display:block;font-size:26px}.kpi span{font-size:13px;opacity:.95}
section{background:#fff;border-radius:14px;margin-top:16px;padding:16px;box-shadow:0 2px 10px rgba(0,0,0,.07);overflow-x:auto}
h2{margin:0 0 10px;font-size:17px;color:var(--p)}table{width:100%;border-collapse:collapse;font-size:13px}
th{background:linear-gradient(90deg,var(--p),var(--s));color:#fff;text-align:left;padding:7px}td{padding:6px 7px;border-bottom:1px solid #eceef6;word-break:break-all}
.bar{display:flex;align-items:center;margin:6px 0;font-size:13px}.bar i{display:block;height:16px;border-radius:8px;margin-left:8px}
.bar em{width:80px;font-style:normal}.tag{padding:2px 9px;border-radius:10px;color:#fff;font-size:12px}
.High{background:#e03131}.Medium{background:#f08c00}.Low{background:#2f9e44}.Match{background:#5b4bdb}.empty{color:#868e96;padding:10px}</style></head>
<body><header><h1 id="title"></h1><p>Personal-data discovery, storage map and consent-revocation console (read-only)</p><span id="net">connecting...</span></header>
<main><div class="kpis" id="kpis"></div><section><h2>Personal data by identifier</h2><div id="bars"></div></section>
<section><h2>Storage map by location</h2><div id="map"></div></section>
<section><h2>Highest-risk files (metadata only - no personal data stored)</h2><div id="pii"></div></section>
<section><h2>Consent-revocation cases</h2><div id="cases"></div></section>
<section><h2>Recent activity</h2><div id="act"></div></section></main>
<script src="/app.js?k=__K__"></script></body></html>"""

PWA_JS = """(function(){var K="__K__";function $(i){return document.getElementById(i)}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e}
function table(host,cols,rows,riskCol){host.textContent='';if(!rows.length){host.appendChild(el('div','empty','No data yet - run a scan in the desktop app.'));return}
var t=el('table'),h=el('tr');cols.forEach(function(c){h.appendChild(el('th',null,c))});t.appendChild(h);
rows.forEach(function(r){var tr=el('tr');r.forEach(function(v,i){var td=el('td');if(i===riskCol){td.appendChild(el('span','tag '+v,v))}else td.textContent=v;tr.appendChild(td)});t.appendChild(tr)});host.appendChild(t)}
function render(d){document.title=d.app_name;$('title').textContent=d.app_name;var k=$('kpis');k.textContent='';
var C=d.colors,ps=d.stats||{};
[['Locations mapped',d.locations.length,C.p],['Files scanned',ps.scanned||0,C.s],['Files with personal data',ps.flagged||0,C.g],
['High-risk files',(ps.risk||{}).High||0,'#e03131'],['Decisions pending',d.pending||0,C.a]].forEach(function(x){
var c=el('div','kpi');c.style.background=x[2];c.appendChild(el('b',null,String(x[1])));c.appendChild(el('span',null,x[0]));k.appendChild(c)});
var b=$('bars');b.textContent='';var tt=ps.totals||{},mx=1;Object.keys(tt).forEach(function(n){mx=Math.max(mx,tt[n])});
Object.keys(tt).forEach(function(n,i){var r=el('div','bar'),e=el('em',null,n),v=el('i');v.style.width=(tt[n]/mx*60)+'%';
v.style.minWidth='4px';v.style.background=[C.p,C.s,C.a,C.w,C.g][i%5];r.appendChild(e);r.appendChild(v);r.appendChild(el('span',null,'  '+tt[n]));b.appendChild(r)});
table($('map'),['Location','Type','Files scanned','With personal data','High risk'],d.locations.map(function(l){return [l.label,l.type,l.scanned,l.flagged,l.high]}));
table($('pii'),['Risk','File','Location','Owner','Findings','Copies','Decision'],d.files.map(function(f){return [f.risk,f.path,f.location,f.owner,f.summary,f.copies,f.decision]}),0);
table($('cases'),['Case','Date','Files found','Deleted','Kept'],d.cases.map(function(c){return [c.case,c.date,c.hits,c.deleted,c.kept]}));
table($('act'),['Time','Action','Detail'],d.activity)}
function load(){fetch('/api/state?k='+K,{cache:'no-store'}).then(function(r){var off=r.headers.get('X-Cache')==='HIT';
return r.json().then(function(d){render(d);$('net').textContent=(off?'Offline snapshot - ':'Live - ')+d.updated})}).catch(function(){$('net').textContent='No data available'})}
load();setInterval(load,5000);
if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js?k='+K).catch(function(){})}})();"""

PWA_SW = """var V='__V__',K='__K__',SHELL=['/?k='+K,'/app.js?k='+K,'/manifest.webmanifest?k='+K,'/icon-192.png?k='+K,'/icon-512.png?k='+K];
self.addEventListener('install',function(e){e.waitUntil(caches.open(V).then(function(c){return c.addAll(SHELL)}).then(function(){return self.skipWaiting()}))});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(ks){return Promise.all(ks.filter(function(k){return k!==V}).map(function(k){return caches.delete(k)}))}).then(function(){return self.clients.claim()}))});
self.addEventListener('fetch',function(e){var r=e.request;if(r.method!=='GET')return;var u=new URL(r.url);if(u.origin!==location.origin)return;
if(u.pathname==='/api/state'){e.respondWith(fetch(r).then(function(n){var cp=n.clone();caches.open(V).then(function(c){c.put(r,cp)});return n}).catch(function(){
return caches.match(r).then(function(c){if(!c)return new Response('{}',{status:503});var h=new Headers(c.headers);h.set('X-Cache','HIT');return c.blob().then(function(b){return new Response(b,{status:200,headers:h})})})}));return}
e.respondWith(caches.match(r).then(function(c){return c||fetch(r)}))});"""


class PwaHandler(BaseHTTPRequestHandler):
    server_version = "LocalConsole"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "connect-src 'self'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            host = (self.headers.get("Host") or "").lower()
            if host not in ("127.0.0.1:%d" % PWA["port"], "localhost:%d" % PWA["port"]):
                return self._send(403, "Forbidden", "text/plain")            # DNS-rebinding guard
            u = urlparse(self.path)
            k = parse_qs(u.query).get("k", [""])[0]
            if not hmac.compare_digest(k, PWA["token"]):
                return self._send(403, "Access token required", "text/plain")
            T, tk = PWA["theme"], PWA["token"]
            rep = {"__K__": tk, "__NAME__": PWA["name"].replace("&", "&amp;").replace("<", "&lt;"),
                   "__P__": T["p"], "__S__": T["s"], "__A__": T["a"], "__W__": T["w"], "__G__": T["g"],
                   "__BG__": T["bg"], "__V__": "v%s-%s" % (APP_VERSION, tk[:4])}

            def fill(s):
                for a, b in rep.items():
                    s = s.replace(a, b)
                return s
            p = u.path
            if p == "/":
                self._send(200, fill(PWA_HTML), "text/html; charset=utf-8", {"Cache-Control": "no-cache"})
            elif p == "/app.js":
                self._send(200, fill(PWA_JS), "application/javascript; charset=utf-8")
            elif p == "/sw.js":
                self._send(200, fill(PWA_SW), "application/javascript; charset=utf-8",
                           {"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})
            elif p == "/manifest.webmanifest":
                m = {"name": PWA["name"], "short_name": PWA["name"][:12], "start_url": "/?k=" + tk,
                     "scope": "/", "display": "standalone", "background_color": T["bg"],
                     "theme_color": T["p"], "description": "Offline DPDP personal-data discovery console",
                     "icons": [{"src": "/icon-192.png?k=" + tk, "sizes": "192x192", "type": "image/png",
                                "purpose": "any maskable"},
                               {"src": "/icon-512.png?k=" + tk, "sizes": "512x512", "type": "image/png",
                                "purpose": "any maskable"}]}
                self._send(200, json.dumps(m), "application/manifest+json")
            elif p in ("/icon-192.png", "/icon-512.png"):
                self._send(200, PWA["icons"].get(p, b""), "image/png")
            elif p == "/api/state":
                self._send(200, PWA["state"], "application/json", {"Cache-Control": "no-store"})
            else:
                self._send(404, "Not found", "text/plain")
        except Exception:
            try:
                self._send(500, "Error", "text/plain")
            except Exception:
                pass


def start_pwa_server(port):
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), PwaHandler)
            PWA["port"] = p
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            return srv, p
        except OSError:
            continue
    return None, None


def make_icon_png(name, theme, size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(theme["p"]))
    g.setColorAt(1, QColor(theme["s"]))
    p.setBrush(QBrush(g))
    p.setPen(Qt.NoPen)
    p.drawRect(0, 0, size, size)                   # full-bleed square => safe for maskable icons
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", int(size * 0.34), QFont.Bold)
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, (name[:1] or "E").upper())
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


# ----------------------------------------------------------------------------------------------
# 6. WORKER THREADS
# ----------------------------------------------------------------------------------------------
class ScanThread(QThread):
    progress = pyqtSignal(str, int)
    finished_ok = pyqtSignal(object)

    def __init__(self, fn, cfg):
        super().__init__()
        self.fn, self.cfg = fn, cfg
        self.cancel = threading.Event()

    def run(self):
        try:
            res = self.fn(self.cfg, self.cancel, lambda m, p: self.progress.emit(m, p))
        except Exception as e:
            res = {"error": str(e)}
        self.finished_ok.emit(res)


# ----------------------------------------------------------------------------------------------
# 7. UI WIDGETS
# ----------------------------------------------------------------------------------------------
def make_qss(t):
    return """
    QMainWindow, QWidget#root { background: %(bg)s; }
    QWidget { font-family: 'Segoe UI', Arial; font-size: 10pt; color: #1e2233; }
    QFrame#header { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %(p)s, stop:1 %(s)s); border-radius: 14px; }
    QLabel#hTitle { color: white; font-size: 22pt; font-weight: 700; background: transparent; }
    QLabel#hSub { color: rgba(255,255,255,0.92); font-size: 10pt; background: transparent; }
    QTabWidget::pane { border: 0; }
    QTabBar::tab { background: white; color: %(p)s; padding: 10px 14px; margin-right: 6px; border-radius: 10px;
                   font-weight: 600; }
    QTabBar::tab:selected { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %(p)s, stop:1 %(s)s); color: white; }
    QTabBar::tab:hover:!selected { background: #e9ecff; }
    QGroupBox { background: white; border: 1px solid #e3e6f3; border-radius: 12px; margin-top: 14px; padding: 12px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: %(p)s; }
    QPushButton { background: %(p)s; color: white; border: 0; border-radius: 8px; padding: 8px 16px; font-weight: 600; }
    QPushButton:hover { background: %(s)s; }
    QPushButton:disabled { background: #c9cddd; color: #f4f5fa; }
    QPushButton#danger { background: #E03131; } QPushButton#danger:hover { background: #C92A2A; }
    QPushButton#ghost { background: white; color: %(p)s; border: 1px solid %(p)s; }
    QPushButton#ghost:hover { background: %(p)s; color: white; }
    QPushButton#good { background: %(g)s; } QPushButton#good:hover { background: %(s)s; }
    QLineEdit, QComboBox, QSpinBox, QListWidget, QPlainTextEdit { background: white; border: 1px solid #cfd4ea;
                   border-radius: 8px; padding: 5px; selection-background-color: %(p)s; }
    QTreeWidget, QTableWidget { background: white; border: 1px solid #e3e6f3; border-radius: 10px;
                   alternate-background-color: #f7f8fe; gridline-color: #eceef8; selection-background-color: %(s)s; selection-color: white; }
    QHeaderView::section { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %(p)s, stop:1 %(s)s); color: white;
                   padding: 7px; border: 0; font-weight: 600; }
    QProgressBar { border: 0; background: #dfe3f5; border-radius: 8px; height: 16px; text-align: center; color: #1e2233; }
    QProgressBar::chunk { border-radius: 8px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %(g)s, stop:1 %(s)s); }
    QCheckBox::indicator { width: 17px; height: 17px; }
    QStatusBar { background: white; color: #555; }
    QToolTip { background: #1e2233; color: white; border: 0; padding: 5px; }
    """ % t


class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Activate licence")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        t = QLabel("Activate your licence")
        t.setStyleSheet("font-size:16pt;font-weight:700;")
        self.st = QLabel()
        self.st.setWordWrap(True)
        info = QLabel("Paste your licence code below. Don't have one? Get a free 7-day trial from our website, "
                      "then paste the code here. Activation works offline.")
        info.setWordWrap(True)
        self.box = QPlainTextEdit()
        self.box.setPlaceholderText("DL-XXXXX-XXXXX-XXXXX-...")
        self.box.setMaximumHeight(110)
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        row = QHBoxLayout()
        a = QPushButton("Activate")
        a.setObjectName("good")
        a.clicked.connect(self.do_activate)
        g = QPushButton("Get free 7-day trial")
        g.setObjectName("ghost")
        g.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TRIAL_URL)))
        c = QPushButton("Close")
        c.setObjectName("ghost")
        c.clicked.connect(self.reject)
        for b in (a, g):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(c)
        for w in (t, self.st, info, self.box, self.msg):
            v.addWidget(w)
        v.addLayout(row)
        self.refresh()

    def refresh(self):
        st = LICENSE.status()
        self.st.setText("Current status: " + st["text"])

    def do_activate(self):
        try:
            st = LICENSE.activate(self.box.toPlainText())
        except ValueError as e:
            self.msg.setStyleSheet("color:#e03131;font-weight:600;")
            self.msg.setText(str(e))
            return
        audit("LICENSE_ACTIVATED", st["text"])
        QMessageBox.information(self, "Activated", st["text"])
        self.accept()


class KpiCard(QFrame):
    def __init__(self, title, color):
        super().__init__()
        self.setStyleSheet("QFrame{background:%s;border-radius:14px;} QLabel{background:transparent;color:white;}" % color)
        lay = QVBoxLayout(self)
        self.val = QLabel("0")
        self.val.setStyleSheet("font-size:24pt;font-weight:700;background:transparent;color:white;")
        self.lbl = QLabel(title)
        self.lbl.setStyleSheet("font-size:10pt;background:transparent;color:white;")
        lay.addWidget(self.val)
        lay.addWidget(self.lbl)
        self.setMinimumHeight(88)

    def set(self, v):
        self.val.setText(str(v))


class DonutChart(QWidget):
    def __init__(self, title):
        super().__init__()
        self.title, self.parts, self.center = title, [], ""
        self.setMinimumSize(240, 230)

    def set(self, parts, center):
        self.parts, self.center = parts, center
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        p.setPen(QColor("#6C5CE7"))
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(12, 22, self.title)
        side = min(self.width(), self.height() - 60) - 40
        r = QRectF((self.width() - side) / 2, 40, side, side)
        total = sum(v for _, v, _ in self.parts)
        if total <= 0:
            p.setPen(QPen(QColor("#dfe3f5"), 22))
            p.drawEllipse(r)
        else:
            start = 90 * 16
            for _, v, col in self.parts:
                span = int(-360 * 16 * v / total)
                p.setPen(QPen(QColor(col), 22, Qt.SolidLine, Qt.FlatCap))
                p.drawArc(r, start, span)
                start += span
        p.setPen(QColor("#1e2233"))
        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.drawText(r, Qt.AlignCenter, self.center)
        p.setFont(QFont("Segoe UI", 8))
        x = 12
        for lbl, _, col in self.parts:
            p.setBrush(QColor(col))
            p.setPen(Qt.NoPen)
            p.drawEllipse(x, self.height() - 22, 10, 10)
            p.setPen(QColor("#444"))
            p.drawText(x + 14, self.height() - 12, lbl)
            x += 22 + p.fontMetrics().horizontalAdvance(lbl)
        p.end()


class BarChart(QWidget):
    def __init__(self, title):
        super().__init__()
        self.title, self.items = title, []
        self.setMinimumSize(300, 230)

    def set(self, items):
        self.items = items
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        p.setPen(QColor("#6C5CE7"))
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(12, 22, self.title)
        mx = max([v for _, v, _ in self.items] + [1])
        y, h = 38, max(12, min(24, (self.height() - 50) // max(1, len(self.items)) - 6))
        p.setFont(QFont("Segoe UI", 9))
        for lbl, v, col in self.items:
            p.setPen(QColor("#444"))
            p.drawText(12, y + h - 4, lbl)
            w = (self.width() - 150) * v / mx
            path = QPainterPath()
            path.addRoundedRect(QRectF(80, y, max(w, 3), h), 5, 5)
            p.fillPath(path, QColor(col))
            p.setPen(QColor("#1e2233"))
            p.drawText(int(80 + max(w, 3) + 6), y + h - 4, str(v))
            y += h + 6
        p.end()


class FolderPicker(QGroupBox):
    def __init__(self, title):
        super().__init__(title)
        lay = QHBoxLayout(self)
        self.lst = QListWidget()
        self.lst.setMaximumHeight(90)
        self.lst.setToolTip("Folders to scan. System folders are always skipped.")
        lay.addWidget(self.lst, 1)
        col = QVBoxLayout()
        b1, b2 = QPushButton("+ Add folder"), QPushButton("Remove")
        b2.setObjectName("ghost")
        b1.clicked.connect(self.add)
        b2.clicked.connect(self.remove)
        col.addWidget(b1)
        col.addWidget(b2)
        lay.addLayout(col)

    def add(self):
        d = QFileDialog.getExistingDirectory(self, "Choose a folder to scan")
        if d and d not in self.folders():
            self.lst.addItem(os.path.normpath(d))

    def remove(self):
        for it in self.lst.selectedItems():
            self.lst.takeItem(self.lst.row(it))

    def folders(self):
        return [self.lst.item(i).text() for i in range(self.lst.count())]


def make_table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    return t


# ----------------------------------------------------------------------------------------------
# 8. REVIEW PANEL (shared by "Review & Decide" and "Consent Revocation"), PREVIEW, MAIN WINDOW
# ----------------------------------------------------------------------------------------------
REASONS_KEEP = ["Legal / regulatory retention", "Ongoing contract or purpose", "Valid consent on record",
                "Legal hold / litigation", "Other (see notes)"]
REASONS_DELETE = ["Consent withdrawn", "Purpose served", "Retention period over", "Stray / duplicate copy",
                  "Other (see notes)"]
DEC_LABEL = {"pending": "Pending", "keep": "KEEP", "delete": "DELETE", "done": "Deleted (quarantined)"}
DEC_COLOR = {"pending": "#868e96", "keep": "#2f9e44", "delete": "#e8590c", "done": "#c92a2a"}
RISK_COLOR = {"High": "#e03131", "Medium": "#f08c00", "Low": "#2f9e44", "Match": "#5b4bdb"}


def open_file(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def explorer_select_cmd(path):
    """Command line that opens Explorer with the file selected. The quotes must wrap only the path:
    passing "/select,<path>" as ONE quoted argument (what a list-form Popen does when the path has spaces) fails."""
    return 'explorer /select,"%s"' % os.path.normpath(path)


def open_folder(path):
    """Open the folder holding `path` (file selected when possible). Falls back to just opening the folder."""
    folder = os.path.dirname(os.path.normpath(path))
    try:
        if os.name == "nt":
            if os.path.exists(path):
                subprocess.Popen(explorer_select_cmd(path))
                return
            os.startfile(folder)                         # file gone/moved: open its folder
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
    except Exception:
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        except Exception:
            pass


class PreviewDialog(QDialog):
    def __init__(self, parent, item, text):
        super().__init__(parent)
        self.setWindowTitle("Review file before deciding")
        self.resize(860, 600)
        v = QVBoxLayout(self)
        head = QLabel("<b>%s</b><br>%s &nbsp;|&nbsp; Owner: %s &nbsp;|&nbsp; %s" % (
            html.escape(item["path"]), html.escape(item["location"]), html.escape(item["owner"]),
            human(item["size"])))
        head.setWordWrap(True)
        head.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(text)
        row = QHBoxLayout()
        b1, b2, b3 = QPushButton("Open file"), QPushButton("Open containing folder"), QPushButton("Close")
        b2.setObjectName("ghost")
        b3.setObjectName("ghost")
        b1.clicked.connect(lambda: open_file(item["path"]))
        b2.clicked.connect(lambda: open_folder(item["path"]))
        b3.clicked.connect(self.accept)
        for b in (b1, b2):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(b3)
        v.addWidget(head)
        v.addWidget(box, 1)
        v.addLayout(row)


class ReviewPanel(QWidget):
    """Table of files with Keep / Delete decisions, masked preview, quarantine, undo and permanent erase."""
    changed = pyqtSignal()

    def __init__(self, win, mode):
        super().__init__()
        self.win, self.mode, self.items = win, mode, []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        fr = QHBoxLayout()
        self.f_risk = QComboBox()
        self.f_risk.addItems(["All risks", "High", "Medium", "Low"])
        self.f_risk.setVisible(mode == "pii")
        self.f_loc = QComboBox()
        self.f_loc.addItem("All locations")
        self.f_dec = QComboBox()
        self.f_dec.addItems(["All decisions", "Pending", "KEEP", "DELETE", "Deleted (quarantined)"])
        self.f_txt = QLineEdit()
        self.f_txt.setPlaceholderText("Filter by file name or path")
        self.f_copy = QCheckBox("Has copies elsewhere")
        for w in (self.f_risk, self.f_loc, self.f_dec):
            w.currentIndexChanged.connect(self.refresh)
            fr.addWidget(w)
        self.f_txt.textChanged.connect(self.refresh)
        self.f_copy.stateChanged.connect(self.refresh)
        fr.addWidget(self.f_txt, 1)
        fr.addWidget(self.f_copy)
        v.addLayout(fr)
        self.table = make_table(["Decision", "Risk" if mode == "pii" else "Result", "File", "Location", "Owner",
                                 "Findings", "Copies", "Reason"])
        self.table.setSortingEnabled(True)
        for ci, wd in enumerate((120, 80, 380, 160, 140, 220, 70)):
            self.table.setColumnWidth(ci, wd)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.table.cellDoubleClicked.connect(lambda *_: self.preview())
        v.addWidget(self.table, 1)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(84)
        self.detail.setPlaceholderText("Select a file to read the remark and suggested action. Double-click to preview.")
        v.addWidget(self.detail)
        self.count = QLabel("")
        v.addWidget(self.count)
        r1 = QHBoxLayout()
        for txt, obj, fn in (("🔍 Preview (masked)", None, self.preview), ("Open file", "ghost", self.open_sel),
                             ("Open folder", "ghost", self.open_dir)):
            b = QPushButton(txt)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            r1.addWidget(b)
        r1.addStretch(1)
        v.addLayout(r1)
        r2 = QHBoxLayout()
        self.c_keep = QComboBox()
        self.c_keep.addItems(REASONS_KEEP)
        self.c_del = QComboBox()
        self.c_del.addItems(REASONS_DELETE)
        if mode == "consent":
            self.c_del.setCurrentIndex(0)
        bk, bd, br = QPushButton("Mark KEEP"), QPushButton("Mark DELETE"), QPushButton("Reset")
        bk.setObjectName("good")
        bd.setObjectName("danger")
        br.setObjectName("ghost")
        bk.clicked.connect(lambda: self.set_decision("keep"))
        bd.clicked.connect(lambda: self.set_decision("delete"))
        br.clicked.connect(lambda: self.set_decision("pending"))
        for w in (QLabel("Keep reason:"), self.c_keep, bk, QLabel("Delete reason:"), self.c_del, bd, br):
            r2.addWidget(w)
        r2.addStretch(1)
        v.addLayout(r2)
        r3 = QHBoxLayout()
        self.chk_dry = QCheckBox("Dry-run (simulate only)")
        self.chk_dry.setChecked(True)
        self.chk_copies = QCheckBox("Include identical copies")
        self.chk_copies.setToolTip("Also move other flagged files with the same SHA-256 (exact copies at other paths).")
        ex = QPushButton("🗑 Move DELETE files to quarantine")
        ex.setObjectName("danger")
        ex.clicked.connect(self.execute)
        un = QPushButton("↩ Undo last quarantine")
        un.setObjectName("ghost")
        un.clicked.connect(self.undo)
        em = QPushButton("Erase quarantine permanently…")
        em.setObjectName("ghost")
        em.clicked.connect(self.empty_q)
        xp = QPushButton("Export decision register")
        xp.setObjectName("ghost")
        xp.clicked.connect(self.export)
        for w in (self.chk_dry, self.chk_copies, ex, un, em, xp):
            r3.addWidget(w)
        r3.addStretch(1)
        v.addLayout(r3)

    # ---- data ----
    def set_items(self, items):
        reg = load_decisions()
        for i, it in enumerate(items):
            d = reg.get(it["path"])
            it["_i"] = i
            ok = d and d.get("decision") in ("keep", "delete") and os.path.exists(it["path"])
            it["decision"] = d["decision"] if ok else "pending"
            it["reason"] = d.get("reason", "") if ok else ""
        self.items = items
        cur = self.f_loc.currentText()
        self.f_loc.blockSignals(True)
        self.f_loc.clear()
        self.f_loc.addItem("All locations")
        self.f_loc.addItems(sorted({i["location"] for i in items}))
        k = self.f_loc.findText(cur)
        self.f_loc.setCurrentIndex(max(k, 0))
        self.f_loc.blockSignals(False)
        self.refresh()

    def _visible(self):
        out = []
        rk, loc, dec = self.f_risk.currentText(), self.f_loc.currentText(), self.f_dec.currentText()
        txt = self.f_txt.text().strip().lower()
        for it in self.items:
            if self.mode == "pii" and rk != "All risks" and it["risk"] != rk:
                continue
            if loc != "All locations" and it["location"] != loc:
                continue
            if dec != "All decisions" and DEC_LABEL[it["decision"]] != dec:
                continue
            if txt and txt not in it["path"].lower():
                continue
            if self.f_copy.isChecked() and not it.get("copies"):
                continue
            out.append(it)
        return out

    def refresh(self):
        t = self.table
        t.setSortingEnabled(False)
        vis = self._visible()
        t.setRowCount(len(vis))
        for r, it in enumerate(vis):
            d = QTableWidgetItem(DEC_LABEL[it["decision"]])
            d.setBackground(QColor(DEC_COLOR[it["decision"]]))
            d.setForeground(QColor("white"))
            d.setTextAlignment(Qt.AlignCenter)
            d.setData(Qt.UserRole, it["_i"])
            rk = QTableWidgetItem(it["risk"])
            rk.setBackground(QColor(RISK_COLOR.get(it["risk"], "#999")))
            rk.setForeground(QColor("white"))
            rk.setTextAlignment(Qt.AlignCenter)
            cp = QTableWidgetItem()
            cp.setData(Qt.DisplayRole, it.get("copies", 0))
            cp.setTextAlignment(Qt.AlignCenter)
            vals = [d, rk, QTableWidgetItem(it["path"]), QTableWidgetItem("%s (%s)" % (it["location"], it["loc_type"])),
                    QTableWidgetItem(it["owner"]), QTableWidgetItem(it["summary"]), cp, QTableWidgetItem(it["reason"])]
            for c, w in enumerate(vals):
                t.setItem(r, c, w)
        t.setSortingEnabled(True)
        n = {k: sum(1 for i in self.items if i["decision"] == k) for k in DEC_LABEL}
        self.count.setText("%d of %d files shown  |  Pending %d  ·  Keep %d  ·  Delete %d  ·  Quarantined %d" % (
            len(vis), len(self.items), n["pending"], n["keep"], n["delete"], n["done"]))
        self.changed.emit()

    def selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        out = []
        for r in rows:
            it = self.table.item(r, 0)
            if it is not None:
                out.append(self.items[it.data(Qt.UserRole)])
        return out

    def show_detail(self):
        s = self.selected()
        if s:
            it = s[0]
            self.detail.setPlainText("REMARKS: %s\n\nSUGGESTED ACTION: %s" % (it["remark"], it["action"]))

    # ---- review actions ----
    def _one(self):
        s = self.selected()
        if not s:
            QMessageBox.information(self, "Select a file", "Select a file in the table first.")
            return None
        return s[0]

    def preview(self):
        it = self._one()
        if it:
            self.win.preview_item(it, self.mode)

    def open_sel(self):
        it = self._one()
        if it:
            open_file(it["path"])

    def open_dir(self):
        it = self._one()
        if it:
            open_folder(it["path"])

    def set_decision(self, dec):
        sel = [i for i in self.selected() if i["decision"] != "done"]
        if not sel:
            QMessageBox.information(self, "Select files", "Select one or more files first.")
            return
        reason = self.c_keep.currentText() if dec == "keep" else self.c_del.currentText() if dec == "delete" else ""
        case = self.win.case_id() if self.mode == "consent" else ""
        upd = {}
        for it in sel:
            it["decision"], it["reason"] = dec, reason
            upd[it["path"]] = {"decision": dec, "reason": reason, "case": case}
        save_decisions(upd)
        audit("DECISION_" + dec.upper(), reason + (" | case " + case if case else ""), "", len(sel))
        self.refresh()

    # ---- delete workflow ----
    def execute(self):
        if not self.win.licensed():
            return
        todo = [i for i in self.items if i["decision"] == "delete"]
        if not todo:
            QMessageBox.information(self, "Nothing to do", "No file is marked DELETE. Review files and mark your decision first.")
            return
        extra = []
        if self.chk_copies.isChecked():
            reasons = {i["hash"]: i["reason"] for i in todo if i["hash"]}
            extra = [i for i in self.items if i["decision"] == "pending" and i["hash"] in reasons]
        dry = self.chk_dry.isChecked()
        total = sum(i["size"] for i in todo + extra)
        txt = ("%d file(s) marked DELETE%s will be moved to the quarantine folder (recoverable).\nSize: %s\n\n"
               "Mode: %s\n\nKEEP files are never touched. Each file is re-verified by SHA-256 first.") % (
            len(todo), (" plus %d identical copy(ies)" % len(extra)) if extra else "", human(total),
            "DRY-RUN (simulation only)" if dry else "LIVE - files will be moved")
        if QMessageBox.question(self, "Confirm quarantine", txt, QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        reasons = {i["hash"]: i["reason"] for i in todo if i["hash"]}
        for it in extra:
            it["decision"], it["reason"] = "delete", reasons.get(it["hash"], "Stray / duplicate copy")
        todo += extra
        case = self.win.case_id() if self.mode == "consent" else ""
        qdir = self.win.cfg["qdir"]
        batch = os.path.join(qdir, "batch_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        manifest, done, skipped = [], 0, []
        dlg = QProgressDialog("Working...", "Cancel", 0, len(todo), self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        for idx, it in enumerate(todo):
            dlg.setValue(idx)
            QApplication.processEvents()
            if dlg.wasCanceled():
                break
            p = it["path"]
            if not os.path.isfile(p) or os.path.islink(p) or is_protected(p):
                skipped.append((p, "missing, link or protected path"))
                continue
            if it.get("hash") and hash_file(p) != it["hash"]:
                skipped.append((p, "file changed since the scan"))
                continue
            if dry:
                audit("DELETE_DRYRUN", it["reason"] + (" | case " + case if case else ""), p, 1, it["size"])
                done += 1
                continue
            try:
                stored = do_quarantine(p, batch, idx)
                manifest.append({"orig": p, "stored": stored, "hash": it.get("hash", ""), "size": it["size"],
                                 "case": case, "reason": it["reason"]})
                audit("DELETE_QUARANTINE", it["reason"] + (" | case " + case if case else ""), p, 1, it["size"])
                it["decision"] = "done"
                done += 1
            except Exception as e:
                skipped.append((p, str(e)))
        dlg.setValue(len(todo))
        if manifest:
            with open(os.path.join(batch, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=1)
        self.refresh()
        self.win.refresh_audit()
        msg = "%s %d file(s).%s" % ("Simulated" if dry else "Moved to quarantine:", done,
                                    ("\n\nSkipped %d:\n" % len(skipped) +
                                     "\n".join("• %s: %s" % (os.path.basename(a), b) for a, b in skipped[:6]))
                                    if skipped else "")
        QMessageBox.information(self, "Result", msg)

    def undo(self):
        ok, sk, b = undo_last_quarantine(self.win.cfg["qdir"])
        if b is None:
            QMessageBox.information(self, "Undo", "No quarantine batch available to restore.")
            return
        upd = {}
        for it in self.items:
            if it["decision"] == "done" and os.path.exists(it["path"]):
                it["decision"], it["reason"] = "pending", ""
                upd[it["path"]] = {"decision": "pending", "reason": "", "case": ""}
        if upd:
            save_decisions(upd)
        audit("DELETE_UNDO", b, "", ok)
        self.win.refresh_audit()
        self.refresh()
        QMessageBox.information(self, "Undo", "Restored %d file(s) from %s. Skipped %d." % (ok, b, sk))

    def empty_q(self):
        n, sz = quarantine_stats(self.win.cfg["qdir"])
        if n == 0:
            QMessageBox.information(self, "Quarantine", "The quarantine folder is empty.")
            return
        text, ok = QInputDialog.getText(
            self, "Erase permanently",
            "This PERMANENTLY deletes %d file(s) (%s) held in quarantine. It cannot be undone and files cannot be "
            "restored afterwards.\n\nType DELETE to confirm:" % (n, human(sz)))
        if not ok or text.strip() != "DELETE":
            QMessageBox.information(self, "Cancelled", "Nothing was deleted.")
            return
        n, sz = empty_quarantine(self.win.cfg["qdir"])
        audit("QUARANTINE_ERASED", "permanent", self.win.cfg["qdir"], n, sz)
        self.win.refresh_audit()
        QMessageBox.information(self, "Erased", "Permanently erased %d file(s), %s." % (n, human(sz)))

    def export(self):
        if not self.items:
            QMessageBox.information(self, "Nothing to export", "Run a scan or search first.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save decision register", "decision_register.csv", "CSV (*.csv)")
        if not fn:
            return
        reg = load_decisions()
        with open(fn, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Risk/Result", "Path", "Location", "Storage type", "Owner", "Findings (counts only)",
                        "Identical copies", "SHA-256", "Decision", "Reason", "Decided by", "Decided at"])
            for it in self.items:
                d = reg.get(it["path"], {})
                w.writerow([it["risk"], csv_safe(it["path"]), csv_safe(it["location"]), it["loc_type"],
                            csv_safe(it["owner"]), it["summary"], it.get("copies", 0), it.get("hash", ""),
                            DEC_LABEL[it["decision"]], csv_safe(it["reason"]), d.get("by", ""), d.get("when", "")])
        audit("REGISTER_EXPORT", fn, "", len(self.items))
        self.win.statusBar().showMessage("Decision register saved: " + fn)


# ----------------------------------------------------------------------------------------------
# 9. MAIN WINDOW
# ----------------------------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.theme = THEMES.get(cfg["theme"], THEMES["Indigo Pulse"])
        last = _read_json(LAST_SCAN_FILE, None)
        self.result = last if isinstance(last, dict) and "findings" in last else {"findings": [], "stats": {}, "folders": []}
        self.search_result = {"hits": [], "stats": {}}
        self.thread = None
        self.case = None
        self.last_rx = []
        self.resize(1320, 860)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(16, 14, 16, 8)
        hdr = QFrame()
        hdr.setObjectName("header")
        hl = QVBoxLayout(hdr)
        self.h_title = QLabel()
        self.h_title.setObjectName("hTitle")
        sub = QLabel("Discover personal data  •  Map where it lives  •  Review, keep or delete  •  Trace consent "
                     "withdrawals  •  100% offline")
        sub.setObjectName("hSub")
        self.lic_pill = QLabel()
        self.lic_pill.setAlignment(Qt.AlignCenter)
        trow = QHBoxLayout()
        trow.addWidget(self.h_title)
        trow.addStretch(1)
        trow.addWidget(self.lic_pill)
        hl.addLayout(trow)
        hl.addWidget(sub)
        v.addWidget(hdr)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self._build_dashboard()
        self._build_map()
        self._build_review()
        self._build_consent()
        self._build_audit()
        self._build_settings()
        self.statusBar().showMessage("Ready. Add storage locations, then scan. Nothing is deleted without your decision and confirmation.")
        self.apply_name()
        self.apply_theme()
        self.review.set_items(self.result["findings"])
        if self.result["folders"]:
            self.fill_map_tree()
        self.refresh_all()

    # ---- naming, theming, licence ----
    def update_pill(self, st=None):
        st = st or LICENSE.status()
        col = {"trial": "#F59F00", "licensed": "#12B886"}.get(st["state"], "#E03131")
        short = {"trial": "TRIAL - %d day(s) left" % st["days_left"], "licensed": "LICENSED - %d day(s) left" % st["days_left"],
                 "expired": "LICENCE EXPIRED", "tampered": "CHECK SYSTEM DATE", "none": "NOT ACTIVATED"}[st["state"]]
        self.lic_pill.setText(short)
        self.lic_pill.setStyleSheet("background:%s;color:white;font-weight:700;border-radius:12px;padding:6px 16px;" % col)
        if hasattr(self, "s_lic"):
            self.s_lic.setText(st["text"])

    def licensed(self):
        st = LICENSE.status()
        self.update_pill(st)
        if st["state"] in ("trial", "licensed"):
            return True
        LicenseDialog(self).exec_()
        st = LICENSE.status()
        self.update_pill(st)
        return st["state"] in ("trial", "licensed")

    def apply_name(self):
        n = self.cfg["app_name"]
        self.setWindowTitle("%s  -  DPDP personal-data discovery" % n)
        self.h_title.setText("🔎  " + n)
        PWA["name"] = n

    def apply_theme(self):
        self.theme = THEMES.get(self.cfg["theme"], THEMES["Indigo Pulse"])
        QApplication.instance().setStyleSheet(make_qss(self.theme))
        PWA["theme"] = self.theme
        PWA["icons"] = {"/icon-192.png": make_icon_png(self.cfg["app_name"], self.theme, 192),
                        "/icon-512.png": make_icon_png(self.cfg["app_name"], self.theme, 512)}
        if hasattr(self, "kpis"):
            self._recolor()
            self.refresh_all()

    def case_id(self):
        return self.case["case"] if self.case else ""

    # ---- dashboard ----
    def _build_dashboard(self):
        w = QWidget()
        v = QVBoxLayout(w)
        grid = QGridLayout()
        names = [("Locations mapped", "p"), ("Files scanned", "s"), ("Files with personal data", "g"),
                 ("High-risk files", "w"), ("Decisions pending", "a")]
        self.kpis = {}
        for i, (n, ck) in enumerate(names):
            c = KpiCard(n, self.theme[ck])
            c.ck = ck
            self.kpis[n] = c
            grid.addWidget(c, 0, i)
        v.addLayout(grid)
        row = QHBoxLayout()
        self.donut = DonutChart("Files with personal data by storage type")
        self.bars = BarChart("Personal data found by identifier")
        row.addWidget(self.donut, 1)
        row.addWidget(self.bars, 1)
        v.addLayout(row)
        g = QGroupBox("Recent activity")
        gl = QVBoxLayout(g)
        self.act = make_table(["Time", "Action", "Detail"])
        self.act.setMaximumHeight(180)
        gl.addWidget(self.act)
        v.addWidget(g)
        self.tabs.addTab(w, "🏠  Dashboard")

    def _recolor(self):
        for c in self.kpis.values():
            c.setStyleSheet("QFrame{background:%s;border-radius:14px;} QLabel{background:transparent;color:white;}" % self.theme[c.ck])

    def refresh_all(self):
        T = self.theme
        ps = self.result.get("stats", {})
        locs = ps.get("locations", {})
        self.kpis["Locations mapped"].set(len(locs))
        self.kpis["Files scanned"].set(ps.get("scanned", 0))
        self.kpis["Files with personal data"].set(ps.get("flagged", 0))
        self.kpis["High-risk files"].set(ps.get("risk", {}).get("High", 0))
        self.kpis["Decisions pending"].set(self.pending_count())
        by_type = {}
        for l in locs.values():
            by_type[l["type"]] = by_type.get(l["type"], 0) + l.get("flagged", 0)
        cols = [T["p"], T["s"], T["a"], T["w"], T["g"]]
        parts = [(k, v, cols[i % 5]) for i, (k, v) in enumerate(sorted(by_type.items()))]
        self.donut.set(parts, str(ps.get("flagged", 0)))
        tt = ps.get("totals", {})
        self.bars.set([(k, tt.get(k, 0), T[PII_COLOR_KEY[k]]) for k in PII_TYPES])
        rows = read_audit(8)
        self.act.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, val in enumerate(r[:3]):
                self.act.setItem(i, j, QTableWidgetItem(val))
        self.act.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.act.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.publish()

    def pending_count(self):
        return sum(1 for i in self.review.items if i["decision"] == "pending") if hasattr(self, "review") else 0

    def publish(self):
        ps = self.result.get("stats", {})
        dec = {k: v for k, v in DEC_LABEL.items()}
        files = [{"risk": f["risk"], "path": f["path"], "location": f["location"], "owner": f["owner"],
                  "summary": f["summary"], "copies": f.get("copies", 0),
                  "decision": dec.get(f.get("decision", "pending"), "Pending")} for f in self.review.items[:40]] \
            if hasattr(self, "review") else []
        cases = []
        for c in _read_json(CASES_FILE, [])[-10:][::-1]:
            cases.append({"case": c.get("case", ""), "date": c.get("date", ""), "hits": c.get("hits", 0),
                          "deleted": c.get("deleted", 0), "kept": c.get("kept", 0)})
        state = {
            "app_name": self.cfg["app_name"], "colors": self.theme,
            "updated": datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
            "stats": ps, "pending": self.pending_count(),
            "locations": [{"label": k, "type": v["type"], "scanned": v["scanned"], "flagged": v["flagged"],
                           "high": v["high"]} for k, v in ps.get("locations", {}).items()],
            "files": files, "cases": cases,
            "activity": [[r[0], r[2], r[3]] for r in read_audit(10)],
        }
        PWA["state"] = json.dumps(state).encode("utf-8")

    # ---- shared scan control ----
    def _start(self, kind, fn, cfg, widgets):
        if not self.licensed():
            return
        if self.thread and self.thread.isRunning():
            QMessageBox.information(self, "Busy", "A scan is already running.")
            return
        if not cfg["locations"]:
            QMessageBox.warning(self, "No locations", "Add at least one storage location in the Storage Map tab first.")
            return
        bad = [l["path"] for l in cfg["locations"] if not os.path.isdir(l["path"])]
        if bad:
            QMessageBox.warning(self, "Location not found", "Not reachable:\n" + "\n".join(bad))
            return
        if any(is_protected(l["path"]) for l in cfg["locations"]):
            QMessageBox.warning(self, "Protected folder", "System folders cannot be scanned. Remove them and retry.")
            return
        self.cur = widgets
        widgets["start"].setEnabled(False)
        widgets["stop"].setEnabled(True)
        widgets["bar"].setValue(0)
        audit("%s_START" % kind, "Locations: %s" % "; ".join(l["path"] for l in cfg["locations"]))
        self.thread = ScanThread(fn, cfg)
        self.thread.progress.connect(lambda m, p, w=widgets: (w["msg"].setText(m), w["bar"].setValue(p)))
        self.thread.finished_ok.connect(lambda res, k=kind: self._finished(k, res))
        self.thread.start()

    def _stop(self):
        if self.thread:
            self.thread.cancel.set()
            self.statusBar().showMessage("Stopping...")

    def _finished(self, kind, res):
        w = self.cur
        w["start"].setEnabled(True)
        w["stop"].setEnabled(False)
        if res is None:
            w["msg"].setText("Cancelled.")
            audit("%s_CANCELLED" % kind)
            return
        if "error" in res:
            w["msg"].setText("Error: " + res["error"])
            QMessageBox.critical(self, "Error", res["error"])
            return
        w["bar"].setValue(100)
        if kind == "SCAN":
            self.result = res
            _write_json(LAST_SCAN_FILE, res)
            s = res["stats"]
            audit("SCAN_DONE", "scanned=%d flagged=%d locations=%d" % (s["scanned"], s["flagged"], len(s["locations"])),
                  "", s["flagged"])
            self.review.set_items(res["findings"])
            self.fill_map_tree()
            self.fill_scan_msg()
        else:
            self.search_result = res
            s = res["stats"]
            audit("CONSENT_SEARCH_DONE", "case=%s files=%d hits=%d" % (self.case_id(), s["scanned"], s["hits"]), "", s["hits"])
            self.consent.set_items(res["hits"])
            if self.case:
                self.case["hits"] = s["hits"]
                self.save_case()
            self.msg_c.setText("%d files searched | %d file(s) mention the data principal | %.1fs" % (
                s["scanned"], s["hits"], s["elapsed"]))
        self.refresh_all()
        self.refresh_audit()
        self.statusBar().showMessage("%s completed." % kind.title())

    def _scan_cfg(self):
        return {"locations": self.locations(), "max_mb": self.dp_max.value(), "extras": self.dp_extras.isChecked(),
                "aadhaar_mode": self.dp_aadhaar.currentText(), "ocr": self.dp_ocr.isChecked(),
                "skip_hidden": self.dp_hidden.isChecked(), "qdir": self.cfg["qdir"]}

    # ---- storage map tab ----
    def _build_map(self):
        w = QWidget()
        v = QVBoxLayout(w)
        g = QGroupBox("1) Storage locations to map (local folders, other drives, network shares, cloud-synced folders)")
        gl = QHBoxLayout(g)
        self.loc_table = QTableWidget(0, 3)
        self.loc_table.setHorizontalHeaderLabels(["Label (double-click to rename)", "Path", "Storage type"])
        self.loc_table.horizontalHeader().setStretchLastSection(True)
        self.loc_table.setColumnWidth(0, 230)
        self.loc_table.setColumnWidth(1, 520)
        self.loc_table.verticalHeader().setVisible(False)
        self.loc_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.loc_table.setMaximumHeight(150)
        gl.addWidget(self.loc_table, 1)
        col = QVBoxLayout()
        for txt, obj, fn in (("+ Add folder", None, self.add_folder), ("+ Network path", "ghost", self.add_network),
                             ("+ My Documents / Desktop / Downloads", "ghost", self.add_common),
                             ("Remove", "ghost", self.remove_loc)):
            b = QPushButton(txt)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            col.addWidget(b)
        gl.addLayout(col)
        v.addWidget(g)
        og = QGroupBox("2) Scan options")
        ol = QHBoxLayout(og)
        self.dp_aadhaar = QComboBox()
        self.dp_aadhaar.addItems(AADHAAR_MODES)
        self.dp_aadhaar.setToolTip("Standard: valid checksum = Aadhaar; 12 digits near the word Aadhaar = 'Aadhaar?'.\n"
                                   "Strict: checksum only. Loose: every 12-digit number is flagged (use for UAT with dummy numbers).")
        self.dp_max = QSpinBox()
        self.dp_max.setRange(1, 500)
        self.dp_max.setValue(25)
        self.dp_max.setSuffix(" MB max read per file")
        self.dp_ocr = QCheckBox("Read images && scanned PDFs (OCR, slower)")
        self.dp_ocr.setChecked(ocr_available())
        self.dp_ocr.setEnabled(ocr_available())
        self.dp_ocr.setToolTip("Reads text from photos, scanned PDFs and pictures inside Office files. Fully offline."
                               if ocr_available() else "OCR engine not installed. Run: python -m pip install rapidocr-onnxruntime")
        self.dp_extras = QCheckBox("Also mobile numbers && e-mails")
        self.dp_hidden = QCheckBox("Skip hidden")
        self.dp_hidden.setChecked(True)
        ol.addWidget(QLabel("Aadhaar:"))
        for wd in (self.dp_aadhaar, self.dp_max, self.dp_ocr, self.dp_extras, self.dp_hidden):
            ol.addWidget(wd)
        ol.addStretch(1)
        v.addWidget(og)
        bl = QHBoxLayout()
        self.dp_start = QPushButton("▶  Scan and map")
        self.dp_stop = QPushButton("■  Stop")
        self.dp_stop.setObjectName("danger")
        self.dp_stop.setEnabled(False)
        self.dp_start.clicked.connect(lambda: self._start("SCAN", run_dpdp, self._scan_cfg(), self.map_widgets))
        self.dp_stop.clicked.connect(self._stop)
        ex = QPushButton("Export storage map CSV")
        ex.setObjectName("ghost")
        ex.clicked.connect(self.export_map)
        bl.addWidget(self.dp_start)
        bl.addWidget(self.dp_stop)
        bl.addStretch(1)
        bl.addWidget(ex)
        v.addLayout(bl)
        self.dp_bar = QProgressBar()
        self.dp_msg = QLabel("Zero-PII storage: only path, owner, size and counts are kept, never the personal data itself.")
        self.dp_msg.setWordWrap(True)
        v.addWidget(self.dp_bar)
        v.addWidget(self.dp_msg)
        self.map_tree = QTreeWidget()
        self.map_tree.setColumnCount(9)
        self.map_tree.setHeaderLabels(["Location / folder", "Files scanned", "With personal data", "High risk",
                                       "Aadhaar", "PAN", "Card", "Other", "Size"])
        self.map_tree.setAlternatingRowColors(True)
        self.map_tree.setColumnWidth(0, 470)
        for ci in (1, 2, 3):
            self.map_tree.setColumnWidth(ci, 125)
        v.addWidget(self.map_tree, 1)
        self.map_widgets = {"start": self.dp_start, "stop": self.dp_stop, "bar": self.dp_bar, "msg": self.dp_msg}
        self.tabs.addTab(w, "🗺  Storage Map")

    def add_location(self, path, label=None):
        path = os.path.normpath(path)
        if any(l["path"].lower() == path.lower() for l in self._loc_rows()):
            return
        label = label or (os.path.basename(path) or path)
        r = self.loc_table.rowCount()
        self.loc_table.insertRow(r)
        self.loc_table.setItem(r, 0, QTableWidgetItem(label))
        p = QTableWidgetItem(path)
        p.setFlags(p.flags() & ~Qt.ItemIsEditable)
        t = QTableWidgetItem(classify_location(path))
        t.setFlags(t.flags() & ~Qt.ItemIsEditable)
        self.loc_table.setItem(r, 1, p)
        self.loc_table.setItem(r, 2, t)

    def _loc_rows(self):
        return [{"label": self.loc_table.item(r, 0).text().strip(), "path": self.loc_table.item(r, 1).text()}
                for r in range(self.loc_table.rowCount())]

    def locations(self):
        out, used = [], set()
        for l in self._loc_rows():
            lab = l["label"] or l["path"]
            base, n = lab, 2
            while lab in used:
                lab = "%s (%d)" % (base, n)
                n += 1
            used.add(lab)
            out.append({"label": lab, "path": l["path"]})
        return out

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose a folder, drive or share to map")
        if d:
            self.add_location(d)

    def add_network(self):
        t, ok = QInputDialog.getText(self, "Network path", "Enter a UNC path or mapped drive, e.g. \\\\server\\share\\HR")
        if ok and t.strip():
            if os.path.isdir(t.strip()):
                self.add_location(t.strip())
            else:
                QMessageBox.warning(self, "Not reachable", "That path could not be opened. Check it and your permissions.")

    def add_common(self):
        home = os.path.expanduser("~")
        for n in ("Documents", "Desktop", "Downloads"):
            p = os.path.join(home, n)
            if os.path.isdir(p):
                self.add_location(p, "My " + n)

    def remove_loc(self):
        for r in sorted({i.row() for i in self.loc_table.selectedIndexes()}, reverse=True):
            self.loc_table.removeRow(r)

    def fill_scan_msg(self):
        s = self.result["stats"]
        extra = ""
        if s.get("unsupported"):
            extra += " | NOT scanned (unsupported): " + ", ".join("%s x%d" % kv for kv in s["unsupported"].items())
        if s.get("ocr_files"):
            extra += " | OCR read %d file(s)" % s["ocr_files"]
        if s.get("no_text"):
            extra += " | %d file(s) had no readable text" % s["no_text"]
        if s.get("partial"):
            extra += " | %d large file(s) read only in part (raise the MB limit)" % s["partial"]
        if s.get("skipped"):
            extra += " | %d very large file(s) skipped" % s["skipped"]
        self.dp_msg.setText("%d files scanned | %d with personal data (High %d, Medium %d, Low %d) | %.1fs | errors %d%s" % (
            s["scanned"], s["flagged"], s["risk"]["High"], s["risk"]["Medium"], s["risk"]["Low"], s["elapsed"],
            s["errors"], extra))

    def fill_map_tree(self):
        tr = self.map_tree
        tr.clear()
        other = ("PAN", "Card")
        stats = self.result.get("stats", {}).get("locations", {})
        by_loc = {}
        for f in self.result.get("folders", []):
            by_loc.setdefault(f["location"], []).append(f)

        def row(label, files, flagged, high, counts, size):
            o = sum(v for k, v in counts.items() if k not in ("Aadhaar", "PAN", "Card"))
            it = QTreeWidgetItem([label, str(files), str(flagged), str(high), str(counts.get("Aadhaar", 0)),
                                  str(counts.get("PAN", 0)), str(counts.get("Card", 0)), str(o), human(size)])
            if high:
                it.setForeground(3, QColor("#e03131"))
            elif flagged:
                it.setForeground(2, QColor("#e8890c"))
            return it

        def agg(items, prefix):
            files = flagged = high = size = 0
            counts = dict.fromkeys(PII_TYPES, 0)
            for f in items:
                k = f["folder"]
                if k == prefix or (prefix == "" ) or k.startswith(prefix + os.sep):
                    files += f["files"]
                    flagged += f["flagged"]
                    high += f["high"]
                    size += f["size"]
                    for c, n in f["counts"].items():
                        counts[c] += n
            return files, flagged, high, counts, size

        for label, items in by_loc.items():
            ls = stats.get(label, {})
            top = row("%s  [%s]  %s" % (label, ls.get("type", ""), ls.get("path", "")), *agg(items, ""))
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            tr.addTopLevelItem(top)
            nodes = {}
            for key in sorted({f["folder"] for f in items if f["folder"]}):
                parts = key.split(os.sep)
                for i in range(1, len(parts) + 1):
                    pk = os.sep.join(parts[:i])
                    if pk in nodes:
                        continue
                    node = row(parts[i - 1], *agg(items, pk))
                    (nodes[os.sep.join(parts[:i - 1])] if i > 1 else top).addChild(node)
                    nodes[pk] = node
            top.setExpanded(True)

    def export_map(self):
        if not self.result.get("folders"):
            QMessageBox.information(self, "Nothing to export", "Run a scan first.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save storage map", "storage_map.csv", "CSV (*.csv)")
        if not fn:
            return
        locs = self.result["stats"].get("locations", {})
        with open(fn, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Location", "Storage type", "Folder", "Files scanned", "With personal data", "High risk",
                        "Size bytes"] + PII_TYPES)
            for x in self.result["folders"]:
                w.writerow([csv_safe(x["location"]), locs.get(x["location"], {}).get("type", ""),
                            csv_safe(x["folder"] or "(top level)"), x["files"], x["flagged"], x["high"], x["size"]] +
                           [x["counts"][k] for k in PII_TYPES])
        audit("MAP_EXPORT", fn, "", len(self.result["folders"]))
        self.statusBar().showMessage("Storage map saved: " + fn)

    # ---- review tab ----
    def _build_review(self):
        w = QWidget()
        v = QVBoxLayout(w)
        info = QLabel("Review every flagged file, then mark it KEEP (with a lawful reason) or DELETE. DELETE moves the file to a "
                      "recoverable quarantine; permanent erasure is a separate, typed-confirmation step.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;")
        v.addWidget(info)
        self.review = ReviewPanel(self, "pii")
        self.review.changed.connect(lambda: hasattr(self, "kpis") and self.kpis["Decisions pending"].set(self.pending_count()))
        v.addWidget(self.review, 1)
        self.tabs.addTab(w, "✅  Review && Decide")

    def preview_item(self, item, mode):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ctx = {}
            try:
                text = extract_text(item["path"], 8 * 1024 * 1024, self.dp_ocr.isChecked(), ctx)
            except Exception as e:
                text = None
                err = str(e)
        finally:
            QApplication.restoreOverrideCursor()
        if text is None:
            body = "Could not read the file: %s" % err
        elif not text.strip():
            body = "No readable text. Use 'Open file' to view the original (images and scans need OCR)."
        elif mode == "consent" and self.last_rx:
            sn = context_snippets(text, self.last_rx)
            body = ("MATCHES IN CONTEXT  (searched value shown inside [[ ]]; other personal data is masked)\n\n" +
                    ("\n\n".join(sn) if sn else "No match text could be extracted. Use 'Open file'."))
        else:
            body = ("MASKED PREVIEW  (personal values are masked; first 6000 characters)\n\n" + mask_text(text[:6000]))
        audit("FILE_PREVIEW", mode, item["path"])
        PreviewDialog(self, item, body).exec_()

    # ---- consent revocation tab ----
    def _build_consent(self):
        w = QWidget()
        v = QVBoxLayout(w)
        top = QHBoxLayout()
        g1 = QGroupBox("Request details")
        f1 = QFormLayout(g1)
        self.c_ref = QLineEdit()
        self.c_ref.setPlaceholderText("Ticket / request number (do not type personal data here)")
        self.c_date = QDateEdit(QDate.currentDate())
        self.c_date.setCalendarPopup(True)
        self.c_date.setDisplayFormat("dd-MMM-yyyy")
        f1.addRow("Reference:", self.c_ref)
        f1.addRow("Request date:", self.c_date)
        note = QLabel("Searches every location in the Storage Map tab. Identifiers are kept in memory only; the case "
                      "register stores one-way fingerprints, never the identifiers themselves.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        f1.addRow(note)
        g2 = QGroupBox("Identifiers of the data principal who withdrew consent")
        f2 = QFormLayout(g2)
        self.c_in = {}
        for kind, ph in (("Name", "Full name"), ("Email", "name@example.com"), ("Mobile", "10-digit mobile"),
                         ("PAN", "ABCDE1234F"), ("Aadhaar", "12-digit number"), ("Other", "Customer ID, account no., ...")):
            e = QLineEdit()
            e.setPlaceholderText(ph)
            self.c_in[kind] = e
            f2.addRow(kind + ":", e)
        top.addWidget(g1, 1)
        top.addWidget(g2, 1)
        v.addLayout(top)
        bl = QHBoxLayout()
        self.c_start = QPushButton("🔎  Find all copies of this person’s data")
        self.c_stop = QPushButton("■  Stop")
        self.c_stop.setObjectName("danger")
        self.c_stop.setEnabled(False)
        self.c_start.clicked.connect(self.start_search)
        self.c_stop.clicked.connect(self._stop)
        xr = QPushButton("Export consent-revocation report")
        xr.setObjectName("ghost")
        xr.clicked.connect(self.export_case)
        bl.addWidget(self.c_start)
        bl.addWidget(self.c_stop)
        bl.addStretch(1)
        bl.addWidget(xr)
        v.addLayout(bl)
        self.bar_c = QProgressBar()
        self.msg_c = QLabel("Fill at least one identifier. A 10-digit mobile, 12-digit Aadhaar or valid e-mail is matched even "
                            "when written with spaces or hyphens.")
        self.msg_c.setWordWrap(True)
        v.addWidget(self.bar_c)
        v.addWidget(self.msg_c)
        self.consent = ReviewPanel(self, "consent")
        self.consent.changed.connect(self._consent_changed)
        v.addWidget(self.consent, 1)
        self.consent_widgets = {"start": self.c_start, "stop": self.c_stop, "bar": self.bar_c, "msg": self.msg_c}
        self.tabs.addTab(w, "↩  Consent Revocation")

    def save_case(self):
        if not self.case:
            return
        cases = _read_json(CASES_FILE, [])
        for i, c in enumerate(cases):
            if c.get("case") == self.case["case"]:
                cases[i] = self.case
                break
        else:
            cases.append(self.case)
        _write_json(CASES_FILE, cases)

    def _consent_changed(self):
        if self.case:
            it = self.consent.items
            self.case["kept"] = sum(1 for i in it if i["decision"] == "keep")
            self.case["deleted"] = sum(1 for i in it if i["decision"] == "done")
            self.save_case()

    def start_search(self):
        terms = []
        for kind, e in self.c_in.items():
            val = e.text().strip()
            if val:
                if term_regex(kind, val) is None:
                    QMessageBox.warning(self, "Check identifier", "The %s value is not valid for matching "
                                        "(Mobile = 10 digits, Aadhaar = 12 digits, E-mail needs @, Other = 3+ characters)." % kind)
                    return
                terms.append({"kind": kind, "value": val})
        if not terms:
            QMessageBox.information(self, "Identifier needed", "Enter at least one identifier of the data principal.")
            return
        now = datetime.now()
        self.case = {"case": "CR-" + now.strftime("%Y%m%d-%H%M%S"), "reference": self.c_ref.text().strip(),
                     "date": self.c_date.date().toString("yyyy-MM-dd"), "created": now.strftime("%Y-%m-%d %H:%M:%S"),
                     "by": getpass.getuser(), "fingerprints": [{"kind": t["kind"], "fp": term_fingerprint(t["value"], self.cfg["salt"])}
                                                               for t in terms], "hits": 0, "kept": 0, "deleted": 0}
        self.save_case()
        self.last_rx = [(t["kind"], term_regex(t["kind"], t["value"])) for t in terms]
        audit("CONSENT_CASE_OPENED", "%s | ref %s | identifiers: %s" % (self.case["case"], self.case["reference"],
                                                                       ", ".join(t["kind"] for t in terms)))
        cfg = self._scan_cfg()
        cfg["terms"] = terms
        self._start("SEARCH", run_search, cfg, self.consent_widgets)

    def export_case(self):
        if not self.case:
            QMessageBox.information(self, "No case", "Run a consent-revocation search first.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save report", "consent_revocation_%s.csv" % self.case["case"], "CSV (*.csv)")
        if not fn:
            return
        reg = load_decisions()
        c = self.case
        with open(fn, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Consent revocation report"])
            w.writerow(["Case ID", c["case"]])
            w.writerow(["Reference", csv_safe(c["reference"])])
            w.writerow(["Request date", c["date"]])
            w.writerow(["Handled by", c["by"]])
            w.writerow(["Identifier fingerprints (one-way)", "; ".join("%s:%s" % (x["kind"], x["fp"]) for x in c["fingerprints"])])
            w.writerow(["Locations searched", "; ".join("%s [%s]" % (k, v["type"]) for k, v in
                                                        self.search_result.get("stats", {}).get("locations", {}).items())])
            w.writerow(["Files found / kept / deleted", "%d / %d / %d" % (c["hits"], c["kept"], c["deleted"])])
            w.writerow([])
            w.writerow(["Path", "Location", "Storage type", "Owner", "Matches (counts)", "Identical copies", "Decision",
                        "Reason", "Decided by", "Decided at"])
            for it in self.consent.items:
                d = reg.get(it["path"], {})
                w.writerow([csv_safe(it["path"]), csv_safe(it["location"]), it["loc_type"], csv_safe(it["owner"]),
                            it["summary"], it.get("copies", 0), DEC_LABEL[it["decision"]], csv_safe(it["reason"]),
                            d.get("by", ""), d.get("when", "")])
        audit("CONSENT_REPORT_EXPORT", c["case"] + " | " + fn, "", c["hits"])
        self.statusBar().showMessage("Report saved: " + fn)

    # ---- audit tab ----
    def _build_audit(self):
        w = QWidget()
        v = QVBoxLayout(w)
        top = QHBoxLayout()
        b = QPushButton("Refresh")
        b.clicked.connect(self.refresh_audit)
        o = QPushButton("Open data folder")
        o.setObjectName("ghost")
        o.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(DATA_DIR)))
        top.addWidget(b)
        top.addWidget(o)
        top.addStretch(1)
        v.addLayout(top)
        self.audit_t = make_table(["Time", "User", "Action", "Detail", "Path", "Count", "Bytes"])
        v.addWidget(self.audit_t, 1)
        self.tabs.addTab(w, "📜  Audit Log")
        self.refresh_audit()

    def refresh_audit(self):
        rows = read_audit(500)
        self.audit_t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, val in enumerate(r[:7]):
                self.audit_t.setItem(i, j, QTableWidgetItem(val))
        self.audit_t.resizeColumnsToContents()
        if hasattr(self, "act"):
            self.publish()

    # ---- settings / PWA tab ----
    def _build_settings(self):
        w = QWidget()
        v = QVBoxLayout(w)
        g1 = QGroupBox("Application")
        f = QGridLayout(g1)
        self.s_name = QLineEdit(self.cfg["app_name"])
        self.s_name.setMaxLength(40)
        self.s_theme = QComboBox()
        self.s_theme.addItems(list(THEMES))
        self.s_theme.setCurrentText(self.cfg["theme"])
        self.s_q = QLineEdit(self.cfg["qdir"])
        qb = QPushButton("Browse")
        qb.setObjectName("ghost")
        qb.clicked.connect(self.pick_q)
        save = QPushButton("Save settings")
        save.setObjectName("good")
        save.clicked.connect(self.save_settings)
        f.addWidget(QLabel("Application name:"), 0, 0)
        f.addWidget(self.s_name, 0, 1, 1, 2)
        f.addWidget(QLabel("Colour theme:"), 1, 0)
        f.addWidget(self.s_theme, 1, 1, 1, 2)
        f.addWidget(QLabel("Quarantine folder:"), 2, 0)
        f.addWidget(self.s_q, 2, 1)
        f.addWidget(qb, 2, 2)
        f.addWidget(QLabel("Data folder:"), 3, 0)
        f.addWidget(QLabel(DATA_DIR), 3, 1, 1, 2)
        f.addWidget(save, 4, 1)
        v.addWidget(g1)
        gl = QGroupBox("Licence")
        ll = QHBoxLayout(gl)
        self.s_lic = QLabel("")
        self.s_lic.setStyleSheet("font-weight:600;")
        lb = QPushButton("Enter / change licence code")
        lb.clicked.connect(lambda: (LicenseDialog(self).exec_(), self.update_pill()))
        tb = QPushButton("Get free 7-day trial")
        tb.setObjectName("ghost")
        tb.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TRIAL_URL)))
        ll.addWidget(self.s_lic, 1)
        ll.addWidget(lb)
        ll.addWidget(tb)
        v.addWidget(gl)
        g2 = QGroupBox("Offline PWA console (hybrid architecture)")
        l2 = QVBoxLayout(g2)
        self.pwa_url = ""
        self.s_url = QLineEdit()
        self.s_url.setReadOnly(True)
        row = QHBoxLayout()
        ob = QPushButton("Open dashboard in browser")
        ob.clicked.connect(lambda: self.pwa_url and QDesktopServices.openUrl(QUrl(self.pwa_url)))
        cb = QPushButton("Copy link")
        cb.setObjectName("ghost")
        cb.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.pwa_url))
        self.s_pwa = QCheckBox("Enable local PWA server (takes effect on restart)")
        self.s_pwa.setChecked(self.cfg["pwa"])
        row.addWidget(ob)
        row.addWidget(cb)
        row.addStretch(1)
        l2.addWidget(self.s_url)
        l2.addLayout(row)
        l2.addWidget(self.s_pwa)
        how = QLabel("Open the link in Chrome or Edge and click the install icon in the address bar (or Menu → Install app). "
                     "The console opens like a native app and works offline from its cache, showing the latest snapshot. "
                     "The server listens on 127.0.0.1 only, is read-only and protected by a private token in the link.")
        how.setWordWrap(True)
        how.setStyleSheet("color:#555;")
        l2.addWidget(how)
        v.addWidget(g2)
        g3 = QGroupBox("Guardrails built in")
        l3 = QVBoxLayout(g3)
        txt = QPlainTextEdit(
            "• Every file is reviewed by a person: masked preview, open file, open folder. Nothing is deleted automatically.\n"
            "• DELETE moves files to a recoverable quarantine with undo. Permanent erase needs a typed DELETE confirmation.\n"
            "• Dry-run is ON by default; files are re-verified by SHA-256 just before any move.\n"
            "• KEEP decisions need a lawful reason; every decision is recorded with user and time.\n"
            "• Scan results and the case register hold paths, owners and counts only. Searched identifiers are never stored.\n"
            "• System folders and symbolic links are skipped. The PWA is localhost-only, read-only and token protected.\n"
            "• Every action is written to a CSV audit log (formula-injection safe).")
        txt.setReadOnly(True)
        l3.addWidget(txt)
        v.addWidget(g3, 1)
        self.tabs.addTab(w, "⚙  Settings && PWA")

    def set_pwa_url(self, port):
        self.pwa_url = "http://127.0.0.1:%d/?k=%s" % (port, self.cfg["token"]) if port else ""
        self.s_url.setText(self.pwa_url or "PWA server is disabled or could not start.")

    def pick_q(self):
        d = QFileDialog.getExistingDirectory(self, "Quarantine folder")
        if d:
            self.s_q.setText(os.path.normpath(d))

    def save_settings(self):
        n = clean_name(self.s_name.text())
        if not n:
            QMessageBox.warning(self, "Name required", "Application name cannot be empty.")
            return
        q = self.s_q.text().strip() or DEFAULT_QDIR
        if is_protected(q):
            QMessageBox.warning(self, "Protected path", "Choose a quarantine folder outside system directories.")
            return
        self.cfg.update(app_name=n, theme=self.s_theme.currentText(), qdir=q, pwa=self.s_pwa.isChecked())
        save_config(self.cfg)
        os.makedirs(q, exist_ok=True)
        self.apply_name()
        self.apply_theme()
        self.statusBar().showMessage("Settings saved.")

    def closeEvent(self, e):
        if self.thread and self.thread.isRunning():
            self.thread.cancel.set()
            self.thread.wait(3000)
        e.accept()


# ----------------------------------------------------------------------------------------------
# 10. ENTRY POINT
# ----------------------------------------------------------------------------------------------
def main():
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    cfg = load_config()
    if not clean_name(cfg.get("app_name", "")):                      # first launch: ask for the name
        name, ok = QInputDialog.getText(None, "Welcome", "Give this application a name:",
                                        QLineEdit.Normal, DEFAULT_NAME)
        cfg["app_name"] = clean_name(name) if ok and clean_name(name) else DEFAULT_NAME
    cfg["token"] = cfg.get("token") or secrets.token_urlsafe(12)
    cfg["salt"] = cfg.get("salt") or secrets.token_hex(16)
    save_config(cfg)
    os.makedirs(cfg["qdir"], exist_ok=True)
    PWA["token"] = cfg["token"]
    win = MainWindow(cfg)
    srv, port = (start_pwa_server(int(cfg["port"])) if cfg.get("pwa", True) else (None, None))
    win.set_pwa_url(port)
    win.refresh_all()
    win.update_pill()
    if LICENSE.status()["state"] not in ("trial", "licensed"):      # must activate before use
        LicenseDialog(win).exec_()
        win.update_pill()
        if LICENSE.status()["state"] not in ("trial", "licensed"):
            if srv:
                srv.shutdown()
            return 0
    t = QTimer(win)                                                  # re-check expiry hourly
    t.timeout.connect(win.update_pill)
    t.start(3600 * 1000)
    win._lic_timer = t
    audit("APP_START", "v%s port=%s" % (APP_VERSION, port))
    win.show()
    win._keep = srv
    rc = app.exec_()
    if srv:
        srv.shutdown()
    return rc


if __name__ == "__main__":
    main()
