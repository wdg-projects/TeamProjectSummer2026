from dataclasses import dataclass
import re
from typing import Callable, override

@dataclass(frozen=True, repr=False)
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

    @override
    def __repr__(self) -> str:
        return f"Color({self.to_hex()}, a={self.a})"

_CSS_NAMED_COLORS: dict[str, Color] = {
    "aliceblue":            Color(240,248,255), "antiquewhite":    Color(250,235,215), "aqua":           Color(0,  255,255),
    "aquamarine":           Color(127,255,212), "azure":           Color(240,255,255), "beige":          Color(245,245,220),
    "bisque":               Color(255,228,196), "black":           Color(0,  0,  0  ), "blanchedalmond": Color(255,235,205),
    "blue":                 Color(0,  0,  255), "blueviolet":      Color(138,43, 226), "brown":          Color(165,42, 42 ),
    "burlywood":            Color(222,184,135), "cadetblue":       Color(95, 158,160), "chartreuse":     Color(127,255,0  ),
    "chocolate":            Color(210,105,30 ), "coral":           Color(255,127,80 ), "cornflowerblue": Color(100,149,237),
    "cornsilk":             Color(255,248,220), "crimson":         Color(220,20, 60 ), "cyan":           Color(0,  255,255),
    "darkblue":             Color(0,  0,  139), "darkcyan":        Color(0,  139,139), "darkgoldenrod":  Color(184,134,11 ),
    "darkgray":             Color(169,169,169), "darkgreen":       Color(0,  100,0  ), "darkgrey":       Color(169,169,169),
    "darkkhaki":            Color(189,183,107), "darkmagenta":     Color(139,0,  139), "darkolivegreen": Color(85, 107,47 ),
    "darkorange":           Color(255,140,0  ), "darkorchid":      Color(153,50, 204), "darkred":        Color(139,0,  0  ),
    "darksalmon":           Color(233,150,122), "darkseagreen":    Color(143,188,143), "deepskyblue":    Color(0,  191,255),
    "darkslateblue":        Color(72, 61, 139), "darkslategray":   Color(47, 79, 79 ), "dodgerblue":     Color(30, 144,255),
    "darkslategrey":        Color(47, 79, 79 ), "darkturquoise":   Color(0,  206,209), "forestgreen":    Color(34, 139,34 ),
    "darkviolet":           Color(148,0,  211), "deeppink":        Color(255,20, 147), "ghostwhite":     Color(248,248,255),
    "dimgray":              Color(105,105,105), "dimgrey":         Color(105,105,105), "gray":           Color(128,128,128),
    "firebrick":            Color(178,34, 34 ), "floralwhite":     Color(255,250,240), "grey":           Color(128,128,128),
    "fuchsia":              Color(255,0,  255), "gainsboro":       Color(220,220,220), "indianred":      Color(205,92, 92 ),
    "gold":                 Color(255,215,0  ), "goldenrod":       Color(218,165,32 ), "khaki":          Color(240,230,140),
    "green":                Color(0,  128,0  ), "greenyellow":     Color(173,255,47 ), "lawngreen":      Color(124,252,0  ),
    "honeydew":             Color(240,255,240), "hotpink":         Color(255,105,180), "lightpink":      Color(255,182,193),
    "indigo":               Color(75, 0,  130), "ivory":           Color(255,255,240), "limegreen":      Color(50, 205,50 ),
    "lavender":             Color(230,230,250), "lavenderblush":   Color(255,240,245), "maroon":         Color(128,0,  0  ), 
    "lemonchiffon":         Color(255,250,205), "lightblue":       Color(173,216,230), "moccasin":       Color(255,228,181),
    "lightcoral":           Color(240,128,128), "lightcyan":       Color(224,255,255), "oldlace":        Color(253,245,230),
    "lightgoldenrodyellow": Color(250,250,210), "lightgray":       Color(211,211,211), "orange":         Color(255,165,0  ),
    "lightgreen":           Color(144,238,144), "lightgrey":       Color(211,211,211), "palegoldenrod":  Color(238,232,170),
    "lightsalmon":          Color(255,160,122), "lightseagreen":   Color(32, 178,170), "pink":           Color(255,192,203),
    "lightskyblue":         Color(135,206,250), "lightslategray":  Color(119,136,153), "purple":         Color(128,0,  128),
    "lightslategrey":       Color(119,136,153), "lightsteelblue":  Color(176,196,222), "rosybrown":      Color(188,143,143),
    "lightyellow":          Color(255,255,224), "lime":            Color(0,  255,0  ), "salmon":         Color(250,128,114),
    "linen":                Color(250,240,230), "magenta":         Color(255,0,  255), "seashell":       Color(255,245,238),
    "mediumaquamarine":     Color(102,205,170), "mediumblue":      Color(0,  0,  205), "skyblue":        Color(135,206,235),
    "mediumorchid":         Color(186,85, 211), "mediumpurple":    Color(147,112,219), "slategrey":      Color(112,128,144),
    "mediumseagreen":       Color(60, 179,113), "mediumslateblue": Color(123,104,238), "steelblue":      Color(70, 130,180),
    "mediumspringgreen":    Color(0,  250,154), "mediumturquoise": Color(72, 209,204), "thistle":        Color(216,191,216),
    "mediumvioletred":      Color(199,21, 133), "midnightblue":    Color(25, 25, 112), "violet":         Color(238,130,238),
    "mintcream":            Color(245,255,250), "mistyrose":       Color(255,228,225), "whitesmoke":     Color(245,245,245),
    "navajowhite":          Color(255,222,173), "navy":            Color(0,  0,  128), "saddlebrown":    Color(139,69, 19 ),
    "olive":                Color(128,128,0  ), "olivedrab":       Color(107,142,35 ), "seagreen":       Color(46, 139,87 ),
    "orangered":            Color(255,69, 0  ), "orchid":          Color(218,112,214), "silver":         Color(192,192,192),
    "palegreen":            Color(152,251,152), "paleturquoise":   Color(175,238,238), "slategray":      Color(112,128,144),
    "palevioletred":        Color(219,112,147), "papayawhip":      Color(255,239,213), "springgreen":    Color(0,  255,127),
    "peachpuff":            Color(255,218,185), "peru":            Color(205,133,63 ), "teal":           Color(0,  128,128),
    "plum":                 Color(221,160,221), "powderblue":      Color(176,224,230), "turquoise":      Color(64, 224,208),
    "rebeccapurple":        Color(102,51, 153), "red":             Color(255,0,  0  ), "white":          Color(255,255,255),
    "royalblue":            Color(65, 105,225), "yellowgreen":     Color(154,205,50 ), "sandybrown":     Color(244,164,96 ),
    "sienna":               Color(160,82, 45 ), "snow":            Color(255,250,250), "tomato":         Color(255,99, 71 ), 
    "slateblue":            Color(106,90, 205), "tan":             Color(210,180,140), "wheat":          Color(245,222,179), 
    "yellow":               Color(255,255,0  )
}

_RE_RGB  = re.compile(
    r"rgb\(\s*(\d+(?:\.\d+)?%?)\s*,\s*(\d+(?:\.\d+)?%?)\s*," +
    r"\s*(\d+(?:\.\d+)?%?)\s*\)", re.I)

_RE_RGBA = re.compile(
    r"rgba\(\s*(\d+(?:\.\d+)?%?)\s*,\s*(\d+(?:\.\d+)?%?)\s*," +
    r"\s*(\d+(?:\.\d+)?%?)\s*,\s*([\d.]+%?)\s*\)", re.I)

class ColorParser:
    """
    Parse any SVG/CSS colour string → Color (or None for 'none'/'transparent').

    Formats: #rgb  #rrggbb  #rrggbbaa  rgb()  rgba()  CSS named  none
    """

    @classmethod
    def parse(cls, value: str | None) -> Color | None:
        if not value:
            return None
        v = value.strip().lower()
        if v in ("none", "transparent", "inherit", "currentcolor", ""):
            return None
        return (cls._parse_hex(v) or cls._parse_rgb(v)
                or cls._parse_rgba(v) or _CSS_NAMED_COLORS.get(v))

    @staticmethod
    def _parse_hex(v: str) -> Color | None:
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
    def _parse_rgb(cls, v: str) -> Color | None:
        m = _RE_RGB.fullmatch(v)
        return Color(cls._channel(m.group(1)), cls._channel(m.group(2)),
                     cls._channel(m.group(3))) if m else None

    @classmethod
    def _parse_rgba(cls, v: str) -> Color | None:
        m = _RE_RGBA.fullmatch(v)
        return Color(cls._channel(m.group(1)), cls._channel(m.group(2)),
                     cls._channel(m.group(3)), cls._alpha(m.group(4))) if m else None

    @staticmethod
    def apply_opacity(color: Color | None, opacity: float) -> Color | None:
        """Multiply alpha by *opacity* (0.0-1.0)."""
        if color is None:
            return None
        return Color(color.r, color.g, color.b,
                     max(0, min(255, round(color.a * opacity))))

# Qt alignment flag strings used in the <enum> property element.
_TEXT_ANCHOR_TO_QT: dict[str, str] = {"start":  "Qt::AlignLeft", "middle": "Qt::AlignHCenter", "end":    "Qt::AlignRight",}

# Canonical Qt font families for common SVG generic names.
_GENERIC_FAMILY_MAP: dict[str, str] = {
    "serif":        "Times New Roman",
    "sans-serif":   "Arial",
    "monospace":    "Courier New",
    "cursive":      "Comic Sans MS",
    "fantasy":      "Impact",
    "system-ui":    "Arial",
    "ui-serif":     "Times New Roman",
    "ui-monospace": "Courier New",
}

@dataclass(frozen=True, repr = False)
class FontStyle:
    """
    Immutable descriptor for the typographic properties of a <text> element.

    point_size  - font size in Qt points  (SVG px converted at 0.75 pt/px)
    family      - resolved font family name
    bold        - True when font-weight >= 600 or == 'bold' / 'bolder'
    italic      - True when font-style == 'italic' or 'oblique'
    underline   - True when text-decoration contains 'underline'
    strikeout   - True when text-decoration contains 'line-through'
    color       - foreground (text) colour, None → inherit
    alignment   - Qt alignment flag string, e.g. 'Qt::AlignLeft'
    """
    point_size: int          = 10
    family:     str          = "Arial"
    bold:       bool         = False
    italic:     bool         = False
    underline:  bool         = False
    strikeout:  bool         = False
    color:      Color | None = None
    alignment:  str          = "Qt::AlignLeft"

    @override
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
    def parse(cls, prop_fn: Callable[[str], str | None]) -> FontStyle:
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
    def _resolve_family(cls, raw: str | None) -> str:
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
    def _resolve_size(cls, raw: str | None) -> int:
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
    def _resolve_bold(raw: str | None) -> bool:
        if not raw:
            return False
        raw = raw.strip().lower()
        if raw in ("bold", "bolder", "800", "900"):
            return True
        try:
            return int(raw) >= 600
        except ValueError:
            return False
