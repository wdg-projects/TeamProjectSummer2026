from dataclasses import dataclass, field
from typing import cast

from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QApplication, QLineEdit, QListView, QMessageBox, QPushButton, QWidget

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
    msg_mgr: AsyncTask[str | list[ollama_adapter.ToolMessage]] | None
    item_model: QStandardItemModel

    chat_log: list[ollama_adapter.ToolMessage]

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
        self.ui.chat_log.setWordWrap(True)

        self.chat_log = []

        self.ensure_model()

    @typed_slot(str, str)
    def on_new_message(self, _role: str, text: str) -> None:
        row = self.item_model.rowCount()
        _ = self.item_model.insertRow(row)
        # self.item_model.setItem(row, 1, QStandardItem(role))
        self.item_model.setItem(row, 0, QStandardItem("".join(f"{x}\u200b" for x in text)))

    def on_send(self) -> None:
        if not self.models_present:
            return
        if self.msg_mgr is not None:
            return

        user_message = self.ui.entry.text()
        self.ui.entry.setText("")

        self.chat_log.append((ollama_adapter.MessageSource.USER, user_message))
        self.new_message.emit("user", user_message)

        chat_iter = ollama_adapter.tool_chat("com_teamproject_uiassistant__deepseek", self.chat_log)
        async def fetch_response(to_send: bool | None) -> str | list[ollama_adapter.ToolMessage]:
            x = await chat_iter.asend(to_send)
            return x

        self.msg_mgr = AsyncTask(fetch_response(None))
        def on_complete(rsp: object) -> None:
            rsp = cast(str | list[ollama_adapter.ToolMessage], rsp)
            if isinstance(rsp, str):
                btn = QMessageBox.warning(self,
                    "The model wants to execute a script",
                    rsp,
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel
                )
                self.msg_mgr = AsyncTask(fetch_response(btn == QMessageBox.StandardButton.Ok))
                self.msg_mgr.complete.connect(on_complete)
                self.msg_mgr.start()
            else:
                self.chat_log = rsp
                self.new_message.emit("assistant", self.chat_log[-1][1])
                self.msg_mgr = None

        self.msg_mgr.complete.connect(on_complete)
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
            ollama_adapter.ensure()
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
