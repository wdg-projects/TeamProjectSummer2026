from typing import Callable
from xml.dom import minidom
import xml.etree.ElementTree as ET

from .atom import FontStyle
from .treenode import TreeNode
from .svgmodel import Circle, Rectangle, SVGElement, TextElement, Button

TMP_CHANGE_ROOT_CLASS = "QWidget"  # "QMainWindow"

class QtUIExporter:
    """
    Walks a TreeNode tree and produces a Qt Designer .ui XML document.

    Rectangle  →  <widget class="QWidget">
                    <property name="geometry"> …
                    <property name="styleSheet"> … (fill/stroke colours)

    TextElement→  <widget class="QLabel">
                    <property name="geometry"> …
                    <property name="font">      … (family/size/bold/italic/…)
                    <property name="styleSheet"> … (text colour, background)
                    <property name="plainText"> … (content)
                    <property name="readOnly">  … (true — read-only by default)
                    <property name="alignment"> … (text-anchor mapping)

    A QLabel is always set readOnly="false" so it remains editable in the
    running application; change readOnly to true if display-only is preferred.
    """

    def export(self, roots: list[TreeNode[SVGElement]], class_name: str = "MainWindow", window_width: int = 800, window_height: int = 600) -> str:
        ui_elem = ET.Element("ui", attrib={"version": "4.0"})
        ET.SubElement(ui_elem, "class").text = class_name

        main_window = ET.SubElement(ui_elem, "widget", attrib={"class": TMP_CHANGE_ROOT_CLASS, "name":  class_name})
        _ = self._geometry_elem((0, 0, window_width, window_height))(main_window)

        central = ET.SubElement(main_window, "widget", attrib={"class": "QWidget", "name": "centralwidget"})
        for root_node in roots:
            self._emit_node(central, root_node)

        return self._pretty_print(ui_elem)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _emit_node(self, parent_elem: ET.Element, node: TreeNode[SVGElement]) -> None:
        """Route to the correct emitter based on element type."""
        if isinstance(node.item, TextElement):
            self._emit_text_edit(parent_elem, node.unpack(TextElement))
        elif isinstance(node.item, Rectangle):
            self._emit_widget(parent_elem, node.unpack(Rectangle))
        elif isinstance(node.item, Circle):
            self._emit_circle_widget(parent_elem, node.unpack(Circle))
        elif isinstance(node.item, Button):
            self._emit_button(parent_elem, node.unpack(Button))

    # ── QWidget emitter (Rectangle) ───────────────────────────────────────────

    def _emit_widget(self, parent_elem: ET.Element, node: TreeNode[Rectangle]) -> None:
        css = self._rect_stylesheet(node.item)

        widget_elem = (
            elem("widget",
                self._geometry_elem(node),
                self._stylesheet_elem(css),
                name=node.qt_name,
                **{"class": "QWidget"}
            )
        )(parent_elem)

        for child in node.children:
            self._emit_node(widget_elem, child)
    
    # -- QWidget emitter (Circle) ----------------------------------------------

    def _emit_circle_widget(self, parent_elem: ET.Element, node: TreeNode[Circle]) -> None:
        css = self._circle_stylesheet(node.item)

        widget_elem = (
            elem("widget",
                self._geometry_elem(node),
                self._stylesheet_elem(css),
                name=node.qt_name,
                **{"class": "QWidget"}
            )
        )(parent_elem)

        for child in node.children:
            self._emit_node(widget_elem, child)

   # ── QButton emitter (Button) ───────────────────────────────────────────

    def _emit_button(self, parent_elem: ET.Element, node: TreeNode[Button]) -> None:
        
        css = self._button_stylesheet(node.item)
        widget_elem = (
            elem("widget",
                self._geometry_elem(node),
                self._font_elem(node.item.font),
                self._stylesheet_elem(css),
                self._property_elem("text", elem("string", node.item.content)),
                name=node.qt_name,
                **{"class": "QPushButton"}
            )
        )(parent_elem)
        for child in node.children:
            self._emit_node(widget_elem, child)

    # ── QLabel emitter (TextElement) ───────────────────────────────────────

    def _emit_text_edit(self, parent_elem: ET.Element, node: TreeNode[TextElement]) -> None:
        """
        Emit a <widget class="QLabel"> with font, colour, and content.

        Qt .ui property reference:
          font        → <property name="font"><font> … </font></property>
          styleSheet  → <property name="styleSheet"><string notr="true">…
          plainText   → <property name="plainText"><string>…
        """
        css = self._text_stylesheet(node.item.font)

        _ = elem("widget",
                self._geometry_elem(node),
                self._font_elem(node.item.font),
                self._stylesheet_elem(css),
                self._property_elem("text", elem("string", node.item.content)),
                name=node.qt_name,
                **{"class": "QLabel"}
            )(parent_elem)

    # ── Qt property builders ──────────────────────────────────────────────────

    @staticmethod
    def _geometry_elem(node: TreeNode[SVGElement] | tuple[int, int, int, int]) -> Callable[[ET.Element], ET.Element]:
        if isinstance(node, TreeNode):
            x, y, w, h = node.relative_geometry()
        else:
            x, y, w, h = node
        return elem("property",
                   elem("rect",
                       elem("x", str(x)),
                       elem("y", str(y)),
                       elem("width", str(w)),
                       elem("height", str(h))
                   ),
                   name="geometry"
               )

    @staticmethod
    def _stylesheet_elem(css: str) -> Callable[[ET.Element], ET.Element] | None:
        if not css.strip():
            return None
        return elem("property",
                   elem("string", css, notr="true"),
                   name="styleSheet"
               )

    @staticmethod
    def _font_elem(font: FontStyle) -> Callable[[ET.Element], ET.Element]:
        return elem("property",
                   elem("font",
                       elem("family",    font.family),
                       elem("pointsize", str(font.point_size)),
                       elem("bold",      str(font.bold).lower()),
                       elem("italic",    str(font.italic).lower()),
                       elem("underline", str(font.underline).lower()),
                       elem("strikeout", str(font.strikeout).lower())
                   ),
                   name="font"
               )

    @staticmethod
    def _property_elem(name: str, element: Callable[[ET.Element], ET.Element]) -> Callable[[ET.Element], ET.Element]:
        return elem("property", element, name=name)

    # ── Stylesheet composers ──────────────────────────────────────────────────

    @staticmethod
    def _rect_stylesheet(rect: Rectangle) -> str:
        """Build a Qt stylesheet string from a Rectangle's fill/stroke."""
        parts: dict[str, str] = {}

        if rect.fill_color:
            parts["background-color"] = rect.fill_color.to_css()

        if rect.stroke_color:
            w = max(1, round(rect.stroke_width))
            parts["border"] = f"{w}px solid {rect.stroke_color.to_css()}"

        return " ".join(f"{k}: {v};" for k, v in parts.items())

    @staticmethod
    def _circle_stylesheet(circle: Circle) -> str:
        """
        Build a Qt stylesheet string from a Circle's fill/stroke.
        """
        parts: dict[str, str] = {}

        if circle.fill_color:
            parts["background-color"] = circle.fill_color.to_css()

        if circle.stroke_color:
            w = max(1, round(circle.stroke_width))
            parts["border"] = f"{w}px solid {circle.stroke_color.to_css()}"
        
        parts["border-radius"] = str(circle.radius) + "px"

        return " ".join(f"{k}: {v};" for k, v in parts.items())

    @staticmethod
    def _button_stylesheet(button: Button) -> str:
        """Build a Qt stylesheet string from a Buttons's fill/stroke and font properties."""
        parts: dict[str, str] = {}

        if button.fill_color:
            parts["background-color"] = button.fill_color.to_css()

        if button.stroke_color:
            w = max(1, round(button.stroke_width))
            parts["border"] = f"{w}px solid {button.stroke_color.to_css()}"
        else:
            parts["border"] = "none"
        
        if button.font.color:
            parts["color"] = button.font.color.to_css()

        return " ".join(f"{k}: {v};" for k, v in parts.items())

    @staticmethod
    def _text_stylesheet(font: FontStyle) -> str:
        """
        Build a Qt stylesheet string for a QLabel.

        We always set background-color to transparent so the QLabel blends
        with whatever parent widget sits beneath it.  The text colour comes
        from the SVG fill attribute on the <text> element.
        """
        parts = {"background-color": "transparent", "border": "none"}
        if font.color:
            parts["color"] = font.color.to_css()
    
        return " ".join(f"{k}: {v};" for k, v in parts.items())

    @staticmethod
    def _pretty_print(root: ET.Element) -> str:
        raw_xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
        dom = minidom.parseString(raw_xml)
        return dom.toprettyxml(indent="    ", encoding=None)

def elem(tag: str, /, *children: Callable[[ET.Element], ET.Element] | str| None, **attrib: str) -> Callable[[ET.Element], ET.Element]:
    """
    Helper function for slightly nicer code when creating loads of XML elements.
    """
    def f(parent: ET.Element) -> ET.Element:
        res = ET.SubElement(parent, tag, attrib=attrib)
        text: str | None = None
        for child in children:
            if isinstance(child, str):
                if text is None:
                    text = child
                else:
                    text += child
            elif child is not None:
                _ = child(res)
        if text is not None:
            res.text = text
        return res
    return f

