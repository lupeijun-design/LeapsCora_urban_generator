import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml


FRONTAGE_TO_LEVEL = {
    "primary_frontage": "main",
    "secondary_frontage": "secondary",
    "back_frontage": "back",
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
        "global.merge_node_distance_m",
        "global.nearest_connect_distance_m",
        "global.indoor_link_distance_m",
        "outdoor.back_continuity.residential",
        "outdoor.back_continuity.commercial",
        "indoor.mall.enabled",
        "indoor.office.enabled",
        "indoor.residential.enabled",
        "vertical.generate_level2_when.require_large_mall",
        "vertical.generate_b1_when.require_metro_access",
        "vertical.connector_modes.mall_default",
        "skeleton.threshold_link_max_distance_m",
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


def poly_center(poly: Sequence[Sequence[float]]) -> Tuple[float, float]:
    pts = clean_ring(poly)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return ((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5)


def poly_bbox(poly: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    pts = clean_ring(poly)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def nearest(pt: Tuple[float, float], candidates: List[Tuple[str, Tuple[float, float]]]) -> Optional[str]:
    if not candidates:
        return None
    return min(candidates, key=lambda c: distance(pt, c[1]))[0]


def frontage_orientation(frontage: dict) -> float:
    pl = frontage.get("polyline", [])
    if isinstance(pl, list) and len(pl) >= 2:
        dx = float(pl[-1][0]) - float(pl[0][0])
        dy = float(pl[-1][1]) - float(pl[0][1])
        return math.degrees(math.atan2(dy, dx))
    return 0.0


def point_in_polygon(pt: Tuple[float, float], poly: Sequence[Sequence[float]]) -> bool:
    pts = clean_ring(poly)
    if len(pts) < 3:
        return False
    x, y = pt
    inside = False
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / ((y2 - y1) if abs(y2 - y1) > 1e-9 else 1e-9) + x1
            if x < xin:
                inside = not inside
    return inside


def project_point_to_segment(p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    ax, ay = a
    bx, by = b
    px, py = p
    abx, aby = bx - ax, by - ay
    den = abx * abx + aby * aby
    if den <= 1e-12:
        return a
    t = ((px - ax) * abx + (py - ay) * aby) / den
    t = max(0.0, min(1.0, t))
    return (ax + t * abx, ay + t * aby)


def _ccw(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float], eps: float = 1e-9) -> bool:
    return min(a[0], b[0]) - eps <= c[0] <= max(a[0], b[0]) + eps and min(a[1], b[1]) - eps <= c[1] <= max(a[1], b[1]) + eps


def segments_intersect(a1: Tuple[float, float], a2: Tuple[float, float], b1: Tuple[float, float], b2: Tuple[float, float], eps: float = 1e-9) -> bool:
    d1 = _ccw(a1, a2, b1)
    d2 = _ccw(a1, a2, b2)
    d3 = _ccw(b1, b2, a1)
    d4 = _ccw(b1, b2, a2)
    if (d1 * d2 < -eps) and (d3 * d4 < -eps):
        return True
    if abs(d1) <= eps and _on_segment(a1, a2, b1):
        return True
    if abs(d2) <= eps and _on_segment(a1, a2, b2):
        return True
    if abs(d3) <= eps and _on_segment(b1, b2, a1):
        return True
    if abs(d4) <= eps and _on_segment(b1, b2, a2):
        return True
    return False


class DSU:
    def __init__(self, items: List[str]):
        self.p = {x: x for x in items}
        self.r = {x: 0 for x in items}

    def find(self, x: str) -> str:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.r[ra] < self.r[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.r[ra] == self.r[rb]:
            self.r[ra] += 1
        return True


def build_tree_edges(
    node_ids: List[str],
    node_pos: Dict[str, Tuple[float, float]],
    non_crossing: bool = False,
    root_id: Optional[str] = None,
) -> List[Tuple[str, str]]:
    if len(node_ids) <= 1:
        return []
    pairs: List[Tuple[float, str, str]] = []
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            u, v = node_ids[i], node_ids[j]
            pairs.append((distance(node_pos[u], node_pos[v]), u, v))
    pairs.sort(key=lambda x: x[0])

    dsu = DSU(node_ids)
    chosen: List[Tuple[str, str]] = []
    chosen_geom: List[Tuple[str, str, Tuple[float, float], Tuple[float, float]]] = []
    for _, u, v in pairs:
        if dsu.find(u) == dsu.find(v):
            continue
        if non_crossing:
            pu, pv = node_pos[u], node_pos[v]
            ok = True
            for a, b, pa, pb in chosen_geom:
                if len({u, v, a, b}) < 4:
                    continue
                if segments_intersect(pu, pv, pa, pb):
                    ok = False
                    break
            if not ok:
                continue
        dsu.union(u, v)
        chosen.append((u, v))
        chosen_geom.append((u, v, node_pos[u], node_pos[v]))
        if len(chosen) == len(node_ids) - 1:
            break

    # Fallback for strict non-crossing failure: star tree (always acyclic/connected).
    if len(chosen) < len(node_ids) - 1:
        root = root_id if root_id in node_ids else node_ids[0]
        chosen = []
        for x in node_ids:
            if x != root:
                chosen.append((root, x))
    return chosen


class NetBuilder:
    def __init__(self, prefix: str, merge_dist: float):
        self.prefix = prefix
        self.merge_dist = merge_dist
        self.nodes: List[dict] = []
        self.edges: List[dict] = []
        self._node_idx = 1
        self._edge_idx = 1

    def _find_existing(self, pt: Tuple[float, float]) -> Optional[str]:
        for n in self.nodes:
            p = n["position"]
            if distance(pt, (float(p[0]), float(p[1]))) <= self.merge_dist:
                return str(n["id"])
        return None

    def add_node(self, node_type: str, pt: Tuple[float, float], **extra: Any) -> str:
        ex = self._find_existing(pt)
        if ex:
            return ex
        nid = f"{self.prefix}_node_{self._node_idx:03d}"
        self._node_idx += 1
        item = {"id": nid, "position": [round(pt[0], 4), round(pt[1], 4)], "node_type": node_type}
        item.update(extra)
        self.nodes.append(item)
        return nid

    def add_edge(self, u: str, v: str, edge_type: str, priority: str, **extra: Any) -> str:
        if u == v:
            return ""
        pu = self.node_pos(u)
        pv = self.node_pos(v)
        if pu is None or pv is None:
            return ""
        eid = f"{self.prefix}_edge_{self._edge_idx:03d}"
        self._edge_idx += 1
        item = {
            "id": eid,
            "from": u,
            "to": v,
            "edge_type": edge_type,
            "length": round(distance(pu, pv), 4),
            "priority": priority,
        }
        item.update(extra)
        self.edges.append(item)
        return eid

    def node_pos(self, nid: str) -> Optional[Tuple[float, float]]:
        for n in self.nodes:
            if str(n["id"]) == nid:
                p = n["position"]
                return (float(p[0]), float(p[1]))
        return None

    def node_items(self) -> List[Tuple[str, Tuple[float, float]]]:
        out = []
        for n in self.nodes:
            p = n["position"]
            out.append((str(n["id"]), (float(p[0]), float(p[1]))))
        return out


def generate_step4(scene: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    generated = scene.get("generated", {}) or {}
    s1 = generated.get("step_1_network", {}) or {}
    s2 = generated.get("step_2_massing", {}) or {}
    s3 = generated.get("step_3_key_nodes", {}) or {}

    blocks = s1.get("block_boundaries", []) or []
    frontages = s1.get("frontage_segments", []) or []
    corners = s1.get("corners", []) or []
    tiz = s1.get("transit_influence_zones", []) or []

    masses = s2.get("building_masses", []) or []
    atriums = s2.get("atriums", []) or []
    cores = s2.get("cores", []) or []
    open_spaces = s2.get("reserved_open_spaces", []) or []
    podium = s2.get("podium_retail_bands", []) or []

    key_nodes = s3.get("key_nodes", []) or []
    entrances = s3.get("entrance_candidates", []) or []
    services = s3.get("service_nodes", []) or []

    rng = random.Random(int(cfg["global"]["random_seed"]))
    merge_dist = float(cfg["global"]["merge_node_distance_m"])

    outdoor = NetBuilder("g", merge_dist)
    indoor = NetBuilder("i", merge_dist)
    vertical = NetBuilder("v", merge_dist)
    level2 = NetBuilder("l2", merge_dist)
    b1 = NetBuilder("b1", merge_dist)

    # Index helpers.
    building_by_id = {str(b.get("id", "")): b for b in masses}
    atrium_by_building: Dict[str, List[dict]] = {}
    for a in atriums:
        bid = str(a.get("building_id", ""))
        atrium_by_building.setdefault(bid, []).append(a)
    core_by_building: Dict[str, List[dict]] = {}
    for c in cores:
        bid = str(c.get("building_id", ""))
        core_by_building.setdefault(bid, []).append(c)
    ent_by_building: Dict[str, List[dict]] = {}
    for e in entrances:
        bid = str(e.get("building_id", ""))
        ent_by_building.setdefault(bid, []).append(e)

    land_use_by_block: Dict[str, set] = {}
    for b in masses:
        blk = str(b.get("block_id", ""))
        lu = str(b.get("land_use", ""))
        if blk:
            land_use_by_block.setdefault(blk, set()).add(lu)

    frontage_by_id = {str(f.get("id", "")): f for f in frontages}
    block_poly_by_id = {str(b.get("id", "")): b.get("polygon", []) for b in blocks}

    # 4.2.1(1) Outdoor ground network.
    corner_node_map: Dict[str, str] = {}
    for c in corners:
        pos = c.get("position")
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        nid = outdoor.add_node(
            "corner",
            (float(pos[0]), float(pos[1])),
            corner_type=str(c.get("corner_type", "normal_corner")),
            block_id=str(c.get("block_id", "")),
        )
        corner_node_map[str(c.get("id", ""))] = nid

    # Add transit/external anchor nodes.
    transit_node_ids: List[str] = []
    for kn in key_nodes:
        nt = str(kn.get("node_type", ""))
        if nt not in {"metro_access", "bus_access"}:
            continue
        pos = kn.get("position")
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        nid = outdoor.add_node(nt, (float(pos[0]), float(pos[1])), related_transit_node_id=kn.get("related_transit_node_id"))
        transit_node_ids.append(nid)

    plaza_node_ids: List[str] = []
    for kn in key_nodes:
        if str(kn.get("node_type", "")) != "plaza_center":
            continue
        pos = kn.get("position")
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        plaza_node_ids.append(outdoor.add_node("plaza", (float(pos[0]), float(pos[1])), related_open_space_id=kn.get("related_open_space_id")))

    entrance_outdoor_ids: Dict[str, str] = {}
    for e in entrances:
        pos = e.get("position")
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        fid = str(e.get("served_frontage_id", ""))
        blk = str((frontage_by_id.get(fid) or {}).get("block_id", ""))
        nid = outdoor.add_node(
            "building_entry",
            (float(pos[0]), float(pos[1])),
            building_id=str(e.get("building_id", "")),
            candidate_type=str(e.get("candidate_type", "")),
            candidate_id=str(e.get("id", "")),
            block_id=blk,
        )
        entrance_outdoor_ids[str(e.get("id", ""))] = nid

    for f in frontages:
        fid = str(f.get("id", ""))
        pl = f.get("polyline", [])
        if not (isinstance(pl, list) and len(pl) >= 2):
            continue
        p0 = (float(pl[0][0]), float(pl[0][1]))
        p1 = (float(pl[-1][0]), float(pl[-1][1]))
        n0 = outdoor.add_node("street_edge", p0, frontage_id=fid, block_id=str(f.get("block_id", "")))
        n1 = outdoor.add_node("street_edge", p1, frontage_id=fid, block_id=str(f.get("block_id", "")))

        ft = str(f.get("frontage_type", "back_frontage"))
        lvl = FRONTAGE_TO_LEVEL.get(ft, "back")
        pri = cfg["outdoor"]["back_priority"]
        edge_type = "back_spine"
        if lvl == "main":
            pri = cfg["outdoor"]["primary_priority"]
            edge_type = "main_spine"
        elif lvl == "secondary":
            pri = cfg["outdoor"]["secondary_priority"]
            edge_type = "secondary_spine"

        block_id = str(f.get("block_id", ""))
        lu_set = land_use_by_block.get(block_id, set())
        if lvl == "back":
            has_commercial = any(x in {"B1", "B2"} for x in lu_set)
            has_only_residential = bool(lu_set) and all(x == "R" for x in lu_set)
            if has_only_residential and not bool(cfg["outdoor"]["back_continuity"]["residential"]):
                continue
            if has_commercial and not bool(cfg["outdoor"]["back_continuity"]["commercial"]):
                continue

        outdoor.add_edge(
            n0,
            n1,
            edge_type=edge_type,
            priority=str(pri),
            network_level=lvl,
            continuous=True,
            frontage_id=fid,
            frontage_type=ft,
            block_id=block_id,
            orientation=round(frontage_orientation(f), 3),
        )

    # Assign missing block_id by point-in-polygon, then enforce block-level tree.
    for n in outdoor.nodes:
        if n.get("block_id"):
            continue
        p = n.get("position", [])
        if not (isinstance(p, list) and len(p) >= 2):
            continue
        pt = (float(p[0]), float(p[1]))
        for bid, poly in block_poly_by_id.items():
            if isinstance(poly, list) and len(poly) >= 3 and point_in_polygon(pt, poly):
                n["block_id"] = bid
                break

    # Add street-side nearest anchor per entrance and connect entrance->anchor.
    for e in entrances:
        eid = str(e.get("id", ""))
        enid = entrance_outdoor_ids.get(eid)
        if not enid:
            continue
        en = next((x for x in outdoor.nodes if str(x.get("id", "")) == enid), None)
        if not en:
            continue
        blk = str(en.get("block_id", ""))
        if not blk:
            continue
        ep = (float(en["position"][0]), float(en["position"][1]))
        bfront = [f for f in frontages if str(f.get("block_id", "")) == blk]
        best_pt = None
        best_d = 1e18
        best_lvl = "secondary"
        for f in bfront:
            pl = f.get("polyline", [])
            if not (isinstance(pl, list) and len(pl) >= 2):
                continue
            a = (float(pl[0][0]), float(pl[0][1]))
            b = (float(pl[-1][0]), float(pl[-1][1]))
            q = project_point_to_segment(ep, a, b)
            d = distance(ep, q)
            if d < best_d:
                best_d = d
                best_pt = q
                best_lvl = FRONTAGE_TO_LEVEL.get(str(f.get("frontage_type", "back_frontage")), "back")
        if best_pt is None:
            continue
        anid = outdoor.add_node(
            "street_anchor",
            best_pt,
            block_id=blk,
            network_level_hint=best_lvl,
            source_entrance_id=eid,
        )
        outdoor.add_edge(
            enid,
            anid,
            edge_type="connector",
            priority="high",
            network_level="connector",
            continuous=True,
            block_id=blk,
        )

    # Rebuild outdoor edges as per-block acyclic connected trees.
    block_nodes: Dict[str, List[str]] = {}
    node_pos_map: Dict[str, Tuple[float, float]] = {}
    node_level: Dict[str, str] = {}
    for n in outdoor.nodes:
        nid = str(n.get("id", ""))
        p = n.get("position", [])
        if not nid or not (isinstance(p, list) and len(p) >= 2):
            continue
        node_pos_map[nid] = (float(p[0]), float(p[1]))
        blk = str(n.get("block_id", ""))
        if blk:
            block_nodes.setdefault(blk, []).append(nid)
        node_level[nid] = str(n.get("network_level_hint", "connector"))

    # Keep entrance-anchor edges as hard constraints and then tree-complete.
    fixed_by_block: Dict[str, List[Tuple[str, str]]] = {}
    for e in outdoor.edges:
        if str(e.get("edge_type", "")) != "connector":
            continue
        u = str(e.get("from", ""))
        v = str(e.get("to", ""))
        nu = next((x for x in outdoor.nodes if str(x.get("id", "")) == u), None)
        nv = next((x for x in outdoor.nodes if str(x.get("id", "")) == v), None)
        if not nu or not nv:
            continue
        tu, tv = str(nu.get("node_type", "")), str(nv.get("node_type", ""))
        if {"building_entry", "street_anchor"} == {tu, tv}:
            blk = str(nu.get("block_id", "") or nv.get("block_id", ""))
            if blk:
                fixed_by_block.setdefault(blk, []).append((u, v))

    new_out_edges: List[dict] = []
    level_rank = {"main": 3, "secondary": 2, "back": 1, "connector": 0}
    for blk, nids in block_nodes.items():
        if len(nids) <= 1:
            continue
        dsu = DSU(nids)
        chosen: List[Tuple[str, str]] = []
        for u, v in fixed_by_block.get(blk, []):
            if u in nids and v in nids and dsu.union(u, v):
                chosen.append((u, v))

        pairs: List[Tuple[float, str, str]] = []
        for i in range(len(nids)):
            for j in range(i + 1, len(nids)):
                u, v = nids[i], nids[j]
                pairs.append((distance(node_pos_map[u], node_pos_map[v]), u, v))
        pairs.sort(key=lambda x: x[0])
        for _, u, v in pairs:
            if len(chosen) >= len(nids) - 1:
                break
            if dsu.union(u, v):
                chosen.append((u, v))

        for u, v in chosen:
            lu = node_level.get(u, "connector")
            lv = node_level.get(v, "connector")
            lvl = lu if level_rank.get(lu, 0) >= level_rank.get(lv, 0) else lv
            if lvl == "main":
                et, pr = "main_spine", str(cfg["outdoor"]["primary_priority"])
            elif lvl == "secondary":
                et, pr = "secondary_spine", str(cfg["outdoor"]["secondary_priority"])
            elif lvl == "back":
                et, pr = "back_spine", str(cfg["outdoor"]["back_priority"])
            else:
                et, pr = "connector", "medium"
            eid = f"{outdoor.prefix}_edge_{outdoor._edge_idx:03d}"
            outdoor._edge_idx += 1
            new_out_edges.append({
                "id": eid,
                "from": u,
                "to": v,
                "edge_type": et,
                "length": round(distance(node_pos_map[u], node_pos_map[v]), 4),
                "priority": pr,
                "network_level": lvl,
                "continuous": True,
                "block_id": blk,
            })
    outdoor.edges = new_out_edges

    # 4.2.1(2) Indoor public network.
    entrance_node_indoor: Dict[str, str] = {}
    for bid, entries in ent_by_building.items():
        b = building_by_id.get(bid)
        if not b:
            continue
        lu = str(b.get("land_use", ""))
        btype = str(b.get("building_type", ""))
        entries = sorted(entries, key=lambda x: float(x.get("score", 0.0)), reverse=True)
        if not entries:
            continue

        for e in entries:
            pos = e.get("position", [])
            if not (isinstance(pos, list) and len(pos) >= 2):
                continue
            eid = indoor.add_node("building_entry_indoor", (float(pos[0]), float(pos[1])), building_id=bid, candidate_id=str(e.get("id", "")))
            entrance_node_indoor[str(e.get("id", ""))] = eid

        if (lu == "B1" or btype == "mall") and bool(cfg["indoor"]["mall"]["enabled"]):
            atrs = atrium_by_building.get(bid, [])
            atr_ids = []
            for a in atrs:
                c = poly_center(a.get("polygon", []))
                atr_ids.append(indoor.add_node("atrium_center", c, building_id=bid, related_atrium_id=str(a.get("id", ""))))
            main_entries = [e for e in entries if str(e.get("candidate_type", "")) == "main"] or entries[:1]
            sec_entries = [e for e in entries if str(e.get("candidate_type", "")) in {"secondary", "main"}]
            if atr_ids:
                for e in main_entries:
                    en = entrance_node_indoor.get(str(e.get("id", "")))
                    if en:
                        indoor.add_edge(en, atr_ids[0], edge_type="indoor_main_corridor", priority="high")
                for e in sec_entries[1:]:
                    en = entrance_node_indoor.get(str(e.get("id", "")))
                    if en:
                        indoor.add_edge(en, atr_ids[0], edge_type="indoor_secondary_corridor", priority="medium")
                if bool(cfg["indoor"]["mall"]["connect_atrium_chain"]) and len(atr_ids) > 1:
                    for i in range(len(atr_ids) - 1):
                        indoor.add_edge(atr_ids[i], atr_ids[i + 1], edge_type="indoor_main_corridor", priority="high")

        elif (lu == "B2" or "office" in btype) and bool(cfg["indoor"]["office"]["enabled"]):
            cores_b = core_by_building.get(bid, [])
            if not cores_b:
                continue
            c0 = poly_center(cores_b[0].get("polygon", []))
            core_id = indoor.add_node("office_core_access", c0, building_id=bid, related_core_id=str(cores_b[0].get("id", "")))
            m = entries[0]
            p = (float(m["position"][0]), float(m["position"][1]))
            if bool(cfg["indoor"]["office"]["create_lobby_node"]):
                lobby = ((p[0] + c0[0]) * 0.5, (p[1] + c0[1]) * 0.5)
                lobby_id = indoor.add_node("office_lobby", lobby, building_id=bid)
                en = entrance_node_indoor.get(str(m.get("id", "")))
                if en:
                    indoor.add_edge(en, lobby_id, edge_type="indoor_main_corridor", priority="high")
                indoor.add_edge(lobby_id, core_id, edge_type="indoor_secondary_corridor", priority="medium")
            else:
                en = entrance_node_indoor.get(str(m.get("id", "")))
                if en:
                    indoor.add_edge(en, core_id, edge_type="indoor_main_corridor", priority="high")

        elif lu == "R" and bool(cfg["indoor"]["residential"]["enabled"]):
            if len(entries) >= 2:
                e0 = entrance_node_indoor.get(str(entries[0].get("id", "")))
                e1 = entrance_node_indoor.get(str(entries[1].get("id", "")))
                if e0 and e1:
                    indoor.add_edge(e0, e1, edge_type="indoor_front_band", priority="low")

    # Add service nodes into indoor network.
    for s in services:
        pos = s.get("position", [])
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        indoor.add_node(
            "service_node",
            (float(pos[0]), float(pos[1])),
            service_type=str(s.get("service_type", "")),
            building_id=str(s.get("building_id", "")),
        )

    # Enforce per-building indoor graph = connected acyclic tree + non-crossing in plan.
    indoor_nodes_by_building: Dict[str, List[str]] = {}
    indoor_node_pos: Dict[str, Tuple[float, float]] = {}
    indoor_node_type: Dict[str, str] = {}
    for n in indoor.nodes:
        nid = str(n.get("id", ""))
        bid = str(n.get("building_id", ""))
        p = n.get("position", [])
        if not nid or not bid or not (isinstance(p, list) and len(p) >= 2):
            continue
        indoor_nodes_by_building.setdefault(bid, []).append(nid)
        indoor_node_pos[nid] = (float(p[0]), float(p[1]))
        indoor_node_type[nid] = str(n.get("node_type", ""))

    indoor_new_edges: List[dict] = []
    for bid, nids in indoor_nodes_by_building.items():
        if len(nids) <= 1:
            continue
        root = next((x for x in nids if indoor_node_type.get(x) == "building_entry_indoor"), nids[0])
        tree = build_tree_edges(nids, indoor_node_pos, non_crossing=True, root_id=root)
        for u, v in tree:
            tu = indoor_node_type.get(u, "")
            tv = indoor_node_type.get(v, "")
            if "service" in tu or "service" in tv:
                et, pr = "indoor_service_link", "low"
            elif ("entry" in tu and ("atrium" in tv or "lobby" in tv or "core" in tv)) or ("entry" in tv and ("atrium" in tu or "lobby" in tu or "core" in tu)):
                et, pr = "indoor_main_corridor", "high"
            else:
                et, pr = "indoor_secondary_corridor", "medium"
            eid = f"{indoor.prefix}_edge_{indoor._edge_idx:03d}"
            indoor._edge_idx += 1
            indoor_new_edges.append({
                "id": eid,
                "from": u,
                "to": v,
                "edge_type": et,
                "length": round(distance(indoor_node_pos[u], indoor_node_pos[v]), 4),
                "priority": pr,
                "building_id": bid,
            })
    indoor.edges = indoor_new_edges

    # 4.2.1(3) Vertical transition network.
    mall_mode = str(cfg["vertical"]["connector_modes"]["mall_default"])
    office_mode = str(cfg["vertical"]["connector_modes"]["office_default"])
    metro_mode = str(cfg["vertical"]["connector_modes"]["metro_default"])

    has_large_mall = any(str(b.get("land_use", "")) == "B1" and float(b.get("height", 0.0)) >= 24.0 for b in masses)
    has_metro_access = any(str(n.get("node_type", "")) == "metro_access" for n in key_nodes)

    for a in atriums:
        c = poly_center(a.get("polygon", []))
        nid = vertical.add_node(
            "vertical_connector_reserved",
            c,
            connector_mode=mall_mode,
            building_id=str(a.get("building_id", "")),
            related_atrium_id=str(a.get("id", "")),
        )
        # Anchor to nearest indoor node.
        cands = indoor.node_items()
        nn = nearest(c, cands)
        if nn:
            np = next((p for i, p in cands if i == nn), None)
            if np is not None:
                off = float(cfg["global"]["merge_node_distance_m"]) + 0.2
                an = vertical.add_node("ground_anchor_indoor", (np[0] + off, np[1]), source_network_node_id=nn)
                vertical.add_edge(nid, an, edge_type="vertical_anchor", priority="high")

    for c0 in cores:
        c = poly_center(c0.get("polygon", []))
        nid = vertical.add_node(
            "vertical_connector_reserved",
            c,
            connector_mode=office_mode,
            building_id=str(c0.get("building_id", "")),
            related_core_id=str(c0.get("id", "")),
        )
        nn = nearest(c, indoor.node_items())
        if nn:
            cands = indoor.node_items()
            np = next((p for i, p in cands if i == nn), None)
            if np is not None:
                off = float(cfg["global"]["merge_node_distance_m"]) + 0.2
                an = vertical.add_node("ground_anchor_indoor", (np[0] + off, np[1]), source_network_node_id=nn)
                vertical.add_edge(nid, an, edge_type="vertical_anchor", priority="medium")

    for n in key_nodes:
        if str(n.get("node_type", "")) != "metro_access":
            continue
        pos = n.get("position", [])
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        c = (float(pos[0]), float(pos[1]))
        nid = vertical.add_node("metro_gate_connection", c, connector_mode=metro_mode, related_transit_node_id=n.get("related_transit_node_id"))
        nn = nearest(c, outdoor.node_items())
        if nn:
            cands = outdoor.node_items()
            np = next((p for i, p in cands if i == nn), None)
            if np is not None:
                off = float(cfg["global"]["merge_node_distance_m"]) + 0.2
                an = vertical.add_node("ground_anchor_outdoor", (np[0] + off, np[1]), source_network_node_id=nn)
                vertical.add_edge(nid, an, edge_type="vertical_anchor", priority="high")

    # Optional 2F/B1 reserved networks.
    if bool(cfg["vertical"]["generate_level2_when"]["require_large_mall"]) and has_large_mall:
        for vn in vertical.nodes:
            if str(vn.get("connector_mode", "")) in {"escalator", "stair"}:
                c = (float(vn["position"][0]), float(vn["position"][1]))
                level2.add_node("level2_access", c, source_vertical_node_id=str(vn["id"]))
        ids = [str(n["id"]) for n in level2.nodes]
        for i in range(len(ids) - 1):
            level2.add_edge(ids[i], ids[i + 1], edge_type="level2_link", priority="medium")

    if bool(cfg["vertical"]["generate_b1_when"]["require_metro_access"]) and has_metro_access:
        for vn in vertical.nodes:
            if str(vn.get("node_type", "")) in {"metro_gate_connection", "vertical_connector_reserved"}:
                c = (float(vn["position"][0]), float(vn["position"][1]))
                b1.add_node("basement_access", c, source_vertical_node_id=str(vn["id"]))
        ids = [str(n["id"]) for n in b1.nodes]
        for i in range(len(ids) - 1):
            b1.add_edge(ids[i], ids[i + 1], edge_type="basement_link", priority="medium")

    # 4.2.2 Circulation skeleton.
    main_spines: List[dict] = []
    secondary_spines: List[dict] = []
    threshold_spines: List[dict] = []
    vertical_spines: List[dict] = []
    node_centers: List[dict] = []

    spine_idx = 1
    for e in outdoor.edges:
        p0 = outdoor.node_pos(str(e["from"]))
        p1 = outdoor.node_pos(str(e["to"]))
        if p0 is None or p1 is None:
            continue
        poly = [[round(p0[0], 4), round(p0[1], 4)], [round(p1[0], 4), round(p1[1], 4)]]
        if str(e.get("edge_type", "")) == "main_spine":
            main_spines.append({"id": f"spine_{spine_idx:03d}", "polyline": poly, "spine_type": "main"})
            spine_idx += 1
        elif str(e.get("edge_type", "")) in {"secondary_spine", "connector"}:
            secondary_spines.append({"id": f"spine_{spine_idx:03d}", "polyline": poly, "spine_type": "secondary"})
            spine_idx += 1

    for e in indoor.edges:
        p0 = indoor.node_pos(str(e["from"]))
        p1 = indoor.node_pos(str(e["to"]))
        if p0 is None or p1 is None:
            continue
        et = str(e.get("edge_type", ""))
        poly = [[round(p0[0], 4), round(p0[1], 4)], [round(p1[0], 4), round(p1[1], 4)]]
        if et in {"indoor_main_corridor"}:
            main_spines.append({"id": f"spine_{spine_idx:03d}", "polyline": poly, "spine_type": "main"})
            spine_idx += 1
        elif et in {"indoor_secondary_corridor", "indoor_front_band", "indoor_service_link"}:
            secondary_spines.append({"id": f"spine_{spine_idx:03d}", "polyline": poly, "spine_type": "secondary"})
            spine_idx += 1

    # Threshold links between each entrance outdoor node and indoor counterpart.
    th_max = float(cfg["skeleton"]["threshold_link_max_distance_m"])
    for e in entrances:
        eid = str(e.get("id", ""))
        out_id = entrance_outdoor_ids.get(eid)
        in_id = entrance_node_indoor.get(eid)
        if not out_id or not in_id:
            continue
        p0 = outdoor.node_pos(out_id)
        p1 = indoor.node_pos(in_id)
        if p0 is None or p1 is None:
            continue
        if distance(p0, p1) <= th_max:
            threshold_spines.append({
                "id": f"spine_{spine_idx:03d}",
                "polyline": [[round(p0[0], 4), round(p0[1], 4)], [round(p1[0], 4), round(p1[1], 4)]],
                "spine_type": "threshold",
            })
            spine_idx += 1

    for n in vertical.nodes:
        p = (float(n["position"][0]), float(n["position"][1]))
        vertical_spines.append({
            "id": f"spine_{spine_idx:03d}",
            "polyline": [[round(p[0], 4), round(p[1], 4)], [round(p[0], 4), round(p[1], 4)]],
            "spine_type": "vertical",
        })
        spine_idx += 1

    include_center_types = set(cfg["skeleton"]["include_node_centers_from"])
    for n in key_nodes:
        nt = str(n.get("node_type", ""))
        if nt not in include_center_types:
            continue
        pos = n.get("position")
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        node_centers.append({
            "id": f"center_{len(node_centers) + 1:03d}",
            "center_type": nt,
            "position": [round(float(pos[0]), 4), round(float(pos[1]), 4)],
            "source_node_id": str(n.get("id", "")),
        })

    return {
        "circulation_networks": {
            "ground_outdoor": {"nodes": outdoor.nodes, "edges": outdoor.edges},
            "ground_indoor_public": {"nodes": indoor.nodes, "edges": indoor.edges},
            "vertical_transition": {"nodes": vertical.nodes, "edges": vertical.edges},
            "level2_reserved": {"nodes": level2.nodes, "edges": level2.edges},
            "basement_reserved": {"nodes": b1.nodes, "edges": b1.edges},
        },
        "circulation_skeleton": {
            "main_spines": main_spines,
            "secondary_spines": secondary_spines,
            "threshold_spines": threshold_spines,
            "vertical_spines": vertical_spines,
            "node_centers": node_centers,
        },
        "metadata": {
            "generator": "generate_step4_pedestrian_network.py",
            "outdoor_node_count": len(outdoor.nodes),
            "outdoor_edge_count": len(outdoor.edges),
            "indoor_node_count": len(indoor.nodes),
            "indoor_edge_count": len(indoor.edges),
            "vertical_node_count": len(vertical.nodes),
            "vertical_edge_count": len(vertical.edges),
            "has_large_mall": has_large_mall,
            "has_metro_access": has_metro_access,
            "seed": int(cfg["global"]["random_seed"]),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Step4 Pedestrian Topology Generator")
    parser.add_argument("--input", default="step3_generated_scene.json", help="input scene json with step_3_key_nodes")
    parser.add_argument("--output", default="step4_generated_scene.json", help="output scene json")
    parser.add_argument("--typology", default="default_pedestrian_network.yaml", help="typology yaml")
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
    for req in ["step_1_network", "step_2_massing", "step_3_key_nodes"]:
        if req not in generated:
            raise ValueError(f"generated.{req} not found in input scene")

    generated["step_4_topology"] = generate_step4(scene, cfg)
    scene["generated"] = generated

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(_format_json_compact(scene) + "\n")

    s4 = generated["step_4_topology"]
    gn = ((s4.get("circulation_networks", {}) or {}).get("ground_outdoor", {}) or {})
    gi = ((s4.get("circulation_networks", {}) or {}).get("ground_indoor_public", {}) or {})
    vv = ((s4.get("circulation_networks", {}) or {}).get("vertical_transition", {}) or {})
    sk = s4.get("circulation_skeleton", {}) or {}
    print("[Summary]")
    print(f"  outdoor_nodes: {len(gn.get('nodes', []) or [])}")
    print(f"  outdoor_edges: {len(gn.get('edges', []) or [])}")
    print(f"  indoor_nodes: {len(gi.get('nodes', []) or [])}")
    print(f"  indoor_edges: {len(gi.get('edges', []) or [])}")
    print(f"  vertical_nodes: {len(vv.get('nodes', []) or [])}")
    print(f"  vertical_edges: {len(vv.get('edges', []) or [])}")
    print(f"  main_spines: {len(sk.get('main_spines', []) or [])}")
    print(f"  secondary_spines: {len(sk.get('secondary_spines', []) or [])}")
    print(f"  threshold_spines: {len(sk.get('threshold_spines', []) or [])}")
    print(f"  vertical_spines: {len(sk.get('vertical_spines', []) or [])}")
    print(f"[Done] wrote: {out_path}")


if __name__ == "__main__":
    main()
