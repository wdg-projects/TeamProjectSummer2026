import sys

from PySide6 import QtWidgets

from common_utils import PythonIODevice
from widgets.uiutils import find, common_ui_loader

import widgets
widgets.register_all()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    with open("mainwindow.ui", "rb") as f:
        window = common_ui_loader().load(PythonIODevice(f))

    # Temporary code
    mdi = find(window, "uiEditArea", QtWidgets.QMdiArea)
    _ = mdi.addSubWindow(QtWidgets.QLabel("Hello, world!", mdi))

    window.show()

    sys.exit(app.exec())
