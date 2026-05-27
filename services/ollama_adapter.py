from collections.abc import AsyncGenerator, AsyncIterator, Iterator
import enum
import functools
import io
import os
import re
import sys
import traceback
from typing import final, override
from dataclasses import dataclass
from PyQt6.QtCore import QObject

import ollama

from asyncbridge import AsyncTask
from common_utils import typed_signal

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

@final
class ModelPullTask(AsyncTask[None]):
    """Downloads a list of models."""

    update_progress = typed_signal(PullProgress)

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

def ensure() -> None:
    _ = os.system("OLLAMA_HOST=127.0.0.1:12588 ollama rm com_teamproject_uiassistant__deepseek")
    if os.system("OLLAMA_HOST=127.0.0.1:12588 ollama create com_teamproject_uiassistant__deepseek -f Modelfile"):
        raise ValueError("Could not create model")

class MessageSource(enum.StrEnum):
    USER = "User"
    ASSISTANT = "Assistant"
    COMPUTER = "Computer"

type ToolMessage = tuple[MessageSource, str]

TRIGGER_PHRASE = re.compile(r"computer,\s+run:\s+```.*\n([\s\S]*)```", re.IGNORECASE)

async def tool_chat(model: str, log: list[ToolMessage]) -> AsyncGenerator[list[ToolMessage] | str, bool | None]:
    # Absolute goddamn mess, but this is merely for testing
    log = log.copy()
    start_len = len(log)

    client = ollama_client()

    PREFIX = {
        MessageSource.USER: "[User says:] ",
        MessageSource.ASSISTANT: "",
        MessageSource.COMPUTER: "[Responding to the assistant, computer says:] "
    }
    chatlog: list[ollama.Message] = [ollama.Message(role="user", content="[A new user has logged in. Your role as assistant begins now.]")]
    for x in log:
        role = "assistant" if x[0] is MessageSource.ASSISTANT else "user"
        chatlog.append(ollama.Message(role=role, content=(PREFIX[x[0]] + x[1]).strip()))

    while True:
        contents = ""
        print("Begin fetch response")
        async for x in await client.chat(model, chatlog, stream=True):
            if x.message.content is not None:
                contents += x.message.content
        print("End fetch response")

        computer_response: str | None = None
        full_match: str | None = None
        for match in TRIGGER_PHRASE.finditer(contents):
            full_match = match.group(0)
            code = match.group(1)
            if (yield code):
                old = sys.stdout, sys.stderr
                tgt = io.StringIO()
                sys.stdout = sys.stderr = tgt
                try:
                    exec(code)
                except:
                    traceback.print_exc()
                sys.stdout, sys.stderr = old
                computer_response = tgt.getvalue()
                break
            else:
                computer_response = "RuntimeError: The user has aborted the operation."

        if computer_response is None or full_match is None:
            chatlog.append(ollama.Message(role="assistant", content=contents))
            log.append((MessageSource.ASSISTANT, contents))
            break
        chatlog.append(ollama.Message(role="assistant", content=full_match))
        log.append((MessageSource.ASSISTANT, full_match))

        if len(computer_response) > 1024:
            text = f"RuntimeError: Your script generated overlong output: {len(computer_response)}B. Please ask me again, assistant, but limiting your script's output length."
        if computer_response.strip():
            text = computer_response
        else:
            text = f"[Responding to the assistant, computer says:] ```runner.py:1:1: UserWarning: your script successfully finished, but generated no stdout / stderr; did you forget to print()?  analyze the exit condition of your script to figure out if this is correct!```"

        chatlog.append(ollama.Message(role="user", content=f"[Responding to the assistant, computer says:] ```\n{text}\n```"))
        log.append((MessageSource.COMPUTER, text))

    yield log[start_len:]
