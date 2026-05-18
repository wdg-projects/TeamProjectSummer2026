import io
from typing import IO, TYPE_CHECKING, Callable, overload, override

from PyQt6.QtCore import QIODeviceBase, QIODevice, QObject, pyqtSignal

class PythonIODevice(QIODevice):
    """
    Adapter between Python binary streams and the QIODevice interface.
    """

    # As it stands, this is necessary in just one spot. I feel like it'll come in handy far more often though, and it's not like it's big!

    file: IO[bytes]

    def __init__(self, file: IO[bytes], parent: QObject | None = None) -> None:
        if parent is None:
            super().__init__()
        else:
            super().__init__(parent)

        self.file = file
        match file.mode:
            case "rb":
                mode = QIODeviceBase.OpenModeFlag.ReadOnly
            case "rb+" | "wb+":
                mode = QIODeviceBase.OpenModeFlag.ReadWrite
            case "wb":
                mode = QIODeviceBase.OpenModeFlag.WriteOnly
            case "ab":
                mode = QIODeviceBase.OpenModeFlag.Append
            case _:
                raise ValueError(f"Unknown mode {file.mode!r}")

        status = self.open(mode)
        assert status

    @override
    def readData(self, maxlen: int) -> bytes:
        try:
            return self.file.read(maxlen)
        except io.UnsupportedOperation:
            self.setErrorString("Not readable")
            return b""

    @override
    def writeData(self, data: bytes | bytearray | memoryview[int], count: int) -> int:  # pyright: ignore[reportIncompatibleMethodOverride]
        if count > len(data):
            self.setErrorString("Count exceeds length of provided data")
            return -1
        try:
            return self.file.write(data[:count])
        except io.UnsupportedOperation:
            self.setErrorString("Not writeable")
            return -1
        except OSError as e:
            self.setErrorString(f"{type(e).__name__}: {e}")
            return -1

    @override
    def close(self, /) -> None:
        self.file.close()
        return super().close()

if TYPE_CHECKING:
    class TypedSignal[*Ts]:
        def __init__(self, sgn: pyqtSignal) -> None: ...
        def __get__(self, instance: object, owner: type[object] | None) -> BoundTypedSignal[*Ts]: ...

    class BoundTypedSignal[*Ts]:
        def connect(self, _: Callable[[*Ts], None]) -> None: ...
        def emit(self, *_: *Ts) -> None: ...
else:
    TypedSignal = lambda x: x
    BoundTypedSignal = None

@overload
def typed_signal() -> TypedSignal[()]: ...

@overload
def typed_signal[T](t1: type[T]) -> TypedSignal[T]: ...

@overload
def typed_signal[T1, T2](t1: type[T1], t2: type[T2]) -> TypedSignal[T1, T2]: ...

@overload
def typed_signal[T1, T2, T3](t1: type[T1], t2: type[T2], t3: type[T3]) -> TypedSignal[T1, T2, T3]: ...

@overload
def typed_signal[T1, T2, T3, T4, T5, T6](t1: type[T1], t2: type[T2], t3: type[T3], t4: type[T4]) -> TypedSignal[T1, T2, T3, T4]: ...

@overload
def typed_signal[T1, T2, T3, T4, T5, T6](t1: type[T1], t2: type[T2], t3: type[T3], t4: type[T4], t5: type[T5]) -> TypedSignal[T1, T2, T3, T4, T5]: ...

@overload
def typed_signal[T1, T2, T3, T4, T5, T6](t1: type[T1], t2: type[T2], t3: type[T3], t4: type[T4], t5: type[T5], t6: type[T6]) -> TypedSignal[T1, T2, T3, T4, T5, T6]: ...

def typed_signal[T1, T2, T3, T4, T5, T6](t1: type[T1] | None = None, t2: type[T2] | None = None, t3: type[T3] | None = None, t4: type[T4] | None = None, t5: type[T5] | None = None, t6: type[T6] | None = None) -> (
    TypedSignal[()] |
    TypedSignal[T1] |
    TypedSignal[T1, T2] |
    TypedSignal[T1, T2, T3] |
    TypedSignal[T1, T2, T3, T4] |
    TypedSignal[T1, T2, T3, T4, T5] |
    TypedSignal[T1, T2, T3, T4, T5, T6]
):
    return TypedSignal(pyqtSignal(*(x for x in (t1, t2, t3, t4, t5, t6) if x is not None)))

@overload
def typed_slot[TSelf]() -> Callable[[Callable[[TSelf], None]], Callable[[TSelf], None]]: ...

@overload
def typed_slot[TSelf, T1](t1: type[T1]) -> Callable[[Callable[[TSelf, T1], None]], Callable[[TSelf, T1], None]]: ...

@overload
def typed_slot[TSelf, T1, T2](t1: type[T1], t2: type[T2]) -> Callable[[Callable[[TSelf, T1, T2], None]], Callable[[TSelf, T1, T2], None]]: ...

@overload
def typed_slot[TSelf, T1, T2, T3](t1: type[T1], t2: type[T2], t3: type[T3]) -> Callable[[Callable[[TSelf, T1, T2, T3], None]], Callable[[TSelf, T1, T2, T3], None]]: ...

def typed_slot[TSelf, T1, T2, T3](t1: type[T1] | None = None, t2: type[T2] | None = None, t3: type[T3] | None = None) -> (
    Callable[[Callable[[TSelf], None]], Callable[[TSelf], None]] |
    Callable[[Callable[[TSelf, T1], None]], Callable[[TSelf, T1], None]] |
    Callable[[Callable[[TSelf, T1, T2], None]], Callable[[TSelf, T1, T2], None]] |
    Callable[[Callable[[TSelf, T1, T2, T3], None]], Callable[[TSelf, T1, T2, T3], None]]
):
    if TYPE_CHECKING:
        _ = t1, t2, t3
        return lambda x: x
    else:
        from PyQt6.QtCore import pyqtSlot
        return pyqtSlot(*(x for x in (t1, t2, t3) if x is not None))
