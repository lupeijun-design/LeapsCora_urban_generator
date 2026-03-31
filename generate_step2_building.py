import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

FRONTAGE_MAP = {
    "primary_frontage": "main_street",
    "secondary_frontage": "secondary_street",
    "back_frontage": "back_street",
}

FRONTAGE_PRIORITY = {
    "main_street": 5,
    "scenic_street": 4,
    "secondary_street": 3,
    "internal_street": 2,
    "back_street": 1,
}


def _is_primitive(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def _format_json_compact(v: Any, indent: int = 0) -> str:
    sp = " " * indent

    def _inline_list(lst: List[Any]) -> str:
        return "[ " + ", ".join(_format_json_compact(x, 0) for x in lst) + " ]"

    if isinstance(v, dict):
        if not v:
            return "{}"
        lines = ["{"]
        items = list(v.items())
        for i, (k, val) in enumerate(items):
            comma = "," if i < len(items) - 1 else ""
            lines.append(" " * (indent + 2) + json.dumps(k, ensure_ascii=False) + ": " + _format_json_compact(val, indent + 2) + comma)
        lines.append(sp + "}")
        return "\n".join(lines)

    if isinstance(v, list):
        if not v:
            return "[]"
        if all(_is_primitive(x) for x in v):
            return _inline_list(v)
        if all(isinstance(x, list) and all(_is_primitive(y) for y in x) for x in v):
            return _inline_list(v)
        lines = ["["]
        for i, item in enumerate(v):
            comma = "," if i < len(v) - 1 else ""
            lines.append(" " * (indent + 2) + _format_json_compact(item, indent + 2) + comma)
        lines.append(sp + "]")
        return "\n".join(lines)

    return json.dumps(v, ensure_ascii=False)


def rect_poly(x0: float, y0: float, x1: float, y1: float) -> List[List[float]]:
    return [[round(x0, 4), round(y0, 4)], [round(x1, 4), round(y0, 4)], [round(x1, 4), round(y1, 4)], [round(x0, 4), round(y1, 4)], [round(x0, 4), round(y0, 4)]]


def poly_area(poly: List[List[float]]) -> float:
    if len(poly) < 4:
        return 0.0
    s = 0.0
    for i in range(len(poly) - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def poly_bbox(poly: List[List[float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def cluster_connected_polygons(polygons: List[List[List[float]]]) -> List[List[List[List[float]]]]:
    if not polygons:
        return []
    boxes = [poly_bbox(p) for p in polygons]
    visited = [False] * len(polygons)
    clusters: List[List[List[List[float]]]] = []
    for i in range(len(polygons)):
        if visited[i]:
            continue
        stack = [i]
        visited[i] = True
        cluster = []
        while stack:
            idx = stack.pop()
            cluster.append(polygons[idx])
            for j in range(len(polygons)):
                if visited[j]:
                    continue
                if rects_touch_or_overlap(boxes[idx], boxes[j]):
                    visited[j] = True
                    stack.append(j)
        clusters.append(cluster)
    return clusters


def point_in_polygon(pt: Tuple[float, float], poly: List[List[float]]) -> bool:
    x, y = pt
    inside = False
    if len(poly) < 4:
        return False
    for i in range(len(poly) - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        cond = (y1 > y) != (y2 > y)
        if cond:
            xin = (x2 - x1) * (y - y1) / ((y2 - y1) if abs(y2 - y1) > 1e-9 else 1e-9) + x1
            if x < xin:
                inside = not inside
    return inside


def rect_area(r: Tuple[float, float, float, float]) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def rect_intersection_area(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1]); x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    return 0.0 if (x1 <= x0 or y1 <= y0) else (x1 - x0) * (y1 - y0)


def rects_touch_or_overlap(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float], eps: float = 1e-5) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 < bx0 - eps or bx1 < ax0 - eps or ay1 < by0 - eps or by1 < ay0 - eps)


def subtract_rect(rect: Tuple[float, float, float, float], cut: Tuple[float, float, float, float], eps: float = 1e-6) -> List[Tuple[float, float, float, float]]:
    x0, y0, x1, y1 = rect
    cx0, cy0, cx1, cy1 = cut
    ix0, iy0 = max(x0, cx0), max(y0, cy0)
    ix1, iy1 = min(x1, cx1), min(y1, cy1)
    if ix1 <= ix0 + eps or iy1 <= iy0 + eps:
        return [rect]

    out: List[Tuple[float, float, float, float]] = []
    if ix0 > x0 + eps:
        out.append((x0, y0, ix0, y1))
    if ix1 < x1 - eps:
        out.append((ix1, y0, x1, y1))
    if iy0 > y0 + eps:
        out.append((ix0, y0, ix1, iy0))
    if iy1 < y1 - eps:
        out.append((ix0, iy1, ix1, y1))
    return [r for r in out if rect_area(r) > eps]


def subtract_rects(rects: List[Tuple[float, float, float, float]], cuts: List[Tuple[float, float, float, float]]) -> List[Tuple[float, float, float, float]]:
    current = list(rects)
    for cut in cuts:
        nxt: List[Tuple[float, float, float, float]] = []
        for r in current:
            nxt.extend(subtract_rect(r, cut))
        current = nxt
        if not current:
            break
    return current


def subtract_rect(rect: Tuple[float, float, float, float], cut: Tuple[float, float, float, float], eps: float = 1e-6) -> List[Tuple[float, float, float, float]]:
    x0, y0, x1, y1 = rect
    cx0, cy0, cx1, cy1 = cut
    ix0, iy0 = max(x0, cx0), max(y0, cy0)
    ix1, iy1 = min(x1, cx1), min(y1, cy1)
    if ix1 <= ix0 + eps or iy1 <= iy0 + eps:
        return [rect]

    out: List[Tuple[float, float, float, float]] = []
    if ix0 > x0 + eps:
        out.append((x0, y0, ix0, y1))
    if ix1 < x1 - eps:
        out.append((ix1, y0, x1, y1))
    if iy0 > y0 + eps:
        out.append((ix0, y0, ix1, iy0))
    if iy1 < y1 - eps:
        out.append((ix0, iy1, ix1, y1))
    return [r for r in out if rect_area(r) > eps]


def subtract_rects(rects: List[Tuple[float, float, float, float]], cuts: List[Tuple[float, float, float, float]]) -> List[Tuple[float, float, float, float]]:
    current = list(rects)
    for cut in cuts:
        nxt: List[Tuple[float, float, float, float]] = []
        for r in current:
            nxt.extend(subtract_rect(r, cut))
        current = nxt
        if not current:
            break
    return current


def frontage_side(frontage_polyline: List[List[float]], bbox: Tuple[float, float, float, float]) -> str:
    x0, y0 = frontage_polyline[0]; x1, y1 = frontage_polyline[1]
    bx0, by0, bx1, by1 = bbox
    mx = (x0 + x1) * 0.5; my = (y0 + y1) * 0.5
    if abs(x0 - x1) < abs(y0 - y1):
        return "left" if abs(mx - bx0) <= abs(mx - bx1) else "right"
    return "bottom" if abs(my - by0) <= abs(my - by1) else "top"


def mass_face_from_side(side: str) -> str:
    return {"bottom": "south", "top": "north", "left": "west", "right": "east"}.get(side, "south")


def split_rect_with_spacing(rect: Tuple[float, float, float, float], count: int, spacing: float, edge_clearance: float) -> List[Tuple[float, float, float, float]]:
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    if count <= 1:
        return [(x0 + edge_clearance, y0 + edge_clearance, x1 - edge_clearance, y1 - edge_clearance)]
    out = []
    split_x = w >= h
    if split_x:
        usable = w - spacing * (count - 1)
        if usable <= 0: return []
        seg = usable / count; cur = x0
        for _ in range(count):
            rx0, rx1 = cur + edge_clearance, cur + seg - edge_clearance
            ry0, ry1 = y0 + edge_clearance, y1 - edge_clearance
            if rx1 > rx0 and ry1 > ry0: out.append((rx0, ry0, rx1, ry1))
            cur += seg + spacing
    else:
        usable = h - spacing * (count - 1)
        if usable <= 0: return []
        seg = usable / count; cur = y0
        for _ in range(count):
            rx0, rx1 = x0 + edge_clearance, x1 - edge_clearance
            ry0, ry1 = cur + edge_clearance, cur + seg - edge_clearance
            if rx1 > rx0 and ry1 > ry0: out.append((rx0, ry0, rx1, ry1))
            cur += seg + spacing
    return out


def scale_rect_about_center(r: Tuple[float, float, float, float], scale: float) -> Tuple[float, float, float, float]:
    x0, y0, x1, y1 = r
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    hw, hh = (x1 - x0) * 0.5 * scale, (y1 - y0) * 0.5 * scale
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def fit_rect_inside(r: Tuple[float, float, float, float], bounds: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    x0, y0, x1, y1 = r; bx0, by0, bx1, by1 = bounds
    w, h = x1 - x0, y1 - y0
    if x0 < bx0: x0, x1 = bx0, bx0 + w
    if x1 > bx1: x1, x0 = bx1, bx1 - w
    if y0 < by0: y0, y1 = by0, by0 + h
    if y1 > by1: y1, y0 = by1, by1 - h
    return (x0, y0, x1, y1)


def require_key(cfg: Dict[str, Any], path: str) -> Any:
    cur: Any = cfg
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            raise ValueError(f"Missing required YAML key: {path}")
        cur = cur[key]
    return cur


def load_typology(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Typology YAML not found: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"Typology YAML is empty: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except Exception as exc:
        raise ValueError(f"Failed to read YAML {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Typology YAML root must be a mapping: {path}")

    # Strict required parameter set for the current generator logic.
    required_paths = [
        "global.solver_grid_m",
        "global.random_seed",
        "global.default_open_space_buffer_m",
        "multi_mass_rules.min_gap_between_masses_m",
        "multi_mass_rules.large_plot_area_threshold_sqm",
        "multi_mass_rules.medium_plot_area_threshold_sqm",
        "multi_mass_rules.max_masses_default",
        "corner_reservations.open_plaza_corner",
        "corner_reservations.transit_corner",
        "transit_influence.metro_open_space_reserve_m",
        "transit_influence.bus_open_space_reserve_m",
        "residential.tower.default_floor_height_m",
        "residential.tower.layout_style_choices",
        "residential.tower.point_layout.footprint_size_m",
        "residential.tower.point_layout.ew_gap_min_m",
        "residential.tower.point_layout.ew_gap_max_m",
        "residential.tower.point_layout.ew_gap_formula.base_m",
        "residential.tower.point_layout.ew_gap_formula.height_threshold_m",
        "residential.tower.point_layout.ew_gap_formula.slope",
        "residential.tower.point_layout.ns_gap_min_m",
        "residential.tower.point_layout.ns_gap_max_m",
        "residential.tower.point_layout.ns_gap_formula.base_m",
        "residential.tower.point_layout.ns_gap_formula.height_threshold_m",
        "residential.tower.point_layout.ns_gap_formula.slope",
        "residential.tower.row_layout.depth_ns_m",
        "residential.tower.row_layout.length_ew_max_m",
        "residential.tower.row_layout.length_ew_min_m",
        "residential.tower.row_layout.ew_gap_m",
        "residential.tower.row_layout.ns_gap_formula.base_m",
        "residential.tower.row_layout.ns_gap_formula.height_threshold_m",
        "residential.tower.row_layout.ns_gap_formula.slope",
        "residential.podium_retail.depth_default_m",
        "residential.podium_retail.depth_range_m",
        "residential.podium_retail.floors_range",
        "residential.podium_retail.floor_heights_m",
        "residential.podium_retail.frontage_mode_choices",
        "residential.podium_retail.continuity_probability",
        "office.core_ratio_default",
        "office.forecourt_default_m",
        "office.default_floor_height_m",
        "office.tower_podium.inter_zone_gap_m",
        "office.tower_podium.short_side_two_row_threshold_m",
        "office.tower_podium.ratio_single_max",
        "office.tower_podium.ratio_double_max",
        "office.tower_podium.ratio_triple_max",
        "office.tower_podium.ratio_quad_max",
        "office.tower_podium.ratio_penta_max",
        "office.tower_podium.plaza_retreat_probability",
        "office.tower_podium.plaza_retreat_priority_weights.primary_or_important",
        "office.tower_podium.plaza_retreat_priority_weights.secondary",
        "office.tower_podium.podium_height_m",
        "office.tower_podium.tower_floorplate_short_range_m",
        "office.tower_podium.tower_floorplate_long_range_m",
        "commercial.default_floor_height_m",
        "commercial.prototype_mode_choices",
        "commercial.prototype_mode_exclude_type_1_when_long_side_gt_m",
        "commercial.short_side_fallback_threshold_m",
        "commercial.short_side_fallback_bar_depth_m",
        "commercial.short_side_fallback_shape_choices",
        "commercial.courtyard.perimeter_depth_short_side_50_120_m",
        "commercial.courtyard.perimeter_depth_long_side_50_120_m",
        "commercial.mall_bigbox.size_min_m",
        "commercial.mall_bigbox.size_max_m",
        "commercial.mall_bigbox.attach_mode_choices",
        "commercial.multi_box.short_side_50_120_split_choices",
        "commercial.multi_box.short_side_120_200_split",
        "commercial.multi_box.primary_secondary_ratio",
        "commercial.multi_box.primary_secondary_secondary_ratio",
        "commercial.multi_box.box_offset_range_m",
        "commercial.mall_rect.atrium_default_size_m",
    ]
    for p in required_paths:
        require_key(raw, p)
    return raw


def pick_block_for_parcel(center: Tuple[float, float], blocks: List[dict]) -> Optional[dict]:
    for b in blocks:
        if point_in_polygon(center, b.get("polygon") or []):
            return b
    return None

def build_edge_setbacks(block_bbox, block_frontages, parcel_setbacks):
    for key in ("primary_frontage", "secondary_frontage", "back_frontage"):
        if key not in parcel_setbacks:
            raise ValueError(f"Missing planning_controls.setbacks.{key} in input JSON")

    sides = ["left", "right", "bottom", "top"]
    side_setback = {s: float(parcel_setbacks["back_frontage"]) for s in sides}
    side_pri = {s: 0 for s in sides}
    side_edge_type = {s: "back_street" for s in sides}
    side_frontage_id = {s: "" for s in sides}

    for f in block_frontages:
        side = frontage_side(f.get("polyline", [[0, 0], [0, 0]]), block_bbox)
        ft = str(f.get("frontage_type", "back_frontage"))
        edge_type = FRONTAGE_MAP.get(ft, "back_street")
        pri = FRONTAGE_PRIORITY.get(edge_type, 1)

        if edge_type == "main_street":
            sb = float(parcel_setbacks["primary_frontage"])
        elif edge_type in {"secondary_street", "scenic_street", "internal_street"}:
            sb = float(parcel_setbacks["secondary_frontage"])
        else:
            sb = float(parcel_setbacks["back_frontage"])

        if pri >= side_pri[side]:
            side_pri[side] = pri
            side_setback[side] = sb
            side_edge_type[side] = edge_type
            side_frontage_id[side] = str(f.get("id", ""))

    return side_setback, side_pri, side_edge_type, side_frontage_id


def make_corner_reserve(corner, block_bbox, cfg_global):
    pos = corner.get("position")
    if not isinstance(pos, list) or len(pos) < 2:
        return None
    x, y = float(pos[0]), float(pos[1])
    ctype = str(corner.get("corner_type", "normal_corner"))
    corner_cfg = cfg_global.get("corner_reservations", {})
    s = float(corner_cfg.get(ctype, 0.0))
    if s <= 0.0:
        return None

    bx0, by0, bx1, by1 = block_bbox
    if abs(x - bx0) <= abs(x - bx1):
        rx0, rx1 = bx0, bx0 + s
    else:
        rx0, rx1 = bx1 - s, bx1
    if abs(y - by0) <= abs(y - by1):
        ry0, ry1 = by0, by0 + s
    else:
        ry0, ry1 = by1 - s, by1
    return (rx0, ry0, rx1, ry1)


def _generate_mass_layout_b1_b2(buildable_rect, forbidden_rects, land_cfg, coverage_max, required_gfa, height_limit, min_spacing, edge_clearance):
    area_buildable = rect_area(buildable_rect)
    floor_h = float(land_cfg["floor_height"])
    max_floors = max(1, int(math.floor(height_limit / max(1e-6, floor_h))))
    feasible_single_gfa = max(1.0, min(coverage_max, area_buildable) * max_floors)
    n_from_far = max(1, int(math.ceil(required_gfa / feasible_single_gfa)))

    max_count = int(land_cfg["max_mass_count"])
    min_count = int(land_cfg["min_mass_count"])
    coverage_target = float(land_cfg["coverage_target"])

    heuristic = 1
    if area_buildable > float(land_cfg["large_plot_area_threshold_sqm"]):
        heuristic = 3
    elif area_buildable > float(land_cfg["medium_plot_area_threshold_sqm"]):
        heuristic = 2
    count0 = max(min_count, min(max_count, max(n_from_far, heuristic)))

    chosen = []
    status = "ok"
    warnings = []

    for n in range(count0, max_count + 1):
        rects = split_rect_with_spacing(buildable_rect, n, min_spacing, edge_clearance)
        if len(rects) < n:
            continue

        adjusted = []
        for r in rects:
            rr = r
            for fr in forbidden_rects:
                if rect_intersection_area(rr, fr) <= 1e-6:
                    continue
                rx0, ry0, rx1, ry1 = rr
                fx0, fy0, fx1, fy1 = fr
                cx, cy = (rx0 + rx1) * 0.5, (ry0 + ry1) * 0.5
                fcx, fcy = (fx0 + fx1) * 0.5, (fy0 + fy1) * 0.5
                if abs(cx - fcx) >= abs(cy - fcy):
                    rr = (rx0, ry0, min(rx1, fx0 - 0.5), ry1) if cx < fcx else (max(rx0, fx1 + 0.5), ry0, rx1, ry1)
                else:
                    rr = (rx0, ry0, rx1, min(ry1, fy0 - 0.5)) if cy < fcy else (rx0, max(ry0, fy1 + 0.5), rx1, ry1)
                rr = fit_rect_inside(rr, buildable_rect)
            if rect_area(rr) > 50.0:
                adjusted.append(rr)
        if not adjusted:
            continue

        total_area = sum(rect_area(r) for r in adjusted)
        target_ground = min(coverage_max, area_buildable * coverage_target)
        if total_area > target_ground and total_area > 1e-6:
            scale = math.sqrt(target_ground / total_area)
            adjusted2 = []
            for r in adjusted:
                sr = fit_rect_inside(scale_rect_about_center(r, max(0.2, scale)), buildable_rect)
                if rect_area(sr) > 35.0:
                    adjusted2.append(sr)
            adjusted = adjusted2
            total_area = sum(rect_area(r) for r in adjusted)

        if total_area * max_floors >= required_gfa * 0.98:
            chosen = adjusted
            break

    if not chosen:
        chosen = split_rect_with_spacing(buildable_rect, min_count, min_spacing, edge_clearance)
        status = "infeasible"
        warnings.append("Cannot satisfy FAR under current max_mass_count/height_limit")

    total_foot = max(1e-6, sum(rect_area(r) for r in chosen))
    avg_floors = max(1, min(max_floors, int(math.ceil(required_gfa / total_foot))))
    floors = []
    for i in range(len(chosen)):
        f = avg_floors - 1 if (i % 2 == 1 and avg_floors > 1) else avg_floors
        floors.append(max(1, min(max_floors, f)))

    est_gfa = sum(rect_area(chosen[i]) * floors[i] for i in range(len(chosen)))
    if est_gfa < required_gfa * 0.98 and max_floors > avg_floors:
        i = 0
        while est_gfa < required_gfa * 0.98 and i < len(chosen) * 6:
            j = i % len(chosen)
            if floors[j] < max_floors:
                floors[j] += 1
                est_gfa += rect_area(chosen[j])
            i += 1

    meta = {
        "status": status,
        "warnings": warnings,
        "max_floors": max_floors,
        "assigned_floors": floors,
        "required_gfa": round(required_gfa, 2),
        "estimated_gfa": round(est_gfa, 2),
        "coverage_max": round(coverage_max, 2),
        "total_footprint": round(sum(rect_area(r) for r in chosen), 2),
    }
    return chosen, meta, {}


def _clip_tower_items_against_forbidden(items, forbidden_rects, bounds):
    out = []
    for item in items:
        rr = item["rect"]
        for fr in forbidden_rects:
            if rect_intersection_area(rr, fr) <= 1e-6:
                continue
            rx0, ry0, rx1, ry1 = rr
            fx0, fy0, fx1, fy1 = fr
            cx, cy = (rx0 + rx1) * 0.5, (ry0 + ry1) * 0.5
            fcx, fcy = (fx0 + fx1) * 0.5, (fy0 + fy1) * 0.5
            if abs(cx - fcx) >= abs(cy - fcy):
                rr = (rx0, ry0, min(rx1, fx0 - 0.2), ry1) if cx < fcx else (max(rx0, fx1 + 0.2), ry0, rx1, ry1)
            else:
                rr = (rx0, ry0, rx1, min(ry1, fy0 - 0.2)) if cy < fcy else (rx0, max(ry0, fy1 + 0.2), rx1, ry1)
            rr = fit_rect_inside(rr, bounds)
        if rect_area(rr) > 50.0:
            copied = dict(item)
            copied["rect"] = rr
            out.append(copied)
    return out


def _select_residential_podium_sides(mode, sorted_sides, side_edge_type):
    if not sorted_sides:
        return []
    if mode == 1:
        return [sorted_sides[0]]
    if mode == 2:
        sides = [s for s in sorted_sides if side_edge_type.get(s) in {"main_street", "secondary_street"}]
        return sides[:2] if sides else sorted_sides[:2]
    if mode == 3:
        return sorted_sides[:3]
    return sorted_sides


def _rect_for_side_depth(bounds, side: str, depth: float):
    x0, y0, x1, y1 = bounds
    if side == "left":
        return (x0, y0, min(x1, x0 + depth), y1)
    if side == "right":
        return (max(x0, x1 - depth), y0, x1, y1)
    if side == "bottom":
        return (x0, y0, x1, min(y1, y0 + depth))
    return (x0, max(y0, y1 - depth), x1, y1)


def _choose_main_side(side_edge_type):
    sides = list(side_edge_type.keys())
    main = [s for s in sides if side_edge_type.get(s) == "main_street"]
    if main:
        return main[0]
    sec = [s for s in sides if side_edge_type.get(s) == "secondary_street"]
    if sec:
        return sec[0]
    return max(sides, key=lambda s: FRONTAGE_PRIORITY.get(side_edge_type.get(s, "back_street"), 0))


def _opposite_side(side: str) -> str:
    return {"left": "right", "right": "left", "bottom": "top", "top": "bottom"}.get(side, "bottom")


def _weighted_segments(start: float, end: float, ratios: List[float]) -> List[Tuple[float, float]]:
    total = sum(max(1e-6, r) for r in ratios)
    length = end - start
    out = []
    cur = start
    for i, r in enumerate(ratios):
        seg = length * (max(1e-6, r) / total)
        nxt = end if i == len(ratios) - 1 else cur + seg
        out.append((cur, nxt))
        cur = nxt
    return out


def _split_rect_weighted(rect, nx, ny, ratios_x, ratios_y):
    x0, y0, x1, y1 = rect
    xs = _weighted_segments(x0, x1, ratios_x[:nx])
    ys = _weighted_segments(y0, y1, ratios_y[:ny])
    out = []
    for yi in range(ny):
        for xi in range(nx):
            out.append((xs[xi][0], ys[yi][0], xs[xi][1], ys[yi][1], xi, yi))
    return out


def _expand_rect(r: Tuple[float, float, float, float], d: float) -> Tuple[float, float, float, float]:
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def _finalize_mass_layout(rects, land_cfg, coverage_max, required_gfa, height_limit):
    rects = [r for r in rects if rect_area(r) > 30.0]
    if not rects:
        return [], {
            "status": "infeasible",
            "warnings": ["No feasible commercial mass generated"],
            "max_floors": 1,
            "assigned_floors": [],
            "required_gfa": round(required_gfa, 2),
            "estimated_gfa": 0.0,
            "coverage_max": round(coverage_max, 2),
            "total_footprint": 0.0,
        }
    area = sum(rect_area(r) for r in rects)
    if area > coverage_max and area > 1e-6:
        scale = math.sqrt(max(0.3, coverage_max / area))
        rects = [scale_rect_about_center(r, scale) for r in rects]
        area = sum(rect_area(r) for r in rects)

    floor_h = float(land_cfg["floor_height"])
    max_floors = max(1, int(math.floor(height_limit / max(1e-6, floor_h))))
    avg_floors = max(1, min(max_floors, int(math.ceil(required_gfa / max(1e-6, area)))))
    assigned = [avg_floors for _ in rects]
    est_gfa = sum(rect_area(rects[i]) * assigned[i] for i in range(len(rects)))
    i = 0
    while est_gfa < required_gfa * 0.98 and i < len(rects) * 8:
        j = i % len(rects)
        if assigned[j] < max_floors:
            assigned[j] += 1
            est_gfa += rect_area(rects[j])
        i += 1
    warnings = []
    if est_gfa < required_gfa * 0.98:
        warnings.append("Commercial FAR target not fully satisfied")
    return rects, {
        "status": "ok",
        "warnings": warnings,
        "max_floors": max_floors,
        "assigned_floors": assigned,
        "required_gfa": round(required_gfa, 2),
        "estimated_gfa": round(est_gfa, 2),
        "coverage_max": round(coverage_max, 2),
        "total_footprint": round(sum(rect_area(r) for r in rects), 2),
    }


def _generate_b1_short_side_fallback(buildable_rect, side_edge_type, depth, shape, high_sides):
    rects = []
    if not high_sides:
        high_sides = [_choose_main_side(side_edge_type)]
    if shape == "L":
        sides = high_sides[:2] if len(high_sides) >= 2 else [high_sides[0], _opposite_side(high_sides[0])]
    else:
        sides = high_sides[:3] if len(high_sides) >= 3 else list(dict.fromkeys(high_sides + [s for s in ["left", "right", "bottom", "top"] if s not in high_sides]))[:3]
    for s in sides:
        rects.append(_rect_for_side_depth(buildable_rect, s, depth))
    return rects


def _generate_mass_layout_b1(
    buildable_rect,
    forbidden_rects,
    land_cfg,
    coverage_max,
    required_gfa,
    height_limit,
    side_edge_type,
    rng,
):
    x0, y0, x1, y1 = buildable_rect
    w = x1 - x0
    h = y1 - y0
    short_side = min(w, h)
    long_side = max(w, h)

    high_sides = [s for s, et in side_edge_type.items() if et in {"main_street", "secondary_street"}]
    main_side = _choose_main_side(side_edge_type)
    if not high_sides:
        high_sides = [main_side]

    mode_choices = [int(v) for v in land_cfg["prototype_mode_choices"] if int(v) in {1, 2, 3}]
    if w > 150.0 and h > 150.0:
        mode = 3
    else:
        if not mode_choices:
            mode_choices = [1, 2, 3]
        # Size-biased random: small blocks prefer type 1, large blocks prefer type 3 (about 50%).
        preferred = None
        if long_side <= 90.0:
            preferred = 1
        elif long_side >= 130.0:
            preferred = 3

        if preferred in mode_choices:
            weights = []
            for m in mode_choices:
                weights.append(0.5 if m == preferred else (0.5 / max(1, len(mode_choices) - 1)))
            r = rng.random()
            acc = 0.0
            mode = mode_choices[-1]
            for m, wgt in zip(mode_choices, weights):
                acc += wgt
                if r <= acc:
                    mode = int(m)
                    break
        else:
            mode = int(rng.choice(mode_choices))

    fallback_thr = float(land_cfg["short_side_fallback_threshold_m"])
    fallback_depth = float(land_cfg["short_side_fallback_bar_depth_m"])
    fallback_shapes = [str(s) for s in land_cfg["short_side_fallback_shape_choices"]]
    fallback_shape = str(rng.choice(fallback_shapes)) if fallback_shapes else "L"
    rects: List[Tuple[float, float, float, float]] = []
    extra = {"b1_mode": mode}

    if short_side < fallback_thr:
        rects = _generate_b1_short_side_fallback(buildable_rect, side_edge_type, fallback_depth, fallback_shape, high_sides)
        extra["b1_mode_name"] = "fallback_lu"
    elif mode == 1:
        depth_s_rng = land_cfg["courtyard_depth_short_range"]
        depth_l_rng = land_cfg["courtyard_depth_long_range"]
        d_short = float(rng.uniform(float(depth_s_rng[0]), float(depth_s_rng[1])))
        d_long = float(rng.uniform(float(depth_l_rng[0]), float(depth_l_rng[1])))
        dl = d_short if w <= h else d_long
        dr = d_short if w <= h else d_long
        db = d_short if h <= w else d_long
        dt = d_short if h <= w else d_long

        left = (x0, y0, min(x1, x0 + dl), y1)
        right = (max(x0, x1 - dr), y0, x1, y1)
        bottom = (x0 + dl, y0, x1 - dr, min(y1, y0 + db))
        top = (x0 + dl, max(y0, y1 - dt), x1 - dr, y1)
        base_rects = [r for r in [left, right, bottom, top] if rect_area(r) > 1.0]

        # Corner processing:
        # - influenced corner/edge: aggressive cut (depth + 10)
        # - non-influenced corner: no cut
        corner_specs = [
            ("lb", x0, y0, dl, db),
            ("rb", x1, y0, dr, db),
            ("lt", x0, y1, dl, dt),
            ("rt", x1, y1, dr, dt),
        ]
        corner_cuts = []
        for _, cx, cy, dx, dy in corner_specs:
            big_hx = dx + 10.0
            big_hy = dy + 10.0
            big_cut = (cx - big_hx, cy - big_hy, cx + big_hx, cy + big_hy)
            influenced = any(rect_intersection_area(big_cut, fr) > 1e-6 for fr in forbidden_rects)
            if influenced:
                corner_cuts.append(big_cut)

        all_cuts = list(forbidden_rects) + corner_cuts
        carved = subtract_rects(base_rects, all_cuts)
        carved = [r for r in carved if rect_area(r) > 20.0]
        if not carved:
            carved = base_rects

        floor_h = float(land_cfg["floor_height"])
        min_target_h = 15.0
        max_target_h = min(24.0, float(height_limit))
        min_floors = max(1, int(math.ceil(min_target_h / max(1e-6, floor_h))))
        max_floors = max(1, int(math.floor(max_target_h / max(1e-6, floor_h))))
        if max_floors < min_floors:
            floors = max_floors
        else:
            floors = int(rng.randint(min_floors, max_floors))
        target_h = round(floors * floor_h, 2)

        area_sum = sum(rect_area(r) for r in carved)
        minx = min(r[0] for r in carved); miny = min(r[1] for r in carved)
        maxx = max(r[2] for r in carved); maxy = max(r[3] for r in carved)
        logical = (minx, miny, maxx, maxy)
        comp_polys = [rect_poly(r[0], r[1], r[2], r[3]) for r in carved]

        meta = {
            "status": "ok",
            "warnings": ["FAR ignored for commercial courtyard mode"],
            "max_floors": floors,
            "assigned_floors": [floors],
            "required_gfa": round(required_gfa, 2),
            "estimated_gfa": round(area_sum * floors, 2),
            "coverage_max": round(coverage_max, 2),
            "total_footprint": round(area_sum, 2),
        }
        extra["b1_mode_name"] = "courtyard"
        extra["component_polygons_by_index"] = {0: comp_polys}
        return [logical], meta, extra
    elif mode == 2:
        smin = land_cfg["mall_size_min"]; smax = land_cfg["mall_size_max"]
        short_target = max(float(smin[0]), min(short_side, float(rng.uniform(float(smin[0]), float(smax[0])))))
        long_target = max(float(smin[1]), min(long_side, float(rng.uniform(float(smin[1]), float(smax[1])))))
        if w >= h:
            bw, bh = long_target, short_target
        else:
            bw, bh = short_target, long_target
        bw = min(bw, w); bh = min(bh, h)

        attach_modes = [str(x) for x in land_cfg["mall_attach_mode_choices"]]
        attach = str(rng.choice(attach_modes)) if attach_modes else "main_side"
        side = main_side if attach == "main_side" else _opposite_side(main_side)
        if side == "left":
            rects = [(x0, y0 + (h - bh) * 0.5, x0 + bw, y0 + (h + bh) * 0.5)]
        elif side == "right":
            rects = [(x1 - bw, y0 + (h - bh) * 0.5, x1, y0 + (h + bh) * 0.5)]
        elif side == "bottom":
            rects = [(x0 + (w - bw) * 0.5, y0, x0 + (w + bw) * 0.5, y0 + bh)]
        else:
            rects = [(x0 + (w - bw) * 0.5, y1 - bh, x0 + (w + bw) * 0.5, y1)]
        extra["b1_mode_name"] = "mall_bigbox"
        # Fixed mall height policy: small mall = 15m, large mall = 30m.
        short_mid = (float(smin[0]) + float(smax[0])) * 0.5
        long_mid = (float(smin[1]) + float(smax[1])) * 0.5
        is_small = short_target <= short_mid and long_target <= long_mid
        forced_h = 15.0 if is_small else 30.0
        extra["forced_height_by_index"] = {0: forced_h}
        extra["mall_size_class"] = "small" if is_small else "large"
    else:
        mb = land_cfg["multi_box"]
        if 50.0 <= short_side < 120.0:
            split = str(rng.choice(mb["split_choices_50_120"]))
            nx, ny = (2, 2) if split == "2x2" else (3, 2)
        elif 120.0 <= short_side <= 200.0:
            split = str(mb["split_120_200"])
            nx, ny = (3, 3) if split == "3x3" else (3, 3)
        else:
            nx, ny = (3, 3)
        ratio2 = [float(x) for x in mb["ratio_2"]]
        ratio3 = [float(x) for x in mb["ratio_3"]]
        ratios_x = ratio3 if nx == 3 else ratio2
        ratios_y = ratio3 if ny == 3 else ratio2
        cells = _split_rect_weighted(buildable_rect, nx, ny, ratios_x, ratios_y)

        # 1) If 3x3, remove center cell.
        cell_items = []
        for (cx0, cy0, cx1, cy1, xi, yi) in cells:
            if nx == 3 and ny == 3 and xi == 1 and yi == 1:
                continue
            cell_items.append({
                "rect": (cx0, cy0, cx1, cy1),
                "members": {(xi, yi)},
            })

        # 2) If near influence, remove nearby cell with 50% probability.
        influence_near = [_expand_rect(fr, 8.0) for fr in forbidden_rects]
        filtered = []
        for c in cell_items:
            near_inf = any(rect_intersection_area(c["rect"], fr) > 1e-6 for fr in influence_near)
            if near_inf and rng.random() < 0.5:
                continue
            filtered.append(c)
        if filtered:
            cell_items = filtered

        # 3) Randomly merge adjacent cells by grid size.
        if nx == 3 and ny == 3:
            merge_target = rng.randint(2, 3)
        elif (nx == 3 and ny == 2) or (nx == 2 and ny == 3):
            merge_target = rng.randint(1, 2)
        elif nx == 2 and ny == 2:
            merge_target = 1
        else:
            merge_target = 0

        def _groups_adjacent(g1, g2):
            for (x1m, y1m) in g1["members"]:
                for (x2m, y2m) in g2["members"]:
                    if abs(x1m - x2m) + abs(y1m - y2m) == 1:
                        return True
            return False

        merge_done = 0
        while merge_done < merge_target and len(cell_items) > 1:
            pairs = []
            for i in range(len(cell_items)):
                for j in range(i + 1, len(cell_items)):
                    if _groups_adjacent(cell_items[i], cell_items[j]):
                        pairs.append((i, j))
            if not pairs:
                break
            i, j = pairs[rng.randrange(len(pairs))]
            a, b = cell_items[i], cell_items[j]
            ax0, ay0, ax1, ay1 = a["rect"]
            bx0, by0, bx1, by1 = b["rect"]
            merged = {
                "rect": (min(ax0, bx0), min(ay0, by0), max(ax1, bx1), max(ay1, by1)),
                "members": set(a["members"]) | set(b["members"]),
            }
            keep = []
            for k, g in enumerate(cell_items):
                if k not in {i, j}:
                    keep.append(g)
            keep.append(merged)
            cell_items = keep
            merge_done += 1

        off_rng = mb["box_offset_range"]
        off_min, off_max = float(off_rng[0]), float(off_rng[1])
        off_min = max(5.0, off_min)
        off_max = min(10.0, off_max)
        if off_max < off_min:
            off_max = off_min
        main_is_x_side = main_side in {"left", "right"}
        for g in cell_items:
            cx0, cy0, cx1, cy1 = g["rect"]
            off = float(rng.uniform(off_min, off_max))
            rx0, ry0, rx1, ry1 = cx0 + off, cy0 + off, cx1 - off, cy1 - off
            members = g["members"]
            touch_left = any(xi == 0 for (xi, _) in members)
            touch_right = any(xi == nx - 1 for (xi, _) in members)
            touch_bottom = any(yi == 0 for (_, yi) in members)
            touch_top = any(yi == ny - 1 for (_, yi) in members)
            if main_is_x_side:
                if main_side == "left" and touch_left:
                    rx0 = cx0
                if main_side == "right" and touch_right:
                    rx1 = cx1
            else:
                if main_side == "bottom" and touch_bottom:
                    ry0 = cy0
                if main_side == "top" and touch_top:
                    ry1 = cy1
            if rx1 > rx0 + 4.0 and ry1 > ry0 + 4.0:
                rects.append((rx0, ry0, rx1, ry1))
        extra["b1_mode_name"] = "multi_box"

    rects = _clip_tower_items_against_forbidden([{"rect": r, "row": 0, "floors": 1} for r in rects], forbidden_rects, buildable_rect)
    rects = [t["rect"] for t in rects]
    rects, meta = _finalize_mass_layout(rects, land_cfg, coverage_max, required_gfa, height_limit)
    if extra.get("b1_mode_name") == "multi_box":
        extra["forced_height_by_index"] = {i: round(rng.uniform(15.0, min(50.0, float(height_limit))), 2) for i in range(len(rects))}
    return rects, meta, extra


def _b2_tower_count_by_ratio(ratio: float, cfg: Dict[str, Any]) -> int:
    if ratio < float(cfg["ratio_single_max"]):
        return 1
    if ratio < float(cfg["ratio_double_max"]):
        return 2
    if ratio < float(cfg["ratio_triple_max"]):
        return 3
    if ratio < float(cfg["ratio_quad_max"]):
        return 4
    if ratio < float(cfg["ratio_penta_max"]):
        return 5
    return max(6, int(math.ceil(ratio)))


def _split_rect_grid_with_gap(rect: Tuple[float, float, float, float], cols: int, rows: int, gap: float) -> List[Tuple[float, float, float, float, int, int]]:
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    usable_w = w - gap * (cols - 1)
    usable_h = h - gap * (rows - 1)
    if usable_w <= 1e-6 or usable_h <= 1e-6:
        return []
    cw = usable_w / cols
    ch = usable_h / rows
    out = []
    for r in range(rows):
        for c in range(cols):
            cx0 = x0 + c * (cw + gap)
            cy0 = y0 + r * (ch + gap)
            out.append((cx0, cy0, cx0 + cw, cy0 + ch, c, r))
    return out


def _generate_mass_layout_b2(
    buildable_rect,
    forbidden_rects,
    land_cfg,
    coverage_max,
    required_gfa,
    height_limit,
    side_edge_type,
    rng,
):
    x0, y0, x1, y1 = buildable_rect
    w, h = x1 - x0, y1 - y0
    short_side = min(w, h)
    long_side = max(w, h)
    ratio = long_side / max(1e-6, short_side)

    tp = land_cfg["tower_podium"]
    tower_count = _b2_tower_count_by_ratio(ratio, tp)
    rows = 1
    if short_side > float(tp["short_side_two_row_threshold_m"]) and tower_count >= 2:
        rows = 2
    cols = int(math.ceil(tower_count / rows))
    grid = _split_rect_grid_with_gap(buildable_rect, cols, rows, float(tp["inter_zone_gap_m"]))
    if not grid:
        grid = [(x0, y0, x1, y1, 0, 0)]
        tower_count = 1
        rows = 1
        cols = 1

    # Keep first N zones in importance order (prefer frontage side first).
    main_side = _choose_main_side(side_edge_type)
    def zone_score(item):
        cx0, cy0, cx1, cy1, c, r = item
        zcx, zcy = (cx0 + cx1) * 0.5, (cy0 + cy1) * 0.5
        if main_side == "left":
            return zcx
        if main_side == "right":
            return -zcx
        if main_side == "bottom":
            return zcy
        return -zcy
    grid = sorted(grid, key=zone_score)
    zones = grid[:tower_count]

    rects: List[Tuple[float, float, float, float]] = []
    b2_role_by_index: Dict[int, str] = {}
    forced_height_by_index: Dict[int, float] = {}
    tower_index = 0

    w_primary = float(tp["plaza_retreat_priority_weights"]["primary_or_important"])
    w_secondary = float(tp["plaza_retreat_priority_weights"]["secondary"])
    retreat_prob = float(tp["plaza_retreat_probability"])
    podium_h = float(tp["podium_height_m"])
    short_rng = tp["tower_floorplate_short_range_m"]
    long_rng = tp["tower_floorplate_long_range_m"]
    floor_h = float(land_cfg["floor_height"])
    tower_h = float(height_limit)
    tower_h = max(floor_h, tower_h)

    for (zx0, zy0, zx1, zy1, c, r) in zones:
        # Podium: touches 3 edges, 1 edge retreats (or no retreat).
        px0, py0, px1, py1 = zx0, zy0, zx1, zy1
        retreat_side = None
        if rng.random() < retreat_prob:
            primary_sides = [s for s, et in side_edge_type.items() if et in {"main_street", "scenic_street"}]
            secondary_sides = [s for s, et in side_edge_type.items() if et == "secondary_street"]
            candidates = []
            if primary_sides:
                candidates.extend([(s, w_primary / max(1, len(primary_sides))) for s in primary_sides])
            if secondary_sides:
                candidates.extend([(s, w_secondary / max(1, len(secondary_sides))) for s in secondary_sides])
            if candidates:
                rnum = rng.random() * sum(w for _, w in candidates)
                acc = 0.0
                for s, ww in candidates:
                    acc += ww
                    if rnum <= acc:
                        retreat_side = s
                        break
        if retreat_side == "left":
            retreat_depth = (zy1 - zy0) / 3.0
            retreat_depth = min(retreat_depth, (zx1 - zx0) * 0.8)
            px0 += retreat_depth
        elif retreat_side == "right":
            retreat_depth = (zy1 - zy0) / 3.0
            retreat_depth = min(retreat_depth, (zx1 - zx0) * 0.8)
            px1 -= retreat_depth
        elif retreat_side == "bottom":
            retreat_depth = (zx1 - zx0) / 3.0
            retreat_depth = min(retreat_depth, (zy1 - zy0) * 0.8)
            py0 += retreat_depth
        elif retreat_side == "top":
            retreat_depth = (zx1 - zx0) / 3.0
            retreat_depth = min(retreat_depth, (zy1 - zy0) * 0.8)
            py1 -= retreat_depth
        podium_rect = (px0, py0, px1, py1)
        if rect_area(podium_rect) < 30.0:
            podium_rect = (zx0, zy0, zx1, zy1)

        # Tower: place on podium top with standard floorplate range.
        pw, ph = podium_rect[2] - podium_rect[0], podium_rect[3] - podium_rect[1]
        t_short = min(float(rng.uniform(float(short_rng[0]), float(short_rng[1]))), min(pw, ph))
        t_long = min(float(rng.uniform(float(long_rng[0]), float(long_rng[1]))), max(pw, ph))
        if pw >= ph:
            tw = min(t_long, pw); th = min(t_short, ph)
        else:
            tw = min(t_short, pw); th = min(t_long, ph)
        tcx, tcy = (podium_rect[0] + podium_rect[2]) * 0.5, (podium_rect[1] + podium_rect[3]) * 0.5
        tower_rect = (tcx - tw * 0.5, tcy - th * 0.5, tcx + tw * 0.5, tcy + th * 0.5)

        # Remove forbidden overlap.
        podium_parts = subtract_rects([podium_rect], forbidden_rects)
        podium_parts = [r for r in podium_parts if rect_area(r) > 20.0]
        if not podium_parts:
            podium_parts = [podium_rect]
        tower_parts = subtract_rects([tower_rect], forbidden_rects)
        tower_parts = [r for r in tower_parts if rect_area(r) > 20.0]
        if not tower_parts:
            continue

        # Add podium mass (first part as logical rect, all parts as components).
        p_idx = len(rects)
        p_logical = (
            min(r0 for r0, _, _, _ in podium_parts),
            min(r1 for _, r1, _, _ in podium_parts),
            max(r2 for _, _, r2, _ in podium_parts),
            max(r3 for _, _, _, r3 in podium_parts),
        )
        rects.append(p_logical)
        b2_role_by_index[p_idx] = "podium"
        forced_height_by_index[p_idx] = podium_h

        # Tower mass.
        t_idx = len(rects)
        t_logical = (
            min(r0 for r0, _, _, _ in tower_parts),
            min(r1 for _, r1, _, _ in tower_parts),
            max(r2 for _, _, r2, _ in tower_parts),
            max(r3 for _, _, _, r3 in tower_parts),
        )
        rects.append(t_logical)
        b2_role_by_index[t_idx] = "tower"
        forced_height_by_index[t_idx] = tower_h
        tower_index += 1

    # Keep reasonable coverage; FAR ignored for B2 tower+podium.
    area_sum = sum(rect_area(r) for r in rects)
    if area_sum > coverage_max and area_sum > 1e-6:
        scale = math.sqrt(max(0.35, coverage_max / area_sum))
        rects = [scale_rect_about_center(r, scale) for r in rects]

    assigned = []
    for i in range(len(rects)):
        fh = float(forced_height_by_index.get(i, floor_h))
        assigned.append(max(1, int(round(fh / max(1e-6, floor_h)))))
    est_gfa = sum(rect_area(rects[i]) * assigned[i] for i in range(len(rects)))
    meta = {
        "status": "ok",
        "warnings": ["FAR ignored for office tower+podium mode"],
        "max_floors": max(assigned) if assigned else 1,
        "assigned_floors": assigned,
        "required_gfa": round(required_gfa, 2),
        "estimated_gfa": round(est_gfa, 2),
        "coverage_max": round(coverage_max, 2),
        "total_footprint": round(sum(rect_area(r) for r in rects), 2),
    }
    extra = {
        "b2_mode_name": "tower_podium",
        "b2_role_by_index": b2_role_by_index,
        "forced_height_by_index": forced_height_by_index,
    }
    return rects, meta, extra


def _generate_mass_layout_residential(
    buildable_rect,
    forbidden_rects,
    land_cfg,
    coverage_max,
    required_gfa,
    height_limit,
    min_spacing,
    edge_clearance,
    side_pri,
    side_edge_type,
    rng,
):
    bx0, by0, bx1, by1 = buildable_rect
    ordered_sides = sorted(side_pri.keys(), key=lambda s: side_pri[s], reverse=True)

    depth_rng = land_cfg["podium_depth_range"]
    depth_min = float(depth_rng[0]); depth_max = float(depth_rng[1])
    podium_depth = float(land_cfg["podium_depth"])
    if podium_depth <= 0.0:
        podium_depth = float(rng.uniform(depth_min, depth_max))

    floors_rng = land_cfg["podium_floors_range"]
    podium_floors = int(rng.randint(int(floors_rng[0]), int(floors_rng[1])))
    podium_floor_heights = [float(x) for x in land_cfg["podium_floor_heights"]]
    podium_height = sum(podium_floor_heights[:podium_floors])

    mode_choices = [int(x) for x in land_cfg["podium_frontage_mode_choices"]]
    mode_choices = [m for m in mode_choices if m in {1, 2, 3, 4}]
    if not mode_choices:
        raise ValueError("residential.podium_retail.frontage_mode_choices must contain at least one of [1,2,3,4]")
    frontage_mode = int(rng.choice(mode_choices))
    podium_sides = _select_residential_podium_sides(frontage_mode, ordered_sides, side_edge_type)

    podium_bands = []
    for side in podium_sides:
        if side == "bottom":
            poly = rect_poly(bx0, by0, bx1, min(by1, by0 + podium_depth))
        elif side == "top":
            poly = rect_poly(bx0, max(by0, by1 - podium_depth), bx1, by1)
        elif side == "left":
            poly = rect_poly(bx0, by0, min(bx1, bx0 + podium_depth), by1)
        else:
            poly = rect_poly(max(bx0, bx1 - podium_depth), by0, bx1, by1)
        podium_bands.append({"polygon": poly, "side": side, "floors": podium_floors})

    ix0, iy0, ix1, iy1 = bx0, by0, bx1, by1
    if "left" in podium_sides: ix0 += podium_depth
    if "right" in podium_sides: ix1 -= podium_depth
    if "bottom" in podium_sides: iy0 += podium_depth
    if "top" in podium_sides: iy1 -= podium_depth
    inner_rect = (ix0 + edge_clearance, iy0 + edge_clearance, ix1 - edge_clearance, iy1 - edge_clearance)
    if inner_rect[2] <= inner_rect[0] + 10.0 or inner_rect[3] <= inner_rect[1] + 10.0:
        inner_rect = (bx0 + edge_clearance, by0 + edge_clearance, bx1 - edge_clearance, by1 - edge_clearance)

    style_choices = [str(x) for x in land_cfg["layout_style_choices"]]
    style_choices = [s for s in style_choices if s in {"point", "row"}]
    if not style_choices:
        raise ValueError("residential.tower.layout_style_choices must contain at least one of ['point','row']")
    tower_style = str(rng.choice(style_choices))
    tower_floor_h = float(land_cfg["floor_height"])
    max_tower_floors = max(1, int(math.floor(max(1e-6, (height_limit - podium_height)) / max(1e-6, tower_floor_h))))

    tower_items = []
    min_row_floors = max(1, int(math.floor(max_tower_floors * 0.45)))
    prev_row_floors = None
    if tower_style == "point":
        point_cfg = land_cfg["point_layout"]
        tw = float(point_cfg["footprint_size_m"][0]); th = float(point_cfg["footprint_size_m"][1])
        ew_formula = point_cfg["ew_gap_formula"]
        ns_formula = point_cfg["ns_gap_formula"]
        row_defs = []
        y = inner_rect[1]
        while y + th <= inner_rect[3] + 1e-6:
            row_floors = int(rng.randint(min_row_floors, max_tower_floors))
            if prev_row_floors is not None and row_floors == prev_row_floors and max_tower_floors > min_row_floors:
                row_floors = row_floors + 1 if row_floors < max_tower_floors else row_floors - 1
            prev_row_floors = row_floors
            row_total_h = podium_height + row_floors * tower_floor_h
            ew_min = max(
                float(point_cfg["ew_gap_min_m"]),
                float(ew_formula["base_m"]) + max(0.0, row_total_h - float(ew_formula["height_threshold_m"])) * float(ew_formula["slope"]),
            )
            ns_min = max(
                float(point_cfg["ns_gap_min_m"]),
                float(ns_formula["base_m"]) + max(0.0, row_total_h - float(ns_formula["height_threshold_m"])) * float(ns_formula["slope"]),
            )
            ew_gap = min(float(point_cfg["ew_gap_max_m"]), ew_min)
            ns_gap = min(float(point_cfg["ns_gap_max_m"]), ns_min)
            row_defs.append({"y": y, "floors": row_floors, "ew_gap": ew_gap, "ns_gap": ns_gap})
            x = inner_rect[0]
            while x + tw <= inner_rect[2] + 1e-6:
                tower_items.append({"rect": (x, y, x + tw, y + th), "row": len(row_defs) - 1, "floors": row_floors})
                x += tw + ew_gap
            y += th + ns_gap
        # Let first/last row stick to inner boundary in north-south direction.
        if row_defs:
            top_y = inner_rect[3] - th
            if top_y > row_defs[-1]["y"] + 1e-6:
                row_floors = int(rng.randint(min_row_floors, max_tower_floors))
                if row_floors == row_defs[-1]["floors"] and max_tower_floors > min_row_floors:
                    row_floors = row_floors + 1 if row_floors < max_tower_floors else row_floors - 1
                row_total_h = podium_height + row_floors * tower_floor_h
                ew_min = max(
                    float(point_cfg["ew_gap_min_m"]),
                    float(ew_formula["base_m"]) + max(0.0, row_total_h - float(ew_formula["height_threshold_m"])) * float(ew_formula["slope"]),
                )
                ew_gap = min(float(point_cfg["ew_gap_max_m"]), ew_min)
                row_defs.append({"y": top_y, "floors": row_floors, "ew_gap": ew_gap, "ns_gap": 0.0})
                x = inner_rect[0]
                while x + tw <= inner_rect[2] + 1e-6:
                    tower_items.append({"rect": (x, top_y, x + tw, top_y + th), "row": len(row_defs) - 1, "floors": row_floors})
                    x += tw + ew_gap
    else:
        row_cfg = land_cfg["row_layout"]
        depth_ns = float(row_cfg["depth_ns_m"])
        length_ew = min(float(row_cfg["length_ew_max_m"]), max(float(row_cfg["length_ew_min_m"]), inner_rect[2] - inner_rect[0]))
        ew_gap = float(row_cfg["ew_gap_m"])
        nsf = row_cfg["ns_gap_formula"]
        row_defs = []
        y = inner_rect[1]
        while y + depth_ns <= inner_rect[3] + 1e-6:
            row_floors = int(rng.randint(min_row_floors, max_tower_floors))
            if prev_row_floors is not None and row_floors == prev_row_floors and max_tower_floors > min_row_floors:
                row_floors = row_floors + 1 if row_floors < max_tower_floors else row_floors - 1
            prev_row_floors = row_floors
            row_total_h = podium_height + row_floors * tower_floor_h
            ns_gap = float(nsf["base_m"]) + max(0.0, row_total_h - float(nsf["height_threshold_m"])) * float(nsf["slope"])
            row_defs.append({"y": y, "floors": row_floors, "ns_gap": ns_gap})
            x = inner_rect[0]
            while x + length_ew <= inner_rect[2] + 1e-6:
                tower_items.append({"rect": (x, y, x + length_ew, y + depth_ns), "row": len(row_defs) - 1, "floors": row_floors})
                x += length_ew + ew_gap
            y += depth_ns + ns_gap
        if row_defs:
            top_y = inner_rect[3] - depth_ns
            if top_y > row_defs[-1]["y"] + 1e-6:
                row_floors = int(rng.randint(min_row_floors, max_tower_floors))
                if row_floors == row_defs[-1]["floors"] and max_tower_floors > min_row_floors:
                    row_floors = row_floors + 1 if row_floors < max_tower_floors else row_floors - 1
                row_defs.append({"y": top_y, "floors": row_floors, "ns_gap": 0.0})
                x = inner_rect[0]
                while x + length_ew <= inner_rect[2] + 1e-6:
                    tower_items.append({"rect": (x, top_y, x + length_ew, top_y + depth_ns), "row": len(row_defs) - 1, "floors": row_floors})
                    x += length_ew + ew_gap

    if not tower_items:
        fallback = split_rect_with_spacing(inner_rect, 1, min_spacing, 0.0)
        tower_items = [{"rect": fallback[0], "row": 0, "floors": max(1, min_row_floors)}] if fallback else []

    tower_items = _clip_tower_items_against_forbidden(tower_items, forbidden_rects, inner_rect)
    if not tower_items:
        fallback = split_rect_with_spacing(inner_rect, 1, min_spacing, 0.0)
        tower_items = [{"rect": fallback[0], "row": 0, "floors": max(1, min_row_floors)}] if fallback else []

    area_tower = sum(rect_area(t["rect"]) for t in tower_items)
    area_podium = sum(poly_area(pb["polygon"]) for pb in podium_bands)
    total_footprint = area_tower + area_podium
    target_tower_area = max(0.0, coverage_max - area_podium)
    if area_tower > target_tower_area and area_tower > 1e-6:
        scale = math.sqrt(max(0.35, target_tower_area / area_tower))
        for t in tower_items:
            t["rect"] = fit_rect_inside(scale_rect_about_center(t["rect"], scale), inner_rect)
        area_tower = sum(rect_area(t["rect"]) for t in tower_items)
    total_footprint = area_tower + area_podium

    podium_gfa = area_podium * podium_floors
    row_area = {}
    row_floors = {}
    for t in tower_items:
        r = int(t["row"])
        row_area[r] = row_area.get(r, 0.0) + rect_area(t["rect"])
        row_floors[r] = int(t["floors"])
    row_order = sorted(row_area.keys())

    assigned_row_floors = {r: max(1, min(max_tower_floors, row_floors[r])) for r in row_order}
    est_gfa = podium_gfa + sum(row_area[r] * assigned_row_floors[r] for r in row_order)

    i = 0
    while est_gfa < required_gfa * 0.98 and i < max(1, len(row_order)) * 20:
        r = row_order[i % len(row_order)]
        if assigned_row_floors[r] < max_tower_floors:
            assigned_row_floors[r] += 1
            est_gfa += row_area[r]
        i += 1
    assigned = [assigned_row_floors[int(t["row"])] for t in tower_items]
    tower_rects = [t["rect"] for t in tower_items]

    status = "ok"
    warnings = []
    if total_footprint < coverage_max * 0.90:
        warnings.append("Residential layout could not fully approach building_density_max under spacing constraints")
    if est_gfa < required_gfa * 0.98:
        warnings.append("Residential FAR target not fully satisfied; density/layout priority applied")

    meta = {
        "status": status,
        "warnings": warnings,
        "max_floors": max_tower_floors,
        "assigned_floors": assigned,
        "required_gfa": round(required_gfa, 2),
        "estimated_gfa": round(est_gfa, 2),
        "coverage_max": round(coverage_max, 2),
        "total_footprint": round(total_footprint, 2),
    }
    extra = {
        "podium_bands": podium_bands,
        "residential_style": tower_style,
        "podium_frontage_mode": frontage_mode,
        "podium_depth": round(podium_depth, 2),
        "podium_floors": podium_floors,
        "podium_height": round(podium_height, 2),
        "row_floor_profile": [[int(r), int(assigned_row_floors[r])] for r in row_order],
    }
    return tower_rects, meta, extra


def generate_mass_layout(
    land_use,
    buildable_rect,
    forbidden_rects,
    land_cfg,
    coverage_max,
    required_gfa,
    height_limit,
    min_spacing,
    edge_clearance,
    side_pri,
    side_edge_type,
    rng,
):
    if land_use == "R":
        return _generate_mass_layout_residential(
            buildable_rect,
            forbidden_rects,
            land_cfg,
            coverage_max,
            required_gfa,
            height_limit,
            min_spacing,
            edge_clearance,
            side_pri,
            side_edge_type,
            rng,
        )
    if land_use == "B1":
        return _generate_mass_layout_b1(
            buildable_rect,
            forbidden_rects,
            land_cfg,
            coverage_max,
            required_gfa,
            height_limit,
            side_edge_type,
            rng,
        )
    if land_use == "B2":
        return _generate_mass_layout_b2(
            buildable_rect,
            forbidden_rects,
            land_cfg,
            coverage_max,
            required_gfa,
            height_limit,
            side_edge_type,
            rng,
        )
    return _generate_mass_layout_b1_b2(
        buildable_rect,
        forbidden_rects,
        land_cfg,
        coverage_max,
        required_gfa,
        height_limit,
        min_spacing,
        edge_clearance,
    )


def choose_entry_side(side_edge_type, land_cfg):
    pri = land_cfg.get("entry_frontage_priority", []) or []
    if not pri:
        return max(side_edge_type.keys(), key=lambda s: FRONTAGE_PRIORITY.get(side_edge_type.get(s, "back_street"), 0))
    best_side, best_rank = "bottom", 10**9
    for side, et in side_edge_type.items():
        rank = pri.index(et) if et in pri else 10**6
        if rank < best_rank:
            best_rank, best_side = rank, side
    return best_side


def make_forecourt_for_building(footprint_rect, buildable_rect, side, depth):
    fx0, fy0, fx1, fy1 = footprint_rect
    bx0, by0, bx1, by1 = buildable_rect
    if side == "bottom":
        return rect_poly(fx0, max(by0, fy0 - depth), fx1, fy0)
    if side == "top":
        return rect_poly(fx0, fy1, fx1, min(by1, fy1 + depth))
    if side == "left":
        return rect_poly(max(bx0, fx0 - depth), fy0, fx0, fy1)
    return rect_poly(fx1, fy0, min(bx1, fx1 + depth), fy1)


def _mode2_atrium_centers(fx0: float, fy0: float, fx1: float, fy1: float, count: int) -> List[Tuple[float, float]]:
    cx, cy = (fx0 + fx1) * 0.5, (fy0 + fy1) * 0.5
    w, h = fx1 - fx0, fy1 - fy0
    if count <= 1:
        return [(cx, cy)]
    if count == 2:
        if w >= h:
            d = w * 0.2
            return [(cx - d, cy), (cx + d, cy)]
        d = h * 0.2
        return [(cx, cy - d), (cx, cy + d)]
    if count == 3:
        return [(cx - w * 0.18, cy - h * 0.12), (cx + w * 0.18, cy - h * 0.12), (cx, cy + h * 0.16)]
    return [
        (cx - w * 0.18, cy - h * 0.18),
        (cx + w * 0.18, cy - h * 0.18),
        (cx - w * 0.18, cy + h * 0.18),
        (cx + w * 0.18, cy + h * 0.18),
    ]


def build_land_use_config(typology: Dict[str, Any], land_use: str) -> Dict[str, Any]:
    mm = typology["multi_mass_rules"]
    global_cfg = typology["global"]
    common = {
        "min_mass_count": 1,
        "max_mass_count": int(mm["max_masses_default"]),
        "large_plot_area_threshold_sqm": float(mm["large_plot_area_threshold_sqm"]),
        "medium_plot_area_threshold_sqm": float(mm["medium_plot_area_threshold_sqm"]),
        "coverage_target": 1.0,
    }
    if land_use == "B1":
        commercial = typology["commercial"]
        mall = commercial["mall_rect"]
        courtyard = commercial["courtyard"]
        mall_big = commercial["mall_bigbox"]
        multi_box = commercial["multi_box"]
        pref = [e for e in mall.get("preferred_entry_edges", []) if e in FRONTAGE_PRIORITY]
        return {
            **common,
            "building_type": "mall",
            "floor_height": float(commercial["default_floor_height_m"]),
            "entry_frontage_priority": pref,
            "atrium_size_xy": [float(mall["atrium_default_size_m"][0]), float(mall["atrium_default_size_m"][1])],
            "forecourt_depth": float(global_cfg["default_open_space_buffer_m"]),
            "prototype_mode_choices": [int(x) for x in commercial["prototype_mode_choices"]],
            "prototype_mode_exclude_type_1_when_long_side_gt_m": float(commercial["prototype_mode_exclude_type_1_when_long_side_gt_m"]),
            "short_side_fallback_threshold_m": float(commercial["short_side_fallback_threshold_m"]),
            "short_side_fallback_bar_depth_m": float(commercial["short_side_fallback_bar_depth_m"]),
            "short_side_fallback_shape_choices": [str(x) for x in commercial["short_side_fallback_shape_choices"]],
            "courtyard_depth_short_range": [float(courtyard["perimeter_depth_short_side_50_120_m"][0]), float(courtyard["perimeter_depth_short_side_50_120_m"][1])],
            "courtyard_depth_long_range": [float(courtyard["perimeter_depth_long_side_50_120_m"][0]), float(courtyard["perimeter_depth_long_side_50_120_m"][1])],
            "mall_size_min": [float(mall_big["size_min_m"][0]), float(mall_big["size_min_m"][1])],
            "mall_size_max": [float(mall_big["size_max_m"][0]), float(mall_big["size_max_m"][1])],
            "mall_attach_mode_choices": [str(x) for x in mall_big["attach_mode_choices"]],
            "multi_box": {
                "split_choices_50_120": [str(x) for x in multi_box["short_side_50_120_split_choices"]],
                "split_120_200": str(multi_box["short_side_120_200_split"]),
                "ratio_2": [float(x) for x in multi_box["primary_secondary_ratio"]],
                "ratio_3": [float(x) for x in multi_box["primary_secondary_secondary_ratio"]],
                "box_offset_range": [float(multi_box["box_offset_range_m"][0]), float(multi_box["box_offset_range_m"][1])],
            },
        }
    if land_use == "B2":
        office = typology["office"]
        tp = office["tower_podium"]
        return {
            **common,
            "building_type": "office",
            "floor_height": float(office["default_floor_height_m"]),
            "entry_frontage_priority": [],
            "core_ratio": float(office["core_ratio_default"]),
            "forecourt_depth": float(office["forecourt_default_m"]),
            "tower_podium": {
                "inter_zone_gap_m": float(tp["inter_zone_gap_m"]),
                "short_side_two_row_threshold_m": float(tp["short_side_two_row_threshold_m"]),
                "ratio_single_max": float(tp["ratio_single_max"]),
                "ratio_double_max": float(tp["ratio_double_max"]),
                "ratio_triple_max": float(tp["ratio_triple_max"]),
                "ratio_quad_max": float(tp["ratio_quad_max"]),
                "ratio_penta_max": float(tp["ratio_penta_max"]),
                "plaza_retreat_probability": float(tp["plaza_retreat_probability"]),
                "plaza_retreat_priority_weights": {
                    "primary_or_important": float(tp["plaza_retreat_priority_weights"]["primary_or_important"]),
                    "secondary": float(tp["plaza_retreat_priority_weights"]["secondary"]),
                },
                "podium_height_m": float(tp["podium_height_m"]),
                "tower_floorplate_short_range_m": [float(tp["tower_floorplate_short_range_m"][0]), float(tp["tower_floorplate_short_range_m"][1])],
                "tower_floorplate_long_range_m": [float(tp["tower_floorplate_long_range_m"][0]), float(tp["tower_floorplate_long_range_m"][1])],
            },
        }
    if land_use == "R":
        res = typology["residential"]
        podium = res["podium_retail"]
        tower = res["tower"]
        point = tower["point_layout"]
        row = tower["row_layout"]
        depth_rng = podium["depth_range_m"]
        floors_rng = podium["floors_range"]
        floor_heights = podium["floor_heights_m"]
        mode_choices = podium["frontage_mode_choices"]
        style_choices = tower["layout_style_choices"]
        return {
            **common,
            "building_type": "residential",
            "floor_height": float(tower["default_floor_height_m"]),
            "entry_frontage_priority": [],
            "podium_depth": float(podium["depth_default_m"]),
            "podium_depth_range": [float(depth_rng[0]), float(depth_rng[1])],
            "podium_floors_range": [int(floors_rng[0]), int(floors_rng[1])],
            "podium_floor_heights": [float(x) for x in floor_heights],
            "podium_frontage_mode_choices": [int(x) for x in mode_choices],
            "podium_random_continuous_prob": float(podium["continuity_probability"]),
            "layout_style_choices": [str(x) for x in style_choices],
            "point_layout": {
                "footprint_size_m": [float(point["footprint_size_m"][0]), float(point["footprint_size_m"][1])],
                "ew_gap_min_m": float(point["ew_gap_min_m"]),
                "ew_gap_max_m": float(point["ew_gap_max_m"]),
                "ew_gap_formula": {
                    "base_m": float(point["ew_gap_formula"]["base_m"]),
                    "height_threshold_m": float(point["ew_gap_formula"]["height_threshold_m"]),
                    "slope": float(point["ew_gap_formula"]["slope"]),
                },
                "ns_gap_min_m": float(point["ns_gap_min_m"]),
                "ns_gap_max_m": float(point["ns_gap_max_m"]),
                "ns_gap_formula": {
                    "base_m": float(point["ns_gap_formula"]["base_m"]),
                    "height_threshold_m": float(point["ns_gap_formula"]["height_threshold_m"]),
                    "slope": float(point["ns_gap_formula"]["slope"]),
                },
            },
            "row_layout": {
                "depth_ns_m": float(row["depth_ns_m"]),
                "length_ew_max_m": float(row["length_ew_max_m"]),
                "length_ew_min_m": float(row["length_ew_min_m"]),
                "ew_gap_m": float(row["ew_gap_m"]),
                "ns_gap_formula": {
                    "base_m": float(row["ns_gap_formula"]["base_m"]),
                    "height_threshold_m": float(row["ns_gap_formula"]["height_threshold_m"]),
                    "slope": float(row["ns_gap_formula"]["slope"]),
                },
            },
        }
    raise ValueError(f"Unsupported land_use: {land_use}")


def generate_step2(scene, typology):
    generated = scene.get("generated", {}) or {}
    step1 = generated.get("step_1_network", {}) or {}
    inputs = scene.get("inputs", {}) or {}

    blocks = step1.get("block_boundaries", []) or []
    frontages = step1.get("frontage_segments", []) or []
    corners = step1.get("corners", []) or []
    tiz = step1.get("transit_influence_zones", []) or []

    parcel_controls = ((inputs.get("planning_controls", {}) or {}).get("parcel_controls", [])) or []
    if not parcel_controls and (inputs.get("planning_controls", {}) or {}).get("parcel_id"):
        parcel_controls = [inputs.get("planning_controls")]

    frontages_by_block = {}
    frontage_block = {}
    for f in frontages:
        bid = f.get("block_id")
        if bid:
            frontages_by_block.setdefault(bid, []).append(f)
            frontage_block[str(f.get("id", ""))] = bid

    corners_by_block = {}
    for c in corners:
        bid = c.get("block_id")
        if bid:
            corners_by_block.setdefault(bid, []).append(c)

    tiz_by_block = {}
    for z in tiz:
        assoc = z.get("associated_frontage_ids", []) or []
        if assoc:
            bid = frontage_block.get(str(assoc[0]))
            if bid:
                tiz_by_block.setdefault(bid, []).append(z)

    global_cfg = typology["global"]
    multi_mass_cfg = typology["multi_mass_rules"]
    corner_cfg = typology["corner_reservations"]
    transit_cfg = typology["transit_influence"]

    min_spacing = float(multi_mass_cfg["min_gap_between_masses_m"])
    edge_clearance = float(global_cfg["default_open_space_buffer_m"])
    solver_grid = float(global_cfg["solver_grid_m"])

    buildable_zones = []
    solve_grids = []
    building_masses = []
    atriums = []
    cores = []
    podium_retail_bands = []
    reserved_open_spaces = []
    massing_reports = []

    bz_idx = 1
    grid_idx = 1
    bld_idx = 1
    atr_idx = 1
    core_idx = 1
    pod_idx = 1
    open_idx = 1
    rng = random.Random(int(global_cfg["random_seed"]))

    for pc in parcel_controls:
        center = pc.get("center")
        if not isinstance(center, list) or len(center) < 2:
            continue
        parcel_id = str(pc.get("parcel_id", f"parcel_{bz_idx:03d}"))
        cpt = (float(center[0]), float(center[1]))

        block = pick_block_for_parcel(cpt, blocks)
        if block is None:
            massing_reports.append({"parcel_id": parcel_id, "status": "infeasible", "reason": "no_matching_block"})
            continue

        block_id = str(block.get("id", ""))
        block_poly = block.get("polygon", [])
        block_bbox = poly_bbox(block_poly)
        parcel_area = poly_area(block_poly)

        land_use = str(pc.get("land_use", "")).strip()
        if land_use not in {"B1", "B2", "R"}:
            raise ValueError(f"Unsupported or missing land_use for parcel {parcel_id}: {land_use}")
        land_cfg = build_land_use_config(typology, land_use)

        setbacks = pc.get("setbacks", {}) or {}
        if not setbacks:
            raise ValueError(f"Missing setbacks for parcel {parcel_id} in planning_controls")
        if "building_density_max" not in pc and "site_coverage_max" not in pc:
            raise ValueError(f"Missing building_density_max/site_coverage_max for parcel {parcel_id}")
        if "far_max" not in pc and "far" not in pc:
            raise ValueError(f"Missing far_max/far for parcel {parcel_id}")
        if "height_max" not in pc and "height_limit" not in pc:
            raise ValueError(f"Missing height_max/height_limit for parcel {parcel_id}")

        coverage_max = parcel_area * float(pc.get("building_density_max", pc.get("site_coverage_max")))
        far = float(pc.get("far_max", pc.get("far")))
        required_gfa = parcel_area * far
        height_limit = float(pc.get("height_max", pc.get("height_limit")))

        b_frontages = frontages_by_block.get(block_id, [])
        b_corners = corners_by_block.get(block_id, [])
        b_tiz = tiz_by_block.get(block_id, [])

        side_setback, side_pri, side_edge_type, side_frontage_id = build_edge_setbacks(block_bbox, b_frontages, setbacks)
        bx0, by0, bx1, by1 = block_bbox
        buildable_rect = (bx0 + side_setback["left"], by0 + side_setback["bottom"], bx1 - side_setback["right"], by1 - side_setback["top"])

        if buildable_rect[2] <= buildable_rect[0] + 6.0 or buildable_rect[3] <= buildable_rect[1] + 6.0:
            massing_reports.append({"parcel_id": parcel_id, "status": "infeasible", "reason": "buildable_zone_too_small"})
            continue

        forbidden_rects = []

        for c in b_corners:
            rr = make_corner_reserve(c, block_bbox, {"corner_reservations": corner_cfg})
            if rr is not None:
                forbidden_rects.append(rr)
                reserved_open_spaces.append({
                    "id": f"open_{open_idx:03d}",
                    "open_space_type": "corner_open_space" if c.get("corner_type") == "open_plaza_corner" else "transit_corner_open_space",
                    "parcel_id": parcel_id,
                    "block_id": block_id,
                    "source_corner_id": c.get("id"),
                    "polygon": rect_poly(rr[0], rr[1], rr[2], rr[3]),
                })
                open_idx += 1

        for z in b_tiz:
            zp = z.get("polygon", [])
            if len(zp) >= 4:
                zx0, zy0, zx1, zy1 = poly_bbox(zp)
                cx, cy = (zx0 + zx1) * 0.5, (zy0 + zy1) * 0.5
                node_id = str(z.get("transit_node_id", "")).lower()
                reserve_size = float(
                    transit_cfg["metro_open_space_reserve_m"] if "metro" in node_id else transit_cfg["bus_open_space_reserve_m"]
                )
                half = reserve_size * 0.5
                rr = (
                    max(cx - half, buildable_rect[0]),
                    max(cy - half, buildable_rect[1]),
                    min(cx + half, buildable_rect[2]),
                    min(cy + half, buildable_rect[3]),
                )
                if rect_area(rr) > 0.0:
                    forbidden_rects.append(rr)
                    reserved_open_spaces.append({
                        "id": f"open_{open_idx:03d}",
                        "open_space_type": "transit_forecourt",
                        "parcel_id": parcel_id,
                        "block_id": block_id,
                        "source_transit_node_id": z.get("transit_node_id"),
                        "related_frontage_ids": z.get("associated_frontage_ids", []),
                        "polygon": rect_poly(rr[0], rr[1], rr[2], rr[3]),
                    })
                    open_idx += 1

        bz_id = f"bz_{bz_idx:03d}"; bz_idx += 1
        buildable_zones.append({"id": bz_id, "parcel_id": parcel_id, "block_id": block_id, "polygon": rect_poly(buildable_rect[0], buildable_rect[1], buildable_rect[2], buildable_rect[3])})

        cells = []
        gx = buildable_rect[0]
        while gx + solver_grid <= buildable_rect[2] + 1e-6:
            gy = buildable_rect[1]
            while gy + solver_grid <= buildable_rect[3] + 1e-6:
                cell = (gx, gy, gx + solver_grid, gy + solver_grid)
                status = "available"
                for fr in forbidden_rects:
                    if rect_intersection_area(cell, fr) > 1e-6:
                        status = "reserved_open_space"; break
                cells.append({"cell": rect_poly(cell[0], cell[1], cell[2], cell[3]), "status": status})
                gy += solver_grid
            gx += solver_grid

        solve_grids.append({"id": f"grid_{grid_idx:03d}", "buildable_zone_id": bz_id, "grid_size": solver_grid, "cells": cells})
        grid_idx += 1

        masses_rects, report, mass_extra = generate_mass_layout(
            land_use,
            buildable_rect,
            forbidden_rects,
            land_cfg,
            coverage_max,
            required_gfa,
            height_limit,
            min_spacing,
            edge_clearance,
            side_pri,
            side_edge_type,
            rng,
        )

        entry_side = choose_entry_side(side_edge_type, land_cfg)
        entry_face = mass_face_from_side(entry_side)
        assigned_floors = report.get("assigned_floors", [1] * len(masses_rects))
        floor_h = float(land_cfg["floor_height"])
        bld_type = str(land_cfg["building_type"])

        for i, r in enumerate(masses_rects):
            fx0, fy0, fx1, fy1 = r
            bld_id = f"bld_{bld_idx:03d}"; bld_idx += 1
            levels = int(assigned_floors[i] if i < len(assigned_floors) else assigned_floors[-1])
            levels = max(1, levels)
            height = min(height_limit, round(levels * floor_h, 2))
            comp_map = mass_extra.get("component_polygons_by_index", {}) if isinstance(mass_extra, dict) else {}
            comp_polys = comp_map.get(i)
            forced_h_map = mass_extra.get("forced_height_by_index", {}) if isinstance(mass_extra, dict) else {}
            if i in forced_h_map:
                height = float(forced_h_map[i])
                levels = max(1, int(round(height / max(1e-6, floor_h))))
            b2_role_map = mass_extra.get("b2_role_by_index", {}) if isinstance(mass_extra, dict) else {}
            b2_role = b2_role_map.get(i)

            related_frontages = [fid for side, fid in side_frontage_id.items() if FRONTAGE_PRIORITY.get(side_edge_type.get(side, "back_street"), 1) >= 3 and fid]
            if not related_frontages:
                related_frontages = [fid for fid in side_frontage_id.values() if fid]

            out_bld_type = bld_type
            if land_use == "B2" and b2_role == "podium":
                out_bld_type = "office_podium"
            elif land_use == "B2" and b2_role == "tower":
                out_bld_type = "office_tower"

            bm = {
                "id": bld_id,
                "parcel_id": parcel_id,
                "block_id": block_id,
                "building_type": out_bld_type,
                "land_use": land_use,
                "residential_layout_style": mass_extra.get("residential_style") if land_use == "R" else None,
                "commercial_prototype_mode": mass_extra.get("b1_mode_name") if land_use == "B1" else None,
                "mall_size_class": mass_extra.get("mall_size_class") if land_use == "B1" else None,
                "b2_role": b2_role if land_use == "B2" else None,
                "footprint": rect_poly(fx0, fy0, fx1, fy1),
                "height": height,
                "levels_above_ground": levels,
                "levels_below_ground": 1 if land_use in {"B1", "B2"} else 0,
                "buildable_zone_id": bz_id,
                "related_frontage_ids": related_frontages,
                "entry_preference_faces": [entry_face],
                "mass_index_in_parcel": i + 1,
            }
            if isinstance(comp_polys, list) and comp_polys:
                bm["component_polygons"] = comp_polys
            building_masses.append(bm)

            if land_use == "B1":
                mode_name = str(mass_extra.get("b1_mode_name", ""))
                base_aw = float(land_cfg["atrium_size_xy"][0])
                base_ah = float(land_cfg["atrium_size_xy"][1])
                if mode_name == "mall_bigbox":
                    minw, minh = float(land_cfg["mall_size_min"][1]), float(land_cfg["mall_size_min"][0])
                    maxw, maxh = float(land_cfg["mall_size_max"][1]), float(land_cfg["mall_size_max"][0])
                    norm_w = 0.0 if maxw <= minw else max(0.0, min(1.0, ((fx1 - fx0) - minw) / (maxw - minw)))
                    norm_h = 0.0 if maxh <= minh else max(0.0, min(1.0, ((fy1 - fy0) - minh) / (maxh - minh)))
                    atrium_count = max(1, min(4, 1 + int(round(((norm_w + norm_h) * 0.5) * 3.0))))
                    centers = _mode2_atrium_centers(fx0, fy0, fx1, fy1, atrium_count)
                    aw = min((fx1 - fx0) * 0.22, base_aw)
                    ah = min((fy1 - fy0) * 0.22, base_ah)
                    for acx, acy in centers:
                        atriums.append({
                            "id": f"atrium_{atr_idx:03d}",
                            "building_id": bld_id,
                            "polygon": rect_poly(acx - aw * 0.5, acy - ah * 0.5, acx + aw * 0.5, acy + ah * 0.5),
                            "multi_level": True,
                            "service_radius": 22.0,
                        })
                        atr_idx += 1
                else:
                    # mode1 (courtyard) and mode3 (multi_box): one atrium per mass at mass center.
                    aw = min((fx1 - fx0) * 0.4, base_aw)
                    ah = min((fy1 - fy0) * 0.4, base_ah)
                    acx, acy = (fx0 + fx1) * 0.5, (fy0 + fy1) * 0.5
                    atriums.append({
                        "id": f"atrium_{atr_idx:03d}",
                        "building_id": bld_id,
                        "polygon": rect_poly(acx - aw * 0.5, acy - ah * 0.5, acx + aw * 0.5, acy + ah * 0.5),
                        "multi_level": True,
                        "service_radius": 22.0,
                    })
                    atr_idx += 1

            elif land_use == "B2" and b2_role != "podium":
                core_ratio = float(land_cfg["core_ratio"])
                cw = (fx1 - fx0) * math.sqrt(core_ratio); ch = (fy1 - fy0) * math.sqrt(core_ratio)
                ccx = (fx0 + fx1) * 0.53; ccy = (fy0 + fy1) * 0.53
                cores.append({
                    "id": f"core_{core_idx:03d}",
                    "building_id": bld_id,
                    "polygon": rect_poly(ccx - cw * 0.5, ccy - ch * 0.5, ccx + cw * 0.5, ccy + ch * 0.5),
                    "core_type": "office_core",
                    "influence_radius": 18.0,
                })
                core_idx += 1

            else:
                pass

        if land_use == "R":
            res_style = str(mass_extra.get("residential_style", "point"))
            frontage_mode = int(mass_extra.get("podium_frontage_mode", 1))
            podium_depth = float(mass_extra.get("podium_depth", land_cfg["podium_depth"]))
            podium_floors = int(mass_extra.get("podium_floors", 2))
            podium_height = float(mass_extra.get("podium_height", podium_floors * 4.0))
            bands = mass_extra.get("podium_bands", []) or []
            res_mass_index = len(masses_rects)
            band_polys = [b.get("polygon") for b in bands if isinstance(b.get("polygon"), list)]
            clusters = cluster_connected_polygons(band_polys)
            for cluster in clusters:
                if not cluster:
                    continue
                res_mass_index += 1
                podium_bld_id = f"bld_{bld_idx:03d}"; bld_idx += 1
                frontage_set = set()
                face_set = set()
                for band in bands:
                    poly = band.get("polygon")
                    if poly in cluster:
                        side = str(band.get("side", ""))
                        if side:
                            face_set.add(mass_face_from_side(side))
                            fid = side_frontage_id.get(side, "")
                            if fid:
                                frontage_set.add(fid)
                building_masses.append({
                    "id": podium_bld_id,
                    "parcel_id": parcel_id,
                    "block_id": block_id,
                    "building_type": "residential_podium",
                    "land_use": "R",
                    "residential_layout_style": res_style,
                    "is_podium_mass": True,
                    "footprint": cluster[0],
                    "component_polygons": cluster,
                    "height": round(podium_height, 2),
                    "levels_above_ground": podium_floors,
                    "levels_below_ground": 0,
                    "buildable_zone_id": bz_id,
                    "related_frontage_ids": sorted(frontage_set),
                    "entry_preference_faces": sorted(face_set),
                    "mass_index_in_parcel": res_mass_index,
                })
                for poly in cluster:
                    continuous = rng.random() < float(land_cfg["podium_random_continuous_prob"])
                    podium_retail_bands.append({
                        "id": f"prb_{pod_idx:03d}",
                        "building_id": podium_bld_id,
                        "polygon": poly,
                        "shop_unit_depth": round(podium_depth, 2),
                        "continuous": continuous,
                        "levels": podium_floors,
                        "layout_style": res_style,
                        "frontage_mode": frontage_mode,
                    })
                    pod_idx += 1

        massing_reports.append({
            "parcel_id": parcel_id,
            "block_id": block_id,
            "land_use": land_use,
            "status": report.get("status", "ok"),
            "warnings": report.get("warnings", []),
            "required_gfa": report.get("required_gfa"),
            "estimated_gfa": report.get("estimated_gfa"),
            "coverage_max": report.get("coverage_max"),
            "total_footprint": report.get("total_footprint"),
            "mass_count": len(masses_rects) + (len(cluster_connected_polygons([b.get("polygon") for b in (mass_extra.get("podium_bands", []) or []) if isinstance(b.get("polygon"), list)])) if land_use == "R" else 0),
            "min_spacing": min_spacing,
            "height_limit": height_limit,
            "layout_style": mass_extra.get("residential_style") if land_use == "R" else None,
            "podium_frontage_mode": mass_extra.get("podium_frontage_mode") if land_use == "R" else None,
            "commercial_prototype_mode": mass_extra.get("b1_mode_name") if land_use == "B1" else None,
            "office_generation_mode": mass_extra.get("b2_mode_name") if land_use == "B2" else None,
        })

    for bm in building_masses:
        if "land_use" not in bm or not bm.get("land_use"):
            raise ValueError(f"Generated building missing land_use: {bm.get('id', '<unknown>')}")

    return {
        "buildable_zones": buildable_zones,
        "solve_grids": solve_grids,
        "building_masses": building_masses,
        "atriums": atriums,
        "cores": cores,
        "podium_retail_bands": podium_retail_bands,
        "reserved_open_spaces": reserved_open_spaces,
        "massing_reports": massing_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Step2 Building Mass Generator")
    parser.add_argument("--input", default="step1_generated_scene.json", help="step1 json")
    parser.add_argument("--output", default="step2_generated_scene.json", help="step2 output json")
    parser.add_argument("--typology", default="default_building.yaml", help="typology defaults yaml")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    typology_path = Path(args.typology)

    if not in_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {in_path}")

    print(f"[Load] scene: {in_path}")
    with in_path.open("r", encoding="utf-8") as f:
        scene = json.load(f)

    print(f"[Load] typology: {typology_path}")
    typology = load_typology(typology_path)

    generated = scene.get("generated", {}) or {}
    if "step_1_network" not in generated:
        raise ValueError("generated.step_1_network not found")

    generated["step_2_massing"] = generate_step2(scene, typology)
    scene["generated"] = generated

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(_format_json_compact(scene) + "\n")

    s2 = generated["step_2_massing"]
    infeasible = [r for r in s2.get("massing_reports", []) if r.get("status") != "ok"]
    print("[Summary]")
    print(f"  buildable_zones: {len(s2.get('buildable_zones', []))}")
    print(f"  solve_grids: {len(s2.get('solve_grids', []))}")
    print(f"  building_masses: {len(s2.get('building_masses', []))}")
    print(f"  atriums: {len(s2.get('atriums', []))}")
    print(f"  cores: {len(s2.get('cores', []))}")
    print(f"  podium_retail_bands: {len(s2.get('podium_retail_bands', []))}")
    print(f"  reserved_open_spaces: {len(s2.get('reserved_open_spaces', []))}")
    print(f"  infeasible_parcels: {len(infeasible)}")
    print(f"[Done] wrote: {out_path}")


if __name__ == "__main__":
    main()
