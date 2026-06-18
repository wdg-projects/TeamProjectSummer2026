import re
from pathlib import Path
from typing import IO, Callable
import xml.etree.ElementTree as ET

from .atom import Color, ColorParser, FontParser
from .svgmodel import Circle, Rectangle, SVGElement, TextElement

_RE_STYLE_PROP = re.compile(r"([\w-]+)\s*:\s*([^;]+)")

# Height multiplier applied to font size to derive the widget bounding box
# when no explicit width/height is given in the SVG.
_TEXT_HEIGHT_FACTOR = 1.6   # line-height ~= font-size * 1.6
_TEXT_WIDTH_PER_PT  = 0.8  # rough average character width relative to pt size

class SVGParser:
    """
    Parses an SVG file and extracts:
      • Rectangle  objects from every <rect> element
      • TextElement objects from every <text> element (with <tspan> support)

    Colour and font extraction strategy:
      1. Parse inline style="" attribute into a property dict.
      2. Fall back to presentation attributes.
      3. Apply opacity / fill-opacity / stroke-opacity adjustments.
    """

    _SVG_NS: str = "http://www.w3.org/2000/svg"

    def parse(self, svg_path: str | Path | IO[str]) -> list[SVGElement]:
        """
        Load *svg_path* and return a list of SVGElement objects in document order.
        """
        tree = ET.parse(str(svg_path) if isinstance(svg_path, Path) else svg_path)
        root = tree.getroot()
        ns = self._SVG_NS

        elements: list[SVGElement] = []

        for elem in root.iter():
            local = elem.tag.replace(f"{{{ns}}}", "")
            if local == "rect":
                r = self._parse_rect(elem)
                if r:
                    elements.append(r)
            elif local == "text":
                t = self._parse_text(elem)
                if t:
                    elements.append(t)
            elif local == "circle":
                c = self._parse_circle(elem)
                if c:
                    elements.append(c)

        return elements

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _to_float(value: str | None, default: float = 0.0) -> float:
        if value is None:
            return default
        cleaned = value.strip().rstrip("px").rstrip("pt").rstrip("em").strip()
        try:
            return float(cleaned)
        except ValueError:
            return default

    @staticmethod
    def _parse_style(style_attr: str | None) -> dict[str, str]:
        if not style_attr:
            return {}
        return {m.group(1).strip().lower(): m.group(2).strip()
                for m in _RE_STYLE_PROP.finditer(style_attr)}

    def _make_prop_fn(self, elem: ET.Element):
        """
        Return a closure that resolves a CSS property name to its effective
        value: inline style first, then presentation attribute, then None.
        """
        style = self._parse_style(elem.get("style"))
        def _prop(css_name: str) -> str | None:
            return style.get(css_name) or elem.get(css_name) or None
        return _prop

    def _apply_opacity(self, fill: Color | None, stroke: Color | None, prop_fn: Callable[[str], str | None]) -> tuple[Color | None, Color | None]:
        """Apply global / channel-specific opacity attributes."""
        op_str = prop_fn("opacity")
        if op_str:
            try:
                op = max(0.0, min(1.0, float(op_str.rstrip("%"))
                                  / (100 if op_str.endswith("%") else 1)))
                fill   = ColorParser.apply_opacity(fill,   op)
                stroke = ColorParser.apply_opacity(stroke, op)
            except ValueError:
                pass

        fo_str = prop_fn("fill-opacity")
        if fo_str:
            try:
                fo = max(0.0, min(1.0, float(fo_str.rstrip("%"))
                                  / (100 if fo_str.endswith("%") else 1)))
                fill = ColorParser.apply_opacity(fill, fo)
            except ValueError:
                pass

        so_str = prop_fn("stroke-opacity")
        if so_str:
            try:
                so = max(0.0, min(1.0, float(so_str.rstrip("%"))
                                  / (100 if so_str.endswith("%") else 1)))
                stroke = ColorParser.apply_opacity(stroke, so)
            except ValueError:
                pass

        return fill, stroke

    # ── <rect> parser ─────────────────────────────────────────────────────────

    def _parse_rect(self, elem: ET.Element) -> Rectangle | None:
        x      = self._to_float(elem.get("x",      "0"))
        y      = self._to_float(elem.get("y",      "0"))
        width  = self._to_float(elem.get("width",  "0"))
        height = self._to_float(elem.get("height", "0"))
        svg_id = elem.get("id")

        if width <= 0 or height <= 0:
            return None

        prop_fn      = self._make_prop_fn(elem)
        fill_color   = ColorParser.parse(prop_fn("fill"))
        stroke_color = ColorParser.parse(prop_fn("stroke"))
        stroke_width = self._to_float(prop_fn("stroke-width"), 0.0)
        fill_color, stroke_color = self._apply_opacity(fill_color, stroke_color, prop_fn)

        return Rectangle(x=x, y=y, width=width, height=height, svg_id=svg_id,
                         fill_color=fill_color, stroke_color=stroke_color,
                         stroke_width=stroke_width)

    # -- <circle> parser -------------------------------------------------------

    def _parse_circle(self, elem: ET.Element) -> Circle | None:
        cx = self._to_float(elem.get("cx", "0"))
        cy = self._to_float(elem.get("cy", "0"))
        radius = self._to_float(elem.get("r", "0"))
        svg_id = elem.get("id")

        if radius <= 0:
            return None
        
        prop_fn      = self._make_prop_fn(elem)
        fill_color   = ColorParser.parse(prop_fn("fill"))
        stroke_color = ColorParser.parse(prop_fn("stroke"))
        stroke_width = self._to_float(prop_fn("stroke-width"), 0.0)
        fill_color, stroke_color = self._apply_opacity(fill_color, stroke_color, prop_fn)
        return Circle(x=cx-radius, y=cy-radius, width=2*radius, height=2*radius,
                      cx=cx, cy=cy, radius=radius, svg_id=svg_id,
                      fill_color=fill_color, stroke_color=stroke_color,
                      stroke_width=stroke_width)


    # ── <text> parser ─────────────────────────────────────────────────────────

    def _parse_text(self, elem: ET.Element) -> TextElement | None:
        """
        Parse a <text> element (and its <tspan> children) into a TextElement.

        Geometry:
          • x, y come from the element attributes (baseline anchor).
          • width / height are estimated from font metrics when not explicit.
          • y is adjusted upward by font_size_px so (x, y) becomes top-left.

        Content:
          • Concatenate the text of the <text> node and all <tspan> children,
            separated by newlines for each <tspan> that has its own y attribute
            (indicating a new line), or a space otherwise.
        """
        svg_id  = elem.get("id")
        prop_fn = self._make_prop_fn(elem)

        # ── Font metrics ───────────────────────────────────────────────────────
        font       = FontParser.parse(prop_fn)
        font_size_px = font.point_size / _TEXT_HEIGHT_FACTOR   # rough px back

        # ── Collect text content from the element and its tspan children ──────
        ns     = self._SVG_NS
        lines: list[str] = []

        # Direct text content on the <text> element itself.
        direct = (elem.text or "").strip()
        if direct:
            lines.append(direct)

        prev_tspan_y: float | None = None
        for child in elem:
            local = child.tag.replace(f"{{{ns}}}", "")
            if local != "tspan":
                continue
            chunk = self._collect_text(child).strip()
            if not chunk:
                continue
            # A tspan with a new y value starts a new visual line.
            tspan_y_str = child.get("y")
            if tspan_y_str is not None:
                tspan_y = self._to_float(tspan_y_str)
                if prev_tspan_y is not None and tspan_y != prev_tspan_y:
                    lines.append("\n")
                prev_tspan_y = tspan_y
            lines.append(chunk)

        content = " ".join(lines).replace(" \n ", "\n").strip()

        if not content:
            return None   # empty <text> – skip

        # Estimate width from character count when not explicit.
        char_count  = max(len(line) for line in content.splitlines() or [""])
        est_width   = max(10.0, char_count * font.point_size * _TEXT_WIDTH_PER_PT)
        est_height  = max(10.0,
                          len(content.splitlines()) * font_size_px * _TEXT_HEIGHT_FACTOR)

        width  = self._to_float(elem.get("width"),  est_width)
        height = self._to_float(elem.get("height"), est_height)

        # ── Geometry ──────────────────────────────────────────────────────────

        anchor_x = self._to_float(elem.get("x", "0")) - 5
        anchor_y = self._to_float(elem.get("y", "0")) - height

        return TextElement(
            x=anchor_x, y=anchor_y,
            width=width, height=height,
            content=content,
            svg_id=svg_id,
            font=font,
        )

    @staticmethod
    def _collect_text(elem: ET.Element) -> str:
        """Collect all text content from an element and its sub-elements."""
        parts = [elem.text or ""]
        for child in elem:
            parts.append((child.text or "") + (child.tail or ""))
        parts.append(elem.tail or "")
        return "".join(parts)
