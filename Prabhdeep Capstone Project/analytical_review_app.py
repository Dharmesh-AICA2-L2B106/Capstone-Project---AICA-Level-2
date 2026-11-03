"""
Analytical review for Audit by Prabhdeep
=========================================
Fictional—For Demonstration Only. Not an audit opinion or fraud conclusion.

HOW TO RUN
  * IDLE: open this file and press F5 (Run > Run Module).
  * Command line: python analytical_review_app.py

The first run checks for the required packages and installs any that are
missing, using the same Python interpreter. First-time installation needs an
internet connection. Manual install (one line):

  python -m pip install PyQt6 matplotlib anthropic

Keep audit_engine.py in the same folder as this file.
"""

import importlib
import importlib.util
import os
import site
import subprocess
import sys

APP_TITLE = "Analytical review for Audit by Prabhdeep"
REQUIRED_PACKAGES = [("PyQt6", "PyQt6"), ("matplotlib", "matplotlib")]   # (import name, pip name)
OPTIONAL_PACKAGES = [("anthropic", "anthropic")]                          # AI drafts only
INSTALL_COMMAND = "python -m pip install PyQt6 matplotlib anthropic"


# --------------------------------------------------------------------------
# 1. Startup dependency check (standard library only - runs before any
#    third-party import)
# --------------------------------------------------------------------------
def _python_for_pip():
    """IDLE on Windows may run under pythonw.exe; prefer python.exe beside it."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        candidate = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(candidate):
            return candidate
    return exe


def _missing(packages):
    return [pip for module, pip in packages if importlib.util.find_spec(module) is None]


def _pip_install(packages):
    python = _python_for_pip()
    base = [python, "-m", "pip", "install", "--disable-pip-version-check", *packages]
    for attempt in (base, base + ["--user"]):          # --user if no admin rights
        print("  Running:", " ".join(attempt[1:]))
        try:
            proc = subprocess.run(attempt, capture_output=True, text=True, timeout=1200)
        except FileNotFoundError:
            print("  Could not start Python to run pip.")
            return False
        except subprocess.TimeoutExpired:
            print("  Installation timed out (slow or no internet connection?).")
            return False
        if proc.returncode == 0:
            return True
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        print("  pip reported:", *tail, sep="\n    ")
        if "No module named pip" in (proc.stderr or ""):
            print("  pip is missing - trying 'python -m ensurepip'...")
            subprocess.run([python, "-m", "ensurepip", "--upgrade"], capture_output=True, text=True)
    return False


def ensure_dependencies():
    missing_required = _missing(REQUIRED_PACKAGES)
    missing_optional = _missing(OPTIONAL_PACKAGES)
    if not missing_required and not missing_optional:
        return True

    print("=" * 70)
    print(APP_TITLE + " - first-time setup")
    print("Missing packages:", ", ".join(missing_required + missing_optional))
    print("Installing with this Python:", _python_for_pip())
    print("First-time installation needs an INTERNET CONNECTION and can take a few minutes.")
    print("=" * 70)

    if missing_required and not _pip_install(missing_required):
        print("\nINSTALLATION FAILED for required packages:", ", ".join(missing_required))
        print("Check your internet connection / proxy, then run this command in a terminal:")
        print("   ", INSTALL_COMMAND)
        print("If you use several Python versions, run it with the same Python that runs IDLE.")
        return False
    if missing_optional and not _pip_install(missing_optional):
        print("\nNOTE: the optional 'anthropic' package could not be installed.")
        print("The app will work normally; only AI draft explanations will be unavailable.")

    importlib.invalidate_caches()
    user_site = site.getusersitepackages()
    if os.path.isdir(user_site) and user_site not in sys.path:
        site.addsitedir(user_site)
    still_missing = _missing(REQUIRED_PACKAGES)
    if still_missing:
        print("\nPackages were installed but cannot be loaded yet:", ", ".join(still_missing))
        print("Please close and restart IDLE (or the terminal), then run the app again.")
        return False
    print("Setup complete. Starting the application...\n")
    return True


if not ensure_dependencies():
    raise SystemExit("Required packages are missing - see the messages above.")

# --------------------------------------------------------------------------
# 2. Third-party imports (only after the check above)
# --------------------------------------------------------------------------
from pathlib import Path  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from PyQt6.QtCore import Qt, QThread, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QBrush, QColor, QFont  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_engine as eng  # noqa: E402

# --------------------------------------------------------------------------
# 3. Look and feel
# --------------------------------------------------------------------------
PASS_BG, FAIL_BG, WARN_BG = "#dcfce7", "#fee2e2", "#fef3c7"
FLAG_BG = "#ffe4e6"
STATUS_COLOURS = {"Open": "#fecaca", "Resolved": "#bbf7d0", "Escalated to engagement lead": "#fbcfe8"}

STYLE = """
QMainWindow, QWidget#page { background: #f5f3ff; }
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #1e1b4b; }
QTabWidget::pane { border: 2px solid #c7d2fe; border-radius: 10px; background: #ffffff; top: -2px; }
QTabBar::tab { background: #e0e7ff; color: #3730a3; padding: 9px 18px; margin-right: 3px;
               border-top-left-radius: 10px; border-top-right-radius: 10px; font-weight: 600; }
QTabBar::tab:selected { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #db2777);
                        color: white; }
QTabBar::tab:hover:!selected { background: #c7d2fe; }
QPushButton { background: #6366f1; color: white; border: none; border-radius: 8px;
              padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: #4f46e5; }
QPushButton:disabled { background: #cbd5e1; color: #64748b; }
QPushButton[kind="green"] { background: #059669; }  QPushButton[kind="green"]:hover { background: #047857; }
QPushButton[kind="pink"] { background: #db2777; }   QPushButton[kind="pink"]:hover { background: #be185d; }
QPushButton[kind="orange"] { background: #ea580c; } QPushButton[kind="orange"]:hover { background: #c2410c; }
QPushButton[kind="teal"] { background: #0891b2; }   QPushButton[kind="teal"]:hover { background: #0e7490; }
QPushButton[kind="light"] { background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.6); }
QPushButton[kind="light"]:hover { background: rgba(255,255,255,0.32); }
QTableWidget { background: white; gridline-color: #e5e7eb; border: 1px solid #c7d2fe; border-radius: 6px;
               alternate-background-color: #f8fafc; selection-background-color: #c7d2fe;
               selection-color: #1e1b4b; }
QHeaderView::section { background: #312e81; color: white; padding: 6px; border: none;
                       border-right: 1px solid #4338ca; font-weight: 600; }
QGroupBox { border: 2px solid #c7d2fe; border-radius: 10px; margin-top: 14px; padding: 12px 10px 10px 10px;
            font-weight: 700; color: #4338ca; background: #ffffff; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QTextEdit, QLineEdit, QComboBox, QDoubleSpinBox { border: 1px solid #a5b4fc; border-radius: 6px;
               padding: 4px; background: white; }
QTextEdit:focus, QLineEdit:focus { border: 2px solid #6366f1; }
QLabel#intro { background: #eef2ff; border-left: 5px solid #6366f1; padding: 8px; border-radius: 6px; }
QLabel#aiBanner { background: #ffedd5; color: #9a3412; border: 1px solid #fb923c; border-radius: 6px;
                  padding: 6px; font-weight: 700; }
QStatusBar { background: #312e81; color: white; }
"""


def button(text, kind=None, slot=None, tip=None):
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


def make_table(headers, stretch_col=None):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    header = t.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch_col is not None:
        header.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    return t


def cell(text, number=False, bg=None, bold=False, fg=None):
    item = QTableWidgetItem("" if text is None else str(text))
    if number:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if bg:
        item.setBackground(QBrush(QColor(bg)))
    if fg:
        item.setForeground(QBrush(QColor(fg)))
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    return item


def fill_table(table, rows, row_colours=None):
    """rows: list of lists of QTableWidgetItem or text."""
    table.setRowCount(0)
    for r, values in enumerate(rows):
        table.insertRow(r)
        for c, value in enumerate(values):
            item = value if isinstance(value, QTableWidgetItem) else cell(value)
            if row_colours and row_colours[r] and item.background().style() == Qt.BrushStyle.NoBrush:
                item.setBackground(QBrush(QColor(row_colours[r])))
            table.setItem(r, c, item)


# --------------------------------------------------------------------------
# 4. Widgets
# --------------------------------------------------------------------------
class RatioCard(QFrame):
    def __init__(self, title, colours):
        super().__init__()
        self.setStyleSheet(
            "QFrame { border-radius: 14px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {colours[0]}, stop:1 {colours[1]}); }}"
            "QLabel { color: white; background: transparent; }")
        self.setMinimumHeight(118)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 10pt; font-weight: 600;")
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 22pt; font-weight: 800;")
        self.sub = QLabel("")
        self.sub.setWordWrap(True)
        self.sub.setStyleSheet("font-size: 9pt;")
        for w in (heading, self.value, self.sub):
            layout.addWidget(w)


class SalesChart(FigureCanvasQTAgg):
    def __init__(self):
        self.figure = Figure(figsize=(8, 4.2), tight_layout=True)
        super().__init__(self.figure)
        self.setMinimumHeight(330)

    def draw_sales(self, monthly, py, cy, thresholds):
        fig = self.figure
        fig.clear()
        ax = fig.add_subplot(111)
        months = [m["month"] for m in monthly]
        x = range(len(months))
        width = 0.38
        py_vals = [m["py"] or 0 for m in monthly]
        cy_vals = [m["cy"] or 0 for m in monthly]
        cy_colours = ["#ef4444" if m["flag"] else "#7c3aed" for m in monthly]
        ax.bar([i - width / 2 for i in x], py_vals, width, color="#38bdf8", label=f"FY{py}")
        ax.bar([i + width / 2 for i in x], cy_vals, width, color=cy_colours, label=f"FY{cy}")
        ax.set_xticks(list(x))
        ax.set_xticklabels(months)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:,.0f}"))
        ax.set_ylabel("Sales (AED, unscaled)")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.25)

        ax2 = ax.twinx()
        growth = [m["pct"] if m["pct"] is not None else float("nan") for m in monthly]
        ax2.plot(list(x), growth, color="#f59e0b", marker="o", linewidth=2, label="Growth % vs PY")
        limit = thresholds["R01"]["Threshold"]
        ax2.axhline(limit, color="#dc2626", linestyle="--", linewidth=1.2,
                    label=f"R01 threshold {thresholds['R01']['Comparison']} {limit:g}%")
        ax2.set_ylabel("Same-month growth %")
        ax2.spines[["top"]].set_visible(False)
        for i, m in enumerate(monthly):
            if m["flag"]:
                ax2.annotate(f"{m['pct']:+.1f}%", (i, m["pct"]), textcoords="offset points",
                             xytext=(0, 8), ha="center", color="#b91c1c", fontweight="bold")
        handles = ax.get_legend_handles_labels()
        handles2 = ax2.get_legend_handles_labels()
        ax.legend(handles[0] + handles2[0], handles[1] + handles2[1], loc="upper left", fontsize=8, frameon=False)
        ax.set_title(f"Monthly sales FY{py} vs FY{cy} (red = flagged)", fontweight="bold", color="#312e81")
        fig.text(0.99, 0.01, eng.DEMO_LABEL, ha="right", va="bottom", fontsize=8, color="#9ca3af")
        self.draw()


class AIWorker(QThread):
    finished_draft = pyqtSignal(str, str, str)    # finding id, text, error

    def __init__(self, finding, verified, model):
        super().__init__()
        self.finding, self.verified, self.model = finding, verified, model

    def run(self):
        try:
            text = eng.draft_ai_explanation(self.finding, self.verified, self.model)
            self.finished_draft.emit(self.finding["id"], text, "")
        except eng.AIUnavailable as exc:
            self.finished_draft.emit(self.finding["id"], "", str(exc))
        except Exception as exc:  # keep the app alive whatever the AI library does
            self.finished_draft.emit(self.finding["id"], "", f"Unexpected AI error: {exc}")


class AISettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("AI settings (optional)")
        self.setMinimumWidth(520)
        settings = eng.load_ai_settings()
        layout = QVBoxLayout(self)
        info = QLabel(
            "AI drafts are optional. The app works fully without them.\n\n"
            f"The API key is stored outside the source code, in:\n{eng.API_KEY_FILE}\n"
            "An ANTHROPIC_API_KEY environment variable, if set, takes priority.\n"
            "Only verified figures for the selected finding are sent. Drafts are labelled "
            f"'{eng.AI_LABEL}'.")
        info.setWordWrap(True)
        info.setObjectName("intro")
        layout.addWidget(info)
        form = QFormLayout()
        self.enabled = QCheckBox("Enable AI draft explanations")
        self.enabled.setChecked(bool(settings.get("enabled", True)))
        self.model = QLineEdit(settings.get("model", eng.DEFAULT_MODEL))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        has_key = eng.get_api_key() is not None
        self.key.setPlaceholderText("Key saved - leave blank to keep it" if has_key else "Paste API key")
        self.clear_key = QCheckBox("Remove the saved key file")
        form.addRow(self.enabled)
        form.addRow("Model:", self.model)
        form.addRow("API key:", self.key)
        form.addRow(self.clear_key)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        key = "" if self.clear_key.isChecked() else (self.key.text().strip() or None)
        eng.save_ai_settings({"enabled": self.enabled.isChecked(),
                              "model": self.model.text().strip() or eng.DEFAULT_MODEL}, api_key=key)


STAGE_INTRO = {
    "Preliminary": "Preliminary analytical review: flags generated from the thresholds appear here. "
                   "Record initial reviewer notes, then move each finding to Substantive/Interim for follow-up.",
    "Substantive/Interim": "Substantive / interim work: record management responses, evidence references "
                           "and reviewer notes, and update the status as evidence is obtained.",
    "Final": "Final review: all findings moved to Final plus every UNRESOLVED finding from earlier stages "
             "(carried forward automatically). Use 'Carry forward unresolved' to log the move formally.",
}


class ReviewPanel(QWidget):
    def __init__(self, main, stage):
        super().__init__()
        self.main, self.stage, self.current_id, self.worker = main, stage, None, None
        layout = QVBoxLayout(self)
        intro = QLabel(STAGE_INTRO[stage])
        intro.setWordWrap(True)
        intro.setObjectName("intro")
        layout.addWidget(intro)

        bar = QHBoxLayout()
        self.summary = QLabel("")
        self.summary.setStyleSheet("font-weight: 700; color: #be185d;")
        bar.addWidget(self.summary)
        bar.addStretch()
        if stage == "Preliminary":
            bar.addWidget(button("+ Add manual finding", "teal", self.add_manual))
        if stage == "Final":
            bar.addWidget(button("Carry forward unresolved", "pink", self.carry_forward))
        bar.addWidget(button("Export findings register (CSV)", "green", self.main.export_csv))
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = make_table(["ID", "Title", "Status", "Stage", "Carried from", "Flag"], stretch_col=1)
        self.table.itemSelectionChanged.connect(self.on_select)
        splitter.addWidget(self.table)

        editor = QWidget()
        form = QVBoxLayout(editor)
        self.title = QLabel("Select a finding")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 12pt; font-weight: 800; color: #312e81;")
        form.addWidget(self.title)
        self.description = QTextEdit()
        self.description.setReadOnly(True)
        self.description.setMaximumHeight(95)
        self.description.setStyleSheet("background: #f1f5f9;")
        form.addWidget(QLabel("Verified analytical figures:"))
        form.addWidget(self.description)

        grid = QGridLayout()
        self.status = QComboBox()
        self.status.addItems(eng.STATUSES)
        self.evidence = QLineEdit()
        self.evidence.setPlaceholderText("e.g. WP C3.2, invoice INV-0912, bank statement Sep-25")
        grid.addWidget(QLabel("Status:"), 0, 0)
        grid.addWidget(self.status, 0, 1)
        grid.addWidget(QLabel("Evidence reference:"), 1, 0)
        grid.addWidget(self.evidence, 1, 1)
        form.addLayout(grid)
        self.mgmt = QTextEdit()
        self.mgmt.setPlaceholderText("Management's explanation, as received")
        self.mgmt.setMaximumHeight(90)
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Reviewer notes, procedures performed, conclusion on this finding")
        self.notes.setMaximumHeight(90)
        form.addWidget(QLabel("Management response:"))
        form.addWidget(self.mgmt)
        form.addWidget(QLabel("Reviewer notes:"))
        form.addWidget(self.notes)

        ai_box = QGroupBox("Draft explanation assistant (optional)")
        ai_layout = QVBoxLayout(ai_box)
        banner = QLabel(f"{eng.AI_LABEL}  |  Possible explanations are UNVERIFIED and require auditor review. "
                        "They are not audit evidence.")
        banner.setWordWrap(True)
        banner.setObjectName("aiBanner")
        ai_layout.addWidget(banner)
        self.ai_text = QTextEdit()
        self.ai_text.setMinimumHeight(120)
        self.ai_text.setPlaceholderText("No draft yet.")
        ai_layout.addWidget(self.ai_text)
        ai_buttons = QHBoxLayout()
        self.ai_button = button("Draft AI explanation", "orange", self.request_ai,
                                "Sends only this finding's verified figures to the AI service")
        ai_buttons.addWidget(self.ai_button)
        ai_buttons.addWidget(button("Insert standard inquiry prompts (no AI)", "teal", self.insert_standard))
        ai_layout.addLayout(ai_buttons)
        self.ai_reviewed = QCheckBox("I have reviewed this draft; it is unverified and not audit evidence")
        ai_layout.addWidget(self.ai_reviewed)
        form.addWidget(ai_box)

        actions = QHBoxLayout()
        actions.addWidget(button("Save finding", "green", self.save))
        if stage != "Final":
            nxt = eng.STAGES[eng.STAGES.index(stage) + 1]
            actions.addWidget(button(f"Save and move to {nxt}", None, self.move_next))
        actions.addStretch()
        form.addLayout(actions)
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setMaximumHeight(80)
        self.history.setStyleSheet("background: #f8fafc; font-size: 9pt;")
        form.addWidget(QLabel("History:"))
        form.addWidget(self.history)

        if stage == "Final":
            final_box = QGroupBox("Overall final review notes")
            fl = QVBoxLayout(final_box)
            self.final_notes = QTextEdit()
            self.final_notes.setMaximumHeight(80)
            self.final_notes.setPlaceholderText("Summary of the final analytical review (no audit opinion)")
            fl.addWidget(self.final_notes)
            fl.addWidget(button("Save final notes", "green", self.save_final_notes))
            form.addWidget(final_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(editor)
        splitter.addWidget(scroll)
        splitter.setSizes([520, 640])
        layout.addWidget(splitter, 1)      # the list/editor takes the spare height, not the intro
        self.set_editor_enabled(False)

    # ----- data helpers
    def visible_findings(self):
        findings = self.main.ws["findings"].values()
        if self.stage == "Final":
            rows = [f for f in findings if f["stage"] == "Final" or eng.is_unresolved(f)]
        else:
            rows = [f for f in findings if f["stage"] == self.stage]
        return sorted(rows, key=lambda f: f["id"])

    def current(self):
        return self.main.ws["findings"].get(self.current_id)

    def set_editor_enabled(self, on):
        for w in (self.status, self.evidence, self.mgmt, self.notes, self.ai_text,
                  self.ai_button, self.ai_reviewed):
            w.setEnabled(on)

    def refresh(self):
        rows = self.visible_findings()
        table_rows = []
        for f in rows:
            carried = f.get("carried_from", "")
            if self.stage == "Final" and f["stage"] != "Final":
                carried = f"Pending ({f['stage']})"
            table_rows.append([
                cell(f["id"], bold=True), cell(f["title"]),
                cell(f["status"], bg=STATUS_COLOURS.get(f["status"], "#fef3c7")),
                cell(f["stage"]), cell(carried, bg="#fce7f3" if carried else None),
                cell("Active" if f.get("flag_active", True) else "Below threshold",
                     fg="#b91c1c" if f.get("flag_active", True) else "#64748b"),
            ])
        self.table.blockSignals(True)
        fill_table(self.table, table_rows)
        self.table.blockSignals(False)
        unresolved = sum(1 for f in rows if eng.is_unresolved(f))
        self.summary.setText(f"{len(rows)} finding(s) | {unresolved} unresolved")
        if self.stage == "Final":
            self.final_notes.setPlainText(self.main.ws.get("final_notes", ""))
        ids = [f["id"] for f in rows]
        if self.current_id in ids:
            self.table.blockSignals(True)
            self.table.selectRow(ids.index(self.current_id))
            self.table.blockSignals(False)
            self.load_editor()
        else:
            self.current_id = None
            self.load_editor()

    def on_select(self):
        selected = self.table.selectedItems()
        if selected:
            self.current_id = self.table.item(selected[0].row(), 0).text()
        self.load_editor()

    def load_editor(self):
        f = self.current()
        if not f:
            self.title.setText("Select a finding")
            for w in (self.description, self.mgmt, self.notes, self.ai_text, self.history):
                w.clear()
            self.evidence.clear()
            self.set_editor_enabled(False)
            return
        self.set_editor_enabled(True)
        self.title.setText(f"{f['id']}  -  {f['title']}")
        text = f["description"]
        if not f.get("flag_active", True):
            text += "\n[No longer flagged at the current thresholds - figures shown are from the last flag.]"
        self.description.setPlainText(text)
        self.status.setCurrentText(f["status"])
        self.evidence.setText(f["evidence_ref"])
        self.mgmt.setPlainText(f["management_response"])
        self.notes.setPlainText(f["reviewer_notes"])
        self.ai_text.setPlainText(f.get("ai_draft", ""))
        self.ai_reviewed.setChecked(bool(f.get("ai_reviewed")))
        self.history.setPlainText("\n".join(f.get("history", [])))
        busy = self.worker is not None and self.worker.isRunning()
        self.ai_button.setEnabled(not busy)

    # ----- actions
    def save(self, quiet=False):
        f = self.current()
        if not f:
            return False
        ai_text = self.ai_text.toPlainText().strip()
        if self.ai_reviewed.isChecked() and not ai_text:
            self.ai_reviewed.setChecked(False)
        old_status = f["status"]
        f.update({"status": self.status.currentText(), "evidence_ref": self.evidence.text().strip(),
                  "management_response": self.mgmt.toPlainText().strip(),
                  "reviewer_notes": self.notes.toPlainText().strip(),
                  "ai_draft": ai_text, "ai_reviewed": self.ai_reviewed.isChecked(),
                  "updated": eng.now_text()})
        if old_status != f["status"]:
            f["history"].append(f"{eng.now_text()} Status '{old_status}' -> '{f['status']}' ({self.stage} tab)")
        self.main.persist()
        if not quiet:
            self.main.statusBar().showMessage(f"Saved {f['id']}", 4000)
        self.main.refresh_reviews()
        return True

    def move_next(self):
        f = self.current()
        if not f or not self.save(quiet=True):
            return
        nxt = eng.STAGES[eng.STAGES.index(f["stage"]) + 1] if f["stage"] != "Final" else "Final"
        f["history"].append(f"{eng.now_text()} Moved from {f['stage']} to {nxt}")
        f["stage"] = nxt
        self.current_id = None
        self.main.persist()
        self.main.refresh_reviews()
        self.main.statusBar().showMessage(f"{f['id']} moved to {nxt}", 4000)

    def add_manual(self):
        title, ok = QInputDialog.getText(self, "Manual finding", "Short title:")
        if not ok or not title.strip():
            return
        detail, ok = QInputDialog.getMultiLineText(self, "Manual finding", "Description:")
        if not ok:
            return
        n = 1 + sum(1 for k in self.main.ws["findings"] if k.startswith("M-"))
        fid = f"M-{n:03d}"
        self.main.ws["findings"][fid] = eng.blank_finding(fid, "Manual", "Manual", title.strip(),
                                                          detail.strip(), auto=False)
        self.current_id = fid
        self.main.persist()
        self.main.refresh_reviews()

    def carry_forward(self):
        moved = eng.carry_forward_unresolved(self.main.ws["findings"])
        self.main.persist()
        self.main.refresh_reviews()
        QMessageBox.information(self, "Carry forward", f"{moved} unresolved finding(s) carried into Final review.")

    def save_final_notes(self):
        self.main.ws["final_notes"] = self.final_notes.toPlainText().strip()
        self.main.persist()
        self.main.statusBar().showMessage("Final review notes saved", 4000)

    def insert_standard(self):
        f = self.current()
        if not f:
            return
        text = eng.standard_procedures_text(f) or "[No standard prompts for manual findings.]"
        existing = self.ai_text.toPlainText().strip()
        self.ai_text.setPlainText((existing + "\n\n" if existing else "") + text)

    def request_ai(self):
        f = self.current()
        if not f:
            return
        settings = eng.load_ai_settings()
        if not settings.get("enabled", True):
            QMessageBox.information(self, "AI disabled", "AI drafts are switched off in AI Settings. "
                                    "You can use 'Insert standard inquiry prompts' instead.")
            return
        verified = (self.main.data is not None and not self.main.data.has_failures
                    and f.get("flag_active", True))
        if self.ai_text.toPlainText().strip() and QMessageBox.question(
                self, "Replace draft?", "Replace the existing draft text?") != QMessageBox.StandardButton.Yes:
            return
        self.save(quiet=True)
        self.ai_button.setEnabled(False)
        self.ai_button.setText("Drafting... (app stays usable)")
        self.worker = AIWorker(dict(f), verified, settings.get("model"))
        self.worker.finished_draft.connect(self.ai_done)
        self.worker.start()

    def ai_done(self, fid, text, error):
        self.ai_button.setText("Draft AI explanation")
        self.ai_button.setEnabled(True)
        f = self.main.ws["findings"].get(fid)
        if f and text:
            f["ai_draft"], f["ai_reviewed"] = text, False
            f["history"].append(f"{eng.now_text()} AI draft generated (unreviewed)")
            self.main.persist()
            self.main.refresh_reviews()
            self.main.statusBar().showMessage(f"AI draft added to {fid} - auditor review required", 6000)
        elif error:
            answer = QMessageBox.warning(
                self, "AI draft unavailable",
                f"{error}\n\nThe application continues to work normally.\n"
                "Insert the standard (non-AI) inquiry prompts instead?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes and fid == self.current_id:
                self.insert_standard()


# --------------------------------------------------------------------------
# 5. Main window
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.base_dir = Path(__file__).resolve().parent
        self.workspace_path = self.base_dir / "review_workspace.json"
        self.tables = {name: None for name in eng.SCHEMAS}
        self.data, self.analysis = None, None
        self.thresholds = {k: dict(v) for k, v in eng.DEFAULT_THRESHOLDS.items()}
        self.ws = self.open_workspace()

        self.setWindowTitle(f"{APP_TITLE}  -  {eng.DEMO_LABEL}")
        self.resize(1380, 880)
        page = QWidget()
        page.setObjectName("page")
        root = QVBoxLayout(page)
        root.addWidget(self.build_header())
        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_data_tab(), "1  Data && Validation")
        self.tabs.addTab(self.build_threshold_tab(), "2  Thresholds")
        self.tabs.addTab(self.build_analytics_tab(), "3  Analytics")
        self.reviews = {stage: ReviewPanel(self, stage) for stage in eng.STAGES}
        self.tabs.addTab(self.reviews["Preliminary"], "4  Preliminary review")
        self.tabs.addTab(self.reviews["Substantive/Interim"], "5  Substantive / Interim")
        self.tabs.addTab(self.reviews["Final"], "6  Final review")
        self.tabs.currentChanged.connect(lambda _i: self.refresh_reviews())
        root.addWidget(self.tabs)
        self.setCentralWidget(page)
        self.statusBar().showMessage(f"{eng.DEMO_LABEL}  |  Workspace: {self.workspace_path}")

        self.reload_remembered_files()
        self.refresh_reviews()

    # ----- layout builders
    def build_header(self):
        header = QFrame()
        header.setStyleSheet(
            "QFrame { border-radius: 14px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #4338ca, stop:0.5 #7c3aed, stop:1 #db2777); }"
            "QLabel { color: white; background: transparent; }")
        layout = QHBoxLayout(header)
        text = QVBoxLayout()
        title = QLabel(APP_TITLE)
        title.setStyleSheet("font-size: 19pt; font-weight: 800;")
        subtitle = QLabel("Trial balance, monthly sales, budget and threshold analytics  |  AED, unscaled  |  "
                          "Sand Dune General Trading LLC (fictional)")
        subtitle.setStyleSheet("font-size: 10pt;")
        text.addWidget(title)
        text.addWidget(subtitle)
        layout.addLayout(text)
        layout.addStretch()
        badge = QLabel(eng.DEMO_LABEL)
        badge.setStyleSheet("background: #fde047; color: #713f12; font-weight: 800; padding: 6px 12px;"
                            "border-radius: 12px;")
        layout.addWidget(badge)
        layout.addWidget(button("AI settings", "light", self.open_ai_settings))
        layout.addWidget(button("Export findings CSV", "light", self.export_csv))
        layout.addWidget(button("About", "light", self.about))
        return header

    def build_data_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        box = QGroupBox("Upload the workbook's CSV exports")
        grid = QGridLayout(box)
        self.file_labels = {}
        for row, name in enumerate(eng.SCHEMAS):
            label = QLabel(f"<b>{name}.csv</b>")
            path = QLabel("Not loaded")
            path.setStyleSheet("color: #64748b;")
            self.file_labels[name] = path
            grid.addWidget(label, row, 0)
            grid.addWidget(path, row, 1)
            grid.addWidget(button("Browse...", "teal", lambda _c=False, n=name: self.browse(n)), row, 2)
        grid.setColumnStretch(1, 1)
        layout.addWidget(box)

        actions = QHBoxLayout()
        actions.addWidget(button("Load sample data (fictional)", "pink", self.load_sample))
        actions.addWidget(button("Load all four from a folder...", "teal", self.load_folder))
        actions.addWidget(button("Run validation & analysis", "green", self.run))
        actions.addStretch()
        layout.addLayout(actions)

        self.banner = QLabel("Load the four CSV files, then run validation & analysis.")
        self.banner.setWordWrap(True)
        self.banner.setObjectName("intro")
        layout.addWidget(self.banner)
        self.validation_table = make_table(["Result", "Area", "Check", "Detail"], stretch_col=3)
        layout.addWidget(self.validation_table, 1)
        return w

    def build_threshold_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        note = QLabel("Thresholds are read from Thresholds.csv. They are ILLUSTRATIVE, not industry standards. "
                      "Change the comparison or value below and click Apply; overrides are saved in the workspace.")
        note.setWordWrap(True)
        note.setObjectName("intro")
        layout.addWidget(note)
        self.threshold_table = make_table(["Rule", "Metric", "Comparison", "Threshold", "Unit", "Source",
                                           "Rationale"], stretch_col=6)
        self.threshold_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.threshold_table)
        actions = QHBoxLayout()
        actions.addWidget(button("Apply thresholds & re-run", "green", self.apply_thresholds))
        actions.addWidget(button("Reset to CSV values", "orange", self.reset_thresholds))
        actions.addStretch()
        layout.addLayout(actions)
        return w

    def build_analytics_tab(self):
        inner = QTabWidget()
        # Ratios
        ratios = QWidget()
        rl = QVBoxLayout(ratios)
        cards = QHBoxLayout()
        self.card_gpm = RatioCard("Gross profit margin", ("#7c3aed", "#db2777"))
        self.card_cr = RatioCard("Current ratio", ("#0891b2", "#2563eb"))
        self.card_rd = RatioCard("Receivable days", ("#ea580c", "#e11d48"))
        self.card_rev = RatioCard("Revenue (AED)", ("#059669", "#0d9488"))
        for card in (self.card_rev, self.card_gpm, self.card_cr, self.card_rd):
            cards.addWidget(card)
        rl.addLayout(cards)
        self.ratio_table = make_table(["Measure", "Prior year", "Current year", "Change", "Note"], stretch_col=4)
        rl.addWidget(self.ratio_table)
        vat = QLabel(eng.VAT_BASIS_NOTE)
        vat.setWordWrap(True)
        vat.setObjectName("intro")
        rl.addWidget(vat)
        inner.addTab(ratios, "Ratios")
        # Annual variances
        self.annual_table = make_table(["Code", "Account", "Category", "Prior year", "Current year",
                                        "Change (AED)", "Change %", "Flag / note"], stretch_col=7)
        inner.addTab(self.annual_table, "Annual variances")
        # Budget
        self.budget_table = make_table(["Code", "Account", "Category", "Actual", "Budget", "Variance (AED)",
                                        "Variance %", "Direction", "Flag / note"], stretch_col=8)
        inner.addTab(self.budget_table, "Actual vs budget")
        # Monthly
        monthly = QWidget()
        ml = QVBoxLayout(monthly)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart = SalesChart()
        splitter.addWidget(self.chart)
        self.monthly_table = make_table(["Month", "Prior year", "Current year", "Change (AED)", "Change %",
                                         "Flag / note"], stretch_col=5)
        splitter.addWidget(self.monthly_table)
        splitter.setSizes([420, 260])
        ml.addWidget(splitter)
        inner.addTab(monthly, "Monthly sales chart")
        return inner

    # ----- workspace
    def open_workspace(self):
        try:
            return eng.load_workspace(self.workspace_path)
        except (OSError, ValueError) as exc:
            backup = self.workspace_path.with_suffix(".corrupt.json")
            try:
                os.replace(self.workspace_path, backup)
            except OSError:
                pass
            QMessageBox.warning(None, "Workspace", f"The saved workspace could not be read ({exc}).\n"
                                f"It was moved to {backup.name} and a new workspace was started.")
            return eng.new_workspace()

    def persist(self):
        try:
            eng.save_workspace(self.workspace_path, self.ws)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save the workspace:\n{exc}")

    def refresh_reviews(self):
        for panel in self.reviews.values():
            panel.refresh()

    # ----- loading files
    def set_file(self, name, path):
        try:
            self.tables[name] = eng.read_csv(path)
        except (OSError, ValueError, UnicodeError) as exc:
            self.tables[name] = None
            self.file_labels[name].setText(f"Could not read: {exc}")
            self.file_labels[name].setStyleSheet("color: #b91c1c;")
            return False
        rows = len(self.tables[name]["rows"])
        self.file_labels[name].setText(f"{path}   ({rows} rows)")
        self.file_labels[name].setStyleSheet("color: #047857; font-weight: 600;")
        self.ws["files"][name] = str(path)
        return True

    def browse(self, name):
        path, _ = QFileDialog.getOpenFileName(self, f"Select {name}.csv", str(self.base_dir), "CSV files (*.csv)")
        if path:
            self.set_file(name, path)
            self.persist()

    def load_from_dir(self, folder):
        found = 0
        files = [p for p in Path(folder).glob("*.csv")]
        for name in eng.SCHEMAS:
            exact = [p for p in files if p.stem.lower() == name.lower()]
            loose = [p for p in files if name.lower() in p.stem.lower()]
            match = (exact or loose or [None])[0]
            if match and self.set_file(name, match):
                found += 1
        return found

    def load_sample(self):
        folder = self.base_dir / "sample_data"
        if self.load_from_dir(folder) < 4:
            QMessageBox.warning(self, "Sample data", f"Some sample files were not found in {folder}.")
        self.run()

    def load_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Folder containing the four CSV exports", str(self.base_dir))
        if folder:
            found = self.load_from_dir(folder)
            self.statusBar().showMessage(f"{found} of 4 files loaded from {folder}", 6000)
            self.run()

    def reload_remembered_files(self):
        loaded = 0
        for name, path in self.ws.get("files", {}).items():
            if name in self.tables and Path(path).exists():
                loaded += self.set_file(name, path)
        if loaded:
            self.run(quiet=True)

    # ----- thresholds
    def effective_thresholds(self):
        base = self.data.thresholds if self.data else eng.DEFAULT_THRESHOLDS
        result = {k: dict(v) for k, v in base.items()}
        for rule, override in self.ws.get("threshold_overrides", {}).items():
            if rule in result:
                result[rule].update(override)
                result[rule]["Source"] = "User override"
        return result

    def fill_thresholds(self):
        t = self.threshold_table
        t.setRowCount(0)
        csv_values = self.data.thresholds if self.data else eng.DEFAULT_THRESHOLDS
        for r, (rule, d) in enumerate(sorted(self.thresholds.items())):
            t.insertRow(r)
            t.setItem(r, 0, cell(rule, bold=True))
            t.setItem(r, 1, cell(d["Metric"]))
            combo = QComboBox()
            combo.addItems(list(eng.OPERATORS))
            combo.setCurrentText(d["Comparison"])
            t.setCellWidget(r, 2, combo)
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 100000)
            spin.setDecimals(2)
            spin.setValue(float(d["Threshold"]))
            t.setCellWidget(r, 3, spin)
            t.setItem(r, 4, cell(d["Unit"]))
            source = d.get("Source", "Thresholds.csv" if self.tables["Thresholds"] else "Built-in default")
            t.setItem(r, 5, cell(source, bg="#fde68a" if source == "User override" else "#dbeafe"))
            rationale = d.get("Rationale") or csv_values.get(rule, {}).get("Rationale", "")
            t.setItem(r, 6, cell(rationale))
        t.resizeRowsToContents()

    def apply_thresholds(self):
        csv_values = self.data.thresholds if self.data else eng.DEFAULT_THRESHOLDS
        overrides = {}
        for r in range(self.threshold_table.rowCount()):
            rule = self.threshold_table.item(r, 0).text()
            comp = self.threshold_table.cellWidget(r, 2).currentText()
            value = self.threshold_table.cellWidget(r, 3).value()
            base = csv_values[rule]
            if comp != base["Comparison"] or abs(value - float(base["Threshold"])) > 1e-9:
                overrides[rule] = {"Comparison": comp, "Threshold": value}
        self.ws["threshold_overrides"] = overrides
        self.persist()
        self.run()
        self.statusBar().showMessage(f"Thresholds applied ({len(overrides)} override(s))", 6000)

    def reset_thresholds(self):
        self.ws["threshold_overrides"] = {}
        self.persist()
        self.run()

    # ----- analysis
    def run(self, quiet=False):
        self.data = eng.build_data(self.tables)
        self.thresholds = self.effective_thresholds()
        self.analysis = eng.run_analysis(self.data, self.thresholds)
        self.fill_validation()
        self.fill_thresholds()
        self.fill_analytics()
        if self.analysis["cy"] is not None and not self.data.has_failures:
            eng.merge_flags(self.ws["findings"], self.analysis["flags"])
        self.persist()
        self.refresh_reviews()
        if not quiet and self.analysis["cy"] is not None:
            self.statusBar().showMessage(f"Analysis complete: {len(self.analysis['flags'])} flag(s) at current "
                                         "thresholds", 6000)

    def fill_validation(self):
        rows, counts = [], {"PASS": 0, "FAIL": 0, "WARN": 0}
        for c in self.data.checks:
            counts[c["result"]] += 1
            bg = {"PASS": PASS_BG, "FAIL": FAIL_BG, "WARN": WARN_BG}[c["result"]]
            rows.append([cell(c["result"], bg=bg, bold=True), cell(c["area"]), cell(c["check"]),
                         cell(c["detail"])])
        fill_table(self.validation_table, rows)
        if counts["FAIL"]:
            self.banner.setText(f"{counts['FAIL']} check(s) FAILED, {counts['WARN']} warning(s). Figures are "
                                "NOT verified: findings were not updated and AI drafts are disabled until the "
                                "data is corrected. Calculations that depend on missing values show 'n/a'.")
            self.banner.setStyleSheet("background: #fee2e2; border-left: 5px solid #dc2626; padding: 8px;")
        else:
            self.banner.setText(f"All {counts['PASS']} checks passed ({counts['WARN']} warning(s)). "
                                f"Figures verified for analysis. {eng.DEMO_LABEL}.")
            self.banner.setStyleSheet("background: #dcfce7; border-left: 5px solid #16a34a; padding: 8px;")

    def fill_analytics(self):
        a = self.analysis
        py, cy = a["py"], a["cy"]
        if cy is None:
            return
        rp, rc = a["ratios"][py], a["ratios"][cy]

        def delta(cur, pri, fmt):
            return fmt(cur - pri) if cur is not None and pri is not None else "n/a"

        self.card_rev.value.setText(eng.fmt_aed(rc["revenue"]))
        self.card_rev.sub.setText(f"FY{py}: {eng.fmt_aed(rp['revenue'])}  |  FY{cy}")
        self.card_gpm.value.setText(eng.fmt_pct(rc["gross_margin_pct"], signed=False)
                                    if rc["gross_margin_pct"] is not None else rc["gross_margin_note"])
        self.card_gpm.sub.setText(f"FY{py}: {eng.fmt_pct(rp['gross_margin_pct'], signed=False)}  |  change "
                                  f"{delta(rc['gross_margin_pct'], rp['gross_margin_pct'], lambda v: f'{v:+.1f} pts')}")
        self.card_cr.value.setText(f"{rc['current_ratio']:.2f}x" if rc["current_ratio"] is not None
                                   else rc["current_ratio_note"])
        self.card_cr.sub.setText(f"FY{py}: {eng.fmt_num(rp['current_ratio'])}x  |  change "
                                 f"{delta(rc['current_ratio'], rp['current_ratio'], lambda v: f'{v:+.2f}')}")
        self.card_rd.value.setText(f"{rc['receivable_days']:.1f} days" if rc["receivable_days"] is not None
                                   else rc["receivable_days_note"])
        rd_change = delta(rc["receivable_days"], rp["receivable_days"], lambda v: f"{v:+.1f} days")
        flagged = any(f["rule"] == "R02" for f in a["flags"])
        self.card_rd.sub.setText(f"FY{py}: {eng.fmt_num(rp['receivable_days'], 1)}  |  change {rd_change}"
                                 + ("  |  FLAGGED (R02)" if flagged else ""))

        measures = [
            ("Revenue (AED)", "revenue", eng.fmt_aed, ""),
            ("Cost of sales (AED)", "cost_of_sales", eng.fmt_aed, ""),
            ("Gross profit (AED)", "gross_profit", eng.fmt_aed, ""),
            ("Gross profit margin %", "gross_margin_pct", lambda v: eng.fmt_pct(v, signed=False), "gross_margin_note"),
            ("Current assets (AED)", "current_assets", eng.fmt_aed, ""),
            ("Current liabilities (AED)", "current_liabilities", eng.fmt_aed, ""),
            ("Current ratio (x)", "current_ratio", eng.fmt_num, "current_ratio_note"),
            ("Trade receivables 1100 (AED, incl. VAT)", "trade_receivables", eng.fmt_aed, ""),
            ("Annual credit sales (AED, excl. VAT)", "credit_sales", eng.fmt_aed, ""),
            ("Receivable days", "receivable_days", lambda v: eng.fmt_num(v, 1), "receivable_days_note"),
        ]
        rows = []
        for label, key, fmt, note_key in measures:
            pv, cv = rp[key], rc[key]
            change = cv - pv if pv is not None and cv is not None else None
            notes = [n for n in (rp.get(note_key) if note_key else "", rc.get(note_key) if note_key else "") if n]
            if change is None:
                change_text = "n/a"
            elif key == "gross_margin_pct":
                change_text = f"{change:+.1f} pts"
            else:
                change_text = fmt(change)
            rows.append([cell(label, bold=True), cell(fmt(pv) if pv is not None else "n/a", True),
                         cell(fmt(cv) if cv is not None else "n/a", True),
                         cell(change_text, True),
                         cell("; ".join(sorted(set(notes))))])
        self.ratio_table.setHorizontalHeaderLabels(["Measure", f"FY{py}", f"FY{cy}", "Change", "Note"])
        fill_table(self.ratio_table, rows)

        flag_ids = {f["id"] for f in a["flags"]}
        rows, colours = [], []
        for r in a["annual"]:
            fid = f"R03-{cy}-{r['code']}"
            note = f"FLAG R03 ({self.thresholds['R03']['Comparison']} {self.thresholds['R03']['Threshold']:g}%)" \
                if fid in flag_ids else r["note"]
            rows.append([r["code"], r["name"], r["category"], cell(eng.fmt_aed(r["py"]), True),
                         cell(eng.fmt_aed(r["cy"]), True), cell(eng.fmt_aed(r["change"]), True),
                         cell(eng.fmt_pct(r["pct"]), True), cell(note, bold=fid in flag_ids)])
            colours.append(FLAG_BG if fid in flag_ids else None)
        self.annual_table.setHorizontalHeaderLabels(["Code", "Account", "Category", f"FY{py}", f"FY{cy}",
                                                     "Change (AED)", "Change %", "Flag / note"])
        fill_table(self.annual_table, rows, colours)

        rows, colours = [], []
        for r in a["budget"]:
            fid = f"R04-{cy}-{r['code']}"
            note = f"FLAG R04 ({self.thresholds['R04']['Comparison']} {self.thresholds['R04']['Threshold']:g}%)" \
                if fid in flag_ids else r["note"]
            dir_colour = "#047857" if r["direction"] == "Favourable" else ("#b91c1c" if r["direction"] == "Adverse" else None)
            rows.append([r["code"], r["name"], r["category"], cell(eng.fmt_aed(r["actual"]), True),
                         cell(eng.fmt_aed(r["budget"]), True), cell(eng.fmt_aed(r["variance"]), True),
                         cell(eng.fmt_pct(r["pct"]), True), cell(r["direction"], fg=dir_colour, bold=True),
                         cell(note, bold=fid in flag_ids)])
            colours.append(FLAG_BG if fid in flag_ids else None)
        self.budget_table.setHorizontalHeaderLabels(["Code", "Account", "Category", f"Actual FY{cy}",
                                                     f"Budget FY{cy}", "Variance (AED)", "Variance %",
                                                     "Direction", "Flag / note"])
        fill_table(self.budget_table, rows, colours)

        rows, colours = [], []
        for m in a["monthly"]:
            note = f"FLAG R01 ({self.thresholds['R01']['Comparison']} {self.thresholds['R01']['Threshold']:g}%)" \
                if m["flag"] else m["note"]
            rows.append([m["month"], cell(eng.fmt_aed(m["py"]), True), cell(eng.fmt_aed(m["cy"]), True),
                         cell(eng.fmt_aed(m["change"]), True), cell(eng.fmt_pct(m["pct"]), True),
                         cell(note, bold=m["flag"])])
            colours.append(FLAG_BG if m["flag"] else None)
        self.monthly_table.setHorizontalHeaderLabels(["Month", f"FY{py}", f"FY{cy}", "Change (AED)", "Change %",
                                                      "Flag / note"])
        fill_table(self.monthly_table, rows, colours)
        try:
            self.chart.draw_sales(a["monthly"], py, cy, self.thresholds)
        except Exception as exc:  # a chart problem must not stop the review
            self.statusBar().showMessage(f"Chart could not be drawn: {exc}", 8000)

    # ----- misc actions
    def export_csv(self):
        if not self.ws["findings"]:
            QMessageBox.information(self, "Export", "There are no findings to export yet.")
            return
        default = str(self.base_dir / "findings_register.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export findings register", default, "CSV files (*.csv)")
        if not path:
            return
        try:
            eng.export_findings_csv(path, self.ws["findings"])
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", f"Could not write the file (is it open in Excel?)\n{exc}")
            return
        QMessageBox.information(self, "Export", f"Findings register exported to:\n{path}\n\n{eng.DEMO_LABEL}")

    def open_ai_settings(self):
        dialog = AISettingsDialog(self)
        if dialog.exec():
            try:
                dialog.save()
                self.statusBar().showMessage("AI settings saved (outside the source code)", 5000)
            except OSError as exc:
                QMessageBox.critical(self, "AI settings", f"Could not save settings:\n{exc}")

    def about(self):
        QMessageBox.information(
            self, "About",
            f"{APP_TITLE}\n\n{eng.DEMO_LABEL}.\n\n"
            "Analytical review support tool for a fictional UAE trading company. It highlights "
            "movements for auditor follow-up. It does NOT provide an audit opinion and does NOT "
            "reach conclusions about fraud or misstatement.\n\n"
            f"AI commentary is labelled '{eng.AI_LABEL}'; possible explanations are unverified "
            "and must be reviewed by the auditor.\n\n"
            f"Findings are saved locally in:\n{self.workspace_path}")

    def closeEvent(self, event):
        self.persist()
        for panel in self.reviews.values():
            if panel.worker is not None and panel.worker.isRunning():
                panel.worker.wait(3000)
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    app.exec()       # no sys.exit(), so IDLE's shell stays open afterwards


if __name__ == "__main__":
    main()
