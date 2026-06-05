from .svgmodel import Rectangle, SVGElement

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


def find_tightest_container(candidate: SVGElement, all_elements: list[SVGElement]) -> SVGElement | None:
    """
    Return the smallest-area element in *all_elements* that fully contains
    *candidate*, or None if *candidate* is at root level.

    Text elements are never treated as containers (a QLabel cannot be a
    parent widget in Qt Designer).
    """
    containers = [e for e in all_elements
                                   if isinstance(e, Rectangle) and contains(e, candidate)]
    return min(containers, key=lambda e: e.area) if containers else None
