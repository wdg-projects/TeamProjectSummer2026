#!/usr/bin/env python3
"""
svg_to_qt_ui.py
===============
Converts an SVG file containing <rect> and <text> elements into a valid
Qt Designer .ui XML file.

  <rect>   →  QWidget   (with background / border from fill / stroke)
  <text>   →  QTextEdit (with font, colour, and plain-text content)

Architecture:
  1.  Color           – immutable RGBA colour model
  2.  ColorParser     – parses every SVG colour syntax → Color
  3.  FontStyle       – immutable font descriptor
  4.  Rectangle       – rect geometry + fill/stroke colours
  5.  TextElement     – text geometry + content + font
  6.  SVGElement      – Union alias used throughout
  7.  SVGParser       – extracts Rectangle and TextElement objects from SVG
  8.  Containment     – geometric parent-finding helpers
  9.  TreeNode        – one node in the widget tree (wraps an SVGElement)
  10. HierarchyBuilder– builds the tree from a flat element list
  11. QtUIExporter    – walks the tree → Qt Designer XML
  12. SVGToQtUI       – pipeline façade
  13. Demo / CLI

SVG colour sources (priority order):
  style=""  >  presentation attributes  >  opacity attributes

Colour formats:  #rgb  #rrggbb  #rrggbbaa  rgb()  rgba()  CSS names  none

SVG font sources:
  style=""  >  font-family= / font-size= / font-weight= / font-style= /
               text-decoration= / text-anchor= / fill= (text colour)

Usage:
  python svg_to_qt_ui.py input.svg [output.ui] [--class-name NAME]
  python svg_to_qt_ui.py --demo
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from xml.dom import minidom


# ──────────────────────────────────────────────────────────────────────────────
# 1. COLOUR DATA MODEL
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Color:
    """Immutable RGBA colour with 8-bit channels (0-255). Alpha 255 = opaque."""
    r: int
    g: int
    b: int
    a: int = 255

    def to_css(self) -> str:
        """Minimal CSS colour string for Qt stylesheets."""
        if self.a == 255:
            return f"rgb({self.r}, {self.g}, {self.b})"
        return f"rgba({self.r}, {self.g}, {self.b}, {self.a})"

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def __repr__(self) -> str:
        return f"Color({self.to_hex()}, a={self.a})"


# ──────────────────────────────────────────────────────────────────────────────
# 2. COLOUR PARSER
# ──────────────────────────────────────────────────────────────────────────────

_CSS_NAMED_COLORS: Dict[str, Tuple[int, int, int]] = {
    "aliceblue":(240,248,255),"antiquewhite":(250,235,215),"aqua":(0,255,255),
    "aquamarine":(127,255,212),"azure":(240,255,255),"beige":(245,245,220),
    "bisque":(255,228,196),"black":(0,0,0),"blanchedalmond":(255,235,205),
    "blue":(0,0,255),"blueviolet":(138,43,226),"brown":(165,42,42),
    "burlywood":(222,184,135),"cadetblue":(95,158,160),"chartreuse":(127,255,0),
    "chocolate":(210,105,30),"coral":(255,127,80),"cornflowerblue":(100,149,237),
    "cornsilk":(255,248,220),"crimson":(220,20,60),"cyan":(0,255,255),
    "darkblue":(0,0,139),"darkcyan":(0,139,139),"darkgoldenrod":(184,134,11),
    "darkgray":(169,169,169),"darkgreen":(0,100,0),"darkgrey":(169,169,169),
    "darkkhaki":(189,183,107),"darkmagenta":(139,0,139),"darkolivegreen":(85,107,47),
    "darkorange":(255,140,0),"darkorchid":(153,50,204),"darkred":(139,0,0),
    "darksalmon":(233,150,122),"darkseagreen":(143,188,143),
    "darkslateblue":(72,61,139),"darkslategray":(47,79,79),
    "darkslategrey":(47,79,79),"darkturquoise":(0,206,209),
    "darkviolet":(148,0,211),"deeppink":(255,20,147),"deepskyblue":(0,191,255),
    "dimgray":(105,105,105),"dimgrey":(105,105,105),"dodgerblue":(30,144,255),
    "firebrick":(178,34,34),"floralwhite":(255,250,240),"forestgreen":(34,139,34),
    "fuchsia":(255,0,255),"gainsboro":(220,220,220),"ghostwhite":(248,248,255),
    "gold":(255,215,0),"goldenrod":(218,165,32),"gray":(128,128,128),
    "green":(0,128,0),"greenyellow":(173,255,47),"grey":(128,128,128),
    "honeydew":(240,255,240),"hotpink":(255,105,180),"indianred":(205,92,92),
    "indigo":(75,0,130),"ivory":(255,255,240),"khaki":(240,230,140),
    "lavender":(230,230,250),"lavenderblush":(255,240,245),"lawngreen":(124,252,0),
    "lemonchiffon":(255,250,205),"lightblue":(173,216,230),
    "lightcoral":(240,128,128),"lightcyan":(224,255,255),
    "lightgoldenrodyellow":(250,250,210),"lightgray":(211,211,211),
    "lightgreen":(144,238,144),"lightgrey":(211,211,211),"lightpink":(255,182,193),
    "lightsalmon":(255,160,122),"lightseagreen":(32,178,170),
    "lightskyblue":(135,206,250),"lightslategray":(119,136,153),
    "lightslategrey":(119,136,153),"lightsteelblue":(176,196,222),
    "lightyellow":(255,255,224),"lime":(0,255,0),"limegreen":(50,205,50),
    "linen":(250,240,230),"magenta":(255,0,255),"maroon":(128,0,0),
    "mediumaquamarine":(102,205,170),"mediumblue":(0,0,205),
    "mediumorchid":(186,85,211),"mediumpurple":(147,112,219),
    "mediumseagreen":(60,179,113),"mediumslateblue":(123,104,238),
    "mediumspringgreen":(0,250,154),"mediumturquoise":(72,209,204),
    "mediumvioletred":(199,21,133),"midnightblue":(25,25,112),
    "mintcream":(245,255,250),"mistyrose":(255,228,225),"moccasin":(255,228,181),
    "navajowhite":(255,222,173),"navy":(0,0,128),"oldlace":(253,245,230),
    "olive":(128,128,0),"olivedrab":(107,142,35),"orange":(255,165,0),
    "orangered":(255,69,0),"orchid":(218,112,214),"palegoldenrod":(238,232,170),
    "palegreen":(152,251,152),"paleturquoise":(175,238,238),
    "palevioletred":(219,112,147),"papayawhip":(255,239,213),
    "peachpuff":(255,218,185),"peru":(205,133,63),"pink":(255,192,203),
    "plum":(221,160,221),"powderblue":(176,224,230),"purple":(128,0,128),
    "rebeccapurple":(102,51,153),"red":(255,0,0),"rosybrown":(188,143,143),
    "royalblue":(65,105,225),"saddlebrown":(139,69,19),"salmon":(250,128,114),
    "sandybrown":(244,164,96),"seagreen":(46,139,87),"seashell":(255,245,238),
    "sienna":(160,82,45),"silver":(192,192,192),"skyblue":(135,206,235),
    "slateblue":(106,90,205),"slategray":(112,128,144),"slategrey":(112,128,144),
    "snow":(255,250,250),"springgreen":(0,255,127),"steelblue":(70,130,180),
    "tan":(210,180,140),"teal":(0,128,128),"thistle":(216,191,216),
    "tomato":(255,99,71),"turquoise":(64,224,208),"violet":(238,130,238),
    "wheat":(245,222,179),"white":(255,255,255),"whitesmoke":(245,245,245),
    "yellow":(255,255,0),"yellowgreen":(154,205,50),
}

_RE_RGB  = re.compile(
    r"rgb\(\s*(\d+(?:\.\d+)?%?)\s*,\s*(\d+(?:\.\d+)?%?)\s*,"
    r"\s*(\d+(?:\.\d+)?%?)\s*\)", re.I)
_RE_RGBA = re.compile(
    r"rgba\(\s*(\d+(?:\.\d+)?%?)\s*,\s*(\d+(?:\.\d+)?%?)\s*,"
    r"\s*(\d+(?:\.\d+)?%?)\s*,\s*([\d.]+%?)\s*\)", re.I)


class ColorParser:
    """
    Parse any SVG/CSS colour string → Color (or None for 'none'/'transparent').

    Formats: #rgb  #rrggbb  #rrggbbaa  rgb()  rgba()  CSS named  none
    """

    @classmethod
    def parse(cls, value: Optional[str]) -> Optional[Color]:
        if not value:
            return None
        v = value.strip().lower()
        if v in ("none", "transparent", "inherit", "currentcolor", ""):
            return None
        return (cls._parse_hex(v) or cls._parse_rgb(v)
                or cls._parse_rgba(v) or cls._parse_named(v))

    @staticmethod
    def _parse_hex(v: str) -> Optional[Color]:
        if not v.startswith("#"):
            return None
        h = v[1:]
        try:
            if len(h) == 3:
                return Color(int(h[0]*2,16), int(h[1]*2,16), int(h[2]*2,16))
            if len(h) == 6:
                return Color(int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))
            if len(h) == 8:
                return Color(int(h[0:2],16), int(h[2:4],16),
                             int(h[4:6],16), int(h[6:8],16))
        except ValueError:
            pass
        return None

    @staticmethod
    def _channel(raw: str) -> int:
        raw = raw.strip()
        if raw.endswith("%"):
            return max(0, min(255, round(float(raw[:-1]) * 255 / 100)))
        return max(0, min(255, round(float(raw))))

    @staticmethod
    def _alpha(raw: str) -> int:
        raw = raw.strip()
        if raw.endswith("%"):
            return max(0, min(255, round(float(raw[:-1]) * 255 / 100)))
        return max(0, min(255, round(float(raw) * 255)))

    @classmethod
    def _parse_rgb(cls, v: str) -> Optional[Color]:
        m = _RE_RGB.fullmatch(v)
        return Color(cls._channel(m.group(1)), cls._channel(m.group(2)),
                     cls._channel(m.group(3))) if m else None

    @classmethod
    def _parse_rgba(cls, v: str) -> Optional[Color]:
        m = _RE_RGBA.fullmatch(v)
        return Color(cls._channel(m.group(1)), cls._channel(m.group(2)),
                     cls._channel(m.group(3)), cls._alpha(m.group(4))) if m else None

    @staticmethod
    def _parse_named(v: str) -> Optional[Color]:
        rgb = _CSS_NAMED_COLORS.get(v)
        return Color(*rgb) if rgb else None

    @staticmethod
    def apply_opacity(color: Optional[Color], opacity: float) -> Optional[Color]:
        """Multiply alpha by *opacity* (0.0–1.0)."""
        if color is None:
            return None
        return Color(color.r, color.g, color.b,
                     max(0, min(255, round(color.a * opacity))))


# ──────────────────────────────────────────────────────────────────────────────
# 3. FONT STYLE
# ──────────────────────────────────────────────────────────────────────────────

# Qt alignment flag strings used in the <enum> property element.
_TEXT_ANCHOR_TO_QT: Dict[str, str] = {
    "start":  "Qt::AlignLeft",
    "middle": "Qt::AlignHCenter",
    "end":    "Qt::AlignRight",
}

# Canonical Qt font families for common SVG generic names.
_GENERIC_FAMILY_MAP: Dict[str, str] = {
    "serif":      "Times New Roman",
    "sans-serif": "Arial",
    "monospace":  "Courier New",
    "cursive":    "Comic Sans MS",
    "fantasy":    "Impact",
    "system-ui":  "Arial",
    "ui-serif":   "Times New Roman",
    "ui-monospace": "Courier New",
}


@dataclass(frozen=True)
class FontStyle:
    """
    Immutable descriptor for the typographic properties of a <text> element.

    point_size  – font size in Qt points  (SVG px converted at 0.75 pt/px)
    family      – resolved font family name
    bold        – True when font-weight >= 600 or == 'bold' / 'bolder'
    italic      – True when font-style == 'italic' or 'oblique'
    underline   – True when text-decoration contains 'underline'
    strikeout   – True when text-decoration contains 'line-through'
    color       – foreground (text) colour, None → inherit
    alignment   – Qt alignment flag string, e.g. 'Qt::AlignLeft'
    """
    point_size: int           = 10
    family:     str           = "Arial"
    bold:       bool          = False
    italic:     bool          = False
    underline:  bool          = False
    strikeout:  bool          = False
    color:      Optional[Color] = None
    alignment:  str           = "Qt::AlignLeft"

    def __repr__(self) -> str:
        flags = "".join([
            "B" if self.bold      else "",
            "I" if self.italic    else "",
            "U" if self.underline else "",
            "S" if self.strikeout else "",
        ])
        col = f" color={self.color.to_hex()}" if self.color else ""
        return (f"FontStyle({self.family} {self.point_size}pt"
                f"{' '+flags if flags else ''}{col})")


class FontParser:
    """
    Extract a FontStyle from SVG style dict + presentation attributes.

    Called with the merged property resolver already set up by SVGParser so
    this class stays pure and stateless.
    """

    # Factor to convert SVG/CSS px → Qt points.
    _PX_TO_PT: float = 0.75

    @classmethod
    def parse(cls, prop_fn) -> FontStyle:
        """
        Build a FontStyle by calling *prop_fn(css_name)* for each property.
        *prop_fn* returns the effective string value or None.
        """
        family    = cls._resolve_family(prop_fn("font-family"))
        point_size= cls._resolve_size(prop_fn("font-size"))
        bold      = cls._resolve_bold(prop_fn("font-weight"))
        italic    = prop_fn("font-style") in ("italic", "oblique")
        deco      = (prop_fn("text-decoration") or "").lower()
        underline = "underline"    in deco
        strikeout = "line-through" in deco
        color     = ColorParser.parse(prop_fn("fill"))
        alignment = _TEXT_ANCHOR_TO_QT.get(
            (prop_fn("text-anchor") or "start").strip().lower(),
            "Qt::AlignLeft",
        )

        # Apply fill-opacity to text colour.
        fo_str = prop_fn("fill-opacity")
        if fo_str and color:
            try:
                fo = max(0.0, min(1.0, float(fo_str.rstrip("%"))
                                  / (100 if fo_str.endswith("%") else 1)))
                color = ColorParser.apply_opacity(color, fo)
            except ValueError:
                pass

        return FontStyle(point_size=point_size, family=family, bold=bold,
                         italic=italic, underline=underline, strikeout=strikeout,
                         color=color, alignment=alignment)

    @classmethod
    def _resolve_family(cls, raw: Optional[str]) -> str:
        """
        SVG font-family can be a comma-separated list of faces.
        Try each candidate in order; map generic names; default to Arial.
        """
        if not raw:
            return "Arial"
        candidates = [f.strip().strip("'\"") for f in raw.split(",")]
        for candidate in candidates:
            lower = candidate.lower()
            # Direct generic map
            if lower in _GENERIC_FAMILY_MAP:
                return _GENERIC_FAMILY_MAP[lower]
            # Non-empty named family – use as-is (Qt will fall back internally)
            if candidate:
                return candidate
        return "Arial"

    @classmethod
    def _resolve_size(cls, raw: Optional[str]) -> int:
        """
        Convert SVG font-size to Qt point size.
        Handles: '16px', '16', '12pt', '1.5em' (em treated as ×16px base),
                 keyword sizes ('small', 'medium', 'large', …).
        """
        _KEYWORD_PX = {
            "xx-small": 9, "x-small": 10, "small": 13,
            "medium": 16, "large": 18, "x-large": 24,
            "xx-large": 32, "xxx-large": 40,
        }
        if not raw:
            return 10
        raw = raw.strip().lower()
        if raw in _KEYWORD_PX:
            return max(1, round(_KEYWORD_PX[raw] * cls._PX_TO_PT))
        try:
            if raw.endswith("pt"):
                return max(1, round(float(raw[:-2])))
            if raw.endswith("em"):
                return max(1, round(float(raw[:-2]) * 16 * cls._PX_TO_PT))
            if raw.endswith("%"):
                return max(1, round(float(raw[:-1]) / 100 * 16 * cls._PX_TO_PT))
            # px or bare number
            px = float(raw.rstrip("px").strip())
            return max(1, round(px * cls._PX_TO_PT))
        except ValueError:
            return 10

    @staticmethod
    def _resolve_bold(raw: Optional[str]) -> bool:
        if not raw:
            return False
        raw = raw.strip().lower()
        if raw in ("bold", "bolder", "800", "900"):
            return True
        try:
            return int(raw) >= 600
        except ValueError:
            return False


# ──────────────────────────────────────────────────────────────────────────────
# 4. DATA MODELS  (Rectangle  &  TextElement)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Rectangle:
    """
    An SVG <rect> → becomes a QWidget in the .ui file.
    All coordinates are absolute SVG viewport space.
    """
    x: float
    y: float
    width: float
    height: float
    svg_id:       Optional[str]   = None
    fill_color:   Optional[Color] = None
    stroke_color: Optional[Color] = None
    stroke_width: float           = 0.0

    @property
    def right(self)  -> float: return self.x + self.width
    @property
    def bottom(self) -> float: return self.y + self.height
    @property
    def area(self)   -> float: return self.width * self.height

    def __repr__(self) -> str:
        tag  = f"id={self.svg_id!r}" if self.svg_id else "no id"
        fill = f" fill={self.fill_color.to_hex()}"    if self.fill_color   else ""
        strk = (f" stroke={self.stroke_color.to_hex()}@{self.stroke_width}px"
                if self.stroke_color else "")
        return (f"Rectangle({tag}, x={self.x}, y={self.y}, "
                f"w={self.width}, h={self.height}{fill}{strk})")


# Height multiplier applied to font size to derive the widget bounding box
# when no explicit width/height is given in the SVG.
_TEXT_HEIGHT_FACTOR = 1.6   # line-height ≈ font-size × 1.6
_TEXT_WIDTH_PER_PT  = 0.65  # rough average character width relative to pt size


@dataclass(frozen=True)
class TextElement:
    """
    An SVG <text> (or <text>/<tspan>) → becomes a QTextEdit in the .ui file.

    SVG text position semantics:
      (x, y) is the *baseline anchor point*, not the top-left corner.
      We convert it to a top-left bounding box using the font metrics:
        top   = y - font_size_px
        width = estimated from character count when not given explicitly
        height= font_size_px × _TEXT_HEIGHT_FACTOR

    If the SVG element carries explicit width/height attributes (uncommon but
    possible via a foreignObject-style convention), those are used directly.
    """
    x:       float          # top-left x (already converted from baseline)
    y:       float          # top-left y (already converted from baseline)
    width:   float          # estimated or explicit
    height:  float          # estimated or explicit
    content: str            = ""    # plain-text content (tspans joined)
    svg_id:  Optional[str]  = None
    font:    FontStyle      = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Provide a default FontStyle when none is given.
        if self.font is None:
            object.__setattr__(self, "font", FontStyle())

    @property
    def right(self)  -> float: return self.x + self.width
    @property
    def bottom(self) -> float: return self.y + self.height
    @property
    def area(self)   -> float: return self.width * self.height

    def __repr__(self) -> str:
        tag = f"id={self.svg_id!r}" if self.svg_id else "no id"
        preview = self.content[:30].replace("\n", "↵")
        return (f"TextElement({tag}, x={self.x:.0f}, y={self.y:.0f}, "
                f"w={self.width:.0f}, h={self.height:.0f}, "
                f"text={preview!r}, {self.font})")


# Union of the two element types – used as the generic SVGElement.
SVGElement = Union[Rectangle, TextElement]


# ──────────────────────────────────────────────────────────────────────────────
# 5. CONTAINMENT HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def contains(outer: SVGElement, inner: SVGElement) -> bool:
    """
    Return True if *outer* fully contains *inner* by bounding-box.
    An element does not contain itself.
    """
    if outer is inner:
        return False
    return (
        inner.x      >= outer.x
        and inner.y      >= outer.y
        and inner.right  <= outer.right
        and inner.bottom <= outer.bottom
    )


def find_tightest_container(
    candidate: SVGElement,
    all_elements: List[SVGElement],
) -> Optional[SVGElement]:
    """
    Return the smallest-area element in *all_elements* that fully contains
    *candidate*, or None if *candidate* is at root level.

    Text elements are never treated as containers (a QTextEdit cannot be a
    parent widget in Qt Designer).
    """
    containers = [
        e for e in all_elements
        if isinstance(e, Rectangle) and contains(e, candidate)
    ]
    return min(containers, key=lambda e: e.area) if containers else None


# ──────────────────────────────────────────────────────────────────────────────
# 6. SVG PARSER
# ──────────────────────────────────────────────────────────────────────────────

_RE_STYLE_PROP = re.compile(r"([\w-]+)\s*:\s*([^;]+)")


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

    _SVG_NS = "http://www.w3.org/2000/svg"

    def parse(self, svg_path: str | Path) -> List[SVGElement]:
        """
        Load *svg_path* and return a list of SVGElement objects in document order.
        """
        tree = ET.parse(str(svg_path))
        root = tree.getroot()
        ns   = self._SVG_NS

        elements: List[SVGElement] = []

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

        return elements

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _to_float(value: Optional[str], default: float = 0.0) -> float:
        if value is None:
            return default
        cleaned = value.strip().rstrip("px").rstrip("pt").rstrip("em").strip()
        try:
            return float(cleaned)
        except ValueError:
            return default

    @staticmethod
    def _parse_style(style_attr: Optional[str]) -> Dict[str, str]:
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
        def _prop(css_name: str) -> Optional[str]:
            return style.get(css_name) or elem.get(css_name) or None
        return _prop

    def _apply_opacity(
        self,
        fill: Optional[Color],
        stroke: Optional[Color],
        prop_fn,
    ) -> Tuple[Optional[Color], Optional[Color]]:
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

    def _parse_rect(self, elem: ET.Element) -> Optional[Rectangle]:
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
        fill_color, stroke_color = self._apply_opacity(
            fill_color, stroke_color, prop_fn)

        return Rectangle(x=x, y=y, width=width, height=height, svg_id=svg_id,
                         fill_color=fill_color, stroke_color=stroke_color,
                         stroke_width=stroke_width)

    # ── <text> parser ─────────────────────────────────────────────────────────

    def _parse_text(self, elem: ET.Element) -> Optional[TextElement]:
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
        lines: List[str] = []

        # Direct text content on the <text> element itself.
        direct = (elem.text or "").strip()
        if direct:
            lines.append(direct)

        prev_tspan_y: Optional[float] = None
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

        # ── Geometry ──────────────────────────────────────────────────────────
        anchor_x = self._to_float(elem.get("x", "0"))
        anchor_y = self._to_float(elem.get("y", "0"))

        # SVG y is the baseline; Qt needs the top-left corner.
        top_y = anchor_y - font_size_px * 1.1   # ≈ cap-height above baseline

        # Estimate width from character count when not explicit.
        char_count  = max(len(line) for line in content.splitlines() or [""])
        est_width   = max(60.0, char_count * font.point_size * _TEXT_WIDTH_PER_PT)
        est_height  = max(20.0,
                          len(content.splitlines()) * font_size_px * _TEXT_HEIGHT_FACTOR)

        width  = self._to_float(elem.get("width"),  est_width)
        height = self._to_float(elem.get("height"), est_height)

        return TextElement(
            x=anchor_x, y=top_y,
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


# ──────────────────────────────────────────────────────────────────────────────
# 7. WIDGET TREE  (TreeNode)
# ──────────────────────────────────────────────────────────────────────────────

class TreeNode:
    """
    One node in the Qt widget tree.

    item      – the underlying SVGElement (Rectangle or TextElement)
    qt_name   – QWidget objectName in the .ui file
    children  – child TreeNodes (always empty for TextElement nodes)
    parent    – reference to parent TreeNode, None → direct child of central
    """

    def __init__(self, item: SVGElement, qt_name: str) -> None:
        self.item     = item
        self.qt_name  = qt_name
        self.children: List[TreeNode] = []
        self.parent:   Optional[TreeNode] = None

    @property
    def is_text(self) -> bool:
        return isinstance(self.item, TextElement)

    def add_child(self, child: "TreeNode") -> None:
        child.parent = self
        self.children.append(child)

    def absolute_origin(self) -> Tuple[float, float]:
        return self.item.x, self.item.y

    def relative_geometry(self) -> Tuple[int, int, int, int]:
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

    def __repr__(self) -> str:
        kind = "text" if self.is_text else "rect"
        return f"TreeNode({kind}, name={self.qt_name!r}, children={len(self.children)})"


# ──────────────────────────────────────────────────────────────────────────────
# 8. HIERARCHY BUILDER
# ──────────────────────────────────────────────────────────────────────────────

class HierarchyBuilder:
    """
    Converts a flat list of SVGElements into a tree of TreeNodes using
    geometric containment to infer parent/child relationships.

    Rules:
      • Only Rectangle elements can be parents (QTextEdit cannot host children).
      • A text element that is not inside any rect becomes a root-level node.
    """

    def __init__(self) -> None:
        self._counter = 0

    def build(self, elements: List[SVGElement]) -> List[TreeNode]:
        nodes         = [TreeNode(e, self._make_name(e)) for e in elements]
        elem_to_node  = {id(n.item): n for n in nodes}
        roots: List[TreeNode] = []

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


# ──────────────────────────────────────────────────────────────────────────────
# 9. QT UI XML EXPORTER
# ──────────────────────────────────────────────────────────────────────────────

class QtUIExporter:
    """
    Walks a TreeNode tree and produces a Qt Designer .ui XML document.

    Rectangle  →  <widget class="QWidget">
                    <property name="geometry"> …
                    <property name="styleSheet"> … (fill/stroke colours)

    TextElement→  <widget class="QTextEdit">
                    <property name="geometry"> …
                    <property name="font">      … (family/size/bold/italic/…)
                    <property name="styleSheet"> … (text colour, background)
                    <property name="plainText"> … (content)
                    <property name="readOnly">  … (true — read-only by default)
                    <property name="alignment"> … (text-anchor mapping)

    A QTextEdit is always set readOnly="false" so it remains editable in the
    running application; change readOnly to true if display-only is preferred.
    """

    def export(
        self,
        roots: List[TreeNode],
        class_name:    str = "MainWindow",
        window_width:  int = 800,
        window_height: int = 600,
    ) -> str:
        ui_elem = ET.Element("ui", attrib={"version": "4.0"})
        ET.SubElement(ui_elem, "class").text = class_name

        main_window = ET.SubElement(ui_elem, "widget",
                                    attrib={"class": "QMainWindow",
                                            "name":  class_name})
        self._add_geometry(main_window, 0, 0, window_width, window_height)

        central = ET.SubElement(main_window, "widget",
                                attrib={"class": "QWidget",
                                        "name":  "centralwidget"})

        for root_node in roots:
            self._emit_node(central, root_node)

        return self._pretty_print(ui_elem)

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _emit_node(self, parent_elem: ET.Element, node: TreeNode) -> None:
        """Route to the correct emitter based on element type."""
        if node.is_text:
            self._emit_text_edit(parent_elem, node)
        else:
            self._emit_widget(parent_elem, node)

    # ── QWidget emitter (Rectangle) ───────────────────────────────────────────

    def _emit_widget(self, parent_elem: ET.Element, node: TreeNode) -> None:
        x, y, w, h = node.relative_geometry()
        widget_elem = ET.SubElement(parent_elem, "widget",
                                    attrib={"class": "QWidget",
                                            "name":  node.qt_name})
        self._add_geometry(widget_elem, x, y, w, h)

        css = self._rect_stylesheet(node.item)   # type: ignore[arg-type]
        if css:
            self._add_stylesheet(widget_elem, css)

        for child in node.children:
            self._emit_node(widget_elem, child)

    # ── QTextEdit emitter (TextElement) ───────────────────────────────────────

    def _emit_text_edit(self, parent_elem: ET.Element, node: TreeNode) -> None:
        """
        Emit a <widget class="QTextEdit"> with font, colour, and content.

        Qt .ui property reference:
          font        → <property name="font"><font> … </font></property>
          styleSheet  → <property name="styleSheet"><string notr="true">…
          plainText   → <property name="plainText"><string>…
          readOnly    → <property name="readOnly"><bool>false</bool>
          alignment   → not a standard QTextEdit property; we add it as a
                        comment so the developer knows the original intent.
        """
        x, y, w, h = node.relative_geometry()
        te: TextElement = node.item  # type: ignore[assignment]

        widget_elem = ET.SubElement(parent_elem, "widget",
                                    attrib={"class": "QTextEdit",
                                            "name":  node.qt_name})
        # Geometry
        self._add_geometry(widget_elem, x, y, w, h)

        # Font
        self._add_font(widget_elem, te.font)

        # Stylesheet (text colour + transparent background by default)
        css = self._text_stylesheet(te.font)
        if css:
            self._add_stylesheet(widget_elem, css)

        # Plain-text content
        self._add_plain_text(widget_elem, te.content)

        # readOnly — set to false so the widget is editable; change as needed.
        self._add_bool_property(widget_elem, "readOnly", False)

    # ── Qt property builders ──────────────────────────────────────────────────

    @staticmethod
    def _add_geometry(parent: ET.Element,
                      x: int, y: int, w: int, h: int) -> None:
        """
        <property name="geometry">
          <rect><x>…</x><y>…</y><width>…</width><height>…</height></rect>
        </property>
        """
        prop = ET.SubElement(parent, "property", attrib={"name": "geometry"})
        rect = ET.SubElement(prop, "rect")
        for tag, val in (("x", x), ("y", y), ("width", w), ("height", h)):
            ET.SubElement(rect, tag).text = str(val)

    @staticmethod
    def _add_stylesheet(parent: ET.Element, css: str) -> None:
        """
        <property name="styleSheet">
          <string notr="true">…</string>
        </property>
        """
        prop = ET.SubElement(parent, "property", attrib={"name": "styleSheet"})
        ET.SubElement(prop, "string", attrib={"notr": "true"}).text = css

    @staticmethod
    def _add_font(parent: ET.Element, font: FontStyle) -> None:
        """
        <property name="font">
          <font>
            <family>Arial</family>
            <pointsize>12</pointsize>
            <bold>true</bold>
            <italic>false</italic>
            <underline>false</underline>
            <strikeout>false</strikeout>
          </font>
        </property>
        """
        prop      = ET.SubElement(parent, "property", attrib={"name": "font"})
        font_elem = ET.SubElement(prop, "font")
        ET.SubElement(font_elem, "family").text    = font.family
        ET.SubElement(font_elem, "pointsize").text = str(font.point_size)
        ET.SubElement(font_elem, "bold").text      = str(font.bold).lower()
        ET.SubElement(font_elem, "italic").text    = str(font.italic).lower()
        ET.SubElement(font_elem, "underline").text = str(font.underline).lower()
        ET.SubElement(font_elem, "strikeout").text = str(font.strikeout).lower()

    @staticmethod
    def _add_plain_text(parent: ET.Element, text: str) -> None:
        """
        <property name="plainText">
          <string>…</string>
        </property>
        """
        prop = ET.SubElement(parent, "property", attrib={"name": "plainText"})
        ET.SubElement(prop, "string").text = text

    @staticmethod
    def _add_bool_property(parent: ET.Element, name: str, value: bool) -> None:
        """<property name="…"><bool>true|false</bool></property>"""
        prop = ET.SubElement(parent, "property", attrib={"name": name})
        ET.SubElement(prop, "bool").text = str(value).lower()

    # ── Stylesheet composers ──────────────────────────────────────────────────

    @staticmethod
    def _rect_stylesheet(rect: Rectangle) -> str:
        """Build a Qt stylesheet string from a Rectangle's fill/stroke."""
        parts: List[str] = []
        if rect.fill_color:
            parts.append(f"background-color: {rect.fill_color.to_css()};")
        if rect.stroke_color:
            w = max(1, int(round(rect.stroke_width))) if rect.stroke_width > 0 else 1
            parts.append(f"border: {w}px solid {rect.stroke_color.to_css()};")
        return " ".join(parts)

    @staticmethod
    def _text_stylesheet(font: FontStyle) -> str:
        """
        Build a Qt stylesheet string for a QTextEdit.

        We always set background-color to transparent so the QTextEdit blends
        with whatever parent widget sits beneath it.  The text colour comes
        from the SVG fill attribute on the <text> element.
        """
        parts = ["background-color: transparent;"]
        if font.color:
            parts.append(f"color: {font.color.to_css()};")
        return " ".join(parts)

    @staticmethod
    def _pretty_print(root: ET.Element) -> str:
        raw_xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
        dom     = minidom.parseString(raw_xml)
        return dom.toprettyxml(indent="    ", encoding=None)


# ──────────────────────────────────────────────────────────────────────────────
# 10. PIPELINE ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

class SVGToQtUI:
    """
    High-level façade:
      SVGParser → HierarchyBuilder → QtUIExporter → file output
    """

    def __init__(self) -> None:
        self._parser   = SVGParser()
        self._builder  = HierarchyBuilder()
        self._exporter = QtUIExporter()

    def convert(
        self,
        svg_path:   str | Path,
        ui_path:    str | Path,
        class_name: str = "MainWindow",
    ) -> None:
        svg_path = Path(svg_path)
        ui_path  = Path(ui_path)

        print(f"[1/4] Parsing SVG: {svg_path}")
        elements = self._parser.parse(svg_path)
        rects = [e for e in elements if isinstance(e, Rectangle)]
        texts = [e for e in elements if isinstance(e, TextElement)]
        print(f"      Found {len(rects)} rectangle(s), {len(texts)} text element(s)")
        for e in elements:
            print(f"      {e}")

        win_w, win_h = self._read_svg_dimensions(svg_path)
        print(f"[2/4] SVG viewport: {win_w} × {win_h}")

        print("[3/4] Building widget hierarchy …")
        roots = self._builder.build(elements)
        self._print_tree(roots, indent=6)

        print(f"[4/4] Writing Qt UI file: {ui_path}")
        xml_str = self._exporter.export(
            roots, class_name=class_name,
            window_width=win_w, window_height=win_h,
        )
        ui_path.write_text(xml_str, encoding="utf-8")
        print(f"      Done.  ({len(xml_str):,} bytes)")

    @staticmethod
    def _read_svg_dimensions(svg_path: Path) -> Tuple[int, int]:
        tree = ET.parse(str(svg_path))
        root = tree.getroot()
        def _int_attr(attr: str, default: int) -> int:
            val = root.get(attr, str(default))
            try:
                return int(float(val.strip().rstrip("px")))
            except ValueError:
                return default
        return _int_attr("width", 800), _int_attr("height", 600)

    @staticmethod
    def _print_tree(nodes: List[TreeNode], indent: int = 0) -> None:
        prefix = " " * indent
        for node in nodes:
            x, y, w, h = node.relative_geometry()
            kind = "QTextEdit" if node.is_text else "QWidget "
            fill_tag = ""
            if node.is_text:
                te: TextElement = node.item  # type: ignore[assignment]
                fill_tag = (f"  color={te.font.color.to_hex()}"
                            if te.font.color else "")
            else:
                rc: Rectangle = node.item    # type: ignore[assignment]
                fill_tag = (f"  fill={rc.fill_color.to_hex()}"
                            if rc.fill_color else "")
            print(f"{prefix}└─ [{kind}] {node.qt_name}  "
                  f"[x={x}, y={y}, w={w}, h={h}]{fill_tag}")
            SVGToQtUI._print_tree(node.children, indent + 4)


# ──────────────────────────────────────────────────────────────────────────────
# 11. BUILT-IN DEMO
# ──────────────────────────────────────────────────────────────────────────────

DEMO_SVG = """\
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">

  <!-- ── Main panel ──────────────────────────────────────────────────── -->
  <rect id="mainPanel" x="10" y="10" width="780" height="580"
        fill="#f0f0f0" stroke="#cccccc" stroke-width="1"/>

  <!-- ── Sidebar ─────────────────────────────────────────────────────── -->
  <rect id="sidebar" x="20" y="20" width="180" height="560"
        fill="#1e2a3a"/>

  <!-- Sidebar heading text -->
  <text id="lblAppName"
        x="30" y="60"
        font-family="Arial, sans-serif" font-size="18px" font-weight="bold"
        fill="white">
    MyApp
  </text>

  <!-- Sidebar section label -->
  <text id="lblNavSection"
        x="30" y="85"
        font-family="Arial" font-size="10px"
        style="fill:#95a5a6;text-anchor:start">
    NAVIGATION
  </text>

  <rect id="sidebarHeader" x="30" y="30" width="160" height="50"
        fill="#2c3e50"/>
  <rect id="navItem1"      x="30" y="90" width="160" height="40"
        fill="#3498db"/>
  <rect id="navItem2"      x="30" y="140" width="160" height="40"
        style="fill:#2980b9"/>

  <!-- Nav item labels (inside navItem1 / navItem2) -->
  <text id="lblNav1"
        x="45" y="115"
        font-family="Arial" font-size="13px" fill="white">
    Dashboard
  </text>
  <text id="lblNav2"
        x="45" y="165"
        font-family="Arial" font-size="13px" fill="white">
    Reports
  </text>

  <!-- ── Content area ─────────────────────────────────────────────────── -->
  <rect id="contentArea" x="210" y="20" width="570" height="560"
        fill="white" stroke="#e0e0e0" stroke-width="1"/>

  <!-- Page title -->
  <text id="lblPageTitle"
        x="225" y="55"
        font-family="Arial, sans-serif" font-size="22px" font-weight="bold"
        fill="#2c3e50">
    Dashboard Overview
  </text>

  <!-- ── Toolbar ──────────────────────────────────────────────────────── -->
  <rect id="toolbar"  x="220" y="65" width="550" height="50"
        fill="#fafafa" stroke="#ddd" stroke-width="1"/>
  <rect id="btnNew"   x="230" y="75" width="80" height="30"
        fill="steelblue"  stroke="#1a5276" stroke-width="1"/>
  <rect id="btnOpen"  x="320" y="75" width="80" height="30"
        fill="seagreen"   stroke="#145a32" stroke-width="1"/>
  <rect id="btnSave"  x="410" y="75" width="80" height="30"
        fill="darkorange" stroke="#784212" stroke-width="1"/>

  <!-- Button labels -->
  <text id="lblBtnNew"  x="255" y="95"
        font-family="Arial" font-size="12px" font-weight="bold" fill="white">
    New
  </text>
  <text id="lblBtnOpen" x="345" y="95"
        font-family="Arial" font-size="12px" font-weight="bold" fill="white">
    Open
  </text>
  <text id="lblBtnSave" x="434" y="95"
        font-family="Arial" font-size="12px" font-weight="bold" fill="white">
    Save
  </text>

  <!-- ── Canvas ───────────────────────────────────────────────────────── -->
  <rect id="canvas" x="220" y="125" width="550" height="380"
        fill="#ffffff" stroke="#b2bec3" stroke-width="2"/>

  <!-- Editor description — multi-line tspan example -->
  <text id="editorHint"
        x="230" y="155"
        font-family="Courier New, monospace" font-size="13px" fill="#636e72">
    <tspan x="230" dy="0">// Start editing here.</tspan>
    <tspan x="230" dy="18">// Use Ctrl+S to save your work.</tspan>
  </text>

  <!-- ── Status bar ───────────────────────────────────────────────────── -->
  <rect id="statusBar" x="220" y="515" width="550" height="55"
        style="fill:rgba(44,62,80,0.95)"/>

  <rect id="statusLabel"    x="230" y="525" width="200" height="35"
        fill="#3498db" fill-opacity="0.8"/>
  <rect id="statusProgress" x="450" y="525" width="300" height="35"
        fill="#27ae6080"/>

  <!-- Status text -->
  <text id="lblStatus"
        x="240" y="548"
        font-family="Arial" font-size="12px" fill="white">
    Ready
  </text>

  <!-- Italic caption at very bottom – font-style demo -->
  <text id="lblVersion"
        x="650" y="548"
        font-family="Arial" font-size="10px"
        style="fill:#bdc3c7;font-style:italic;text-anchor:end">
    v1.0.0
  </text>

</svg>
"""


def run_demo(output_dir: Path = Path(".")) -> None:
    svg_path = output_dir / "demo_input.svg"
    ui_path  = output_dir / "demo_output.ui"

    print("=" * 64)
    print("  SVG → Qt .ui  DEMO  (rects + text, with colours & fonts)")
    print("=" * 64)
    print(f"\nWriting demo SVG → {svg_path}\n")
    svg_path.write_text(DEMO_SVG, encoding="utf-8")

    SVGToQtUI().convert(svg_path, ui_path, class_name="MainWindow")

    print("\n── Generated .ui snippet (first 60 lines) ───────────────────")
    lines = ui_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines[:60], 1):
        print(f"  {i:3}: {line}")
    if len(lines) > 60:
        print(f"  … ({len(lines) - 60} more lines)")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# 12. CLI
# ──────────────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="svg_to_qt_ui",
        description=(
            "Convert SVG <rect> and <text> elements to a Qt Designer .ui file.\n"
            "  <rect>  → QWidget   (geometry + fill/stroke colours)\n"
            "  <text>  → QTextEdit (font, colour, plain-text content)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("svg", nargs="?",
                   help="Path to input .svg file (omit when using --demo)")
    p.add_argument("ui",  nargs="?",
                   help="Path for output .ui file (defaults to <svg_stem>.ui)")
    p.add_argument("--class-name", "-c", default="MainWindow", metavar="NAME",
                   help="Qt class / object name for the main window")
    p.add_argument("--demo", action="store_true",
                   help="Run with the built-in coloured+text demo SVG and exit")
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.demo:
        run_demo()
        return 0

    if not args.svg:
        build_arg_parser().error("Provide an SVG file path or use --demo")

    svg_path = Path(args.svg)
    if not svg_path.exists():
        print(f"Error: file not found: {svg_path}", file=sys.stderr)
        return 1

    ui_path = Path(args.ui) if args.ui else svg_path.with_suffix(".ui")
    SVGToQtUI().convert(svg_path, ui_path, class_name=args.class_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())