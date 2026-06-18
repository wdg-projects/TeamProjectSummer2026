from typing import Generic, TypeVar, cast, override

from .svgmodel import Circle, Rectangle, SVGElement, TextElement, Button

TElement = TypeVar("TElement", bound=SVGElement, covariant=True)
class TreeNode(Generic[TElement]):
    """
    One node in the Qt widget tree.

    item      - the underlying SVGElement (Rectangle, TextElement or Circle)
    qt_name   - QWidget objectName in the .ui file
    children  - child TreeNodes (always empty for TextElement nodes)
    parent    - reference to parent TreeNode, None → direct child of central
    """

    item: TElement
    qt_name: str
    children: list[TreeNode[SVGElement]]
    parent: TreeNode[SVGElement] | None

    def __init__(self, item: TElement, qt_name: str) -> None:
        self.item = item
        self.qt_name = qt_name
        self.children = []
        self.parent = None

    def add_child(self, child: TreeNode[SVGElement]) -> None:
        child.parent = self
        self.children.append(child)

    def absolute_origin(self) -> tuple[float, float]:
        return self.item.x, self.item.y

    def relative_geometry(self) -> tuple[int, int, int, int]:
        """
        Return (x, y, w, h) with x/y relative to the direct parent widget.
        Root-level elements use absolute SVG coordinates.
        """
        ax, ay = self.item.x, self.item.y
        if self.parent is not None:
            px, py = self.parent.absolute_origin()
            ax -= px
            ay -= py
        return (int(round(ax)), int(round(ay)),
                int(round(self.item.width)), int(round(self.item.height)))

    def unpack[U: SVGElement](self, inner_type: type[U]) -> TreeNode[U]:
        if isinstance(self.item, inner_type):
            return cast(TreeNode[U], self)
        raise ValueError("The node type doesn't match the given type")

    @override
    def __repr__(self) -> str:
        if isinstance(self.item, TextElement):
            kind = "text"
        elif isinstance(self.item, Rectangle):
            kind = "rect"
        elif isinstance(self.item, Circle):
            kind = "circle"
        elif isinstance(self.item, Button):
            kind = "button"
        else:
            kind = "idk"
        return f"TreeNode({kind}, name={self.qt_name!r}, children={len(self.children)})"
