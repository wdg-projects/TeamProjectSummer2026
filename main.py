import sys

from PyQt6 import QtWidgets

from widgets.uiutils import find, load_ui

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    with open("mainwindow.ui", "rb") as f:
        window = load_ui(QtWidgets.QMainWindow, f)

    # Temporary code
    mdi = find(window, "uiEditArea", QtWidgets.QMdiArea)
    _ = mdi.addSubWindow(QtWidgets.QLabel("Hello, world!", mdi))

    window.show()
    sys.exit(app.exec())
