#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRN FS Solution  -  one launcher: Tally  ->  financial statements
=============================================================
Run:   python drn_studio.py            (opens the studio in your browser)

What it does
  * Serves drn-schedule3-studio.html on http://127.0.0.1:8765  (this PC only).
  * Gives the studio a bridge to Tally (/api/companies, /api/tb): the studio's "Refresh from Tally" button asks this
    program for the current and previous year trial balance and rebuilds the Balance Sheet, Profit and Loss, notes and Excel.
  * Everything you enter is saved automatically in a SQLite database (drn_studio.db next to this file): clients, financial years,
    mappings, closing stock, fixed-asset register, deferred-tax inputs and disclosures. "Roll forward" starts next year from it.
  * A dated backup copy of the database is made every day in the "backups" folder (last 30 kept).
    Keep this folder OUTSIDE OneDrive / Dropbox - cloud sync can corrupt a database that is being written.

Keep these files in the same folder:  drn_studio.py, tally_tb_extractor.py, drn-schedule3-studio.html, engine.js (embedded in the html).
Tally must be open with Client/Server enabled (F1 > Settings > Connectivity), default port 9000.
No third-party libraries are needed for this launcher.
"""
import os, sys, json, socket, threading, webbrowser, traceback, sqlite3, shutil, time, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["DRN_NO_BOOTSTRAP"] = "1"          # the studio bridge only needs the standard library
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tally_tb_extractor as T                 # noqa: E402

HTML = os.path.join(HERE, "drn-schedule3-studio.html")
DB_PATH = os.environ.get("DRN_DB") or os.path.join(HERE, "drn_studio.db")
BACKUP_DIR = os.path.join(os.path.dirname(DB_PATH), "backups")
_DBLOCK = threading.Lock()


def db():
    cn = sqlite3.connect(DB_PATH, timeout=15)
    cn.row_factory = sqlite3.Row
    return cn


def db_init():
    with _DBLOCK, db() as cn:
        cn.executescript("""
            CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE NOT NULL, maps TEXT DEFAULT '{}', created TEXT, updated TEXT);
            CREATE TABLE IF NOT EXISTS years (client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE, fy INTEGER NOT NULL, state TEXT NOT NULL, updated TEXT,
                                              PRIMARY KEY (client_id, fy));
            CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);""")


def db_daily_backup():
    """One dated copy per day (SQLite online backup, safe while the file is in use); keep the newest 30."""
    if not os.path.exists(DB_PATH):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dest = os.path.join(BACKUP_DIR, f"drn_studio_{datetime.date.today():%Y%m%d}.db")
    if os.path.exists(dest):
        return
    src = sqlite3.connect(DB_PATH)
    out = sqlite3.connect(dest)
    with out:
        src.backup(out)
    out.close(); src.close()
    files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("drn_studio_") and f.endswith(".db"))
    for f in files[:-30]:
        try:
            os.remove(os.path.join(BACKUP_DIR, f))
        except OSError:
            pass


def db_list():
    with _DBLOCK, db() as cn:
        clients = []
        for c in cn.execute("SELECT id, name, updated FROM clients ORDER BY name COLLATE NOCASE"):
            ys = [dict(fy=y["fy"], updated=y["updated"]) for y in cn.execute("SELECT fy, updated FROM years WHERE client_id=? ORDER BY fy DESC", (c["id"],))]
            clients.append(dict(name=c["name"], updated=c["updated"], years=ys))
        last = {r["k"]: r["v"] for r in cn.execute("SELECT k, v FROM meta WHERE k IN ('last_client','last_fy')")}
    return dict(clients=clients, last=dict(client=last.get("last_client"), fy=int(last["last_fy"]) if last.get("last_fy") else None), path=DB_PATH)


def db_save(client, fy, state, maps):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with _DBLOCK, db() as cn:
        row = cn.execute("SELECT id FROM clients WHERE name=?", (client,)).fetchone()
        if row:
            cid = row["id"]
            cn.execute("UPDATE clients SET updated=?, maps=COALESCE(?, maps) WHERE id=?", (now, json.dumps(maps) if maps is not None else None, cid))
        else:
            cid = cn.execute("INSERT INTO clients(name, maps, created, updated) VALUES (?,?,?,?)", (client, json.dumps(maps or {}), now, now)).lastrowid
        cn.execute("INSERT INTO years(client_id, fy, state, updated) VALUES (?,?,?,?) ON CONFLICT(client_id, fy) DO UPDATE SET state=excluded.state, updated=excluded.updated",
                   (cid, fy, json.dumps(state), now))
        cn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES ('last_client', ?)", (client,))
        cn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES ('last_fy', ?)", (str(fy),))
    return now


def db_load(client, fy):
    with _DBLOCK, db() as cn:
        row = cn.execute("SELECT c.id, c.maps, y.state FROM clients c JOIN years y ON y.client_id=c.id WHERE c.name=? AND y.fy=?", (client, fy)).fetchone()
        if not row:
            return None
        cn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES ('last_client', ?)", (client,))
        cn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES ('last_fy', ?)", (str(fy),))
        return dict(state=json.loads(row["state"]), maps=json.loads(row["maps"] or "{}"))


def db_delete(client, fy):
    with _DBLOCK, db() as cn:
        row = cn.execute("SELECT id FROM clients WHERE name=?", (client,)).fetchone()
        if not row:
            return
        if fy is None:
            cn.execute("DELETE FROM years WHERE client_id=?", (row["id"],)); cn.execute("DELETE FROM clients WHERE id=?", (row["id"],))
        else:
            cn.execute("DELETE FROM years WHERE client_id=? AND fy=?", (row["id"], fy))


def db_backup_bytes():
    tmp = DB_PATH + ".dl"
    src = sqlite3.connect(DB_PATH)
    out = sqlite3.connect(tmp)
    with out:
        src.backup(out)
    out.close(); src.close()
    try:
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        os.remove(tmp)
HEADER = ["Name", "Parent", "PrimaryGroup", "OpeningBalance", "Net Debit", "Net Credit", "ClosingBalance", "PY ClosingBalance", "PY OpeningBalance", "Description"]


def tb_payload(host, port, company, company_py, fy, skip_py=False):
    """Current + previous year from Tally -> rows in the Tally ledger-export layout (one row per ledger), plus warnings."""
    log = []
    a, b = T.fy_dates(fy)
    cy = T.xml_fetch(host, port, company, a, b, log.append)
    warn = []
    if skip_py:                                          # previous year comes from the saved database (roll forward)
        py = []
    else:
        c, d = T.fy_dates(fy - 1)
        py = T.xml_fetch(host, port, company_py or company, c, d, log.append)
    nom = lambda rows: sum(abs(r["close"]) for r in rows if T.NOMINAL.search(r["pg"] or r["parent"]))
    if not skip_py and nom(cy) > 0.5 and nom(py) < 0.5:
        warn.append("Previous year has no income / expense in the selected company - choose the company that holds the previous-year books.")
    rows = [HEADER + [T.fy_label(fy), T.fy_label(fy - 1)]]
    for r in T.merge_years(cy, py):
        mv = round(r["close"] - r["open"], 2)
        nd = r["nd"] if r.get("nd") is not None else (round(-mv, 2) if mv < 0 else 0)
        nc = r["nc"] if r.get("nc") is not None else (mv if mv > 0 else 0)
        rows.append([r["name"], r["parent"] or "Primary", "" if T.is_pl(r) else r["pg"], r["open"], nd, nc, r["close"], r["pyclose"], "" if r.get("pyopen") is None else r["pyopen"], "", "", ""])
    return dict(rows=rows, warnings=warn, count=len(rows) - 1)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html", "/studio"):
            try:
                with open(HTML, "rb") as f:
                    page = f.read()
            except OSError:
                return self._send(500, "drn-schedule3-studio.html not found next to drn_studio.py", "text/plain; charset=utf-8")
            if not page.lstrip().lower().startswith(b"<!doctype"):
                page = b"<!doctype html>\n" + page
            return self._send(200, page, "text/html; charset=utf-8")
        if path == "/api/ping":
            return self._send(200, json.dumps({"ok": True, "bridge": "drn-studio", "version": 3, "db": True, "features": ["tb", "stock", "assets", "db"]}))
        if path == "/api/db/list":
            return self._send(200, json.dumps(db_list()))
        if path == "/api/db/backup":
            data = db_backup_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="drn_studio_backup_{datetime.date.today():%Y%m%d}.db"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)
            return
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            host, port = (req.get("host") or "localhost").strip(), str(req.get("port") or "9000").strip()
            if path == "/api/companies":
                return self._send(200, json.dumps({"companies": T.xml_companies(host, port)}))
            if path == "/api/tb":
                fy = int(req.get("fy"))
                return self._send(200, json.dumps(tb_payload(host, port, (req.get("company") or "").strip(),
                                                             (req.get("companyPy") or "").strip(), fy, bool(req.get("skipPy")))))
            if path == "/api/assets":
                fy = int(req.get("fy"))
                a, b = T.fy_dates(fy)
                ent = T.asset_entries(host, port, (req.get("company") or "").strip(), a, b, [str(x) for x in (req.get("ledgers") or [])])
                return self._send(200, json.dumps({"entries": ent, "count": len(ent)}))
            if path == "/api/stock":
                fy = int(req.get("fy"))
                company = (req.get("company") or "").strip()
                out = {"cy": T.stock_fetch(host, port, company, *T.fy_dates(fy))}
                if not req.get("skipPy"):
                    out["py"] = T.stock_fetch(host, port, (req.get("companyPy") or "").strip() or company, *T.fy_dates(fy - 1))
                return self._send(200, json.dumps(out))
            if path == "/api/db/save":
                stamp = db_save(str(req["client"]).strip(), int(req["fy"]), req["state"], req.get("maps"))
                return self._send(200, json.dumps({"ok": True, "saved": stamp}))
            if path == "/api/db/load":
                got = db_load(str(req["client"]).strip(), int(req["fy"]))
                return self._send(200, json.dumps(got if got else {"error": "That client / year is not in the database."}))
            if path == "/api/db/delete":
                db_delete(str(req["client"]).strip(), int(req["fy"]) if req.get("fy") is not None else None)
                return self._send(200, json.dumps({"ok": True}))
            self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:                                  # shown inside the studio
            traceback.print_exc()
            self._send(200, json.dumps({"error": " ".join(str(e).split())[:400]}))

    def log_message(self, *a):
        pass


def free_port(start=8765):
    for p in range(start, start + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("No free port between 8765 and 8784.")


def main():
    if not os.path.exists(HTML):
        sys.exit(f"Cannot find {HTML}")
    db_init()
    try:
        db_daily_backup()
    except Exception as e:
        print("Backup skipped:", e)
    port = free_port(int(os.environ.get("DRN_PORT", "8765")))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)     # localhost only: nobody else on the network can reach it
    url = f"http://127.0.0.1:{port}/"
    print(f"DRN FS Solution running at {url}\nDatabase: {DB_PATH}\nKeep this window open while you work. Press Ctrl+C to stop.")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
