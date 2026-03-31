"""
render_step3_result.py

Usage:
1) Blender UI:
   - Open and run in Scripting workspace.
2) Command line:
   blender --python render_step3_result.py -- step3_generated_scene.json
   blender --background --python render_step3_result.py -- step3_generated_scene.json
"""

import json
import math
import os
import sys
from typing import List, Optional, Sequence, Tuple

import bmesh
import bpy
from mathutils import Vector


JSON_PATH = None
CLEANUP = True
AUTO_FRAME = True
SHOW_BUILDINGS = True
ROOT_COLLECTION = "Step3KeyPointPreview"

MATERIALS = {
    "building_base": (0.42, 0.44, 0.48, 0.22),
    "node_transit_metro": (0.20, 0.50, 0.95, 1.0),
    "node_transit_bus": (0.24, 0.78, 0.92, 1.0),
    "node_atrium": (0.95, 0.82, 0.30, 1.0),
    "node_core": (0.30, 0.36, 0.50, 1.0),
    "node_plaza": (0.18, 0.78, 0.35, 1.0),
    "entrance_main": (0.96, 0.35, 0.20, 1.0),
    "entrance_secondary": (0.96, 0.62, 0.20, 1.0),
    "entrance_service": (0.65, 0.65, 0.65, 1.0),
    "service_pickup": (0.95, 0.35, 0.20, 1.0),
    "service_parcel": (0.85, 0.55, 0.20, 1.0),
    "service_frontdesk": (0.60, 0.72, 0.92, 1.0),
    "service_waiting": (0.55, 0.82, 0.55, 1.0),
    "service_loading": (0.45, 0.45, 0.45, 1.0),
    "ground": (0.16, 0.16, 0.16, 1.0),
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
        path = os.path.join(base, "step3_generated_scene.json")
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


def clean_ring(poly: Sequence[Sequence[float]]) -> List[Tuple[float, float]]:
    pts = []
    for p in poly or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            q = (float(p[0]), float(p[1]))
            if not pts or q != pts[-1]:
                pts.append(q)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def polygon_mesh(name: str, poly: Sequence[Sequence[float]], z: float = 0.0) -> Optional[bpy.types.Object]:
    pts = clean_ring(poly)
    if len(pts) < 3:
        return None
    me = bpy.data.meshes.new(f"{name}_Mesh")
    me.from_pydata([(x, y, z) for x, y in pts], [], [list(range(len(pts)))])
    me.update()
    return bpy.data.objects.new(name, me)


def extrude_polygon(name: str, poly: Sequence[Sequence[float]], z0: float, h: float) -> Optional[bpy.types.Object]:
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
    obj = bpy.data.objects.new(name, me)
    obj.location.z = float(z0)
    return obj


def marker_box(name: str, x: float, y: float, sx: float, sy: float, h: float = 0.3, z0: float = 0.0) -> bpy.types.Object:
    hx, hy, hz = sx * 0.5, sy * 0.5, h * 0.5
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


def marker_cylinder(name: str, x: float, y: float, radius: float, h: float = 0.5, z0: float = 0.0) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=24,
        radius1=max(0.05, radius),
        radius2=max(0.05, radius),
        depth=max(0.1, h),
    )
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, z0 + h * 0.5)
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
    sun = bpy.data.objects.get("Step3Sun")
    if sun is None:
        ld = bpy.data.lights.new("Step3Sun", "SUN")
        ld.energy = 3.0
        sun = bpy.data.objects.new("Step3Sun", ld)
        sc.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 600.0)
    sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))

    cam = bpy.data.objects.get("Step3Camera")
    if cam is None:
        cd = bpy.data.cameras.new("Step3Camera")
        cam = bpy.data.objects.new("Step3Camera", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
    cam.data.clip_end = 5000.0

    if not bounds:
        cam.location = (240.0, -500.0, 360.0)
        cam.rotation_euler = (math.radians(63), 0.0, math.radians(30))
        return

    (minx, miny, _), (maxx, maxy, maxz) = bounds
    cx, cy = (minx + maxx) * 0.5, (miny + maxy) * 0.5
    ext = max(maxx - minx, maxy - miny, 50.0)
    cam.location = (cx + ext * 0.45, cy - ext * 1.3, maxz + ext * 0.85)
    cam.rotation_euler = (math.radians(62), 0.0, math.radians(30))


def _node_material(node_type: str) -> str:
    n = node_type.lower()
    if "metro" in n:
        return "node_transit_metro"
    if "bus" in n:
        return "node_transit_bus"
    if "atrium" in n:
        return "node_atrium"
    if "core" in n:
        return "node_core"
    return "node_plaza"


def _service_material(stype: str) -> str:
    s = stype.lower()
    if "pickup" in s or "delivery" in s:
        return "service_pickup"
    if "parcel" in s:
        return "service_parcel"
    if "frontdesk" in s or "property_frontdesk" in s:
        return "service_frontdesk"
    if "loading" in s:
        return "service_loading"
    return "service_waiting"


def run(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input JSON not found: {path}")
    print(f"[Load] scene: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    step2 = (((data.get("generated", {}) or {}).get("step_2_massing", {})) or {})
    step3 = (((data.get("generated", {}) or {}).get("step_3_key_nodes", {})) or {})
    if not step3:
        raise ValueError("generated.step_3_key_nodes not found")

    root = ensure_collection(ROOT_COLLECTION)
    cols = {
        "Buildings": ensure_collection("Buildings", root),
        "KeyNodes": ensure_collection("KeyNodes", root),
        "EntranceCandidates": ensure_collection("EntranceCandidates", root),
        "ServiceNodes": ensure_collection("ServiceNodes", root),
    }
    if CLEANUP:
        print("[Cleanup] Removing old Step3 preview objects")
        for c in cols.values():
            clear_collection_objects(c)

    created: List[bpy.types.Object] = []

    if SHOW_BUILDINGS:
        for b in step2.get("building_masses", []) or []:
            obj = extrude_polygon(f"B_{b.get('id','')}", b.get("footprint", []), z0=0.0, h=max(0.1, float(b.get("height", 1.0))))
            if not obj:
                continue
            link_only(obj, cols["Buildings"])
            set_mat(obj, "building_base")
            attach_props(obj, b)
            created.append(obj)

    for n in step3.get("key_nodes", []) or []:
        pos = n.get("position", [])
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        size = n.get("node_size_m", [1.6, 1.6])
        sx = float(size[0]) if isinstance(size, list) and len(size) > 0 else 1.6
        sy = float(size[1]) if isinstance(size, list) and len(size) > 1 else sx
        obj = marker_box(f"KN_{n.get('id','')}", float(pos[0]), float(pos[1]), sx=sx, sy=sy, h=0.6, z0=0.05)
        link_only(obj, cols["KeyNodes"])
        set_mat(obj, _node_material(str(n.get("node_type", ""))))
        attach_props(obj, n)
        created.append(obj)

    for e in step3.get("entrance_candidates", []) or []:
        pos = e.get("position", [])
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        ctype = str(e.get("candidate_type", "secondary")).lower()
        if ctype == "main":
            mk = "entrance_main"
            radius = 0.55
            h = 1.2
        elif ctype == "service":
            mk = "entrance_service"
            radius = 0.35
            h = 0.8
        else:
            mk = "entrance_secondary"
            radius = 0.42
            h = 1.0
        obj = marker_cylinder(f"EN_{e.get('id','')}", float(pos[0]), float(pos[1]), radius=radius, h=h, z0=0.05)
        link_only(obj, cols["EntranceCandidates"])
        set_mat(obj, mk)
        attach_props(obj, e)
        created.append(obj)

    for s in step3.get("service_nodes", []) or []:
        pos = s.get("position", [])
        if not (isinstance(pos, list) and len(pos) >= 2):
            continue
        size = s.get("node_size_m", [1.0, 1.0])
        sx = float(size[0]) if isinstance(size, list) and len(size) > 0 else 1.0
        sy = float(size[1]) if isinstance(size, list) and len(size) > 1 else sx
        h = 0.55 if max(sx, sy) < 4.0 else 0.35
        obj = marker_box(f"SV_{s.get('id','')}", float(pos[0]), float(pos[1]), sx=sx, sy=sy, h=h, z0=0.05)
        link_only(obj, cols["ServiceNodes"])
        set_mat(obj, _service_material(str(s.get("service_type", ""))))
        attach_props(obj, s)
        created.append(obj)

    if created:
        b = compute_bounds(created)
        if b:
            (minx, miny, _), (maxx, maxy, _) = b
            m = 25.0
            g = polygon_mesh(
                "Step3Ground",
                [[minx - m, miny - m], [maxx + m, miny - m], [maxx + m, maxy + m], [minx - m, maxy + m], [minx - m, miny - m]],
                z=-0.02,
            )
            if g:
                link_only(g, cols["Buildings"])
                set_mat(g, "ground")
                created.append(g)

    if AUTO_FRAME:
        ensure_camera_light(compute_bounds(created))

    print("[Summary]")
    print(f"  key_nodes: {len(step3.get('key_nodes', []) or [])}")
    print(f"  entrance_candidates: {len(step3.get('entrance_candidates', []) or [])}")
    print(f"  service_nodes: {len(step3.get('service_nodes', []) or [])}")
    print("[Done] Step3 preview generated")


def main() -> None:
    run(resolve_input())


if __name__ == "__main__":
    main()
