"""
Utility functions for managing an asyncio event loop running in a separate thread.
Remember that, since run in a separate thread, async tasks must not interact with Qt beyond emitting signals!
"""

# I found that this is the only good way to get asyncio and PyQt6 to play nice.
# This is confusing code, but fingers crossed shouldn't be confusing in usage:
# - Use AsyncTask the same way you'd use threading.Thread, except you also can also connect to the provided Qt signals, if you'd like to watch for completion/errors
# - You probably won't need to ever invoke threaded_event_loop()

import sys
import asyncio
import traceback
import functools
import threading
from typing import override
from collections.abc import Coroutine

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

from common_utils import BoundTypedSignal, TypedSignal, typed_signal

@functools.lru_cache(maxsize=1)
def threaded_event_loop() -> asyncio.AbstractEventLoop:
    """Returns the threaded event loop. Spins one up if it doesn't exist yet. Requires an initialized QApplication."""

    app = QApplication.instance()
    if app is None:
        raise RuntimeError("Create a QApplication before fetching the threaded event loop")

    loop = asyncio.new_event_loop()
    def target():
        asyncio.set_event_loop(loop)
        loop.run_forever()
    threading.Thread(target=target, daemon=True).start()

    _ = app.aboutToQuit.connect(lambda: loop.call_soon_threadsafe(loop.stop))
    return loop

class AsyncTask[ResultType](QObject):
    """
    A wrapper that allows for a coroutine to be scheduled in the threaded event loop.
    If you'd like additional signals, you can inherit from this class and override the run() method.

    Due to typing limitations, the `complete` signal has a single parameter of ALWAYS type `object`. I recommend using pyqtSlot instead of typed_slot when wiring a completion listener.
    """

    complete: TypedSignal[object] = typed_signal(object)
    thrown: TypedSignal[Exception] = typed_signal(Exception)

    _fired: bool
    _exc_watch: bool
    _coro: Coroutine[object, object, ResultType] | None

    def __init__(self, coro: Coroutine[object, object, ResultType] | None = None, parent: QObject | None = None) -> None:
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

    async def run(self) -> ResultType:
        if self._coro is None:
            raise RuntimeError("AsyncTask fired with no target")
        return await self._coro

    # Private

    def _report_exc(self, exc: Exception) -> None:
        if self._exc_watch:
            return
        print(f"In async task {self!r}:", file=sys.stderr)
        traceback.print_exception(exc)

    # And now, for a terrible hack to ensure exceptions are only logged if nothing is watching for them yet:

    def _thrown_signal(self) -> BoundTypedSignal[Exception]:
        return super().__getattribute__("thrown")  # pyright: ignore[reportAny]

    @override
    def __getattribute__(self, name: str, /) -> object:
        if name == "thrown":
            self._exc_watch = True
        return super().__getattribute__(name)  # pyright: ignore[reportAny]
