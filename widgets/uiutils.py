"""
UI utilities.
"""

import os
import functools
import dataclasses
from typing import Callable, LiteralString, get_type_hints, TYPE_CHECKING

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtCore import QBuffer, QByteArray, QIODevice

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

def find[T: QWidget](where: QWidget, widget_named: str, of_type: type[T]) -> T:
    """Wrapper around QWidget::findChild that throws an exception instead of returning None."""

    res = where.findChild(of_type, widget_named)
    if not res:
        raise LookupError(f"Could not find a {of_type.__name__} named {widget_named!r}")
    return res

@functools.lru_cache(maxsize=1)
def common_ui_loader() -> QUiLoader:
    """Returns the global QUiLoader instance. Creates one if it doesn't exist yet. This is the instance that will be used for widget registration."""
    return QUiLoader()

# The rest of the file has some dubious code.
# The problem I faced was that pyside6-uic does not generate type hints. In my experience type hints speed up development time immensely, I really wanted to have them.
# Also, keeping generated code up-to-date is annoying.
# 
# My solution is this. I won't force anyone to use it, it's very hacky.
# If you'd prefer it removed cuz it's too bespoke, that's okay too. I'm just explaining the code as I left it before publishing.
# The big idea is you define a dataclass that specifies the names and types of every UI component you're interested in, and then use load_and_apply_ui to:
#  - Load the UI from a file
#  - Populate your dataclass with the widgets within
#  - Insert it into your root widget with a QVBoxLayout
#
# As a short example:
#
#     EXAMPLE_UI = preload_ui("example.ui")
#
#     @dataclass
#     class UI_Example:
#         # This field is special and will receive the QVBoxLayout itself.
#         widget: QDialog = field(metadata=SOURCE_FIELD)
#
#         # A QPushButton named "btn" must be defined in the UI file. It will be automatically placed into this attribute.
#         btn: QPushButton
#
#         # Same for this QLabel
#         lbl: QLabel
#
#     class Example(QWidget):
#         ui: UI_ModelDownload
# 
#         def __init__(self, parent: QWidget | None = None) -> None:
#             super().__init__(parent)
#             # This is how you actually load it
#             self.ui = load_and_apply_ui(EXAMPLE_UI(), self, UI_Example)
#
# Of course, this could also be written using more traditional Qt patterns:
# 
#     EXAMPLE_UI = preload_ui("example.ui")
#
#     class Example(QWidget):
#         vbox: QVBoxLayout
#         btn: QPushButton
#         lbl: QLabel
# 
#         def __init__(self, parent: QWidget | None = None) -> None:
#             super().__init__(parent)
#
#             loaded = common_ui_loader().load(EXAMPLE_UI(), self)
#             self.vbox = QVBoxLayout(self)
#             self.vbox.setContentsMargins(0, 0, 0, 0)
#             self.vbox.addWidget(loaded)
#             self.setLayout(layout)
# 
#             self.btn = find(self, "btn", QPushButton)
#             self.lbl = find(self, "lbl", QLabel)
# 
# That involves a lot of repetition though, especially across patterns, keeping it DRY is part why I went to all this hassle

def preload_ui(name: LiteralString) -> Callable[[], QIODevice]:
    """Returns a function you can invoke to get a fresh QIODevice of the UI file. Only performs I/O at initial call time."""

    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), name)
    with open(path, "rb") as f:
        data = QByteArray(f.read())
    
    return lambda: QBuffer(data)

SOURCE_FIELD = {"teamproject.utils.source_field": True}

def populate_children[T: DataclassInstance](source: QWidget, cls: type[T]) -> T:
    """Creates an instance of the given dataclass, extracting named widgets from the source."""
    type_hints = get_type_hints(cls)

    source_field: str | None = None

    field_types: dict[str, type[QWidget]] = {}
    for field in dataclasses.fields(cls):
        if field.metadata.get("teamproject.utils.source_field", False):
            if source_field is not None:
                raise ValueError("Multiple source fields specified")
            source_field = field.name
            continue

        type_ = type_hints[field.name]  # pyright: ignore[reportAny]
        if not isinstance(type_, type):
            raise ValueError(f"Field doesn't have concrete type (got {type_!r})")
        if not issubclass(type_, QWidget):
            raise ValueError(f"Type of field {field.name} doesn't subclass QWidget (got {type_.__qualname__!r})")
        field_types[field.name] = type_

    kwargs = {name: find(source, name, type_) for name, type_ in field_types.items()}
    if source_field is not None:
        kwargs[source_field] = source

    return cls(**kwargs)

def load_and_apply_ui[T: DataclassInstance](dev: QIODevice, parent: QWidget, ui_class: type[T]) -> T:
    # I suspect the horrible bug to be here somewhere? To be honest, I don't even know
    loaded = common_ui_loader().load(dev, parent)
    ui = populate_children(loaded, ui_class)

    layout = QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(loaded)
    parent.setLayout(layout)

    return ui
