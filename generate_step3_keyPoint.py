import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

FRONTAGE_MAP = {
    "primary_frontage": "main_street",
    "secondary_frontage": "secondary_street",
    "back_frontage": "back_street",
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
        raise ValueError("YAML root must be mapping")

    required = [
        "global.random_seed",
        "global.near_distance_m",
        "global.transit_influence_distance_m",
        "global.corner_influence_distance_m",
        "global.anchor_influence_distance_m",
        "global.duplicate_merge_distance_m",
        "dimensions.transit_nodes.bus_boarding_rect_m",
        "dimensions.transit_nodes.metro_access_rect_m",
        "dimensions.entrance.min_clear_door_width_m",
        "dimensions.entrance.min_access_route_width_m",
        "dimensions.entrance.threshold_turning_diameter_m",
        "dimensions.internal_nodes.atrium_public_attract_radius_m",
        "dimensions.internal_nodes.core_influence_radius_m",
        "dimensions.service_nodes.pickup_node_rect_m",
        "dimensions.service_nodes.parcel_locker_rect_m",
        "dimensions.service_nodes.frontdesk_rect_m",
        "dimensions.service_nodes.waiting_node_rect_m",
        "dimensions.service_nodes.loading_point_rect_m",
        "entrance_generation.mall.min_candidates_per_mass",
        "entrance_generation.mall.max_candidates_per_mass",
        "entrance_generation.office.min_candidates_per_mass",
        "entrance_generation.residential.min_candidates_per_mass",
        "weights.frontage_level.main_street",
        "weights.corner_value.transit_corner",
        "weights.score_components.frontage_level",
        "service_generation.mall.create_types",
        "service_generation.office.create_types",
        "service_generation.residential.create_types",
    ]
    for p in required:
        require_key(raw, p)
    return raw


def clean_ring(poly: Sequence[Sequence[float]]) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for p in poly or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            q = (float(p[0]), float(p[1]))
            if not pts or q != pts[-1]:
                pts.append(q)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def poly_bbox(poly: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    pts = clean_ring(poly)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def poly_center(poly: Sequence[Sequence[float]]) -> Tuple[float, float]:
    x0, y0, x1, y1 = poly_bbox(poly)
    return ((x0 + x1) * 0.5, (y0 + y1) * 0.5)


def point_in_polygon(pt: Tuple[float, float], poly: Sequence[Sequence[float]]) -> bool:
    pts = clean_ring(poly)
    if len(pts) < 3:
        return False
    x, y = pt
    inside = False
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        cross = (y1 > y) != (y2 > y)
        if cross:
            xin = (x2 - x1) * (y - y1) / ((y2 - y1) if abs(y2 - y1) > 1e-9 else 1e-9) + x1
            if x < xin:
                inside = not inside
    return inside


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def frontage_side(frontage_polyline: Sequence[Sequence[float]], bbox: Tuple[float, float, float, float]) -> str:
    if len(frontage_polyline) < 2:
        return "bottom"
    x0, y0 = float(frontage_polyline[0][0]), float(frontage_polyline[0][1])
    x1, y1 = float(frontage_polyline[1][0]), float(frontage_polyline[1][1])
    bx0, by0, bx1, by1 = bbox
    mx = (x0 + x1) * 0.5
    my = (y0 + y1) * 0.5
    if abs(x0 - x1) < abs(y0 - y1):
        return "left" if abs(mx - bx0) <= abs(mx - bx1) else "right"
    return "bottom" if abs(my - by0) <= abs(my - by1) else "top"


def side_midpoint(side: str, bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    x0, y0, x1, y1 = bbox
    if side == "left":
        return (x0, (y0 + y1) * 0.5)
    if side == "right":
        return (x1, (y0 + y1) * 0.5)
    if side == "bottom":
        return ((x0 + x1) * 0.5, y0)
    return ((x0 + x1) * 0.5, y1)


def side_quarter_points(side: str, bbox: Tuple[float, float, float, float]) -> List[Tuple[float, float]]:
    x0, y0, x1, y1 = bbox
    if side in {"left", "right"}:
        x = x0 if side == "left" else x1
        return [(x, y0 + (y1 - y0) * 0.25), (x, y0 + (y1 - y0) * 0.75)]
    y = y0 if side == "bottom" else y1
    return [(x0 + (x1 - x0) * 0.25, y), (x0 + (x1 - x0) * 0.75, y)]


def edge_lengths(bbox: Tuple[float, float, float, float]) -> Dict[str, float]:
    x0, y0, x1, y1 = bbox
    return {"left": y1 - y0, "right": y1 - y0, "bottom": x1 - x0, "top": x1 - x0}


def nearest_corner_value(pt: Tuple[float, float], block_corners: List[dict], corner_weights: Dict[str, float], dmax: float) -> float:
    best = 0.0
    for c in block_corners:
        pos = c.get("position")
        if not isinstance(pos, list) or len(pos) < 2:
            continue
        d = dist(pt, (float(pos[0]), float(pos[1])))
        if d > dmax:
            continue
        cv = float(corner_weights.get(str(c.get("corner_type", "normal_corner")), 0.0))
        score = cv * max(0.0, 1.0 - d / max(1e-6, dmax))
        if score > best:
            best = score
    return round(best, 4)


def transit_proximity_score(pt: Tuple[float, float], transit_pts: List[Tuple[str, Tuple[float, float]]], dmax: float) -> float:
    best = 0.0
    for _, tp in transit_pts:
        d = dist(pt, tp)
        if d <= dmax:
            best = max(best, 1.0 - d / max(1e-6, dmax))
    return round(best, 4)


def threshold_score(pt: Tuple[float, float], open_spaces: List[dict], dmax: float) -> float:
    best = 0.0
    for o in open_spaces:
        poly = o.get("polygon")
        if not isinstance(poly, list) or len(poly) < 3:
            continue
        c = poly_center(poly)
        d = dist(pt, c)
        if d <= dmax:
            best = max(best, 1.0 - d / max(1e-6, dmax))
    return round(best, 4)


def anchor_score(pt: Tuple[float, float], anchors: List[Tuple[float, float]], dmax: float) -> float:
    if not anchors:
        return 0.0
    best = 0.0
    for a in anchors:
        d = dist(pt, a)
        if d <= dmax:
            best = max(best, 1.0 - d / max(1e-6, dmax))
    return round(best, 4)


def merge_points(pts: List[Tuple[float, float]], dmin: float) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for p in pts:
        if not any(dist(p, q) < dmin for q in out):
            out.append(p)
    return out


def side_rank(side: str, side_edge: Dict[str, str], frontage_weights: Dict[str, float]) -> float:
    return float(frontage_weights.get(side_edge.get(side, "back_street"), 0.0))


def choose_service_back_side(side_edge: Dict[str, str]) -> str:
    sides = list(side_edge.keys())
    for s in sides:
        if side_edge.get(s) == "back_street":
            return s
    return sides[0] if sides else "top"


def offset_point_by_side(pt: Tuple[float, float], side: str, off: float) -> Tuple[float, float]:
    if side == "left":
        return (pt[0] + off, pt[1])
    if side == "right":
        return (pt[0] - off, pt[1])
    if side == "bottom":
        return (pt[0], pt[1] + off)
    return (pt[0], pt[1] - off)


def generate_step3(scene: Dict[str, Any], typology: Dict[str, Any]) -> Dict[str, Any]:
    generated = scene.get("generated", {}) or {}
    step1 = generated.get("step_1_network", {}) or {}
    step2 = generated.get("step_2_massing", {}) or {}
    inputs = scene.get("inputs", {}) or {}

    roads = inputs.get("roads", []) or []
    transit_nodes_input = inputs.get("transit_nodes", []) or []
    frontages = step1.get("frontage_segments", []) or []
    corners = step1.get("corners", []) or []
    tiz = step1.get("transit_influence_zones", []) or []
    buildings = step2.get("building_masses", []) or []
    atriums = step2.get("atriums", []) or []
    cores = step2.get("cores", []) or []
    podium_bands = step2.get("podium_retail_bands", []) or []
    open_spaces = step2.get("reserved_open_spaces", []) or []

    g = typology["global"]
    dims = typology["dimensions"]
    weights = typology["weights"]
    e_cfg = typology["entrance_generation"]
    s_cfg = typology["service_generation"]
    rng = random.Random(int(g["random_seed"]))

    frontage_w = weights["frontage_level"]
    corner_w = weights["corner_value"]
    score_w = weights["score_components"]

    frontages_by_block: Dict[str, List[dict]] = {}
    frontages_by_id: Dict[str, dict] = {}
    for f in frontages:
        bid = str(f.get("block_id", ""))
        if bid:
            frontages_by_block.setdefault(bid, []).append(f)
        fid = str(f.get("id", ""))
        if fid:
            frontages_by_id[fid] = f

    corners_by_block: Dict[str, List[dict]] = {}
    for c in corners:
        bid = str(c.get("block_id", ""))
        if bid:
            corners_by_block.setdefault(bid, []).append(c)

    transit_points: List[Tuple[str, Tuple[float, float]]] = []
    road_by_id = {str(r.get("id", "")): r for r in roads}
    for t in transit_nodes_input:
        pos = t.get("position")
        if isinstance(pos, list) and len(pos) >= 2:
            transit_points.append((str(t.get("id", "")), (float(pos[0]), float(pos[1]))))

    atrium_centers: Dict[str, List[Tuple[float, float]]] = {}
    for a in atriums:
        bid = str(a.get("building_id", ""))
        if bid:
            atrium_centers.setdefault(bid, []).append(poly_center(a.get("polygon", [])))

    core_centers: Dict[str, List[Tuple[float, float]]] = {}
    for c in cores:
        bid = str(c.get("building_id", ""))
        if bid:
            core_centers.setdefault(bid, []).append(poly_center(c.get("polygon", [])))

    podium_by_building: Dict[str, List[dict]] = {}
    for p in podium_bands:
        bid = str(p.get("building_id", ""))
        if bid:
            podium_by_building.setdefault(bid, []).append(p)

    key_nodes: List[dict] = []
    entrance_candidates: List[dict] = []
    service_nodes: List[dict] = []

    node_idx = 1
    ent_idx = 1
    srv_idx = 1

    # 3.2.1 Transit anchor nodes.
    for t in transit_nodes_input:
        tid = str(t.get("id", ""))
        ttype = str(t.get("type", "bus")).lower()
        pos = t.get("position", [])
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        if "metro" in ttype:
            ntype = "metro_access"
            sz = dims["transit_nodes"]["metro_access_rect_m"]
        else:
            ntype = "bus_access"
            sz = dims["transit_nodes"]["bus_boarding_rect_m"]
        key_nodes.append({
            "id": f"node_{node_idx:03d}",
            "node_type": ntype,
            "position": [round(float(pos[0]), 4), round(float(pos[1]), 4)],
            "related_transit_node_id": tid,
            "node_size_m": [float(sz[0]), float(sz[1])],
        })
        node_idx += 1

    # 3.2.3 Internal key nodes.
    for a in atriums:
        c = poly_center(a.get("polygon", []))
        key_nodes.append({
            "id": f"node_{node_idx:03d}",
            "node_type": "atrium_center",
            "position": [round(c[0], 4), round(c[1], 4)],
            "related_atrium_id": str(a.get("id", "")),
            "service_radius": float(a.get("service_radius", dims["internal_nodes"]["atrium_public_attract_radius_m"])),
            "public_attract_radius": float(dims["internal_nodes"]["atrium_public_attract_radius_m"]),
        })
        node_idx += 1

    for c0 in cores:
        c = poly_center(c0.get("polygon", []))
        key_nodes.append({
            "id": f"node_{node_idx:03d}",
            "node_type": "core_center",
            "position": [round(c[0], 4), round(c[1], 4)],
            "related_core_id": str(c0.get("id", "")),
            "influence_radius": float(c0.get("influence_radius", dims["internal_nodes"]["core_influence_radius_m"])),
        })
        node_idx += 1

    for o in open_spaces:
        c = poly_center(o.get("polygon", []))
        key_nodes.append({
            "id": f"node_{node_idx:03d}",
            "node_type": "plaza_center",
            "position": [round(c[0], 4), round(c[1], 4)],
            "related_open_space_id": str(o.get("id", "")),
        })
        node_idx += 1

    # 3.2.2 Candidate entrances + 3.2.5 pre-scoring.
    building_to_candidates: Dict[str, List[dict]] = {}
    for b in buildings:
        bid = str(b.get("id", ""))
        btype = str(b.get("building_type", ""))
        land_use = str(b.get("land_use", ""))
        poly = b.get("footprint", [])
        if not isinstance(poly, list) or len(poly) < 4:
            continue

        bbox = poly_bbox(poly)
        block_id = str(b.get("block_id", ""))
        b_frontages = frontages_by_block.get(block_id, [])
        side_edge: Dict[str, str] = {}
        side_frontage_id: Dict[str, str] = {}
        for f in b_frontages:
            s = frontage_side(f.get("polyline", []), bbox)
            side_edge[s] = FRONTAGE_MAP.get(str(f.get("frontage_type", "back_frontage")), "back_street")
            side_frontage_id[s] = str(f.get("id", ""))
        for s in ["left", "right", "bottom", "top"]:
            side_edge.setdefault(s, "back_street")
            side_frontage_id.setdefault(s, "")

        sorted_sides = sorted(["left", "right", "bottom", "top"], key=lambda x: side_rank(x, side_edge, frontage_w), reverse=True)
        longest_side = max(edge_lengths(bbox).items(), key=lambda kv: kv[1])[0]

        pts: List[Tuple[float, float]] = []
        if land_use == "B1" or btype == "mall":
            ec = e_cfg["mall"]
            # Prioritize high frontage side corners + transit/open adjacency.
            pts.extend(side_quarter_points(sorted_sides[0], bbox))
            pts.append(side_midpoint(sorted_sides[0], bbox))
            if len(sorted_sides) > 1:
                pts.append(side_midpoint(sorted_sides[1], bbox))
            pts.extend(side_quarter_points(longest_side, bbox))
            pts = merge_points(pts, float(g["duplicate_merge_distance_m"]))
            min_cnt = int(ec["min_candidates_per_mass"])
            max_cnt = int(ec["max_candidates_per_mass"])
            if len(pts) < min_cnt:
                pts.extend(side_quarter_points(sorted_sides[0], bbox))
                pts = merge_points(pts, float(g["duplicate_merge_distance_m"]))
            pts = pts[:max_cnt]
        elif land_use == "B2" or "office" in btype:
            ec = e_cfg["office"]
            pts.append(side_midpoint(sorted_sides[0], bbox))
            if len(sorted_sides) > 1:
                pts.append(side_midpoint(sorted_sides[1], bbox))
            # Bias toward nearest core.
            ac = core_centers.get(bid, [])
            if ac:
                c = ac[0]
                mids = [side_midpoint(s, bbox) for s in ["left", "right", "bottom", "top"]]
                mids.sort(key=lambda p: dist(p, c))
                pts.insert(1, mids[0])
            pts = merge_points(pts, float(g["duplicate_merge_distance_m"]))
            pts = pts[: int(ec["max_candidates_per_mass"])]
        else:
            ec = e_cfg["residential"]
            pts.append(side_midpoint(sorted_sides[0], bbox))
            if len(sorted_sides) > 1:
                pts.append(side_midpoint(sorted_sides[1], bbox))
            # Keep one candidate away from podium bands if available.
            pod = podium_by_building.get(bid, [])
            if pod:
                pc = poly_center(pod[0].get("polygon", []))
                mids = [side_midpoint(s, bbox) for s in ["left", "right", "bottom", "top"]]
                mids.sort(key=lambda p: dist(p, pc), reverse=True)
                pts.append(mids[0])
            else:
                pts.append(side_midpoint(sorted_sides[-1], bbox))
            pts = merge_points(pts, float(g["duplicate_merge_distance_m"]))
            pts = pts[: int(ec["max_candidates_per_mass"])]

        anchors: List[Tuple[float, float]] = []
        if land_use == "B1":
            anchors = atrium_centers.get(bid, [])
        elif land_use == "B2":
            anchors = core_centers.get(bid, [])
        else:
            anchors = [poly_center(p.get("polygon", [])) for p in podium_by_building.get(bid, [])]

        b_candidates: List[dict] = []
        for i, p in enumerate(pts):
            nearest_side = min(["left", "right", "bottom", "top"], key=lambda s: dist(p, side_midpoint(s, bbox)))
            frontage_id = side_frontage_id.get(nearest_side, "")
            edge_type = side_edge.get(nearest_side, "back_street")
            road_priority = float(frontage_w.get(edge_type, 0.0))
            sc_frontage = road_priority
            sc_transit = transit_proximity_score(p, transit_points, float(g["transit_influence_distance_m"]))
            sc_corner = nearest_corner_value(p, corners_by_block.get(block_id, []), corner_w, float(g["corner_influence_distance_m"]))
            sc_anchor = anchor_score(p, anchors, float(g["anchor_influence_distance_m"]))
            sc_threshold = threshold_score(p, open_spaces, float(g["near_distance_m"]))
            score = (
                float(score_w["frontage_level"]) * sc_frontage
                + float(score_w["transit_proximity"]) * sc_transit
                + float(score_w["corner_value"]) * sc_corner
                + float(score_w["anchor_proximity"]) * sc_anchor
                + float(score_w["threshold_potential"]) * sc_threshold
            )
            if land_use == "B1":
                ctype = "main" if i == 0 else ("secondary" if i < 3 else "service")
            elif land_use == "B2":
                ctype = "main" if i == 0 else "secondary"
            else:
                ctype = "main" if i == 0 else "secondary"
            item = {
                "id": f"entrance_candidate_{ent_idx:03d}",
                "building_id": bid,
                "building_type": btype,
                "land_use": land_use,
                "position": [round(p[0], 4), round(p[1], 4)],
                "served_frontage_id": frontage_id,
                "candidate_type": ctype,
                "score": round(score, 4),
                "score_breakdown": {
                    "frontage_level": round(sc_frontage, 4),
                    "transit_proximity": round(sc_transit, 4),
                    "corner_value": round(sc_corner, 4),
                    "anchor_proximity": round(sc_anchor, 4),
                    "threshold_potential": round(sc_threshold, 4),
                },
                "min_clear_door_width_m": float(dims["entrance"]["min_clear_door_width_m"]),
                "min_access_route_width_m": float(dims["entrance"]["min_access_route_width_m"]),
                "threshold_turning_diameter_m": float(dims["entrance"]["threshold_turning_diameter_m"]),
            }
            entrance_candidates.append(item)
            b_candidates.append(item)
            ent_idx += 1
        b_candidates.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        building_to_candidates[bid] = b_candidates

    # 3.2.4 Service nodes.
    service_size_map = {
        "pickup_node": dims["service_nodes"]["pickup_node_rect_m"],
        "delivery_node": dims["service_nodes"]["pickup_node_rect_m"],
        "parcel_locker": dims["service_nodes"]["parcel_locker_rect_m"],
        "property_frontdesk": dims["service_nodes"]["frontdesk_rect_m"],
        "frontdesk": dims["service_nodes"]["frontdesk_rect_m"],
        "waiting_node": dims["service_nodes"]["waiting_node_rect_m"],
        "loading_point": dims["service_nodes"]["loading_point_rect_m"],
    }

    for b in buildings:
        bid = str(b.get("id", ""))
        land_use = str(b.get("land_use", ""))
        btype = str(b.get("building_type", ""))
        poly = b.get("footprint", [])
        if not (isinstance(poly, list) and len(poly) >= 4):
            continue
        bbox = poly_bbox(poly)
        side_edge: Dict[str, str] = {}
        block_id = str(b.get("block_id", ""))
        for f in frontages_by_block.get(block_id, []):
            s = frontage_side(f.get("polyline", []), bbox)
            side_edge[s] = FRONTAGE_MAP.get(str(f.get("frontage_type", "back_frontage")), "back_street")
        for s in ["left", "right", "bottom", "top"]:
            side_edge.setdefault(s, "back_street")

        if land_use == "B1":
            service_types = list(s_cfg["mall"]["create_types"])
        elif land_use == "B2":
            service_types = list(s_cfg["office"]["create_types"])
        else:
            service_types = list(s_cfg["residential"]["create_types"])

        cands = building_to_candidates.get(bid, [])
        main_pos = tuple(cands[0]["position"]) if cands else side_midpoint("bottom", bbox)
        sec_pos = tuple(cands[1]["position"]) if len(cands) > 1 else side_midpoint("right", bbox)
        back_side = choose_service_back_side(side_edge)
        back_pos = side_midpoint(back_side, bbox)

        for st in service_types:
            if st in {"pickup_node", "parcel_locker", "property_frontdesk", "frontdesk"}:
                pos = main_pos
                if st in {"parcel_locker"}:
                    pos = sec_pos
            elif st in {"waiting_node"}:
                pos = sec_pos
            else:
                pos = back_pos
            # Small offset to avoid exact overlap.
            pos = offset_point_by_side((float(pos[0]), float(pos[1])), back_side, 1.2 if st == "loading_point" else 0.6)
            sn = {
                "id": f"service_{srv_idx:03d}",
                "service_type": st,
                "position": [round(pos[0], 4), round(pos[1], 4)],
                "building_id": bid,
                "priority": "high" if st in {"pickup_node", "property_frontdesk", "frontdesk"} else ("medium" if st in {"parcel_locker", "waiting_node"} else "low"),
                "node_size_m": [float(service_size_map[st][0]), float(service_size_map[st][1])],
            }
            # For compatibility with previous schema naming.
            if st == "frontdesk":
                sn["service_type"] = "property_frontdesk"
            service_nodes.append(sn)
            srv_idx += 1

    entrance_candidates.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)

    return {
        "key_nodes": key_nodes,
        "entrance_candidates": entrance_candidates,
        "service_nodes": service_nodes,
        "metadata": {
            "generator": "generate_step3_keyPoint.py",
            "input_scene_has_step1": "step_1_network" in generated,
            "input_scene_has_step2": "step_2_massing" in generated,
            "transit_node_count": len(transit_nodes_input),
            "building_count": len(buildings),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Step3 Key Point Generator")
    parser.add_argument("--input", default="step2_generated_scene.json", help="Input scene with step_2_massing")
    parser.add_argument("--output", default="step3_generated_scene.json", help="Output scene with step_3_key_nodes")
    parser.add_argument("--typology", default="default_keyPoint.yaml", help="Typology yaml for key points")
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
    if "step_1_network" not in generated or "step_2_massing" not in generated:
        raise ValueError("Input scene must contain generated.step_1_network and generated.step_2_massing")

    generated["step_3_key_nodes"] = generate_step3(scene, typology)
    scene["generated"] = generated

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(_format_json_compact(scene) + "\n")

    s3 = generated["step_3_key_nodes"]
    print("[Summary]")
    print(f"  key_nodes: {len(s3.get('key_nodes', []))}")
    print(f"  entrance_candidates: {len(s3.get('entrance_candidates', []))}")
    print(f"  service_nodes: {len(s3.get('service_nodes', []))}")
    print(f"[Done] wrote: {out_path}")


if __name__ == "__main__":
    main()
