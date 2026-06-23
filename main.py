import sys
from typing import final

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import QObject, QPoint, Qt, pyqtSlot

from widgets.assistantpanel import AssistantPanel
from widgets.uiutils import find, load_ui
from edited_subwindow import EditedSubwindow

from svg_to_qt_ui import SVGToQtUI

@final
class ContextMenu(QObject):

    def __init__(self, mdi: QtWidgets.QMdiArea, edited_subwindow: EditedSubwindow, assistant_panel: AssistantPanel, parent: QObject | None) -> None:
        super().__init__(parent)
        self.point = QPoint(0, 0)

        self.menu = QtWidgets.QMenu(mdi)
        self.menu.addAction("Ask...", self.on_ask)

        self.mdi = mdi
        self.mdi.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        _ = self.mdi.customContextMenuRequested.connect(self.on_open)

        self.edited_subwindow = edited_subwindow
        self.assistant_panel = assistant_panel

        self.dialog = QtWidgets.QDialog(mdi)
        self.dialog.setWindowTitle("What do you want to ask the assistant?")
        self.dialog.setModal(True)

        vbox = QtWidgets.QHBoxLayout(self.dialog)
        self.dialog.setLayout(vbox)

        self.edit = QtWidgets.QLineEdit(self.dialog)
        self.edit.setFixedWidth(700)
        vbox.addWidget(self.edit)

        btn = QtWidgets.QPushButton("Ask!", self.dialog)
        _ = btn.clicked.connect(self.on_clicked)
        vbox.addWidget(btn)

        self.widget: QtWidgets.QWidget | None = None

    @pyqtSlot(QPoint)
    def on_open(self, point: QPoint) -> None:
        w = self.mdi.viewport()
        assert w
        self.point = w.mapToGlobal(point)
        self.menu.popup(self.point)

    @pyqtSlot()
    def on_ask(self) -> None:
        self.widget = QtWidgets.QApplication.widgetAt(self.point)
        if self.widget is not None:
            self.dialog.show()

    @pyqtSlot()
    def on_clicked(self) -> None:
        widget = self.widget
        assert widget is not None
        self.edited_subwindow.highlighted_widget = widget
        self.assistant_panel.controller.manual_send(f"(I have selected a widget) {self.edit.text()}")
        _ = self.dialog.close()

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

    menu = ContextMenu(mdi, edited_subwindow, assistant_panel, mdi)

    window.show()
    sys.exit(app.exec())
