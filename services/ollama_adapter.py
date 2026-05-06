import functools
from typing import override
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal

import ollama

from asyncbridge import AsyncTask

@functools.lru_cache(maxsize=1)
def ollama_client() -> ollama.AsyncClient:
    """Get a connection to ollama. Create one if it doesn't exist yet."""
    # TODO: Don't hard-code this
    return ollama.AsyncClient("127.0.0.1:12588")

@dataclass
class PullProgress:
    current_model_downloading_name: str
    all_models_downloaded_percent: float
    single_model_download_percent: float | None

class ModelPullTask(AsyncTask):
    """Downloads a list of models."""

    update_progress: Signal = Signal(PullProgress)

    to_download: list[str]

    def __init__(self, to_download: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent=parent)
        self.to_download = to_download

    @override
    async def run(self) -> None:
        client = ollama_client()

        for i, model in enumerate(self.to_download):
            all_models_percent = i / len(self.to_download) * 100
            self.update_progress.emit(PullProgress(model, all_models_percent, None))

            stream = await client.pull(model, stream=True)
            async for progress in stream:
                single_model_percent = None
                if progress.total is not None and progress.completed is not None and progress.total > 0:
                    single_model_percent = progress.completed / progress.total * 100
                self.update_progress.emit(PullProgress(model, all_models_percent, single_model_percent))

            self.update_progress.emit(PullProgress("[done]", (i + 1) / len(self.to_download) * 100, 100.0))

async def get_missing_models(expected: set[str]) -> list[str]:
    """Computes an alphabetically sorted list of models that are expected but aren't installed."""

    client = ollama_client()
    models = {model.model for model in (await client.list()).models if model.model}

    return sorted(expected - models)

async def chat(model: str, log: list[ollama.Message]) -> ollama.Message:
    return (await ollama_client().chat(model, log)).message

