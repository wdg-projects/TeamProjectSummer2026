import io
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QWidget

from widgets.uiutils import load_ui

class EditedSubwindow(QObject):
    # path: str
    data: str
    contents: QWidget

    def __init__(self, raw_data: bytes, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # self.path = path
        # with open(path, "rb") as f:
            # raw_data = f.read()
        self.data = raw_data.decode("utf8")
        self.contents = load_ui(QWidget, io.BytesIO(raw_data))
