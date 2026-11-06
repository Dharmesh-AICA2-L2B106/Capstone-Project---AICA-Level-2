# ABC FinSight App - Management Reporting Assistant (PyQt5)
# Run in IDLE (F5). Missing libraries are installed automatically on first run.
import sys, subprocess, importlib

REQUIRED = {"PyQt5": "PyQt5", "pandas": "pandas", "openpyxl": "openpyxl", "matplotlib": "matplotlib"}
for _mod, _pkg in REQUIRED.items():
    try:
        importlib.import_module(_mod)
    except ImportError:
        print("Installing", _pkg, "...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", _pkg])

import random
from datetime import datetime
import pandas as pd
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as Canvas
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QTextDocument
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QStackedWidget, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QComboBox, QLineEdit, QTextEdit, QDoubleSpinBox, QCheckBox, QFrame, QHeaderView)

APP = "ABC FinSight App"
PL = ["Revenue", "COGS", "Operating Expense"]
DISCLAIMER = ("AI/automated output is a draft and requires professional review. "
              "Prepared under IFRS. Figures in AED. Not audited.")
STYLE = """
QMainWindow,QWidget{font-family:Segoe UI;font-size:13px;background:#F4F6FB;color:#1B2340}
#side{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4B2BD8,stop:1 #0EA5A5)}
#side QPushButton{background:transparent;color:white;text-align:left;padding:12px 18px;border:none;font-size:14px;font-weight:600}
#side QPushButton:hover{background:rgba(255,255,255,60)}
#side QPushButton:checked{background:rgba(255,255,255,110)}
#logo{color:white;font-size:20px;font-weight:800;padding:18px;background:transparent}
#card{background:white;border-radius:12px}
QPushButton.act{background:#FF7A18;color:white;border-radius:8px;padding:8px 16px;font-weight:700}
QPushButton.act:hover{background:#E8650A}
QPushButton.alt{background:#0EA5A5;color:white;border-radius:8px;padding:8px 16px;font-weight:700}
QTableWidget{background:white;gridline-color:#E3E7F2;alternate-background-color:#F3F0FF}
QHeaderView::section{background:#4B2BD8;color:white;padding:6px;border:none;font-weight:700}
QTextEdit,QLineEdit,QComboBox,QDoubleSpinBox{background:white;border:1px solid #C9D0E6;border-radius:6px;padding:4px}
"""


def money(x):
    return f"{x:,.0f}"


def btn(text, kind="act", fn=None):
    b = QPushButton(text)
    b.setProperty("class", kind)
    b.setCursor(Qt.PointingHandCursor)
    if fn:
        b.clicked.connect(fn)
    return b


def fill(t, headers, rows, colors=None):
    t.clear()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setRowCount(len(rows))
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            it = QTableWidgetItem(str(v))
            if isinstance(v, str) and v.replace(",", "").replace("-", "").replace(".", "").replace("%", "").isdigit():
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if colors and colors.get(r):
                it.setBackground(colors[r])
            t.setItem(r, c, it)


def sample_data():
    rnd = random.Random(7)
    rows, n = [], 1
    for prop in ["Marina Tower", "Downtown Residences", "JLT Offices"]:
        base = {"Marina Tower": 1.0, "Downtown Residences": 1.25, "JLT Offices": 0.8}[prop]
        items = [("Rental Income", "Revenue", 900000), ("Service Charges", "Revenue", 220000),
                 ("Cleaning & Security", "COGS", 160000), ("Maintenance", "Operating Expense", 60000),
                 ("DEWA Utilities", "Operating Expense", 85000), ("Staff Costs", "Operating Expense", 140000),
                 ("Depreciation", "Operating Expense", 75000), ("Bank Charges", "Operating Expense", 6000)]
        for name, cat, b in items:
            b = b * base
            cur = b * rnd.uniform(0.92, 1.08)
            pri = b * rnd.uniform(0.9, 1.05)
            rows.append([1000 + n, name, cat, round(cur), round(pri), round(b), prop]); n += 1
        rows.append([1000 + n, "VAT Payable", "Liability", round(60000 * base), 58000, 60000, prop]); n += 1
    # deliberate anomalies
    rows.append([2001, "Maintenance - Lift Repair", "Operating Expense", 38450, 0, 20000, "Marina Tower"])
    rows.append([2002, "Maintenance - Lift Repair", "Operating Expense", 38450, 0, 20000, "Marina Tower"])
    rows.append([2003, "Consultancy Fees", "Operating Expense", 100000, 15000, 30000, "Downtown Residences"])
    rows.append([2004, "Maintenance - Major Repairs", "Operating Expense", 185000, 55000, 60000, "JLT Offices"])
    rows.append([2005, "Rental Refund", "Revenue", -42000, 0, 0, "Downtown Residences"])
    return pd.DataFrame(rows, columns=["Code", "Account", "Category", "Current", "Prior", "Budget", "Centre"])


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP)
        self.resize(1250, 780)
        self.df = None
        self.logs = []
        self.status = {}
        self.flags = []
        root = QWidget(); self.setCentralWidget(root)
        lay = QHBoxLayout(root); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        side = QFrame(); side.setObjectName("side"); side.setFixedWidth(210)
        sl = QVBoxLayout(side); sl.setContentsMargins(0, 0, 0, 0)
        lg = QLabel("ABC FinSight"); lg.setObjectName("logo"); sl.addWidget(lg)
        self.stack = QStackedWidget()
        self.navs = []
        pages = [("Dashboard", self.pg_dash()), ("Upload Data", self.pg_upload()),
                 ("Variance Analysis", self.pg_var()), ("AI Commentary", self.pg_comm()),
                 ("Anomaly Flags", self.pg_anom()), ("Report Export", self.pg_export()),
                 ("Audit Log", self.pg_log())]
        for i, (name, w) in enumerate(pages):
            b = QPushButton(name); b.setCheckable(True)
            b.clicked.connect(lambda _, k=i: self.go(k))
            sl.addWidget(b); self.navs.append(b); self.stack.addWidget(w)
        sl.addStretch()
        note = QLabel("Data stays on this PC.\nOutput is a draft:\nprofessional review\nrequired. All actions\nare logged.")
        note.setStyleSheet("color:white;padding:14px;background:transparent;font-size:11px")
        sl.addWidget(note)
        lay.addWidget(side); lay.addWidget(self.stack, 1)
        self.go(1)

    def go(self, i):
        for k, b in enumerate(self.navs):
            b.setChecked(k == i)
        self.stack.setCurrentIndex(i)

    def wrap(self, title, *widgets):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(22, 18, 22, 18)
        h = QLabel(title); h.setStyleSheet("font-size:22px;font-weight:800;color:#4B2BD8")
        v.addWidget(h)
        for x in widgets:
            v.addWidget(x) if isinstance(x, QWidget) else v.addLayout(x)
        return w

    def log(self, action):
        self.logs.append((datetime.now().strftime("%Y-%m-%d %H:%M:%S"), action))
        fill(self.t_log, ["Timestamp", "Action"], self.logs)

    def need(self):
        if self.df is None:
            QMessageBox.information(self, APP, "Please load a file or the sample data first (Upload Data).")
            return False
        return True

    # ---------- Upload ----------
    def pg_upload(self):
        self.lbl_file = QLabel("No data loaded.")
        self.lbl_file.setStyleSheet("font-size:14px")
        info = QLabel("Expected columns: Account Code, Account Name, Category (Revenue, COGS, Operating Expense, "
                      "Asset, Liability, Equity), Current Period, Prior Period, Budget. Optional: Cost Centre.")
        info.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(btn("Open Excel / CSV", "act", self.open_file))
        row.addWidget(btn("Load Sample Data", "alt", self.load_sample)); row.addStretch()
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card); cl.addWidget(info); cl.addLayout(row); cl.addWidget(self.lbl_file)
        self.t_prev = QTableWidget()
        return self.wrap("Upload Data", card, self.t_prev)

    def load_sample(self):
        self.set_df(sample_data(), "Sample UAE real-estate data")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "Data (*.xlsx *.xls *.csv)")
        if not path:
            return
        try:
            raw = pd.read_csv(path) if path.lower().endswith(".csv") else pd.read_excel(path)
            keys = {"Code": ["code", "account code", "acc code"], "Account": ["account name", "account", "name"],
                    "Category": ["category", "type"], "Current": ["current period", "current", "actual"],
                    "Prior": ["prior period", "prior", "previous"], "Budget": ["budget"],
                    "Centre": ["cost centre", "cost center", "property", "centre"]}
            cols = {str(c).strip().lower(): c for c in raw.columns}
            out = pd.DataFrame()
            for k, alts in keys.items():
                hit = next((cols[a] for a in alts if a in cols), None)
                if hit is None and k != "Centre":
                    raise ValueError("Column not found for: " + k)
                out[k] = raw[hit] if hit is not None else "All"
            for c in ["Current", "Prior", "Budget"]:
                out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
            out["Category"] = out["Category"].astype(str).str.strip().str.title().replace(
                {"Opex": "Operating Expense", "Operating Expenses": "Operating Expense", "Cogs": "COGS"})
            self.set_df(out, path)
        except Exception as e:
            QMessageBox.warning(self, APP, "Could not read file:\n" + str(e))

    def set_df(self, df, src):
        df = df.copy()
        df["Variance"] = df["Current"] - df["Budget"]
        df["VarPct"] = df.apply(lambda r: r["Variance"] / abs(r["Budget"]) * 100 if r["Budget"] else 0, axis=1)

        def fav(r):
            if r["Category"] not in PL:
                return "-"
            good = r["Variance"] >= 0 if r["Category"] == "Revenue" else r["Variance"] <= 0
            return "Favourable" if good else "Adverse"
        df["Fav"] = df.apply(fav, axis=1)
        self.df = df
        self.status = {}
        self.lbl_file.setText(f"Loaded: {src}  ({len(df)} rows)")
        rows = [[r.Code, r.Account, r.Category, money(r.Current), money(r.Prior), money(r.Budget), r.Centre]
                for r in df.itertuples()]
        fill(self.t_prev, ["Code", "Account", "Category", "Current", "Prior", "Budget", "Centre"], rows)
        self.log("File loaded: " + str(src))
        self.refresh()

    def refresh(self):
        self.draw_dash(); self.fill_var(); self.fill_anom()

    # ---------- KPIs ----------
    def kpis(self, col):
        d = self.df
        s = lambda cat: d.loc[d.Category == cat, col].sum()
        rev, cogs, opex = s("Revenue"), s("COGS"), s("Operating Expense")
        gp, np_ = rev - cogs, rev - cogs - opex
        return {"Revenue": rev, "Gross Profit": gp, "Gross Margin %": gp / rev * 100 if rev else 0,
                "Operating Expenses": opex, "Net Profit": np_, "Net Margin %": np_ / rev * 100 if rev else 0}

    # ---------- Dashboard ----------
    def pg_dash(self):
        self.kgrid = QGridLayout()
        self.fig = Figure(figsize=(9, 6), facecolor="#F4F6FB")
        self.canvas = Canvas(self.fig)
        return self.wrap("Dashboard", self.kgrid, self.canvas)

    def draw_dash(self):
        if self.df is None:
            return
        while self.kgrid.count():
            self.kgrid.takeAt(0).widget().deleteLater()
        cur, pri, bud = self.kpis("Current"), self.kpis("Prior"), self.kpis("Budget")
        colors = ["#4B2BD8", "#0EA5A5", "#FF7A18", "#E11D74", "#16A34A", "#2563EB"]
        for i, k in enumerate(cur):
            pct = "%" in k
            fmt = (lambda x: f"{x:.1f}%") if pct else (lambda x: "AED " + money(x))
            vp, vb = cur[k] - pri[k], cur[k] - bud[k]
            fmt_d = (lambda x: f"{x:+.1f} pts") if pct else (lambda x: f"{x:+,.0f}")
            card = QLabel(f"<div style='font-size:11px;color:white'>{k}</div>"
                          f"<div style='font-size:19px;font-weight:800;color:white'>{fmt(cur[k])}</div>"
                          f"<div style='font-size:10px;color:white'>vs Prior {'&#9650;' if vp >= 0 else '&#9660;'} {fmt_d(vp)}"
                          f"<br>vs Budget {'&#9650;' if vb >= 0 else '&#9660;'} {fmt_d(vb)}</div>")
            card.setStyleSheet(f"background:{colors[i]};border-radius:12px;padding:10px")
            self.kgrid.addWidget(card, 0, i)
        d = self.df
        self.fig.clear()
        a1, a2, a3, a4 = [self.fig.add_subplot(2, 2, i) for i in range(1, 5)]
        rv = d[d.Category == "Revenue"].groupby("Centre")[["Current", "Budget"]].sum()
        rv.plot.bar(ax=a1, color=["#4B2BD8", "#0EA5A5"], rot=15); a1.set_title("Revenue vs Budget"); a1.set_xlabel("")
        ex = d[d.Category.isin(["COGS", "Operating Expense"])].groupby("Account")["Current"].sum()
        ex = ex[ex > 0].sort_values(ascending=False).head(6)
        a2.pie(ex.values, labels=ex.index, wedgeprops=dict(width=0.45), textprops={"fontsize": 7}); a2.set_title("Expense breakdown")
        a3.plot(["Prior", "Current", "Budget"], [pri["Net Profit"], cur["Net Profit"], bud["Net Profit"]],
                marker="o", color="#E11D74", linewidth=2); a3.set_title("Net profit trend")
        np_c = {}
        for c, g in d.groupby("Centre"):
            np_c[c] = (g[g.Category == "Revenue"].Current.sum()
                       - g[g.Category.isin(["COGS", "Operating Expense"])].Current.sum())
        a4.bar(list(np_c.keys()), list(np_c.values()), color="#FF7A18"); a4.set_title("Profit by cost centre")
        a4.tick_params(axis="x", rotation=15)
        for a in (a1, a3, a4):
            a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"{x/1000:,.0f}k"))
        for a in (a1, a2, a3, a4):
            a.tick_params(labelsize=7)
        self.fig.tight_layout(); self.canvas.draw()

    # ---------- Variance ----------
    def pg_var(self):
        top = QHBoxLayout()
        self.sp_pct = QDoubleSpinBox(); self.sp_pct.setRange(0, 500); self.sp_pct.setValue(10); self.sp_pct.setSuffix(" %")
        self.sp_amt = QDoubleSpinBox(); self.sp_amt.setRange(0, 1e9); self.sp_amt.setValue(25000); self.sp_amt.setSingleStep(5000)
        self.cb_cat = QComboBox(); self.cb_cat.addItems(["All", "Revenue", "COGS", "Operating Expense", "Asset", "Liability", "Equity"])
        self.cb_cc = QComboBox(); self.cb_cc.addItem("All")
        self.ed_s = QLineEdit(); self.ed_s.setPlaceholderText("Search account...")
        for w in (self.sp_pct, self.sp_amt, self.cb_cat, self.cb_cc, self.ed_s):
            (w.valueChanged if isinstance(w, QDoubleSpinBox) else w.textChanged if isinstance(w, QLineEdit)
             else w.currentIndexChanged).connect(self.fill_var)
        for lbl, w in (("Materiality %", self.sp_pct), ("or AED", self.sp_amt), ("Category", self.cb_cat),
                       ("Centre", self.cb_cc), ("", self.ed_s)):
            if lbl:
                top.addWidget(QLabel(lbl))
            top.addWidget(w)
        self.t_var = QTableWidget(); self.t_var.setSortingEnabled(False)
        return self.wrap("Variance Analysis", top, self.t_var)

    def fill_var(self):
        if self.df is None:
            return
        d = self.df
        cur = self.cb_cc.currentText()
        if self.cb_cc.count() == 1:
            self.cb_cc.blockSignals(True)
            self.cb_cc.addItems(sorted(d.Centre.astype(str).unique())); self.cb_cc.blockSignals(False)
        if self.cb_cat.currentText() != "All":
            d = d[d.Category == self.cb_cat.currentText()]
        if cur != "All":
            d = d[d.Centre.astype(str) == cur]
        q = self.ed_s.text().strip().lower()
        if q:
            d = d[d.Account.astype(str).str.lower().str.contains(q)]
        rows, colors = [], {}
        for i, r in enumerate(d.itertuples()):
            rows.append([r.Account, r.Centre, r.Category, money(r.Current), money(r.Budget), money(r.Prior),
                         money(r.Variance), f"{r.VarPct:.1f}%", r.Fav])
            if abs(r.VarPct) > self.sp_pct.value() or abs(r.Variance) > self.sp_amt.value():
                colors[i] = QColor("#FFE9B8")
        fill(self.t_var, ["Account", "Centre", "Category", "Actual", "Budget", "Prior", "Variance AED", "Var %", "Status"],
             rows, colors)

    # ---------- Commentary ----------
    def pg_comm(self):
        top = QHBoxLayout()
        self.cb_tone = QComboBox(); self.cb_tone.addItems(["CFO", "Board", "Operational"])
        top.addWidget(QLabel("Tone")); top.addWidget(self.cb_tone)
        top.addWidget(btn("Generate Commentary", "act", self.gen_comm)); top.addStretch()
        warn = QLabel("Draft generated by built-in rules: requires professional review. Edit freely before export.")
        warn.setStyleSheet("color:#E11D74;font-weight:700")
        self.ed_comm = QTextEdit()
        return self.wrap("AI Commentary", top, warn, self.ed_comm)

    def gen_comm(self):
        if not self.need():
            return
        cur, pri, bud = self.kpis("Current"), self.kpis("Prior"), self.kpis("Budget")
        d = self.df[self.df.Category.isin(PL)].copy()
        d["Impact"] = d.apply(lambda r: r.Variance if r.Category == "Revenue" else -r.Variance, axis=1)
        good = d.sort_values("Impact", ascending=False).head(3)
        bad = d.sort_values("Impact").head(3)
        intro = {"CFO": "Summary for the CFO", "Board": "Board summary", "Operational": "Operational update"}[self.cb_tone.currentText()]
        pv = (cur["Net Profit"] - bud["Net Profit"])
        txt = [f"EXECUTIVE SUMMARY ({intro})",
               f"Revenue was AED {money(cur['Revenue'])}, {cur['Revenue']-bud['Revenue']:+,.0f} vs budget and "
               f"{cur['Revenue']-pri['Revenue']:+,.0f} vs prior period.",
               f"Gross margin was {cur['Gross Margin %']:.1f}% and net profit AED {money(cur['Net Profit'])} "
               f"({cur['Net Margin %']:.1f}% margin), {'ahead of' if pv >= 0 else 'behind'} budget by AED {money(abs(pv))}.",
               "", "KEY DRIVERS (favourable)"]
        txt += [f"- {r.Account} ({r.Centre}): AED {money(r.Impact)} favourable ({r.VarPct:+.1f}% vs budget)" for r in good.itertuples() if r.Impact > 0]
        txt += ["", "KEY DRIVERS (adverse)"]
        txt += [f"- {r.Account} ({r.Centre}): AED {money(-r.Impact)} adverse ({r.VarPct:+.1f}% vs budget)" for r in bad.itertuples() if r.Impact < 0]
        txt += ["", "RISKS / ATTENTION", f"- {len([f for f in self.flags if f[0]=='High'])} high-severity anomaly flag(s) need review (see Anomaly Flags).",
                "- Confirm whether adverse cost variances are one-off or recurring.",
                "", "SUGGESTED ACTIONS",
                "- Investigate the largest adverse variances with the cost centre owners.",
                "- Resolve flagged duplicates, round-sum and negative-revenue entries before sign-off.",
                "- Update the forecast if favourable trends are expected to continue."]
        self.ed_comm.setPlainText("\n".join(txt))
        self.log("Commentary generated (" + self.cb_tone.currentText() + ")")

    # ---------- Anomalies ----------
    def pg_anom(self):
        self.t_an = QTableWidget()
        top = QHBoxLayout(); top.addWidget(btn("Re-run checks", "alt", self.fill_anom)); top.addStretch()
        return self.wrap("Anomaly Flags", top, self.t_an)

    def compute_flags(self):
        d, out = self.df, []
        pl = d[d.Category.isin(PL)]
        dup = pl[(pl.Current > 0) & pl.duplicated(["Account", "Centre", "Current"], keep=False)]
        for r in dup.itertuples():
            out.append(("High", "Duplicate amount", r.Account, r.Centre, f"Same amount AED {money(r.Current)} posted more than once"))
        for r in pl.itertuples():
            if abs(r.Current) >= 50000 and r.Current % 10000 == 0:
                out.append(("Medium", "Round-sum entry", r.Account, r.Centre, f"AED {money(r.Current)} is a round figure"))
            if r.Category == "Revenue" and r.Current < 0:
                out.append(("High", "Negative revenue", r.Account, r.Centre, f"Revenue of AED {money(r.Current)}"))
            if r.Category != "Revenue" and r.Budget > 0 and r.VarPct > self.sp_pct.value() and r.Variance > self.sp_amt.value():
                out.append(("High" if r.VarPct > 100 else "Medium", "Over budget", r.Account, r.Centre,
                            f"{r.VarPct:.0f}% over budget (AED {money(r.Variance)})"))
            if r.Prior and abs((r.Current - r.Prior) / r.Prior) > 0.30 and abs(r.Current - r.Prior) > 10000:
                out.append(("Low", "Swing > 30% vs prior", r.Account, r.Centre, f"Prior {money(r.Prior)} to current {money(r.Current)}"))
            if r.Current == 0:
                out.append(("Low", "Zero activity", r.Account, r.Centre, "No activity in current period"))
        return out

    def fill_anom(self):
        if self.df is None:
            return
        order = {"High": 0, "Medium": 1, "Low": 2}
        self.flags = sorted(self.compute_flags(), key=lambda f: order[f[0]])
        rows = [[f[0], f[1], f[2], f[3], f[4], ""] for f in self.flags]
        sev = {"High": "#FFC9C9", "Medium": "#FFE9B8", "Low": "#D5F5E3"}
        fill(self.t_an, ["Severity", "Rule", "Account", "Centre", "Detail", "Review status"], rows,
             {i: QColor(sev[f[0]]) for i, f in enumerate(self.flags)})
        for i, f in enumerate(self.flags):
            key = "|".join(f[1:4])
            cb = QComboBox(); cb.addItems(["Open", "Reviewed", "Cleared", "Escalated"])
            cb.setCurrentText(self.status.get(key, "Open"))
            cb.currentTextChanged.connect(lambda v, k=key: self.set_status(k, v))
            self.t_an.setCellWidget(i, 5, cb)

    def set_status(self, key, v):
        self.status[key] = v
        self.log(f"Flag {v}: {key}")

    # ---------- Export ----------
    def pg_export(self):
        self.ed_co = QLineEdit("ABC Real Estate LLC")
        self.ed_by = QLineEdit(); self.ed_by.setPlaceholderText("Prepared by")
        self.ed_rv = QLineEdit(); self.ed_rv.setPlaceholderText("Reviewed by")
        row = QHBoxLayout()
        for lbl, w in (("Company", self.ed_co), ("Prepared by", self.ed_by), ("Reviewed by", self.ed_rv)):
            row.addWidget(QLabel(lbl)); row.addWidget(w)
        row2 = QHBoxLayout()
        row2.addWidget(btn("Export PDF Report", "act", self.exp_pdf))
        row2.addWidget(btn("Export Excel", "alt", self.exp_xlsx)); row2.addStretch()
        tip = QLabel("Tip: generate the commentary and review flags first; they are included in the report.")
        return self.wrap("Report Export", row, row2, tip)

    def report_html(self):
        cur, pri, bud = self.kpis("Current"), self.kpis("Prior"), self.kpis("Budget")
        kp = "".join(f"<tr><td>{k}</td><td align=right>{cur[k]:,.1f}</td><td align=right>{pri[k]:,.1f}</td>"
                     f"<td align=right>{bud[k]:,.1f}</td></tr>" for k in cur)
        pl = "".join(f"<tr><td>{r.Account}</td><td>{r.Centre}</td><td align=right>{money(r.Current)}</td>"
                     f"<td align=right>{money(r.Budget)}</td><td align=right>{money(r.Variance)}</td>"
                     f"<td>{r.Fav}</td></tr>" for r in self.df[self.df.Category.isin(PL)].itertuples())
        fl = "".join(f"<tr><td>{f[0]}</td><td>{f[1]}</td><td>{f[2]}</td><td>{f[3]}</td>"
                     f"<td>{self.status.get('|'.join(f[1:4]), 'Open')}</td></tr>" for f in self.flags)
        com = self.ed_comm.toPlainText().replace("\n", "<br>")
        return (f"<h1 style='color:#4B2BD8'>{self.ed_co.text()}</h1><h2>Management Report - {datetime.now():%d %b %Y}</h2>"
                f"<h3>Commentary</h3><p>{com or 'Not generated.'}</p>"
                f"<h3>KPI Summary (AED)</h3><table border=1 cellpadding=4 width=100%><tr><th>KPI</th><th>Current</th><th>Prior</th><th>Budget</th></tr>{kp}</table>"
                f"<h3>P&amp;L with Variances</h3><table border=1 cellpadding=4 width=100%><tr><th>Account</th><th>Centre</th><th>Actual</th><th>Budget</th><th>Variance</th><th>Status</th></tr>{pl}</table>"
                f"<h3>Anomaly Summary</h3><table border=1 cellpadding=4 width=100%><tr><th>Severity</th><th>Rule</th><th>Account</th><th>Centre</th><th>Status</th></tr>{fl}</table>"
                f"<br><p>Prepared by: {self.ed_by.text() or '__________'} &nbsp;&nbsp; Reviewed by: {self.ed_rv.text() or '__________'} "
                f"&nbsp;&nbsp; Date: {datetime.now():%d-%m-%Y}</p><p><i>{DISCLAIMER}</i></p>")

    def exp_pdf(self):
        if not self.need():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "ABC_FinSight_Report.pdf", "PDF (*.pdf)")
        if not path:
            return
        doc = QTextDocument(); doc.setHtml(self.report_html())
        pr = QPrinter(QPrinter.HighResolution); pr.setOutputFormat(QPrinter.PdfFormat); pr.setOutputFileName(path)
        doc.print_(pr)
        self.log("Report exported (PDF): " + path)
        QMessageBox.information(self, APP, "PDF saved.")

    def exp_xlsx(self):
        if not self.need():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Excel", "ABC_FinSight_Report.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            with pd.ExcelWriter(path) as w:
                self.df.to_excel(w, "Variance", index=False)
                pd.DataFrame(self.flags, columns=["Severity", "Rule", "Account", "Centre", "Detail"]).to_excel(w, "Anomalies", index=False)
                pd.DataFrame({"Commentary": self.ed_comm.toPlainText().split("\n")}).to_excel(w, "Commentary", index=False)
                pd.DataFrame(self.logs, columns=["Timestamp", "Action"]).to_excel(w, "Audit Log", index=False)
            self.log("Report exported (Excel): " + path)
            QMessageBox.information(self, APP, "Excel saved.")
        except Exception as e:
            QMessageBox.warning(self, APP, "Export failed:\n" + str(e))

    # ---------- Audit log ----------
    def pg_log(self):
        self.t_log = QTableWidget()
        fill(self.t_log, ["Timestamp", "Action"], [])
        return self.wrap("Audit Log", self.t_log)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = Main()
    win.show()
    try:
        app.exec_()
    except SystemExit:
        pass
