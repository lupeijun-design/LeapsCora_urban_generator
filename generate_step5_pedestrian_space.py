import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml
from shapely import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union


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
        "global.min_polygon_area_sqm",
        "global.gap_smooth_distance_m",
        "outdoor_clear_passage.main_width_m",
        "threshold_space.main_entry_width_m",
        "semi_public_frontage_band.commercial_width_m",
        "indoor_public_corridor.mall_width_m",
        "node_generation.outdoor_node_area_sqm",
        "heights.fallback_space_height_m",
        "cleanup.enforce_indoor_continuous_per_building",
    ]
    for p in required:
        require_key(raw, p)
    return raw


def poly_to_shape(poly: List[List[float]]) -> Optional[Polygon]:
    if not isinstance(poly, list) or len(poly) < 3:
        return None
    pts = []
    for p in poly:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append((float(p[0]), float(p[1])))
    if len(pts) < 3:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    shp = Polygon(pts)
    if not shp.is_valid:
        shp = shp.buffer(0)
    if shp.is_empty:
        return None
    return shp


def shape_to_polygons(geom) -> List[List[List[float]]]:
    if geom is None or geom.is_empty:
        return []
    out: List[List[List[float]]] = []
    if isinstance(geom, Polygon):
        coords = list(geom.exterior.coords)
        out.append([[round(x, 4), round(y, 4)] for x, y in coords])
        return out
    if isinstance(geom, MultiPolygon):
        for g in geom.geoms:
            coords = list(g.exterior.coords)
            out.append([[round(x, 4), round(y, 4)] for x, y in coords])
        return out
    try:
        for g in geom.geoms:
            if isinstance(g, Polygon):
                coords = list(g.exterior.coords)
                out.append([[round(x, 4), round(y, 4)] for x, y in coords])
    except Exception:
        pass
    return out


def first_floor_height(building: dict, cfg: Dict[str, Any]) -> float:
    use_b = bool(cfg["heights"]["use_building_first_floor_height"])
    if not use_b:
        return float(cfg["heights"]["fallback_space_height_m"])
    h = float(building.get("height", 0.0) or 0.0)
    lv = int(building.get("levels_above_ground", 0) or 0)
    if h > 0.0 and lv > 0:
        return max(2.6, h / float(lv))
    return float(cfg["heights"]["fallback_space_height_m"])


def node_rect_from_area(center: Tuple[float, float], area: float, aspect: float, angle_rad: float = 0.0) -> Polygon:
    w = math.sqrt(max(1e-6, area) * max(1e-3, aspect))
    h = max(1e-6, area) / max(1e-6, w)
    cx, cy = center
    hw, hh = w * 0.5, h * 0.5
    pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    rpts = []
    for x, y in pts:
        rx = x * ca - y * sa + cx
        ry = x * sa + y * ca + cy
        rpts.append((rx, ry))
    return Polygon(rpts)


def mean_direction(p: Tuple[float, float], neighbors: List[Tuple[float, float]]) -> float:
    if not neighbors:
        return 0.0
    sx = 0.0
    sy = 0.0
    for q in neighbors:
        dx, dy = q[0] - p[0], q[1] - p[1]
        l = math.hypot(dx, dy)
        if l > 1e-6:
            sx += dx / l
            sy += dy / l
    if abs(sx) < 1e-8 and abs(sy) < 1e-8:
        return 0.0
    return math.atan2(sy, sx)


def geometry_union(polys: Iterable[Polygon], smooth_gap: float = 0.0):
    vals = [p for p in polys if p is not None and not p.is_empty]
    if not vals:
        return None
    g = unary_union(vals)
    if smooth_gap > 1e-6:
        g = g.buffer(smooth_gap * 0.5, join_style=2).buffer(-smooth_gap * 0.5, join_style=2)
    if not g.is_valid:
        g = g.buffer(0)
    return g


def generate_step5(scene: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    generated = scene.get("generated", {}) or {}
    s2 = generated.get("step_2_massing", {}) or {}
    s3 = generated.get("step_3_key_nodes", {}) or {}
    s4 = generated.get("step_4_topology", {}) or {}

    masses = s2.get("building_masses", []) or []
    open_spaces = s2.get("reserved_open_spaces", []) or []
    podium = s2.get("podium_retail_bands", []) or []
    entrances = s3.get("entrance_candidates", []) or []
    nets = s4.get("circulation_networks", {}) or {}

    outdoor = nets.get("ground_outdoor", {}) or {}
    indoor = nets.get("ground_indoor_public", {}) or {}
    lvl2 = nets.get("level2_reserved", {}) or {}
    b1 = nets.get("basement_reserved", {}) or {}

    random.Random(int(cfg["global"]["random_seed"]))
    min_area = float(cfg["global"]["min_polygon_area_sqm"])
    smooth_gap = float(cfg["global"]["gap_smooth_distance_m"])

    bld_by_id = {str(b.get("id", "")): b for b in masses}
    bld_shape = {}
    for b in masses:
        bid = str(b.get("id", ""))
        shp = poly_to_shape(b.get("footprint", []))
        if shp:
            bld_shape[bid] = shp

    # node index
    out_nodes = {str(n.get("id", "")): (float(n["position"][0]), float(n["position"][1])) for n in (outdoor.get("nodes", []) or []) if isinstance(n.get("position"), list) and len(n["position"]) >= 2}
    in_nodes = {str(n.get("id", "")): (float(n["position"][0]), float(n["position"][1])) for n in (indoor.get("nodes", []) or []) if isinstance(n.get("position"), list) and len(n["position"]) >= 2}
    l2_nodes = {str(n.get("id", "")): (float(n["position"][0]), float(n["position"][1])) for n in (lvl2.get("nodes", []) or []) if isinstance(n.get("position"), list) and len(n["position"]) >= 2}
    b1_nodes = {str(n.get("id", "")): (float(n["position"][0]), float(n["position"][1])) for n in (b1.get("nodes", []) or []) if isinstance(n.get("position"), list) and len(n["position"]) >= 2}

    # adjacency for node shapes
    out_adj: Dict[str, List[str]] = {k: [] for k in out_nodes.keys()}
    for e in outdoor.get("edges", []) or []:
        u, v = str(e.get("from", "")), str(e.get("to", ""))
        if u in out_adj and v in out_adj:
            out_adj[u].append(v)
            out_adj[v].append(u)
    in_adj: Dict[str, List[str]] = {k: [] for k in in_nodes.keys()}
    for e in indoor.get("edges", []) or []:
        u, v = str(e.get("from", "")), str(e.get("to", ""))
        if u in in_adj and v in in_adj:
            in_adj[u].append(v)
            in_adj[v].append(u)

    walkable_spaces: List[dict] = []
    node_spaces: List[dict] = []
    reserved_level_spaces: List[dict] = []

    # 1) Outdoor clear passage: path buffers + node expansion polygons + union.
    out_polys: List[Polygon] = []
    for e in outdoor.get("edges", []) or []:
        u = out_nodes.get(str(e.get("from", "")))
        v = out_nodes.get(str(e.get("to", "")))
        if not u or not v:
            continue
        lvl = str(e.get("network_level", "connector"))
        if lvl == "main":
            w = float(cfg["outdoor_clear_passage"]["main_width_m"])
        elif lvl == "secondary":
            w = float(cfg["outdoor_clear_passage"]["secondary_width_m"])
        elif lvl == "back":
            w = float(cfg["outdoor_clear_passage"]["back_width_m"])
        else:
            w = float(cfg["outdoor_clear_passage"]["connector_width_m"])
        out_polys.append(LineString([u, v]).buffer(w * 0.5, cap_style=2, join_style=2))
    for nid, p in out_nodes.items():
        nei = [out_nodes[x] for x in out_adj.get(nid, []) if x in out_nodes]
        ang = mean_direction(p, nei)
        area = float(cfg["node_generation"]["outdoor_node_area_sqm"])
        asp = float(cfg["node_generation"]["rectangle_aspect_ratio"])
        out_polys.append(node_rect_from_area(p, area, asp, ang))
    g_out = geometry_union(out_polys, smooth_gap=smooth_gap)
    for poly in shape_to_polygons(g_out):
        p = Polygon(poly)
        if p.area >= min_area:
            walkable_spaces.append({
                "id": f"ws_{len(walkable_spaces) + 1:03d}",
                "space_type": "street_clear_path",
                "polygon": poly,
                "level": "ground",
                "extrude_height": float(cfg["heights"]["outdoor_space_height_m"]),
            })

    # 2) Threshold spaces from entrance vectors (not bbox).
    bld_centers = {bid: (shp.centroid.x, shp.centroid.y) for bid, shp in bld_shape.items()}
    th_polys: List[Polygon] = []
    th_map: List[Tuple[str, str]] = []
    for e in entrances:
        bid = str(e.get("building_id", ""))
        pos = e.get("position")
        if bid not in bld_shape or not (isinstance(pos, list) and len(pos) >= 2):
            continue
        p0 = (float(pos[0]), float(pos[1]))
        cen = bld_centers[bid]
        dx, dy = p0[0] - cen[0], p0[1] - cen[1]
        ln = math.hypot(dx, dy)
        if ln < 1e-6:
            dx, dy, ln = 1.0, 0.0, 1.0
        ux, uy = dx / ln, dy / ln
        ctype = str(e.get("candidate_type", "secondary"))
        if ctype == "main":
            w = float(cfg["threshold_space"]["main_entry_width_m"])
            d = float(cfg["threshold_space"]["main_entry_depth_m"])
        elif ctype == "service":
            w = float(cfg["threshold_space"]["service_entry_width_m"])
            d = float(cfg["threshold_space"]["service_entry_depth_m"])
        else:
            w = float(cfg["threshold_space"]["secondary_entry_width_m"])
            d = float(cfg["threshold_space"]["secondary_entry_depth_m"])
        p1 = (p0[0] + ux * d, p0[1] + uy * d)
        shp = LineString([p0, p1]).buffer(w * 0.5, cap_style=2, join_style=2)
        shp = shp.intersection(bld_shape[bid].buffer(d + 2.0))
        if not shp.is_empty:
            th_polys.append(shp)
            th_map.append((bid, str(e.get("id", ""))))
    g_th = geometry_union(th_polys, smooth_gap=0.0)
    for poly in shape_to_polygons(g_th):
        p = Polygon(poly)
        if p.area >= min_area:
            # nearest building for height
            bid = min(bld_shape.keys(), key=lambda k: p.centroid.distance(bld_shape[k].centroid)) if bld_shape else ""
            eh = first_floor_height(bld_by_id.get(bid, {}), cfg) if bid else float(cfg["heights"]["fallback_space_height_m"])
            walkable_spaces.append({
                "id": f"ws_{len(walkable_spaces) + 1:03d}",
                "space_type": "entrance_threshold",
                "polygon": poly,
                "level": "ground",
                "related_building_id": bid,
                "extrude_height": round(eh, 4),
            })

    # 3) Semi-public frontage band: from podium or building edge buffer ring.
    band_polys: List[Polygon] = []
    if podium:
        for p in podium:
            shp = poly_to_shape(p.get("polygon", []))
            if shp:
                band_polys.append(shp)
    else:
        for b in masses:
            bid = str(b.get("id", ""))
            shp = bld_shape.get(bid)
            if not shp:
                continue
            lu = str(b.get("land_use", "R"))
            if lu == "B1":
                w = float(cfg["semi_public_frontage_band"]["commercial_width_m"])
            elif lu == "B2":
                w = float(cfg["semi_public_frontage_band"]["office_width_m"])
            else:
                w = float(cfg["semi_public_frontage_band"]["residential_width_m"])
            ring = shp.buffer(w, join_style=2).difference(shp)
            band_polys.append(ring)
    g_band = geometry_union(band_polys, smooth_gap=0.0)
    for poly in shape_to_polygons(g_band):
        p = Polygon(poly)
        if p.area >= min_area:
            bid = min(bld_shape.keys(), key=lambda k: p.centroid.distance(bld_shape[k].centroid)) if bld_shape else ""
            eh = first_floor_height(bld_by_id.get(bid, {}), cfg) if bid else float(cfg["heights"]["fallback_space_height_m"])
            walkable_spaces.append({
                "id": f"ws_{len(walkable_spaces) + 1:03d}",
                "space_type": "semi_public_frontage_band",
                "polygon": poly,
                "level": "ground",
                "related_building_id": bid,
                "extrude_height": round(eh, 4),
            })

    # 4) Indoor public corridor: edge buffers + node rectangles; enforce single connected shape per building.
    in_node_meta = {str(n.get("id", "")): n for n in (indoor.get("nodes", []) or [])}
    in_polys_by_building: Dict[str, List[Polygon]] = {}
    for e in indoor.get("edges", []) or []:
        u_id, v_id = str(e.get("from", "")), str(e.get("to", ""))
        u, v = in_nodes.get(u_id), in_nodes.get(v_id)
        if not u or not v:
            continue
        nu, nv = in_node_meta.get(u_id, {}), in_node_meta.get(v_id, {})
        bid = str(nu.get("building_id", "") or nv.get("building_id", ""))
        if not bid:
            continue
        lu = str(bld_by_id.get(bid, {}).get("land_use", "R"))
        if lu == "B1":
            w = float(cfg["indoor_public_corridor"]["mall_width_m"])
        elif lu == "B2":
            w = float(cfg["indoor_public_corridor"]["office_width_m"])
        else:
            w = float(cfg["indoor_public_corridor"]["residential_width_m"])
        w = max(w, float(cfg["indoor_public_corridor"]["min_corridor_width_m"]))
        in_polys_by_building.setdefault(bid, []).append(LineString([u, v]).buffer(w * 0.5, cap_style=2, join_style=2))
    for nid, p in in_nodes.items():
        meta = in_node_meta.get(nid, {})
        bid = str(meta.get("building_id", ""))
        if not bid:
            continue
        nei = [in_nodes[x] for x in in_adj.get(nid, []) if x in in_nodes]
        ang = mean_direction(p, nei)
        area = float(cfg["node_generation"]["indoor_node_area_sqm"])
        asp = float(cfg["node_generation"]["rectangle_aspect_ratio"])
        in_polys_by_building.setdefault(bid, []).append(node_rect_from_area(p, area, asp, ang))

    for bid, polys in in_polys_by_building.items():
        shp = geometry_union(polys, smooth_gap=smooth_gap)
        if shp is None or shp.is_empty:
            continue
        if bool(cfg["cleanup"]["enforce_indoor_continuous_per_building"]) and isinstance(shp, MultiPolygon):
            # connect components by corridor between nearest points iteratively
            geoms = list(shp.geoms)
            base = geoms[0]
            for g in geoms[1:]:
                a = base.representative_point()
                b = g.representative_point()
                lu = str(bld_by_id.get(bid, {}).get("land_use", "R"))
                if lu == "B1":
                    w = float(cfg["indoor_public_corridor"]["mall_width_m"])
                elif lu == "B2":
                    w = float(cfg["indoor_public_corridor"]["office_width_m"])
                else:
                    w = float(cfg["indoor_public_corridor"]["residential_width_m"])
                connector = LineString([(a.x, a.y), (b.x, b.y)]).buffer(max(1.2, w * 0.4), cap_style=2, join_style=2)
                base = unary_union([base, g, connector])
            shp = base.buffer(smooth_gap * 0.25, join_style=2).buffer(-smooth_gap * 0.25, join_style=2)
        shp = shp.intersection(bld_shape.get(bid, shp))
        eh = first_floor_height(bld_by_id.get(bid, {}), cfg)
        for poly in shape_to_polygons(shp):
            p = Polygon(poly)
            if p.area >= min_area:
                walkable_spaces.append({
                    "id": f"ws_{len(walkable_spaces) + 1:03d}",
                    "space_type": "indoor_public_continuous",
                    "polygon": poly,
                    "level": "ground",
                    "related_building_id": bid,
                    "continuous": True,
                    "extrude_height": round(eh, 4),
                })

    # 5) Node spaces from open spaces (keep detailed input geometry).
    for o in open_spaces:
        shp = poly_to_shape(o.get("polygon", []))
        if not shp or shp.area < min_area:
            continue
        ot = str(o.get("open_space_type", "small_plaza"))
        if "corner" in ot:
            ntype = "corner_expansion"
        elif "office" in ot:
            ntype = "office_lobby_forecourt"
        elif "commercial" in ot or "transit" in ot:
            ntype = "atrium_forecourt"
        else:
            ntype = "small_plaza"
        for poly in shape_to_polygons(shp):
            node_spaces.append({
                "id": f"ns_{len(node_spaces) + 1:03d}",
                "node_space_type": ntype,
                "polygon": poly,
                "level": "ground",
                "source_open_space_id": str(o.get("id", "")),
                "extrude_height": float(cfg["heights"]["outdoor_space_height_m"]),
            })

    # 6) Reserved 2F/B1 space by precise path buffer.
    for e in lvl2.get("edges", []) or []:
        u, v = l2_nodes.get(str(e.get("from", ""))), l2_nodes.get(str(e.get("to", "")))
        if not u or not v:
            continue
        shp = LineString([u, v]).buffer(float(cfg["reserved_level_spaces"]["level2_corridor_width_m"]) * 0.5, cap_style=2, join_style=2)
        for poly in shape_to_polygons(shp):
            if Polygon(poly).area >= min_area:
                reserved_level_spaces.append({
                    "id": f"rs_{len(reserved_level_spaces) + 1:03d}",
                    "space_type": "level2_reserved_corridor",
                    "polygon": poly,
                    "level": "level2",
                    "source_edge_id": str(e.get("id", "")),
                    "extrude_height": float(cfg["heights"]["fallback_space_height_m"]),
                })
    for e in b1.get("edges", []) or []:
        u, v = b1_nodes.get(str(e.get("from", ""))), b1_nodes.get(str(e.get("to", "")))
        if not u or not v:
            continue
        shp = LineString([u, v]).buffer(float(cfg["reserved_level_spaces"]["basement_corridor_width_m"]) * 0.5, cap_style=2, join_style=2)
        for poly in shape_to_polygons(shp):
            if Polygon(poly).area >= min_area:
                reserved_level_spaces.append({
                    "id": f"rs_{len(reserved_level_spaces) + 1:03d}",
                    "space_type": "basement_reserved_corridor",
                    "polygon": poly,
                    "level": "basement",
                    "source_edge_id": str(e.get("id", "")),
                    "extrude_height": float(cfg["heights"]["fallback_space_height_m"]),
                })

    # optional final dedup by type using geometric union (precise, non-bbox)
    grouped: Dict[str, List[Polygon]] = {}
    meta_by_type: Dict[str, dict] = {}
    for w in walkable_spaces:
        shp = poly_to_shape(w["polygon"])
        if not shp:
            continue
        st = str(w.get("space_type", "unknown"))
        grouped.setdefault(st, []).append(shp)
        meta_by_type.setdefault(st, {"level": w.get("level", "ground"), "extrude_height": w.get("extrude_height")})

    final_walkable: List[dict] = []
    for st, polys in grouped.items():
        g = geometry_union(polys, smooth_gap=0.0)
        for poly in shape_to_polygons(g):
            if Polygon(poly).area < float(cfg["cleanup"]["remove_sliver_area_sqm"]):
                continue
            final_walkable.append({
                "id": f"ws_{len(final_walkable) + 1:03d}",
                "space_type": st,
                "polygon": poly,
                "level": meta_by_type[st]["level"],
                "extrude_height": meta_by_type[st]["extrude_height"],
            })

    return {
        "walkable_spaces": final_walkable,
        "node_spaces": node_spaces,
        "reserved_level_spaces": reserved_level_spaces,
        "metadata": {
            "generator": "generate_step5_pedestrian_space.py",
            "geometry_engine": "shapely",
            "path_based_generation": True,
            "walkable_count": len(final_walkable),
            "node_space_count": len(node_spaces),
            "reserved_space_count": len(reserved_level_spaces),
            "indoor_continuous_enforced": bool(cfg["cleanup"]["enforce_indoor_continuous_per_building"]),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Step5 Pedestrian Space Generator")
    parser.add_argument("--input", default="step4_generated_scene.json", help="input scene json with step_4_topology")
    parser.add_argument("--output", default="step5_generated_scene.json", help="output scene json")
    parser.add_argument("--typology", default="defaults_pedestrian_space.yaml", help="pedestrian space defaults yaml")
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
    cfg = load_typology(typology_path)

    generated = scene.get("generated", {}) or {}
    for req in ["step_1_network", "step_2_massing", "step_4_topology"]:
        if req not in generated:
            raise ValueError(f"generated.{req} not found in input scene")

    generated["step_5_spaces"] = generate_step5(scene, cfg)
    scene["generated"] = generated

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(_format_json_compact(scene) + "\n")

    s5 = generated["step_5_spaces"]
    print("[Summary]")
    print(f"  walkable_spaces: {len(s5.get('walkable_spaces', []) or [])}")
    print(f"  node_spaces: {len(s5.get('node_spaces', []) or [])}")
    print(f"  reserved_level_spaces: {len(s5.get('reserved_level_spaces', []) or [])}")
    print(f"[Done] wrote: {out_path}")


if __name__ == "__main__":
    main()

