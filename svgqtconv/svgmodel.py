from dataclasses import dataclass, field
import statistics
from typing import override

from .atom import Color, FontStyle

@dataclass(frozen=True)
class BoxElement:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height

@dataclass(frozen=True, repr=False)
class Rectangle(BoxElement):
    """
    An SVG <rect> → becomes a QWidget in the .ui file.
    All coordinates are absolute SVG viewport space.
    """
    svg_id: str | None = None
    fill_color: Color | None = None
    stroke_color: Color | None = None
    stroke_width: float = 0.0

    @override
    def __repr__(self) -> str:
        tag  = f"id={self.svg_id!r}" if self.svg_id else "no id"
        fill = f" fill={self.fill_color.to_hex()}"    if self.fill_color   else ""
        strk = (f" stroke={self.stroke_color.to_hex()}@{self.stroke_width}px"
                if self.stroke_color else "")
        return (f"Rectangle({tag}, x={self.x}, y={self.y}, "
                f"w={self.width}, h={self.height}{fill}{strk})")

@dataclass(frozen=True, repr=False)
class Circle(BoxElement):
    """
    An SVG <circle> -> becomes a square QWidget with fully rounded corners
    OR a QRadioButton if it's small enough and accompanied by text.
    All coordinates are absolute SVG viewport space.
    """
    cx: float
    cy: float
    radius: float

    svg_id: str | None = None
    fill_color: Color | None = None
    stroke_color: Color | None = None
    stroke_width: float = 0.0
    
    @override
    def __repr__(self) -> str:
        tag  = f"id={self.svg_id!r}" if self.svg_id else "no id"
        fill = f" fill={self.fill_color.to_hex()}"    if self.fill_color   else ""
        strk = (f" stroke={self.stroke_color.to_hex()}@{self.stroke_width}px"
                if self.stroke_color else "")
        return (f"Circle({tag}, x={self.cx},y={self.cy}, r={self.radius}{fill}{strk}")

@dataclass(frozen=True, repr=False)
class TextElement(BoxElement):
    """
    An SVG <text> (or <text>/<tspan>) → becomes a QLabel in the .ui file.

    SVG text position semantics:
      (x, y) is the *baseline anchor point*, not the top-left corner.
      We convert it to a top-left bounding box using the font metrics:
        top   = y - font_size_px
        width = estimated from character count when not given explicitly
        height= font_size_px × _TEXT_HEIGHT_FACTOR

    If the SVG element carries explicit width/height attributes (uncommon but
    possible via a foreignObject-style convention), those are used directly.
    """
    content: str = ""       # plain-text content (tspans joined)
    svg_id:  str | None = None
    font:    FontStyle = field(default_factory=FontStyle)

    @override
    def __repr__(self) -> str:
        tag = f"id={self.svg_id!r}" if self.svg_id else "no id"
        preview = self.content[:30].replace("\n", "↵")
        return (f"TextElement({tag}, x={self.x:.0f}, y={self.y:.0f}, "
                f"w={self.width:.0f}, h={self.height:.0f}, "
                f"text={preview!r}, {self.font})")

type SVGElement = Rectangle | TextElement | Circle

