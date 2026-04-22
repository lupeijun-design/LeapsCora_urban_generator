import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


CLASS_PRIORITY = {
    "expressway": 6,
    "primary": 5,
    "secondary": 4,
    "tree-lined avenue": 3,
    "local": 2,
    "internal road": 1,
    "internal road(residential school)": 1,
}

ALIASES = {
    "internal road(residential school)": "internal road",
}


def _is_primitive(v) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def _format_json_compact(v, indent: int = 0) -> str:
    sp = " " * indent
    def _inline_list(lst):
        return "[ " + ", ".join(_format_json_compact(x, 0) for x in lst) + " ]"

    if isinstance(v, dict):
        if not v:
            return "{}"
        items = list(v.items())
        lines = ["{"]
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


@dataclass
class Road:
    id: str
    name: str
    road_class: str
    width: float
    p0: Tuple[float, float]
    p1: Tuple[float, float]
    orientation: str


@dataclass
class Frontage:
    id: str
    block_id: str
    polyline: List[List[float]]
    adjacent_road_id: str
    road_class: str
    frontage_type: str
    orientation: float
    length: float
    transit_influenced: bool
    served_transit_node_ids: List[str]


def normalize_class(name: str) -> str:
    n = (name or "").strip()
    return ALIASES.get(n, n)


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("settings yaml is not a mapping")
    return data


def parse_roads(inputs: dict, settings: dict) -> Tuple[List[Road], List[Road]]:
    width_map = settings.get("default_road_width_by_class", {}) or {}
    roads = []
    for r in inputs.get("roads", []) or []:
        rid = r.get("id")
        cl = normalize_class(str(r.get("road_class", "local")))
        centerline = r.get("centerline") or []
        if not rid or len(centerline) < 2:
            continue
        p0 = (float(centerline[0][0]), float(centerline[0][1]))
        p1 = (float(centerline[-1][0]), float(centerline[-1][1]))
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        if abs(dx) >= abs(dy):
            orientation = "horizontal"
        else:
            orientation = "vertical"

        custom = r.get("custom_width")
        if custom is None:
            width = float(width_map.get(cl, 8.0))
        else:
            width = float(custom)

        roads.append(Road(
            id=rid,
            name=str(r.get("name", rid)),
            road_class=cl,
            width=width,
            p0=p0,
            p1=p1,
            orientation=orientation,
        ))

    v = sorted([r for r in roads if r.orientation == "vertical"], key=lambda x: (x.p0[0] + x.p1[0]) * 0.5)
    h = sorted([r for r in roads if r.orientation == "horizontal"], key=lambda x: (x.p0[1] + x.p1[1]) * 0.5)
    if len(v) < 2 or len(h) < 2:
        raise ValueError("Need at least 2 vertical and 2 horizontal roads for block generation")
    return v, h


def seg_distance_point(px: float, py: float, a: Tuple[float, float], b: Tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    denom = abx * abx + aby * aby
    if denom <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
    qx = ax + t * abx
    qy = ay + t * aby
    return math.hypot(px - qx, py - qy)


def build_radius_lookup(settings: dict):
    block = settings.get("default_corner_radius_by_pair", {}) or {}
    labels = [normalize_class(str(x)) for x in (block.get("labels") or [])]
    values = block.get("values") or []
    table: Dict[Tuple[str, str], float] = {}
    for i, row in enumerate(values):
        if i >= len(labels):
            continue
        for j, val in enumerate(row):
            if j >= len(labels):
                continue
            table[(labels[i], labels[j])] = float(val)
            table[(labels[j], labels[i])] = float(val)

    def lookup(a: str, b: str) -> float:
        aa = normalize_class(a)
        bb = normalize_class(b)
        if (aa, bb) in table:
            return table[(aa, bb)]
        pa = CLASS_PRIORITY.get(aa, 2)
        pb = CLASS_PRIORITY.get(bb, 2)
        return 5.0 + 1.5 * max(pa, pb)

    return lookup


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _polygon_area(poly: List[List[float]]) -> float:
    if len(poly) < 4:
        return 0.0
    area = 0.0
    for i in range(len(poly) - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _rounded_rect_polygon(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    r_bl: float,
    r_br: float,
    r_tr: float,
    r_tl: float,
    arc_segments: int = 4,
) -> List[List[float]]:
    w = max(1e-6, x_max - x_min)
    h = max(1e-6, y_max - y_min)

    r_bl = _clamp(r_bl, 0.0, min(w * 0.5, h * 0.5))
    r_br = _clamp(r_br, 0.0, min(w * 0.5, h * 0.5))
    r_tr = _clamp(r_tr, 0.0, min(w * 0.5, h * 0.5))
    r_tl = _clamp(r_tl, 0.0, min(w * 0.5, h * 0.5))

    if r_bl + r_br > w:
        s = w / (r_bl + r_br)
        r_bl *= s
        r_br *= s
    if r_tl + r_tr > w:
        s = w / (r_tl + r_tr)
        r_tl *= s
        r_tr *= s
    if r_bl + r_tl > h:
        s = h / (r_bl + r_tl)
        r_bl *= s
        r_tl *= s
    if r_br + r_tr > h:
        s = h / (r_br + r_tr)
        r_br *= s
        r_tr *= s

    def arc(cx: float, cy: float, r: float, a0: float, a1: float) -> List[List[float]]:
        if r <= 1e-6:
            return []
        pts: List[List[float]] = []
        for i in range(1, arc_segments + 1):
            t = i / arc_segments
            a = a0 + (a1 - a0) * t
            pts.append([cx + r * math.cos(a), cy + r * math.sin(a)])
        return pts

    pts: List[List[float]] = []
    pts.append([x_min + r_bl, y_min])
    pts.append([x_max - r_br, y_min])
    pts.extend(arc(x_max - r_br, y_min + r_br, r_br, -math.pi * 0.5, 0.0))
    pts.append([x_max, y_max - r_tr])
    pts.extend(arc(x_max - r_tr, y_max - r_tr, r_tr, 0.0, math.pi * 0.5))
    pts.append([x_min + r_tl, y_max])
    pts.extend(arc(x_min + r_tl, y_max - r_tl, r_tl, math.pi * 0.5, math.pi))
    pts.append([x_min, y_min + r_bl])
    pts.extend(arc(x_min + r_bl, y_min + r_bl, r_bl, math.pi, math.pi * 1.5))

    out: List[List[float]] = []
    for p in pts:
        if not out or (abs(out[-1][0] - p[0]) > 1e-9 or abs(out[-1][1] - p[1]) > 1e-9):
            out.append([round(p[0], 4), round(p[1], 4)])
    if out and (out[0][0] != out[-1][0] or out[0][1] != out[-1][1]):
        out.append(out[0])
    return out


def _make_transit_zone_for_frontage(
    frontage: Frontage,
    node_pos: Tuple[float, float],
    block_rect: Tuple[float, float, float, float],
    zone_width: float = 5.0,
    zone_length: float = 20.0,
) -> List[List[float]]:
    p0 = (float(frontage.polyline[0][0]), float(frontage.polyline[0][1]))
    p1 = (float(frontage.polyline[1][0]), float(frontage.polyline[1][1]))
    vx = p1[0] - p0[0]
    vy = p1[1] - p0[1]
    seg_len = math.hypot(vx, vy)
    if seg_len < 1e-6:
        return []
    ux, uy = vx / seg_len, vy / seg_len

    apx = node_pos[0] - p0[0]
    apy = node_pos[1] - p0[1]
    t = _clamp((apx * ux + apy * uy), 0.0, seg_len)
    half = zone_length * 0.5
    t0 = _clamp(t - half, 0.0, seg_len)
    t1 = _clamp(t + half, 0.0, seg_len)
    if t1 - t0 < 1e-3:
        return []

    ax = p0[0] + ux * t0
    ay = p0[1] + uy * t0
    bx = p0[0] + ux * t1
    by = p0[1] + uy * t1

    x_min, y_min, x_max, y_max = block_rect
    cx = (x_min + x_max) * 0.5
    cy = (y_min + y_max) * 0.5
    px = p0[0] + ux * t
    py = p0[1] + uy * t

    n1 = (-uy, ux)
    n2 = (uy, -ux)
    d1 = (cx - px) * n1[0] + (cy - py) * n1[1]
    d2 = (cx - px) * n2[0] + (cy - py) * n2[1]
    nx, ny = n1 if d1 >= d2 else n2

    dx = nx * zone_width
    dy = ny * zone_width

    poly = [
        [ax, ay],
        [bx, by],
        [bx + dx, by + dy],
        [ax + dx, ay + dy],
    ]

    clipped = []
    for x, y in poly:
        clipped.append([
            round(_clamp(x, x_min, x_max), 4),
            round(_clamp(y, y_min, y_max), 4),
        ])
    clipped.append(clipped[0])
    if _polygon_area(clipped) < 1e-3:
        return []
    return clipped


def generate_step1(data: dict, settings: dict) -> dict:
    inputs = data.get("inputs", {}) or {}
    transit_nodes = inputs.get("transit_nodes", []) or []
    v_roads, h_roads = parse_roads(inputs, settings)

    influence_w = 5.0
    influence_len = 20.0
    radius_lookup = build_radius_lookup(settings)

    blocks = []
    frontages: List[Frontage] = []
    corners = []
    tiz = []
    tiz_count = 1
    block_rects: Dict[str, Tuple[float, float, float, float]] = {}
    node_pos_map: Dict[str, Tuple[float, float]] = {}
    node_type_map: Dict[str, str] = {}
    for tn in transit_nodes:
        tid = tn.get("id")
        pos = tn.get("position")
        if tid and isinstance(pos, list) and len(pos) >= 2:
            node_pos_map[str(tid)] = (float(pos[0]), float(pos[1]))
            node_type_map[str(tid)] = str(tn.get("type", "bus"))

    trans_frontage_index: Dict[str, List[str]] = {str(t.get("id")): [] for t in transit_nodes if t.get("id")}

    frontage_count = 1
    corner_count = 1

    for ix in range(len(v_roads) - 1):
        lv = v_roads[ix]
        rv = v_roads[ix + 1]
        x_min = (lv.p0[0] + lv.p1[0]) * 0.5 + lv.width * 0.5
        x_max = (rv.p0[0] + rv.p1[0]) * 0.5 - rv.width * 0.5
        if x_max <= x_min:
            continue

        for iy in range(len(h_roads) - 1):
            bh = h_roads[iy]
            th = h_roads[iy + 1]
            y_min = (bh.p0[1] + bh.p1[1]) * 0.5 + bh.width * 0.5
            y_max = (th.p0[1] + th.p1[1]) * 0.5 - th.width * 0.5
            if y_max <= y_min:
                continue

            block_id = f"block_{ix+1:02d}_{iy+1:02d}"
            block_rects[block_id] = (x_min, y_min, x_max, y_max)

            specs = [
                (lv, [x_min, y_min], [x_min, y_max]),
                (rv, [x_max, y_min], [x_max, y_max]),
                (bh, [x_min, y_min], [x_max, y_min]),
                (th, [x_min, y_max], [x_max, y_max]),
            ]

            local_frontages: List[Frontage] = []
            priorities = []

            for road, p0, p1 in specs:
                seg_len = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                orient = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))

                served = []
                for tn in transit_nodes:
                    tid = tn.get("id")
                    pos = tn.get("position")
                    if not tid or not isinstance(pos, list) or len(pos) < 2:
                        continue
                    dist = seg_distance_point(float(pos[0]), float(pos[1]), (p0[0], p0[1]), (p1[0], p1[1]))
                    if dist <= influence_w:
                        served.append(str(tid))

                transit_inf = len(served) > 0
                pr = CLASS_PRIORITY.get(road.road_class, 2)
                priorities.append(pr)

                f = Frontage(
                    id=f"frontage_{frontage_count:04d}",
                    block_id=block_id,
                    polyline=[[p0[0], p0[1]], [p1[0], p1[1]]],
                    adjacent_road_id=road.id,
                    road_class=road.road_class,
                    frontage_type="back_frontage",
                    orientation=orient,
                    length=seg_len,
                    transit_influenced=transit_inf,
                    served_transit_node_ids=served,
                )
                frontage_count += 1
                local_frontages.append(f)

            max_p = max(priorities)
            second_p = sorted(set(priorities), reverse=True)[1] if len(set(priorities)) > 1 else max_p

            for f in local_frontages:
                p = CLASS_PRIORITY.get(f.road_class, 2)
                if p == max_p:
                    f.frontage_type = "primary_frontage"
                elif p == second_p or f.transit_influenced:
                    f.frontage_type = "secondary_frontage"
                else:
                    f.frontage_type = "back_frontage"

                for tid in f.served_transit_node_ids:
                    trans_frontage_index.setdefault(tid, []).append(f.id)

                frontages.append(f)

            pts = [
                ([x_min, y_min], local_frontages[0], local_frontages[2], lv.road_class, bh.road_class),
                ([x_max, y_min], local_frontages[1], local_frontages[2], rv.road_class, bh.road_class),
                ([x_max, y_max], local_frontages[1], local_frontages[3], rv.road_class, th.road_class),
                ([x_min, y_max], local_frontages[0], local_frontages[3], lv.road_class, th.road_class),
            ]

            for pos, f1, f2, c1, c2 in pts:
                near_transit = False
                for tn in transit_nodes:
                    p = tn.get("position")
                    if not isinstance(p, list) or len(p) < 2:
                        continue
                    if math.hypot(float(p[0]) - pos[0], float(p[1]) - pos[1]) <= influence_w * 1.2:
                        near_transit = True
                        break

                if near_transit:
                    ctype = "transit_corner"
                else:
                    tags = {f1.frontage_type, f2.frontage_type}
                    if "primary_frontage" in tags and ("secondary_frontage" in tags or len(tags) == 1):
                        ctype = "open_plaza_corner"
                    else:
                        ctype = "normal_corner"

                corners.append({
                    "id": f"corner_{corner_count:04d}",
                    "block_id": block_id,
                    "position": [round(pos[0], 4), round(pos[1], 4)],
                    "corner_type": ctype,
                    "radius": round(radius_lookup(c1, c2), 2),
                    "adjacent_frontage_ids": [f1.id, f2.id],
                })
                corner_count += 1

    corner_lookup: Dict[str, Dict[str, float]] = {}
    for tn in transit_nodes:
        tid = str(tn.get("id")) if tn.get("id") else ""
        if not tid:
            continue
        if trans_frontage_index.get(tid):
            continue
        pos = node_pos_map.get(tid)
        if pos is None or not frontages:
            continue

        best_f = None
        best_d = 1e30
        for f in frontages:
            p0 = (float(f.polyline[0][0]), float(f.polyline[0][1]))
            p1 = (float(f.polyline[1][0]), float(f.polyline[1][1]))
            d = seg_distance_point(pos[0], pos[1], p0, p1)
            if d < best_d:
                best_d = d
                best_f = f

        if best_f is not None:
            if tid not in best_f.served_transit_node_ids:
                best_f.served_transit_node_ids.append(tid)
            best_f.transit_influenced = True
            if best_f.frontage_type == "back_frontage":
                best_f.frontage_type = "secondary_frontage"
            trans_frontage_index.setdefault(tid, []).append(best_f.id)

    for block_id, (x_min, y_min, x_max, y_max) in block_rects.items():
        corner_lookup[block_id] = {"bl": 0.0, "br": 0.0, "tr": 0.0, "tl": 0.0}
        for c in corners:
            if c["block_id"] != block_id:
                continue
            x, y = c["position"]
            r = float(c.get("radius", 0.0))
            if abs(x - x_min) < 1e-6 and abs(y - y_min) < 1e-6:
                corner_lookup[block_id]["bl"] = r
            elif abs(x - x_max) < 1e-6 and abs(y - y_min) < 1e-6:
                corner_lookup[block_id]["br"] = r
            elif abs(x - x_max) < 1e-6 and abs(y - y_max) < 1e-6:
                corner_lookup[block_id]["tr"] = r
            elif abs(x - x_min) < 1e-6 and abs(y - y_max) < 1e-6:
                corner_lookup[block_id]["tl"] = r

    for block_id, rect in block_rects.items():
        x_min, y_min, x_max, y_max = rect
        rc = corner_lookup.get(block_id, {"bl": 0.0, "br": 0.0, "tr": 0.0, "tl": 0.0})
        poly = _rounded_rect_polygon(
            x_min, y_min, x_max, y_max,
            rc["bl"], rc["br"], rc["tr"], rc["tl"],
            arc_segments=4,
        )
        blocks.append({"id": block_id, "polygon": poly})

    for f in frontages:
        if not f.served_transit_node_ids:
            continue
        block_rect = block_rects.get(f.block_id)
        if block_rect is None:
            continue
        for tid in f.served_transit_node_ids:
            pos = node_pos_map.get(tid)
            if pos is None:
                continue
            poly = _make_transit_zone_for_frontage(
                frontage=f,
                node_pos=pos,
                block_rect=block_rect,
                zone_width=influence_w,
                zone_length=influence_len,
            )
            if not poly:
                continue
            boost = 0.25 if node_type_map.get(tid) == "metro" else 0.15
            tiz.append({
                "id": f"tiz_{tiz_count:04d}",
                "transit_node_id": tid,
                "geometry_type": "polygon",
                "polygon": poly,
                "width": influence_w,
                "length": influence_len,
                "priority_boost": boost,
                "associated_frontage_ids": [f.id],
            })
            tiz_count += 1

    for tn in transit_nodes:
        tid = tn.get("id")
        if tid:
            tn["served_frontage_ids"] = sorted(set(trans_frontage_index.get(str(tid), [])))

    return {
        "block_boundaries": blocks,
        "frontage_segments": [
            {
                "id": f.id,
                "block_id": f.block_id,
                "polyline": f.polyline,
                "frontage_type": f.frontage_type,
                "adjacent_road_id": f.adjacent_road_id,
                "length": round(f.length, 3),
                "orientation": round(f.orientation, 2),
                "transit_influenced": f.transit_influenced,
                "served_transit_node_ids": f.served_transit_node_ids,
            }
            for f in frontages
        ],
        "corners": corners,
        "transit_influence_zones": tiz,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate generated.step_1_network from scene inputs")
    parser.add_argument("--input", default="step1_test_input.json", help="input scene json")
    parser.add_argument("--settings", default="default_network.yaml", help="settings yaml")
    parser.add_argument("--output", default="step1_generated_scene.json", help="output scene json")
    args = parser.parse_args()

    in_path = Path(args.input)
    settings_path = Path(args.settings)
    out_path = Path(args.output)

    if not in_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {in_path}")
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings YAML not found: {settings_path}")

    print(f"[Load] scene: {in_path}")
    with in_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"[Load] settings: {settings_path}")
    settings = load_yaml(settings_path)

    data["global_settings"] = settings
    generated = data.get("generated", {}) or {}
    generated["step_1_network"] = generate_step1(data, settings)
    data["generated"] = generated

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(_format_json_compact(data) + "\n")

    step = data["generated"]["step_1_network"]
    print("[Summary]")
    print(f"  blocks: {len(step.get('block_boundaries', []))}")
    print(f"  frontages: {len(step.get('frontage_segments', []))}")
    print(f"  corners: {len(step.get('corners', []))}")
    print(f"  transit_zones: {len(step.get('transit_influence_zones', []))}")
    print(f"[Done] wrote: {out_path}")


if __name__ == "__main__":
    main()
