"""PDF Play Station 2.0 - start the application.

    run.bat                               normal start (sets up components on first run)
    python PDF_Play_Station.py            start directly from the private .venv
    python PDF_Play_Station.py --version  print the version
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str]) -> int:
    from app import APP_NAME, APP_VERSION
    if "--version" in argv:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    # [EXE build, change 3] hidden self-test that proves the packaged program works;
    # never runs on a normal double-click.
    if "--selftest" in argv:
        from app.selftest import run_selftest
        return run_selftest(argv)

    from app import logger
    log = logger.setup()
    log.info("Starting %s %s (Python %s)", APP_NAME, APP_VERSION, sys.version.split()[0])

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtWidgets import QApplication

    from app import theme
    from app.icons import app_icon
    from app.shell import MainWindow

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(theme.stylesheet(str(ROOT / "assets" / "check.svg")))
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    code = app.exec()
    log.info("Closed (exit code %s)", code)
    return code


if __name__ == "__main__":
    # [EXE build, change 1] Required in a frozen EXE: background jobs run in worker
    # processes started from this same EXE; without this each would open a new window.
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv))
