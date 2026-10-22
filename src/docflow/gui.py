"""Public Qt entrypoint; the workspace lives in docflow.ui.window."""
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from .ui.window import MainWindow, GenerationWorker

def configure_app(app):
    app.setApplicationName('DocFlow Lite')
    app.setStyle('Fusion')
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)

def main():
    app=QApplication(sys.argv)
    configure_app(app)
    window=MainWindow();window.show()
    return app.exec()

if __name__=='__main__':
    raise SystemExit(main())
