#!/usr/bin/env python3
"""
svg_to_qt_ui.py
===============
Converts an SVG file containing <rect> and <text> elements into a valid
Qt Designer .ui XML file.

  <rect>   →  QWidget   (with background / border from fill / stroke)
  <text>   →  QLabel (with font, colour, and plain-text content)

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
"""

# pyright: reportUninitializedInstanceVariable=false

from __future__ import annotations

import io
import sys
import argparse
from pathlib import Path
from typing import IO, final
import xml.etree.ElementTree as ET

from svgqtconv.treenode import TreeNode
from svgqtconv.svgparser import SVGParser
from svgqtconv.qtuiexporter import QtUIExporter
from svgqtconv.hierarchybuilder import HierarchyBuilder
from svgqtconv.svgmodel import Rectangle, SVGElement, TextElement

@final
class SVGToQtUI:
    """
    High-level façade:
      SVGParser → HierarchyBuilder → QtUIExporter → file output
    """

    def __init__(self) -> None:
        self._parser   = SVGParser()
        self._builder  = HierarchyBuilder()
        self._exporter = QtUIExporter()

    def convert_str(self, svg_data: str, class_name: str = "MainWindow") -> str:
        elements = self._parser.parse(io.StringIO(svg_data))
        win_w, win_h = self._read_svg_dimensions(io.StringIO(svg_data))
        roots = self._builder.build(elements)
        return self._exporter.export(roots, class_name=class_name, window_width=win_w, window_height=win_h)

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
        _ = ui_path.write_text(xml_str, encoding="utf-8")
        print(f"      Done.  ({len(xml_str):,} bytes)")

    @staticmethod
    def _read_svg_dimensions(svg_path: Path | IO[str]) -> tuple[int, int]:
        tree = ET.parse(str(svg_path) if isinstance(svg_path, Path) else svg_path)
        root = tree.getroot()
        def _int_attr(attr: str, default: int) -> int:
            val = root.get(attr, str(default))
            try:
                return int(float(val.strip().rstrip("px")))
            except ValueError:
                return default
        return _int_attr("width", 800), _int_attr("height", 600)

    @staticmethod
    def _print_tree(nodes: list[TreeNode[SVGElement]], indent: int = 0) -> None:
        prefix = " " * indent
        for node in nodes:
            x, y, w, h = node.relative_geometry()
            kind = "QLabel" if isinstance(node.item, TextElement) else "QWidget "
            fill_tag = ""
            if isinstance(node.item, TextElement):
                assert isinstance(node.item, TextElement)
                te = node.item
                fill_tag = (f"  color={te.font.color.to_hex()}"
                            if te.font.color else "")
            else:
                assert isinstance(node.item, Rectangle)
                rc: Rectangle = node.item
                fill_tag = (f"  fill={rc.fill_color.to_hex()}"
                            if rc.fill_color else "")
            print(f"{prefix}└─ [{kind}] {node.qt_name}  [x={x}, y={y}, w={w}, h={h}]{fill_tag}")
            SVGToQtUI._print_tree(node.children, indent + 4)

# ──────────────────────────────────────────────────────────────────────────────
# 12. CLI
# ──────────────────────────────────────────────────────────────────────────────

class Args(argparse.Namespace):
    svg: str | None
    ui: str | None
    class_name: str

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="svg_to_qt_ui",
        description=(
            "Convert SVG <rect> and <text> elements to a Qt Designer .ui file.\n"
            "  <rect>  → QWidget   (geometry + fill/stroke colours)\n"
            "  <text>  → QLabel (font, colour, plain-text content)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _ = p.add_argument("svg", nargs="?", help="Path to input .svg file")
    _ = p.add_argument("ui", nargs="?", help="Path for output .ui file (defaults to <svg_stem>.ui)")
    _ = p.add_argument("--class-name", "-c", default="MainWindow", metavar="NAME", help="Qt class / object name for the main window")
    return p

def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv, namespace=Args())

    if not args.svg:
        build_arg_parser().error("Provide an SVG file path")

    svg_path = Path(args.svg)
    if not svg_path.exists():
        print(f"Error: file not found: {svg_path}", file=sys.stderr)
        return 1

    ui_path = Path(args.ui) if args.ui else svg_path.with_suffix(".ui")
    SVGToQtUI().convert(svg_path, ui_path, class_name=args.class_name)
    return 0

if __name__ == "__main__":
    sys.exit(main())
