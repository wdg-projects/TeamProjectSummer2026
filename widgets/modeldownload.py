from typing import override
from dataclasses import dataclass, field

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QWidget

from services.ollama_adapter import ModelPullTask, PullProgress

from .uiutils import common_ui_loader, preload_ui, load_and_apply_ui, SOURCE_FIELD

def register_all() -> None:
    common_ui_loader().registerCustomWidget(ModelDownload)

MODEL_DOWNLOAD_UI = preload_ui("modeldownload.ui")

@dataclass
class UI_ModelDownload:
    widget: QDialog = field(metadata=SOURCE_FIELD)

    text: QLabel
    all_models_progress: QProgressBar
    model_progress: QProgressBar
    cancel: QPushButton

class ModelDownload(QDialog):
    to_download: list[str]
    base_text: str
    dl_mgr: ModelPullTask | None

    ui: UI_ModelDownload

    closed: Signal = Signal()

    def __init__(self, to_download: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.to_download = to_download

        self.ui = load_and_apply_ui(MODEL_DOWNLOAD_UI(), self, UI_ModelDownload)
        self.setModal(True)
        layout = self.layout()
        assert layout is not None
        layout.setContentsMargins(8, 8, 8, 8)

        _ = self.ui.cancel.pressed.connect(self.close)

        self.base_text = self.ui.text.text()

        self.dl_mgr = ModelPullTask(self.to_download)
        _ = self.dl_mgr.update_progress.connect(self.update_progress)
        _ = self.dl_mgr.complete.connect(self.download_done)
        self.dl_mgr.start()

    @override
    def closeEvent(self, _1: object, /) -> None:
        self.closed.emit()

    @Slot()
    def download_done(self) -> None:
        self.dl_mgr = None
        _ = self.close()

    @Slot(str, tuple, tuple)
    def update_progress(self, progress: PullProgress) -> None:
        self.ui.text.setText(self.base_text.format(model_name=progress.current_model_downloading_name))

        self.ui.all_models_progress.setMinimum(0)
        self.ui.all_models_progress.setMaximum(100)
        self.ui.all_models_progress.setValue(int(progress.all_models_downloaded_percent))

        self.ui.model_progress.setMinimum(0)
        if progress.single_model_download_percent is None:
            self.ui.model_progress.setMaximum(0)
            self.ui.model_progress.setValue(0)
        else:
            self.ui.model_progress.setMaximum(100)
            self.ui.model_progress.setValue(int(progress.single_model_download_percent))
