import io
from typing import IO, override

from PySide6.QtCore import QIODeviceBase, QIODevice, QObject

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
    def writeData(self, data: bytes | bytearray | memoryview[int], count: int) -> int:
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
