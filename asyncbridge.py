"""
Utility functions for managing an asyncio event loop running in a separate thread.
Remember that, since run in a separate thread, async tasks must not interact with Qt beyond emitting signals!
"""

# I found that this is the only good way to get asyncio and PySide6 to play nice:
# - QtAsyncio remains poorly implemented
# - qasync had strange issues regarding cancellation
# 
# This is confusing code, but fingers crossed shouldn't be confusing in usage:
# - Use AsyncTask the same way you'd use threading.Thread, except you also can also connect to the provided Qt signals, if you'd like to watch for completion/errors
# - You probably won't need to ever invoke threaded_event_loop()

import asyncio
import sys
import traceback
from typing import Any, override
import warnings
import functools
import threading
from collections.abc import Coroutine

from PySide6.QtCore import QObject, Signal, SignalInstance
from PySide6.QtWidgets import QApplication

_quit_event = asyncio.Event()

@functools.lru_cache(maxsize=1)
def threaded_event_loop() -> asyncio.AbstractEventLoop:
    """Returns the threaded event loop. Spins one up if it doesn't exist yet. Requires an initialized QApplication."""

    app = QApplication.instance()
    if app is None:
        raise RuntimeError("Create a QApplication before fetching the threaded event loop")

    loop = asyncio.new_event_loop()
    def target():
        asyncio.set_event_loop(loop)
        _ = loop.run_until_complete(_quit_event.wait())
        pending = asyncio.all_tasks()
        if pending:
            warnings.warn(f"{len(pending)} pending tasks on application shutdown")
            _ = loop.run_until_complete(asyncio.gather(*pending))
    threading.Thread(target=target, daemon=True).start()

    # TODO: Check for sneaky race condition between application exit and _quit_event.wait
    _ = app.aboutToQuit.connect(lambda: _quit_event.set())
    return loop

class AsyncTask(QObject):
    """
    A wrapper that allows for a coroutine to be scheduled in the threaded event loop.
    If you'd like additional signals, you can inherit from this class and override the run() method.
    """

    complete: Signal = Signal(object)
    thrown: Signal = Signal(Exception)

    _fired: bool
    _exc_watch: bool
    _coro: Coroutine[object, object, object] | None

    def __init__(self, coro: Coroutine[object, object, object] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fired = False
        self._exc_watch = False
        self._coro = coro
        _ = self._thrown_signal().connect(self._report_exc)

    def start(self) -> None:
        """Schedules the coroutine to be ran as soon as possible. Call this only *after* binding your signals of interest."""
        if self._fired:
            raise RuntimeError("Task already fired")
        self._fired = True

        async def wrap() -> None:
            try:
                self.complete.emit(await self.run())
            except Exception as e:
                self._thrown_signal().emit(e)
        _ = threaded_event_loop().call_soon_threadsafe(lambda: asyncio.create_task(wrap()))

    async def run(self) -> object:
        if self._coro is None:
            raise RuntimeError("AsyncTask() fired with no target")
        return await self._coro

    # Private

    def _report_exc(self, exc: Exception) -> None:
        if self._exc_watch:
            return
        print(f"In async task {self!r}:", file=sys.stderr)
        traceback.print_exception(exc)

    # And now, for a terrible hack to ensure exceptions are only logged if nothing is watching for them yet:

    def _thrown_signal(self) -> SignalInstance:
        return super().__getattribute__("thrown")  # pyright: ignore[reportAny]

    @override
    def __getattribute__(self, name: str, /) -> object:
        if name == "thrown":
            self._exc_watch = True
        return super().__getattribute__(name)  # pyright: ignore[reportAny]
