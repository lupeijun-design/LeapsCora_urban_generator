"""
render_step4_result.py

Usage:
1) Blender UI:
   - Open and run in Scripting workspace.
2) Command line:
   blender --python render_step4_result.py -- step4_generated_scene.json
   blender --background --python render_step4_result.py -- step4_generated_scene.json
"""

import json
import math
import os
import sys
from typing import List, Optional, Tuple

import bmesh
import bpy
from mathutils import Vector


JSON_PATH = None
CLEANUP = True
AUTO_FRAME = True
SHOW_BUILDINGS = True
ROOT_COLLECTION = "Step4TopologyPreview"

MATERIALS = {
    "building_base": (0.40, 0.43, 0.48, 0.16),
    "outdoor_node": (0.25, 0.78, 0.90, 1.0),
    "indoor_node": (0.95, 0.82, 0.35, 1.0),
    "vertical_node": (0.62, 0.48, 0.95, 1.0),
    "outdoor_main_edge": (0.95, 0.30, 0.20, 1.0),
    "outdoor_secondary_edge": (0.95, 0.60, 0.20, 1.0),
    "outdoor_back_edge": (0.70, 0.70, 0.70, 1.0),
    "indoor_main_edge": (0.20, 0.80, 0.35, 1.0),
    "indoor_secondary_edge": (0.42, 0.85, 0.62, 1.0),
    "vertical_edge": (0.70, 0.40, 0.95, 1.0),
    "skeleton_main": (1.00, 0.12, 0.10, 1.0),
    "skeleton_secondary": (1.00, 0.55, 0.10, 1.0),
    "skeleton_threshold": (0.15, 0.85, 0.45, 1.0),
    "skeleton_vertical": (0.65, 0.45, 1.00, 1.0),
    "node_center": (0.12, 0.72, 0.95, 1.0),
}


def resolve_input() -> str:
    path = JSON_PATH
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if args and not path:
            path = args[0]
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = bpy.path.abspath("//")
    if not path:
        path = os.path.join(base, "step4_generated_scene.json")
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    return path


def ensure_collection(name: str, parent: Optional[bpy.types.Collection] = None) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    anchor = parent or bpy.context.scene.collection
    if col.name not in anchor.children:
        anchor.children.link(col)
    return col


def clear_collection_objects(collection: bpy.types.Collection) -> None:
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def create_material(name: str, rgba: Tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
    if mat.node_tree is None:
        try:
            mat.use_nodes = True
        except Exception:
            return mat
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        out = nodes.new(type="ShaderNodeOutputMaterial")
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = 0.75
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = rgba[3]
    if rgba[3] < 1.0:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "NONE"
    return mat


def set_mat(obj: bpy.types.Object, mat_key: str) -> None:
    mat = create_material(mat_key, MATERIALS[mat_key])
    if hasattr(obj.data, "materials"):
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)


def link_only(obj: bpy.types.Object, col: bpy.types.Collection) -> None:
    if obj.name not in col.objects:
        col.objects.link(obj)
    for c in list(obj.users_collection):
        if c != col:
            c.objects.unlink(obj)


def attach_props(obj: bpy.types.Object, d: dict) -> None:
    if not isinstance(d, dict):
        return
    for k, v in d.items():
        key = "src__" + str(k).replace(" ", "_")
        if isinstance(v, (str, int, float, bool)) or v is None:
            obj[key] = v
        else:
            obj[key + "_json"] = json.dumps(v, ensure_ascii=False)


def clean_ring(poly) -> List[Tuple[float, float]]:
    pts = []
    for p in poly or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            q = (float(p[0]), float(p[1]))
            if not pts or q != pts[-1]:
                pts.append(q)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def extrude_polygon(name: str, poly, h: float) -> Optional[bpy.types.Object]:
    pts = clean_ring(poly)
    if len(pts) < 3:
        return None
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, 0.0)) for x, y in pts]
    bm.verts.ensure_lookup_table()
    try:
        base = bm.faces.new(vs)
    except ValueError:
        bmesh.ops.contextual_create(bm, geom=vs)
        if not bm.faces:
            bm.free()
            return None
        base = bm.faces[0]
    ex = bmesh.ops.extrude_face_region(bm, geom=[base])
    exv = [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, 0.0, float(h)), verts=exv)
    me = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def line_curve(name: str, p0: Tuple[float, float], p1: Tuple[float, float], z: float, w: float) -> bpy.types.Object:
    cu = bpy.data.curves.new(f"{name}_Curve", type="CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new(type="POLY")
    sp.points.add(1)
    sp.points[0].co = (float(p0[0]), float(p0[1]), float(z), 1.0)
    sp.points[1].co = (float(p1[0]), float(p1[1]), float(z), 1.0)
    cu.bevel_depth = float(w)
    return bpy.data.objects.new(name, cu)


def marker_box(name: str, x: float, y: float, s: float, h: float, z0: float) -> bpy.types.Object:
    hx, hy, hz = s * 0.5, s * 0.5, h * 0.5
    verts = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    me = bpy.data.meshes.new(f"{name}_Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    obj.location = (x, y, z0 + hz)
    return obj


def compute_bounds(objs: List[bpy.types.Object]):
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


def ensure_camera_light(bounds) -> None:
    sc = bpy.context.scene
    sun = bpy.data.objects.get("Step4Sun")
    if sun is None:
        ld = bpy.data.lights.new("Step4Sun", "SUN")
        ld.energy = 3.0
        sun = bpy.data.objects.new("Step4Sun", ld)
        sc.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 700.0)
    sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))

    cam = bpy.data.objects.get("Step4Camera")
    if cam is None:
        cd = bpy.data.cameras.new("Step4Camera")
        cam = bpy.data.objects.new("Step4Camera", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
    cam.data.clip_end = 6000.0

    if not bounds:
        cam.location = (260.0, -520.0, 380.0)
        cam.rotation_euler = (math.radians(63), 0.0, math.radians(30))
        return
    (minx, miny, _), (maxx, maxy, maxz) = bounds
    cx, cy = (minx + maxx) * 0.5, (miny + maxy) * 0.5
    ext = max(maxx - minx, maxy - miny, 50.0)
    cam.location = (cx + ext * 0.5, cy - ext * 1.35, maxz + ext * 0.9)
    cam.rotation_euler = (math.radians(62), 0.0, math.radians(30))


def _add_network(col_nodes, col_edges, net: dict, node_mat: str, z: float, edge_color_picker):
    created = []
    node_pos = {}
    for n in net.get("nodes", []) or []:
        p = n.get("position", [])
        if not (isinstance(p, list) and len(p) >= 2):
            continue
        obj = marker_box(f"N_{n.get('id','')}", float(p[0]), float(p[1]), s=0.7, h=0.5, z0=z)
        link_only(obj, col_nodes)
        set_mat(obj, node_mat)
        attach_props(obj, n)
        created.append(obj)
        node_pos[str(n.get("id", ""))] = (float(p[0]), float(p[1]))

    for e in net.get("edges", []) or []:
        u = node_pos.get(str(e.get("from", "")))
        v = node_pos.get(str(e.get("to", "")))
        if not u or not v:
            continue
        obj = line_curve(f"E_{e.get('id','')}", u, v, z=z + 0.05, w=0.08)
        link_only(obj, col_edges)
        set_mat(obj, edge_color_picker(e))
        attach_props(obj, e)
        created.append(obj)
    return created


def run(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input JSON not found: {path}")
    print(f"[Load] scene: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    s2 = (((data.get("generated", {}) or {}).get("step_2_massing", {})) or {})
    s4 = (((data.get("generated", {}) or {}).get("step_4_topology", {})) or {})
    if not s4:
        raise ValueError("generated.step_4_topology not found")

    nets = s4.get("circulation_networks", {}) or {}
    sk = s4.get("circulation_skeleton", {}) or {}

    root = ensure_collection(ROOT_COLLECTION)
    cols = {
        "Buildings": ensure_collection("Buildings", root),
        "OutdoorNodes": ensure_collection("OutdoorNodes", root),
        "OutdoorEdges": ensure_collection("OutdoorEdges", root),
        "IndoorNodes": ensure_collection("IndoorNodes", root),
        "IndoorEdges": ensure_collection("IndoorEdges", root),
        "VerticalNodes": ensure_collection("VerticalNodes", root),
        "VerticalEdges": ensure_collection("VerticalEdges", root),
        "Skeleton": ensure_collection("Skeleton", root),
    }
    if CLEANUP:
        print("[Cleanup] Removing old Step4 preview objects")
        for c in cols.values():
            clear_collection_objects(c)

    created = []
    if SHOW_BUILDINGS:
        for b in s2.get("building_masses", []) or []:
            obj = extrude_polygon(f"B_{b.get('id','')}", b.get("footprint", []), max(0.1, float(b.get("height", 1.0))))
            if obj:
                link_only(obj, cols["Buildings"])
                set_mat(obj, "building_base")
                attach_props(obj, b)
                created.append(obj)

    def outdoor_edge_mat(e):
        t = str(e.get("edge_type", ""))
        lvl = str(e.get("network_level", ""))
        if t == "main_spine" or lvl == "main":
            return "outdoor_main_edge"
        if t in {"secondary_spine", "connector"} or lvl == "secondary":
            return "outdoor_secondary_edge"
        return "outdoor_back_edge"

    def indoor_edge_mat(e):
        t = str(e.get("edge_type", ""))
        if t in {"indoor_main_corridor"}:
            return "indoor_main_edge"
        return "indoor_secondary_edge"

    def vertical_edge_mat(_e):
        return "vertical_edge"

    created += _add_network(cols["OutdoorNodes"], cols["OutdoorEdges"], nets.get("ground_outdoor", {}) or {}, "outdoor_node", 0.10, outdoor_edge_mat)
    created += _add_network(cols["IndoorNodes"], cols["IndoorEdges"], nets.get("ground_indoor_public", {}) or {}, "indoor_node", 0.20, indoor_edge_mat)
    created += _add_network(cols["VerticalNodes"], cols["VerticalEdges"], nets.get("vertical_transition", {}) or {}, "vertical_node", 0.30, vertical_edge_mat)

    # skeleton
    for item in sk.get("main_spines", []) or []:
        pl = item.get("polyline", [])
        if isinstance(pl, list) and len(pl) >= 2:
            p0 = (float(pl[0][0]), float(pl[0][1]))
            p1 = (float(pl[-1][0]), float(pl[-1][1]))
            o = line_curve(f"SK_{item.get('id','')}", p0, p1, z=0.45, w=0.12)
            link_only(o, cols["Skeleton"])
            set_mat(o, "skeleton_main")
            attach_props(o, item)
            created.append(o)
    for item in sk.get("secondary_spines", []) or []:
        pl = item.get("polyline", [])
        if isinstance(pl, list) and len(pl) >= 2:
            p0 = (float(pl[0][0]), float(pl[0][1]))
            p1 = (float(pl[-1][0]), float(pl[-1][1]))
            o = line_curve(f"SK_{item.get('id','')}", p0, p1, z=0.47, w=0.09)
            link_only(o, cols["Skeleton"])
            set_mat(o, "skeleton_secondary")
            attach_props(o, item)
            created.append(o)
    for item in sk.get("threshold_spines", []) or []:
        pl = item.get("polyline", [])
        if isinstance(pl, list) and len(pl) >= 2:
            p0 = (float(pl[0][0]), float(pl[0][1]))
            p1 = (float(pl[-1][0]), float(pl[-1][1]))
            o = line_curve(f"SK_{item.get('id','')}", p0, p1, z=0.49, w=0.08)
            link_only(o, cols["Skeleton"])
            set_mat(o, "skeleton_threshold")
            attach_props(o, item)
            created.append(o)
    for item in sk.get("vertical_spines", []) or []:
        pl = item.get("polyline", [])
        if isinstance(pl, list) and len(pl) >= 2:
            p0 = (float(pl[0][0]), float(pl[0][1]))
            p1 = (float(pl[-1][0]), float(pl[-1][1]))
            o = line_curve(f"SK_{item.get('id','')}", p0, p1, z=0.51, w=0.08)
            link_only(o, cols["Skeleton"])
            set_mat(o, "skeleton_vertical")
            attach_props(o, item)
            created.append(o)
    for c in sk.get("node_centers", []) or []:
        p = c.get("position", [])
        if isinstance(p, list) and len(p) >= 2:
            o = marker_box(f"Center_{c.get('id','')}", float(p[0]), float(p[1]), s=1.2, h=0.6, z0=0.55)
            link_only(o, cols["Skeleton"])
            set_mat(o, "node_center")
            attach_props(o, c)
            created.append(o)

    if AUTO_FRAME:
        ensure_camera_light(compute_bounds(created))

    print("[Summary]")
    print(f"  outdoor_nodes: {len((nets.get('ground_outdoor', {}) or {}).get('nodes', []) or [])}")
    print(f"  outdoor_edges: {len((nets.get('ground_outdoor', {}) or {}).get('edges', []) or [])}")
    print(f"  indoor_nodes: {len((nets.get('ground_indoor_public', {}) or {}).get('nodes', []) or [])}")
    print(f"  indoor_edges: {len((nets.get('ground_indoor_public', {}) or {}).get('edges', []) or [])}")
    print(f"  vertical_nodes: {len((nets.get('vertical_transition', {}) or {}).get('nodes', []) or [])}")
    print(f"  vertical_edges: {len((nets.get('vertical_transition', {}) or {}).get('edges', []) or [])}")
    print("[Done] Step4 preview generated")


def main() -> None:
    run(resolve_input())


if __name__ == "__main__":
    main()

