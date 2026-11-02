"""Regenerate assets/app_icon.png and assets/app_icon.ico from assets/app_icon.svg."""

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "assets"

if __name__ == "__main__":
    QGuiApplication(sys.argv)
    renderer = QSvgRenderer(QByteArray((ASSETS / "app_icon.svg").read_bytes()))
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    image.save(str(ASSETS / "app_icon.png"))
    Image.open(ASSETS / "app_icon.png").save(ASSETS / "app_icon.ico",
                                             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icons written to", ASSETS)
