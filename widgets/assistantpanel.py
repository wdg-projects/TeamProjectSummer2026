from dataclasses import dataclass, field

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QLineEdit, QListView, QMessageBox, QPushButton, QWidget
from ollama import Message

from asyncbridge import AsyncTask
from services import ollama_adapter
from widgets.modeldownload import ModelDownload

from .uiutils import common_ui_loader, preload_ui, load_and_apply_ui, SOURCE_FIELD

def register_all() -> None:
    common_ui_loader().registerCustomWidget(AssistantPanel)

ASSISTANT_PANEL_UI = preload_ui("assistantpanel.ui")

@dataclass
class UI_AssistantPanel:
    widget: QWidget = field(metadata=SOURCE_FIELD)

    chat_log: QListView
    entry: QLineEdit
    send: QPushButton

class AssistantPanel(QWidget):
    new_message: Signal = Signal(str, str)

    ui: UI_AssistantPanel
    mdl_mgr: AsyncTask
    msg_mgr: AsyncTask | None
    item_model: QStandardItemModel

    models_present: bool

    def __init__(self, parent: QWidget | None = None) -> None:
        global ui
        super().__init__(parent)
        self.ui = load_and_apply_ui(ASSISTANT_PANEL_UI(), self, UI_AssistantPanel)
        self.models_present = False
        self.msg_mgr = None
        self.item_model = QStandardItemModel(self)
        _ = self.item_model.insertColumns(0, 2)

        self.ui.chat_log.setModel(self.item_model)
        _ = self.ui.send.pressed.connect(self.on_send)
        _ = self.new_message.connect(self.on_new_message)

        self.ensure_model()

    @Slot(str, str)
    def on_new_message(self, role: str, text: str) -> None:
        _ = self.item_model.insertRow(row := self.item_model.rowCount())
        self.item_model.setItem(row, 0, QStandardItem(role))
        self.item_model.setItem(row, 1, QStandardItem(text))

    def on_send(self) -> None:
        if not self.models_present:
            return
        if self.msg_mgr is not None:
            return

        user_message = self.ui.entry.text()
        self.ui.entry.setText("")

        self.new_message.emit("user", user_message)

        messages: list[Message] = []
        for i in range(self.item_model.rowCount()):
            role = self.item_model.item(i, 0).text()
            content = self.item_model.item(i, 1).text()
            messages.append(Message(role=role, content=content))

        async def fetch_response():
            reply = await ollama_adapter.chat("deepseek-r1:latest", messages)
            self.new_message.emit("assistant", reply)
            self.msg_mgr = None

        self.msg_mgr = AsyncTask(fetch_response())
        self.msg_mgr.start()

    def ensure_model(self) -> None:
        self.mdl_mgr = AsyncTask(ollama_adapter.get_missing_models({"deepseek-r1:latest", "llama3.1:latest"}))
        _ = self.mdl_mgr.complete.connect(self.model_tested)
        _ = self.mdl_mgr.thrown.connect(self.model_test_error)
        self.mdl_mgr.start()

    @Slot(Exception)
    def model_test_error(self, exc: Exception) -> None:
        # TODO: Of course, don't require the user to launch ollama manually!!
        _ = QMessageBox.critical(self, "Error", f"There was a problem trying to check ollama status: {type(exc).__qualname__}: {exc}.", QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok)
        QApplication.quit()

    @Slot(list)
    def model_tested(self, missing: list[str]) -> None:
        if not missing:
            self.models_present = True
            return

        missing_text = ", ".join(missing)
        pressed = QMessageBox.critical(self, "Models missing", f"You are missing the following models: {missing_text}\nBefore using this utility, you need to download the missing models. Proceed?", QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok)
        match pressed:
            case QMessageBox.StandardButton.Cancel:
                QApplication.quit()
            case QMessageBox.StandardButton.Ok:
                download_panel = ModelDownload(missing, self)
                download_panel.show()
                _ = download_panel.closed.connect(lambda: self.ensure_model())
            case _:
                assert False
