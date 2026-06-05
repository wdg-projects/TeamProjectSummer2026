from typing import final

from .treenode import TreeNode
from .util import find_tightest_container
from .svgmodel import SVGElement, TextElement

@final
class HierarchyBuilder:
    """
    Converts a flat list of SVGElements into a tree of TreeNodes using
    geometric containment to infer parent/child relationships.

    Rules:
      • Only Rectangle elements can be parents (QLabel cannot host children).
      • A text element that is not inside any rect becomes a root-level node.
    """

    def __init__(self) -> None:
        self._counter = 0

    def build(self, elements: list[SVGElement]) -> list[TreeNode[SVGElement]]:
        nodes = [TreeNode(e, self._make_name(e)) for e in elements]
        elem_to_node = {id(n.item): n for n in nodes}
        roots: list[TreeNode[SVGElement]] = []

        for node in nodes:
            parent_elem = find_tightest_container(node.item, elements)
            if parent_elem is None:
                roots.append(node)
            else:
                elem_to_node[id(parent_elem)].add_child(node)

        return roots

    def _make_name(self, elem: SVGElement) -> str:
        if elem.svg_id:
            return _sanitise_qt_name(elem.svg_id)
        self._counter += 1
        prefix = "textEdit" if isinstance(elem, TextElement) else "widget"
        return f"{prefix}_{self._counter}"

def _sanitise_qt_name(name: str) -> str:
    s = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
    if s and s[0].isdigit():
        s = "w_" + s
    return s or "widget"
