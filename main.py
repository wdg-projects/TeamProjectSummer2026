import sys

from PyQt6 import QtWidgets

from widgets.assistantpanel import AssistantPanel
from widgets.uiutils import find, load_ui
from edited_subwindow import EditedSubwindow

from svg_to_qt_ui import SVGToQtUI

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    with open("mainwindow.ui", "rb") as f:
        window = load_ui(QtWidgets.QMainWindow, f)

    # Temporary code
    with open(sys.argv[1] if len(sys.argv) > 1 else "demo_input.svg", "r", encoding="utf8", errors="replace") as f:
        ui_data = SVGToQtUI().convert_str(f.read())

    edited_subwindow = EditedSubwindow(ui_data.encode("utf8"))

    assistant_panel = find(window, "assistantPanel", AssistantPanel)
    assistant_panel.controller.inject_edited_subwindow(edited_subwindow)

    mdi = find(window, "uiEditArea", QtWidgets.QMdiArea)
    mdi_subwindow = mdi.addSubWindow(edited_subwindow.contents)
    assert mdi_subwindow is not None
    mdi_subwindow.setFixedSize(900, 650)

    window.show()
    sys.exit(app.exec())
