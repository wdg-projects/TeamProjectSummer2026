import collections.abc
from dataclasses import dataclass, field
import enum
from typing import cast, override

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QObject, QVariant, Qt, pyqtSlot
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
    ui: UI_AssistantPanel

    controller: AssistantPanelController

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.ui = load_and_apply_ui(ASSISTANT_PANEL_UI(), self, UI_AssistantPanel)

        model = AssistantChatModel(self)

        self.ui.chat_log.setModel(model)
        self.ui.chat_log.setWordWrap(True)
        self.ui.entry.setEnabled(False)

        self.controller = AssistantPanelController(model, self, self)

class AssistantPanelController(QObject):
    model: AssistantChatModel
    view: AssistantPanel

    @dataclass
    class StartState:
        pass

    @dataclass
    class WaitForModelVerifiedState:
        mdl_mgr: AsyncTask[list[str]]

    @dataclass
    class WaitForUserMessageState:
        pass

    @dataclass
    class WaitForOllamaResponseState:
        msg_mgr: AsyncTask[str | list[ollama_adapter.ToolMessage]]
        chat_iter: collections.abc.AsyncGenerator[str | list[ollama_adapter.ToolMessage], bool]

    type State = StartState | WaitForModelVerifiedState | WaitForUserMessageState | WaitForOllamaResponseState

    state: State = StartState()

    new_messages: TypedSignal[list[ollama_adapter.ToolMessage]] = typed_signal(list)

    def __init__(self, model: AssistantChatModel, view: AssistantPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.view = view

        _ = self.view.ui.send.pressed.connect(self.on_send)
        _ = self.new_messages.connect(self.on_new_message)

        self.ensure_model()

    def change_state(self, new: State) -> None:
        match (self.state, new):
            case (self.StartState(), self.WaitForModelVerifiedState()):
                pass

            case (self.WaitForModelVerifiedState(), self.WaitForUserMessageState()):
                ollama_adapter.ensure()
                self.view.ui.entry.setEnabled(True)

            case (self.WaitForUserMessageState(), self.WaitForOllamaResponseState()):
                self.view.ui.entry.setText("")
                self.view.ui.entry.setEnabled(False)

            case (self.WaitForOllamaResponseState(), self.WaitForUserMessageState()):
                self.view.ui.entry.setEnabled(True)
            
            case (self.WaitForOllamaResponseState(), self.WaitForOllamaResponseState()):
                pass

            case _:
                raise ValueError("Invalid state transition")

        self.state = new

    def ensure_model(self) -> None:
        assert isinstance(self.state, (self.WaitForModelVerifiedState, self.StartState))

        mdl_mgr = AsyncTask(ollama_adapter.get_missing_models({"deepseek-r1:latest", "llama3.1:latest"}))
        _ = mdl_mgr.complete.connect(self.model_tested)
        _ = mdl_mgr.thrown.connect(self.model_test_error)
        mdl_mgr.start()

        self.change_state(self.WaitForModelVerifiedState(mdl_mgr))

    @typed_slot(Exception)
    def model_test_error(self, exc: Exception) -> None:
        # TODO: Of course, don't require the user to launch ollama manually!!
        _ = QMessageBox.critical(self.view,
            "Error",
            f"There was a problem trying to check ollama status: {type(exc).__qualname__}: {exc}.",
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok
        )
        QApplication.quit()

    @typed_slot(object)
    def model_tested(self, missing: object) -> None:
        missing = cast(list[str], missing)
        if not missing:
            return self.change_state(self.WaitForUserMessageState())

        missing_text = ", ".join(missing)
        pressed = QMessageBox.warning(self.view,
            "Models missing",
            f"You are missing the following models: {missing_text}\nBefore using this utility, you need to download the missing models. Proceed?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok
        )
        match pressed:
            case QMessageBox.StandardButton.Cancel:
                QApplication.quit()
            case QMessageBox.StandardButton.Ok:
                download_panel = ModelDownload(missing, self.view)
                download_panel.show()
                _ = download_panel.closed.connect(lambda: self.ensure_model())
            case _:
                assert False

    @typed_slot(list)
    def on_new_message(self, msgs: list[ollama_adapter.ToolMessage]) -> None:
        self.model.extend(msgs)

    def on_send(self) -> None:
        if not isinstance(self.state, self.WaitForUserMessageState):
            return

        msg = (ollama_adapter.MessageSource.USER, self.view.ui.entry.text())
        self.new_messages.emit([msg])

        chat_iter = ollama_adapter.tool_chat("com_teamproject_uiassistant__deepseek", self.model.log)
        msg_mgr = AsyncTask(chat_iter.asend(None))

        msg_mgr.complete.connect(self.on_model_response_fragment)
        msg_mgr.start()

        self.change_state(self.WaitForOllamaResponseState(msg_mgr, chat_iter))

    @pyqtSlot(object)
    def on_model_response_fragment(self, rsp: object) -> None:
        rsp = cast(str | list[ollama_adapter.ToolMessage], rsp)
        if not isinstance(self.state, self.WaitForOllamaResponseState):
            return

        if isinstance(rsp, str):
            btn = QMessageBox.warning(self.view,
                "The model wants to execute a script",
                rsp,
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel
            )
            msg_mgr = AsyncTask(self.state.chat_iter.asend(btn == QMessageBox.StandardButton.Ok))
            msg_mgr.complete.connect(self.on_model_response_fragment)
            msg_mgr.start()
            return self.change_state(self.WaitForOllamaResponseState(msg_mgr, self.state.chat_iter))

        self.new_messages.emit(rsp)
        self.change_state(self.WaitForUserMessageState())

class AssistantChatModel(QAbstractTableModel):
    log: list[ollama_adapter.ToolMessage]

    def __init__(self, parent: QObject | None) -> None:
        super().__init__(parent)
        self.log = []

    @override
    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len([x for x in self.log if x[0] != ollama_adapter.MessageSource.COMPUTER])

    @override
    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 2

    @override
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if role == Qt.ItemDataRole.DisplayRole:
            try:
                msg = [x for x in self.log if x[0] != ollama_adapter.MessageSource.COMPUTER][index.row()]
            except IndexError:
                return QVariant()
            if index.column() == 0:
                res = str("".join(f"{x}\u200b" for x in msg[1]))
            elif index.column() == 1:
                res = str(msg[0])
            else:
                res = None
        else:
            res = None
        return QVariant(res)

    def append(self, item: ollama_adapter.ToolMessage) -> None:
        self.extend([item])

    def extend(self, other: collections.abc.Iterable[ollama_adapter.ToolMessage]) -> None:
        other = list(other)
        other_visible = [x for x in other if x[0] != ollama_adapter.MessageSource.COMPUTER]

        self.beginInsertRows(QModelIndex(), len(self.log), len(self.log) + len(other_visible) - 1)
        self.log.extend(other)
        self.endInsertRows()
