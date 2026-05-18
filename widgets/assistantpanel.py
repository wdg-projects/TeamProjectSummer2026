from dataclasses import dataclass, field
from typing import cast

from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QApplication, QLineEdit, QListView, QMessageBox, QPushButton, QWidget

from ollama import Message

from asyncbridge import AsyncTask
from services import ollama_adapter
from widgets.modeldownload import ModelDownload
from common_utils import TypedSignal, typed_signal, typed_slot

from .uiutils import preload_ui, load_and_apply_ui, SOURCE_FIELD

ASSISTANT_PANEL_UI = preload_ui("assistantpanel.ui")

@dataclass
class UI_AssistantPanel:
    widget: QWidget = field(metadata=SOURCE_FIELD)

    chat_log: QListView
    entry: QLineEdit
    send: QPushButton

class AssistantPanel(QWidget):
    new_message: TypedSignal[str, str] = typed_signal(str, str) # = Signal(str, str)

    ui: UI_AssistantPanel
    mdl_mgr: AsyncTask[list[str]]
    msg_mgr: AsyncTask[None] | None
    item_model: QStandardItemModel

    models_present: bool

    def __init__(self, parent: QWidget | None = None) -> None:
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

    @typed_slot(str, str)
    def on_new_message(self, role: str, text: str) -> None:
        row = self.item_model.rowCount()
        _ = self.item_model.insertRow(row)
        self.item_model.setItem(row, 1, QStandardItem(role))
        self.item_model.setItem(row, 0, QStandardItem(text))

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
            role_item, content_item = self.item_model.item(i, 1), self.item_model.item(i, 0)
            assert role_item and content_item
            role = role_item.text()
            content = content_item.text()
            messages.append(Message(role=role, content=content))

        async def fetch_response():
            print("Begin fetch response")
            reply = (await ollama_adapter.chat("deepseek-r1:latest", messages)).content
            assert reply is not None
            self.new_message.emit("assistant", reply)
            self.msg_mgr = None
            print("End fetch response")

        self.msg_mgr = AsyncTask(fetch_response())
        self.msg_mgr.start()

    def ensure_model(self) -> None:
        self.mdl_mgr = AsyncTask(ollama_adapter.get_missing_models({"deepseek-r1:latest", "llama3.1:latest"}))
        _ = self.mdl_mgr.complete.connect(self.model_tested)
        _ = self.mdl_mgr.thrown.connect(self.model_test_error)
        self.mdl_mgr.start()

    @typed_slot(Exception)
    def model_test_error(self, exc: Exception) -> None:
        # TODO: Of course, don't require the user to launch ollama manually!!
        _ = QMessageBox.critical(self, "Error", f"There was a problem trying to check ollama status: {type(exc).__qualname__}: {exc}.", QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok)
        QApplication.quit()

    @typed_slot(object)
    def model_tested(self, missing: object) -> None:
        missing = cast(list[str], missing)
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
