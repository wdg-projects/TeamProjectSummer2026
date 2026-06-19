import collections.abc
from dataclasses import dataclass, field
from typing import cast, override

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QObject, QVariant, Qt, pyqtSlot, QRect
from PyQt6.QtGui import QPalette, QPainter, QColor, QFont
from PyQt6.QtWidgets import QApplication, QLineEdit, QListView, QMessageBox, QPushButton, QWidget, QStyledItemDelegate, \
    QItemDelegate, QStyleOptionViewItem

from asyncbridge import AsyncTask
from services import ollama_adapter, toolchat
from edited_subwindow import EditedSubwindow
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

        delegate: MyDelegate = MyDelegate()
        self.ui.chat_log.setItemDelegate(delegate)

        self.controller = AssistantPanelController(model, self, self)

class MyDelegate(QItemDelegate):

    @override
    def paint(self, painter: QPainter | None, option: object, index: QModelIndex) -> None:
        if painter is None:
            return
        contents = index.data()
        role = index.siblingAtColumn(1).data()
        if (role == 'user'):
            painter.setPen(QColor(255, 0, 0))
            painter.setFont(QFont("Comic Sans MS", 12))
        if (role == 'assistant'):
            painter.setPen(QColor(0, 255, 0))
            painter.setFont(QFont("Arial", 12))

        if hasattr(option, 'rect'):
            #we check is the object has attribute rect, if so we can use it
            option_rect = option.rect
        else:
            # Default Fallback - if no attribute we use this as default
            option_rect = QRect(0, 0, 300, 100)
        flags = Qt.TextWordWrap | Qt.AlignCenter
        bound_rect = painter.boundingRect(option_rect, flags, contents)
        if bound_rect.width() > option_rect.width():
            bound_rect.setWidth(option_rect.width())
        painter.drawRoundedRect(bound_rect, 10, 10)
        painter.drawText(bound_rect, flags, contents)

class AssistantPanelController(QObject):
    model: AssistantChatModel
    view: AssistantPanel

    edited_subwindow: EditedSubwindow | None

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
        msg_mgr: AsyncTask[toolchat.Script | toolchat.ResponseFragment]
        chat_iter: collections.abc.AsyncGenerator[toolchat.Script | toolchat.ResponseFragment, str | None]

    type State = StartState | WaitForModelVerifiedState | WaitForUserMessageState | WaitForOllamaResponseState

    state: State = StartState()

    new_messages: TypedSignal[list[toolchat.ChatMessage]] = typed_signal(list)

    def __init__(self, model: AssistantChatModel, view: AssistantPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.view = view
        self.edited_subwindow = None

        _ = self.view.ui.send.pressed.connect(self.on_send)
        _ = self.new_messages.connect(self.on_new_message)

        self.ensure_model()

    @typed_slot(EditedSubwindow)
    def inject_edited_subwindow(self, edited_subwindow: EditedSubwindow) -> None:
        self.edited_subwindow = edited_subwindow
        print("woohoo i own an", self.edited_subwindow, "now")

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

        mdl_mgr = AsyncTask(ollama_adapter.get_missing_models({"deepseek-r1:latest", "qwen3:latest"}))
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
    def on_new_message(self, msgs: list[toolchat.ChatMessage]) -> None:
        self.model.extend(msgs)

    def on_send(self) -> None:
        if not isinstance(self.state, self.WaitForUserMessageState):
            return

        msg = toolchat.ChatMessage(toolchat.ChatMessageSource.USER, self.view.ui.entry.text())  # (ollama_adapter.MessageSource.USER, self.view.ui.entry.text())
        self.new_messages.emit([msg])

        chat_iter = toolchat.script_chat("com_teamproject_uiassistant__qwen3", self.model.log)
        msg_mgr = AsyncTask(chat_iter.asend(None))

        msg_mgr.complete.connect(self.on_model_response_fragment)
        msg_mgr.start()

        self.change_state(self.WaitForOllamaResponseState(msg_mgr, chat_iter))

    @pyqtSlot(object)
    def on_model_response_fragment(self, rsp: object) -> None:
        rsp = cast(toolchat.ResponseFragment | toolchat.Script, rsp)
        if not isinstance(self.state, self.WaitForOllamaResponseState):
            return

        if not rsp[0]:
            btn = QMessageBox.warning(self.view,
                "The model wants to execute a script",
                rsp[1],
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel
            )
            if btn == QMessageBox.StandardButton.Ok:
                res = ollama_adapter.run_script(rsp[1], self.edited_subwindow)
            else:
                res = None
            msg_mgr = AsyncTask(self.state.chat_iter.asend(res))
            msg_mgr.complete.connect(self.on_model_response_fragment)
            msg_mgr.start()
            return self.change_state(self.WaitForOllamaResponseState(msg_mgr, self.state.chat_iter))

        self.new_messages.emit([toolchat.ChatMessage(toolchat.ChatMessageSource.ASSISTANT, rsp[1])])
        self.change_state(self.WaitForUserMessageState())

class AssistantChatModel(QAbstractTableModel):
    log: list[toolchat.ChatMessage]

    def __init__(self, parent: QObject | None) -> None:
        super().__init__(parent)
        self.log = []

    @override
    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.log)

    @override
    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 2

    @override
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        res = None
        if role == Qt.ItemDataRole.DisplayRole:
            try:
                msg = self.log[index.row()]
            except IndexError:
                return QVariant()
            if index.column() == 0:
                res = str("".join(f"{x}\u200b" for x in msg.content))
            elif index.column() == 1:
                res = str(msg.source.ollama_role())
        return QVariant(res)

    def append(self, item: toolchat.ChatMessage) -> None:
        self.extend([item])

    def extend(self, other: collections.abc.Iterable[toolchat.ChatMessage]) -> None:
        other = list(other)

        self.beginInsertRows(QModelIndex(), len(self.log), len(self.log) + len(other) - 1)
        self.log.extend(other)
        self.endInsertRows()