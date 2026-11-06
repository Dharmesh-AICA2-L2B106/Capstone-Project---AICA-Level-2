"""Qt compatibility wrapper providing unified imports for PyQt6 and PySide6."""

import sys

QT_API = None

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import Qt, QDate, QDateTime, QSize, QRect, pyqtSignal as Signal, pyqtSlot as Slot
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
        QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QStackedWidget,
        QProgressBar, QScrollArea, QFrame, QSplitter, QMessageBox, QFileDialog,
        QCheckBox, QSpinBox, QDateEdit, QToolButton, QGroupBox, QStatusBar, QButtonGroup,
        QInputDialog, QStyledItemDelegate, QStyleOptionViewItem, QStyle, QMenu,
        QTableWidgetSelectionRange
    )
    from PyQt6.QtGui import QIcon, QFont, QColor, QPalette, QAction, QPainter, QBrush, QPen, QPixmap
    QT_API = "PyQt6"
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from PySide6.QtCore import Qt, QDate, QDateTime, QSize, QRect, Signal, Slot
        from PySide6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
            QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox,
            QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QStackedWidget,
            QProgressBar, QScrollArea, QFrame, QSplitter, QMessageBox, QFileDialog,
            QCheckBox, QSpinBox, QDateEdit, QToolButton, QGroupBox, QStatusBar, QButtonGroup,
            QInputDialog, QStyledItemDelegate, QStyleOptionViewItem, QStyle, QMenu,
        QTableWidgetSelectionRange
        )
        from PySide6.QtGui import QIcon, QFont, QColor, QPalette, QAction, QPainter, QBrush, QPen, QPixmap
        QT_API = "PySide6"
    except ImportError as exc:
        raise RuntimeError(
            "Neither PyQt6 nor PySide6 is installed. Please install PyQt6 or PySide6."
        ) from exc
