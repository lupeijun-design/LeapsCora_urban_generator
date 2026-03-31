"""
render_scene_full.py

Usage:
1) Blender UI: run this script in Scripting workspace.
2) CLI:
   blender --background --python render_scene_full.py -- sample_scene_full.json 111111

Mask bits:
1:step_1_network 2:step_2_massing 3:step_3_key_nodes
4:step_4_topology 5:step_5_spaces 6:step_6_functionalization
"""

import json, math, os, sys
from typing import Dict, List, Optional, Sequence, Tuple

import bpy, bmesh
from mathutils import Vector

JSON_PATH = None
STEP_MASK = None
CLEANUP = True
ADD_GROUND = True
AUTO_FRAME = True
STEP_COLOR_MODE = True
STEP_TINT_STRENGTH = 1.0
ACTIVE_STEP = None

STEPS = [
    "step_1_network",
    "step_2_massing",
    "step_3_key_nodes",
    "step_4_topology",
    "step_5_spaces",
    "step_6_functionalization",
]
STEP_COL = {
    "step_1_network": "Step1_Network",
    "step_2_massing": "Step2_Massing",
    "step_3_key_nodes": "Step3_KeyNodes",
    "step_4_topology": "Step4_Topology",
    "step_5_spaces": "Step5_Spaces",
    "step_6_functionalization": "Step6_Functionalization",
}
STEP_TINT = {
    "step_1_network": (0.90, 0.42, 0.28),
    "step_2_massing": (0.98, 0.74, 0.22),
    "step_3_key_nodes": (0.30, 0.82, 0.46),
    "step_4_topology": (0.24, 0.62, 0.96),
    "step_5_spaces": (0.57, 0.50, 0.95),
    "step_6_functionalization": (0.96, 0.35, 0.72),
}

PALETTE = {
    "building_facade_commercial": (0.76, 0.73, 0.69, 1.0),
    "building_facade_office": (0.60, 0.67, 0.75, 1.0),
    "building_facade_residential": (0.80, 0.76, 0.72, 1.0),
    "pavement_main": (0.40, 0.40, 0.40, 1.0),
    "indoor_floor_mall": (0.60, 0.56, 0.50, 1.0),
    "indoor_floor_office": (0.53, 0.56, 0.60, 1.0),
    "urban_furniture_default": (0.30, 0.28, 0.25, 1.0),
    "plaza_default": (0.54, 0.51, 0.47, 1.0),
    "atrium_default": (0.77, 0.72, 0.63, 1.0),
    "functional_zone_overlay": (0.95, 0.45, 0.20, 0.40),
    "node_space_default": (0.20, 0.55, 0.78, 1.0),
    "block_outline": (0.12, 0.12, 0.12, 1.0),
    "block_ground": (0.28, 0.28, 0.28, 1.0),
    "frontage_primary": (0.95, 0.90, 0.25, 1.0),
    "frontage_secondary": (0.20, 0.78, 0.80, 1.0),
    "frontage_back": (0.65, 0.65, 0.65, 1.0),
    "transit_overlay": (0.15, 0.80, 0.30, 0.35),
    "buildable_overlay": (0.40, 0.85, 0.40, 0.25),
    "core_default": (0.25, 0.35, 0.45, 1.0),
    "podium_default": (0.83, 0.56, 0.36, 1.0),
    "node_marker": (0.90, 0.20, 0.25, 1.0),
    "edge_default": (0.95, 0.95, 0.95, 1.0),
    "spine_main": (1.00, 0.85, 0.20, 1.0),
    "spine_secondary": (0.22, 0.85, 0.90, 1.0),
    "spine_threshold": (1.00, 0.50, 0.20, 1.0),
    "spine_vertical": (0.90, 0.35, 0.95, 1.0),
    "restricted_overlay": (0.95, 0.10, 0.10, 0.35),
}

WALK_MAT = {
    "street_clear_path": "pavement_main",
    "entrance_threshold": "pavement_main",
    "indoor_public_corridor": "indoor_floor_mall",
    "semi_public_frontage_band": "pavement_main",
    "lobby_space": "indoor_floor_office",
    "atrium_spillout": "atrium_default",
}
BLD_MAT = {"mall": "building_facade_commercial", "office": "building_facade_office", "residential": "building_facade_residential"}
ELEMENT_DIMS = {
    "bench": (1.6, 0.5, 0.5), "signage": (0.2, 0.8, 2.2), "planter": (1.0, 1.0, 0.6),
    "parcel_locker": (1.6, 0.6, 2.0), "frontdesk": (2.2, 0.8, 1.1), "awning": (2.5, 0.6, 0.25), "bollard": (0.3, 0.3, 1.0),
}
SERVICE_TO_ELEMENT = {"pickup_node": "signage", "delivery_node": "signage", "property_frontdesk": "frontdesk", "parcel_locker": "parcel_locker", "loading_point": "bollard", "waiting_node": "bench"}


def load_json(path: str) -> dict:
    print(f"[Load] Reading JSON: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_col(name: str, parent: Optional[bpy.types.Collection] = None) -> bpy.types.Collection:
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    p = parent or bpy.context.scene.collection
    if c.name not in p.children:
        p.children.link(c)
    return c


def clear_col(c: bpy.types.Collection) -> None:
    for o in list(c.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def make_mat(name: str, rgba=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    color = rgba or PALETTE.get(name, (0.8, 0.8, 0.8, 1.0))
    if m.node_tree is None:
        try:
            m.use_nodes = True
        except Exception:
            return m
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        n = m.node_tree.nodes
        l = m.node_tree.links
        n.clear()
        bsdf = n.new(type="ShaderNodeBsdfPrincipled")
        out = n.new(type="ShaderNodeOutputMaterial")
        l.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = color
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = color[3]
    if color[3] < 1.0:
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "BLENDED"
        elif hasattr(m, "blend_method"):
            m.blend_method = "BLEND"
        if hasattr(m, "shadow_method"):
            m.shadow_method = "NONE"
    return m


def set_mat(obj, name: str):
    m = make_step_mat(name, ACTIVE_STEP) if STEP_COLOR_MODE and ACTIVE_STEP else make_mat(name)
    if hasattr(obj.data, "materials"):
        if obj.data.materials:
            obj.data.materials[0] = m
        else:
            obj.data.materials.append(m)


def _blend_rgb(a, b, t):
    return (a[0] * (1.0 - t) + b[0] * t, a[1] * (1.0 - t) + b[1] * t, a[2] * (1.0 - t) + b[2] * t)


def make_step_mat(base_name: str, step_name: str):
    key = f"{base_name}__{step_name}"
    m = bpy.data.materials.get(key)
    if m is not None:
        return m

    base_rgba = PALETTE.get(base_name, (0.8, 0.8, 0.8, 1.0))
    tint = STEP_TINT.get(step_name, (0.8, 0.8, 0.8))
    rgb = _blend_rgb(base_rgba[:3], tint, STEP_TINT_STRENGTH)
    rgba = (rgb[0], rgb[1], rgb[2], base_rgba[3])
    return make_mat(key, rgba)


def ring(poly):
    pts = [(float(p[0]), float(p[1])) for p in (poly or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    out = []
    for p in pts:
        if not out or p != out[-1]:
            out.append(p)
    return out


def line(poly):
    out = []
    for p in (poly or []):
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            q = (float(p[0]), float(p[1]))
            if not out or q != out[-1]:
                out.append(q)
    return out


def poly_mesh(name, poly, z=0.0):
    pts = ring(poly)
    if len(pts) < 3:
        return None
    me = bpy.data.meshes.new(f"{name}_Mesh")
    o = bpy.data.objects.new(name, me)
    me.from_pydata([(x, y, z) for x, y in pts], [], [list(range(len(pts)))])
    me.update()
    return o


def polyline_curve(name, poly, z=0.05, w=0.03):
    pts = line(poly)
    if len(pts) < 2:
        return None
    cu = bpy.data.curves.new(f"{name}_Curve", type="CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new(type="POLY")
    sp.points.add(len(pts) - 1)
    for i, (x, y) in enumerate(pts):
        sp.points[i].co = (x, y, z, 1.0)
    cu.bevel_depth = w
    return bpy.data.objects.new(name, cu)


def extrude(name, poly, h):
    pts = ring(poly)
    if len(pts) < 3:
        return None
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, 0.0)) for x, y in pts]
    try:
        f = bm.faces.new(vs)
    except ValueError:
        bmesh.ops.contextual_create(bm, geom=vs)
        if not bm.faces:
            bm.free()
            return None
        f = bm.faces[0]
    ex = bmesh.ops.extrude_face_region(bm, geom=[f])
    v2 = [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, 0.0, float(h)), verts=v2)
    me = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def box(name, dims, loc, rz=0.0):
    dx, dy, dz = dims
    hx, hy, hz = dx * 0.5, dy * 0.5, dz * 0.5
    verts = [(-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),(-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz)]
    faces = [[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    me = bpy.data.meshes.new(f"{name}_Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = (0.0, 0.0, float(rz))
    return o


def marker(name, pos, size=0.8, z=0.02):
    h = max(size * 0.35, 0.2)
    return box(name, (size, size, h), (float(pos[0]), float(pos[1]), z + h * 0.5), 0.0)


def element(name, etype, pos, rot=0.0):
    dims = ELEMENT_DIMS.get(etype, (1.0, 1.0, 1.0))
    z = 2.6 if etype == "awning" else dims[2] * 0.5
    return box(name, dims, (float(pos[0]), float(pos[1]), z), rot)


def link(o, c):
    if o.name not in c.objects:
        c.objects.link(o)
    for u in list(o.users_collection):
        if u != c:
            u.objects.unlink(o)


def sem_index(data: dict) -> Dict[str, List[str]]:
    s = data.get("semantics", {}) or {}
    idx: Dict[str, List[str]] = {}
    for k, items in s.items():
        if not k.endswith("_labels"):
            continue
        for it in items or []:
            t = it.get("target_id")
            l = it.get("label")
            if t and l:
                idx.setdefault(str(t), []).append(str(l))
    for k, v in list(idx.items()):
        idx[k] = list(dict.fromkeys(v))
    return idx


def attach(o, target_id: str, idx: Dict[str, List[str]]):
    ls = idx.get(target_id)
    if ls:
        o["semantic_label"] = ",".join(ls)


def mat_for(item_id: str, default: str, rb: dict) -> str:
    return str((rb.get("material_classes", {}) or {}).get(item_id, default))


def meta(o, item_id: str, rb: dict):
    ac = (rb.get("asset_classes", {}) or {}).get(item_id)
    st = (rb.get("style_tags", {}) or {}).get(item_id)
    if ac is not None:
        o["asset_class"] = str(ac)
    if st is not None:
        o["style_tags"] = ",".join(map(str, st)) if isinstance(st, list) else str(st)


def parse_mask(mask: Optional[str]) -> Dict[str, bool]:
    m = mask or "111111"
    if any(ch not in "01" for ch in m):
        raise ValueError(f"Invalid step mask: {m}")
    m = (m + "000000")[:6]
    return {STEPS[i]: m[i] == "1" for i in range(6)}


def bounds(objs):
    if not objs:
        return None
    mn = [math.inf, math.inf, math.inf]
    mx = [-math.inf, -math.inf, -math.inf]
    for o in objs:
        if o.type not in {"MESH", "CURVE"}:
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn[0], mn[1], mn[2] = min(mn[0], w.x), min(mn[1], w.y), min(mn[2], w.z)
            mx[0], mx[1], mx[2] = max(mx[0], w.x), max(mx[1], w.y), max(mx[2], w.z)
    if math.isinf(mn[0]):
        return None
    return (tuple(mn), tuple(mx))


def cam_light(b):
    sc = bpy.context.scene
    sun = bpy.data.objects.get("PreviewSun")
    if sun is None:
        sd = bpy.data.lights.new("PreviewSun", "SUN")
        sd.energy = 3.2
        sun = bpy.data.objects.new("PreviewSun", sd)
        sc.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 120.0)
    sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))

    cam = bpy.data.objects.get("PreviewCamera")
    if cam is None:
        cd = bpy.data.cameras.new("PreviewCamera")
        cam = bpy.data.objects.new("PreviewCamera", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
    if not b:
        cam.location = (60.0, -140.0, 80.0)
        cam.rotation_euler = (math.radians(65), 0.0, math.radians(30))
        return
    (minx, miny, _), (maxx, maxy, maxz) = b
    cx, cy = (minx + maxx) * 0.5, (miny + maxy) * 0.5
    e = max(maxx - minx, maxy - miny, 20.0)
    cam.location = (cx + e * 0.4, cy - e * 1.2, maxz + e * 0.75)
    cam.rotation_euler = (math.radians(62), 0.0, math.radians(30))

def gen_step1(data, col, created, sidx, rb):
    c = 0
    print("[Generate] step_1_network")
    for it in data.get("block_boundaries", []) or []:
        i, poly = it.get("id"), it.get("polygon")
        if not i or not poly:
            continue
        f = poly_mesh(f"Block_{i}", poly, 0.0)
        if f:
            link(f, col); set_mat(f, "block_ground"); f["source_id"] = i; attach(f, i, sidx); created.append(f); c += 1
        o = polyline_curve(f"BlockOutline_{i}", poly, 0.03, 0.03)
        if o:
            link(o, col); set_mat(o, "block_outline"); o["source_id"] = i; created.append(o)

    for it in data.get("frontage_segments", []) or []:
        i, pl = it.get("id"), it.get("polyline")
        if not i or not pl:
            continue
        o = polyline_curve(f"Frontage_{i}", pl, 0.05, 0.025)
        if not o:
            continue
        ft = str(it.get("frontage_type", "secondary_frontage"))
        mat = "frontage_primary" if ft == "primary_frontage" else ("frontage_back" if ft == "back_frontage" else "frontage_secondary")
        link(o, col); set_mat(o, mat); o["source_id"] = i; o["frontage_type"] = ft; created.append(o)

    for it in data.get("corners", []) or []:
        i, p = it.get("id"), it.get("position")
        if not i or not isinstance(p, list) or len(p) < 2:
            continue
        o = marker(f"Corner_{i}", p, 1.0, 0.02)
        link(o, col); set_mat(o, "node_marker"); o["source_id"] = i; o["corner_type"] = str(it.get("corner_type", "corner")); created.append(o)

    for it in data.get("transit_influence_zones", []) or []:
        i, poly = it.get("id"), it.get("polygon")
        if not i or not poly:
            continue
        o = poly_mesh(f"TransitZone_{i}", poly, 0.07)
        if o:
            link(o, col); set_mat(o, "transit_overlay"); o["source_id"] = i; created.append(o)
    return c


def gen_step2(data, col, created, sidx, rb):
    c = 0
    print("[Generate] step_2_massing")
    for it in data.get("buildable_zones", []) or []:
        i, poly = it.get("id"), it.get("polygon")
        if i and poly:
            o = poly_mesh(f"Buildable_{i}", poly, 0.015)
            if o:
                link(o, col); set_mat(o, "buildable_overlay"); o["source_id"] = i; created.append(o)

    for it in data.get("building_masses", []) or []:
        i, fp = it.get("id"), it.get("footprint")
        if not i or not fp:
            continue
        o = extrude(f"Bld_{i}", fp, float(it.get("height", 12.0)))
        if not o:
            continue
        bt = str(it.get("building_type", "commercial"))
        link(o, col); set_mat(o, mat_for(i, BLD_MAT.get(bt, "building_facade_commercial"), rb))
        o["source_id"] = i; o["building_type"] = bt; meta(o, i, rb); attach(o, i, sidx); created.append(o); c += 1

    for key, z, dmat, pref in [
        ("atriums", 0.08, "atrium_default", "Atrium"),
        ("cores", 0.09, "core_default", "Core"),
        ("podium_retail_bands", 0.10, "podium_default", "PodiumBand"),
        ("reserved_open_spaces", 0.02, "plaza_default", "Open"),
    ]:
        for it in data.get(key, []) or []:
            i, poly = it.get("id"), it.get("polygon")
            if not i or not poly:
                continue
            o = poly_mesh(f"{pref}_{i}", poly, z)
            if not o:
                continue
            link(o, col); set_mat(o, mat_for(i, dmat, rb)); o["source_id"] = i; meta(o, i, rb); created.append(o)
    return c


def gen_step3(data, col, created, sidx, rb):
    print("[Generate] step_3_key_nodes")
    c = 0
    for it in data.get("key_nodes", []) or []:
        i, p = it.get("id"), it.get("position")
        if not i or not isinstance(p, list) or len(p) < 2:
            continue
        o = marker(f"KeyNode_{i}", p, 0.9, 0.12)
        link(o, col); set_mat(o, "node_marker"); o["source_id"] = i; o["node_type"] = str(it.get("node_type", "key_node")); attach(o, i, sidx); created.append(o); c += 1

    for it in data.get("entrance_candidates", []) or []:
        i, p = it.get("id"), it.get("position")
        if not i or not isinstance(p, list) or len(p) < 2:
            continue
        o = box(f"EntranceCand_{i}", (0.5, 0.5, 1.8), (float(p[0]), float(p[1]), 0.9), 0.0)
        link(o, col); set_mat(o, "frontage_primary"); o["source_id"] = i; o["candidate_type"] = str(it.get("candidate_type", "candidate")); attach(o, i, sidx); created.append(o)

    for it in data.get("service_nodes", []) or []:
        i, p = it.get("id"), it.get("position")
        if not i or not isinstance(p, list) or len(p) < 2:
            continue
        st = str(it.get("service_type", "service_node"))
        o = element(f"Service_{i}", SERVICE_TO_ELEMENT.get(st, "bench"), p, 0.0)
        link(o, col); set_mat(o, "urban_furniture_default"); o["source_id"] = i; o["service_type"] = st; attach(o, i, sidx); created.append(o)
    return c


def gen_step4(data, col, created, sidx, rb):
    print("[Generate] step_4_topology")
    c = 0
    circs = data.get("circulation_networks", {}) or {}
    for net_name, net in circs.items():
        nmap = {}
        for n in net.get("nodes", []) or []:
            i, p = n.get("id"), n.get("position")
            if not i or not isinstance(p, list) or len(p) < 2:
                continue
            nmap[i] = p
            o = marker(f"TopoNode_{i}", p, 0.6, 0.14)
            link(o, col); set_mat(o, "node_marker"); o["source_id"] = i; o["topology_network"] = net_name; attach(o, i, sidx); created.append(o); c += 1

        for e in net.get("edges", []) or []:
            i, a, b = e.get("id"), e.get("from"), e.get("to")
            if not i or a not in nmap or b not in nmap:
                continue
            o = polyline_curve(f"TopoEdge_{i}", [nmap[a], nmap[b]], 0.16, 0.02)
            if o:
                link(o, col); set_mat(o, "edge_default"); o["source_id"] = i; o["edge_type"] = str(e.get("edge_type", "edge")); created.append(o)

    sk = data.get("circulation_skeleton", {}) or {}
    for grp, mat in [("main_spines", "spine_main"), ("secondary_spines", "spine_secondary"), ("threshold_spines", "spine_threshold"), ("vertical_spines", "spine_vertical")]:
        for it in sk.get(grp, []) or []:
            i, pl = it.get("id"), it.get("polyline")
            if not i or not pl:
                continue
            o = polyline_curve(f"Spine_{i}", pl, 0.18, 0.03)
            if o:
                link(o, col); set_mat(o, mat); o["source_id"] = i; o["spine_type"] = str(it.get("spine_type", "spine")); created.append(o)
    return c


def gen_step5(data, col, created, sidx, rb):
    print("[Generate] step_5_spaces")
    c = 0
    for it in data.get("walkable_spaces", []) or []:
        i, poly = it.get("id"), it.get("polygon")
        if not i or not poly:
            continue
        o = poly_mesh(f"Walk_{i}", poly, 0.03)
        if not o:
            continue
        st = str(it.get("space_type", "street_clear_path"))
        link(o, col); set_mat(o, mat_for(i, WALK_MAT.get(st, "pavement_main"), rb))
        o["source_id"] = i; o["space_type"] = st; meta(o, i, rb); attach(o, i, sidx); created.append(o); c += 1

    for it in data.get("node_spaces", []) or []:
        i, poly = it.get("id"), it.get("polygon")
        if not i or not poly:
            continue
        o = poly_mesh(f"NodeSpace_{i}", poly, 0.04)
        if o:
            link(o, col); set_mat(o, mat_for(i, "node_space_default", rb)); o["source_id"] = i; o["node_space_type"] = str(it.get("node_space_type", "node_space")); meta(o, i, rb); attach(o, i, sidx); created.append(o)
    return c


def gen_step6(data, col, created, sidx, rb, semantics):
    print("[Generate] step_6_functionalization")
    c = 0
    for it in data.get("functional_zones", []) or []:
        i, poly = it.get("id"), it.get("polygon")
        if not i or not poly:
            continue
        o = poly_mesh(f"FZone_{i}", poly, 0.06)
        if o:
            link(o, col); set_mat(o, mat_for(i, "functional_zone_overlay", rb)); o["source_id"] = i; o["zone_type"] = str(it.get("zone_type", "functional_zone")); meta(o, i, rb); attach(o, i, sidx); created.append(o)

    for it in data.get("placed_elements", []) or []:
        i, et, p = it.get("id"), str(it.get("element_type", "bench")), it.get("position")
        if not i or not isinstance(p, list) or len(p) < 2:
            continue
        o = element(f"Elem_{i}", et, p, float(it.get("rotation", 0.0)))
        link(o, col); set_mat(o, mat_for(i, "urban_furniture_default", rb)); o["source_id"] = i; o["element_type"] = et; meta(o, i, rb); attach(o, i, sidx); created.append(o); c += 1

    for ra in (semantics.get("restricted_areas", []) or []):
        i, poly = ra.get("id"), ra.get("polygon")
        if not i or not poly:
            continue
        o = poly_mesh(f"Restricted_{i}", poly, 0.09)
        if o:
            link(o, col); set_mat(o, "restricted_overlay"); o["source_id"] = i; o["restricted_reason"] = str(ra.get("reason", "restricted")); created.append(o)
    return c


def run(json_path: str, mask: Optional[str]):
    global ACTIVE_STEP
    data = load_json(json_path)
    for k in ["schema_version", "scene_info", "generated", "semantics", "render_bindings"]:
        if k not in data:
            raise ValueError(f"Missing required key: {k}")
    gen = data.get("generated", {}) or {}
    rb = data.get("render_bindings", {}) or {}
    semantics = data.get("semantics", {}) or {}
    sidx = sem_index(data)
    enabled = parse_mask(mask)
    print("[Config] Step mask:", "".join("1" if enabled[s] else "0" for s in STEPS))

    root = ensure_col("UrbanPreview")
    cols = {s: ensure_col(STEP_COL[s], root) for s in STEPS}
    if CLEANUP:
        print("[Cleanup] Removing old generated objects")
        for c in cols.values():
            clear_col(c)
    for n, rgba in PALETTE.items():
        make_mat(n, rgba)

    created = []
    counts = {"blocks": 0, "buildings": 0, "walkable_spaces": 0, "elements": 0}
    if enabled["step_1_network"] and "step_1_network" in gen:
        ACTIVE_STEP = "step_1_network"
        counts["blocks"] += gen_step1(gen["step_1_network"], cols["step_1_network"], created, sidx, rb)
    if enabled["step_2_massing"] and "step_2_massing" in gen:
        ACTIVE_STEP = "step_2_massing"
        counts["buildings"] += gen_step2(gen["step_2_massing"], cols["step_2_massing"], created, sidx, rb)
    if enabled["step_3_key_nodes"] and "step_3_key_nodes" in gen:
        ACTIVE_STEP = "step_3_key_nodes"
        gen_step3(gen["step_3_key_nodes"], cols["step_3_key_nodes"], created, sidx, rb)
    if enabled["step_4_topology"] and "step_4_topology" in gen:
        ACTIVE_STEP = "step_4_topology"
        gen_step4(gen["step_4_topology"], cols["step_4_topology"], created, sidx, rb)
    if enabled["step_5_spaces"] and "step_5_spaces" in gen:
        ACTIVE_STEP = "step_5_spaces"
        counts["walkable_spaces"] += gen_step5(gen["step_5_spaces"], cols["step_5_spaces"], created, sidx, rb)
    if enabled["step_6_functionalization"] and "step_6_functionalization" in gen:
        ACTIVE_STEP = "step_6_functionalization"
        counts["elements"] += gen_step6(gen["step_6_functionalization"], cols["step_6_functionalization"], created, sidx, rb, semantics)

    b = bounds(created)
    if ADD_GROUND and b:
        ACTIVE_STEP = "step_1_network"
        (minx, miny, _), (maxx, maxy, _) = b
        poly = [(minx - 20, miny - 20), (maxx + 20, miny - 20), (maxx + 20, maxy + 20), (minx - 20, maxy + 20), (minx - 20, miny - 20)]
        g = poly_mesh("GroundPlane", poly, -0.02)
        if g:
            link(g, cols["step_1_network"]); set_mat(g, "pavement_main"); created.append(g); b = bounds(created)
    if AUTO_FRAME:
        cam_light(b)
    ACTIVE_STEP = None

    print("[Summary]")
    print(f"  blocks: {counts['blocks']}")
    print(f"  buildings: {counts['buildings']}")
    print(f"  walkable_spaces: {counts['walkable_spaces']}")
    print(f"  elements: {counts['elements']}")
    print("[Done] Full scene generation completed")


def resolve_inputs():
    path, mask = JSON_PATH, STEP_MASK
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if args and not path:
            path = args[0]
        if len(args) > 1 and not mask:
            mask = args[1]
    if not path:
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base = bpy.path.abspath("//")
        path = os.path.join(base, "sample_scene_full.json")
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    return path, mask


def main():
    path, mask = resolve_inputs()
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input JSON not found: {path}")
    run(path, mask)


if __name__ == "__main__":
    main()
