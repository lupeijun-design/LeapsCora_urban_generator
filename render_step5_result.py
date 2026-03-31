"""
render_step5_result.py

Usage:
  blender --python render_step5_result.py -- step5_generated_scene.json
  blender --background --python render_step5_result.py -- step5_generated_scene.json
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
ROOT_COLLECTION = "Step5SpacePreview"

MATERIALS = {
    "building_base": (0.42, 0.42, 0.46, 0.14),
    "street_clear_path": (0.24, 0.72, 0.92, 0.55),
    "entrance_threshold": (0.95, 0.36, 0.20, 0.70),
    "semi_public_frontage_band": (0.96, 0.62, 0.20, 0.62),
    "indoor_public_continuous": (0.20, 0.78, 0.38, 0.68),
    "indoor_public_corridor": (0.20, 0.78, 0.38, 0.68),
    "node_space": (0.62, 0.46, 0.92, 0.58),
    "reserved_level": (0.66, 0.66, 0.66, 0.60),
    "default_space": (0.85, 0.85, 0.85, 0.55),
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
        path = os.path.join(base, "step5_generated_scene.json")
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
    bsdf.inputs["Roughness"].default_value = 0.8
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


def set_mat(obj: bpy.types.Object, key: str) -> None:
    mk = key if key in MATERIALS else "default_space"
    mat = create_material(mk, MATERIALS[mk])
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
        kk = "src__" + str(k).replace(" ", "_")
        if isinstance(v, (str, int, float, bool)) or v is None:
            obj[kk] = v
        else:
            obj[kk + "_json"] = json.dumps(v, ensure_ascii=False)


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


def polygon_mesh(name: str, poly: Sequence[Sequence[float]], z: float) -> Optional[bpy.types.Object]:
    pts = clean_ring(poly)
    if len(pts) < 3:
        return None
    me = bpy.data.meshes.new(f"{name}_Mesh")
    me.from_pydata([(x, y, z) for x, y in pts], [], [list(range(len(pts)))])
    me.update()
    return bpy.data.objects.new(name, me)


def extrude_polygon(name: str, poly: Sequence[Sequence[float]], h: float) -> Optional[bpy.types.Object]:
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
    sun = bpy.data.objects.get("Step5Sun")
    if sun is None:
        ld = bpy.data.lights.new("Step5Sun", "SUN")
        ld.energy = 3.0
        sun = bpy.data.objects.new("Step5Sun", ld)
        sc.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 700.0)
    sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))

    cam = bpy.data.objects.get("Step5Camera")
    if cam is None:
        cd = bpy.data.cameras.new("Step5Camera")
        cam = bpy.data.objects.new("Step5Camera", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
    cam.data.clip_end = 6000.0

    if not bounds:
        cam.location = (260.0, -540.0, 390.0)
        cam.rotation_euler = (math.radians(63), 0.0, math.radians(30))
        return
    (minx, miny, _), (maxx, maxy, maxz) = bounds
    cx, cy = (minx + maxx) * 0.5, (miny + maxy) * 0.5
    ext = max(maxx - minx, maxy - miny, 50.0)
    cam.location = (cx + ext * 0.5, cy - ext * 1.35, maxz + ext * 0.95)
    cam.rotation_euler = (math.radians(62), 0.0, math.radians(30))


def run(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input JSON not found: {path}")
    print(f"[Load] scene: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    s2 = (((data.get("generated", {}) or {}).get("step_2_massing", {})) or {})
    s5 = (((data.get("generated", {}) or {}).get("step_5_spaces", {})) or {})
    if not s5:
        raise ValueError("generated.step_5_spaces not found")

    root = ensure_collection(ROOT_COLLECTION)
    cols = {
        "Buildings": ensure_collection("Buildings", root),
        "Walkable": ensure_collection("WalkableSpaces", root),
        "NodeSpaces": ensure_collection("NodeSpaces", root),
        "Reserved": ensure_collection("ReservedLevelSpaces", root),
    }
    if CLEANUP:
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

    for w in s5.get("walkable_spaces", []) or []:
        st = str(w.get("space_type", "default_space"))
        eh = float(w.get("extrude_height", 0.15) or 0.15)
        obj = extrude_polygon(f"WS_{w.get('id','')}", w.get("polygon", []), h=max(0.05, eh))
        if obj:
            link_only(obj, cols["Walkable"])
            set_mat(obj, st)
            attach_props(obj, w)
            created.append(obj)

    for n in s5.get("node_spaces", []) or []:
        eh = float(n.get("extrude_height", 0.15) or 0.15)
        obj = extrude_polygon(f"NS_{n.get('id','')}", n.get("polygon", []), h=max(0.05, eh))
        if obj:
            link_only(obj, cols["NodeSpaces"])
            set_mat(obj, "node_space")
            attach_props(obj, n)
            created.append(obj)

    for r in s5.get("reserved_level_spaces", []) or []:
        eh = float(r.get("extrude_height", 0.2) or 0.2)
        obj = extrude_polygon(f"RS_{r.get('id','')}", r.get("polygon", []), h=max(0.05, eh))
        if obj:
            link_only(obj, cols["Reserved"])
            set_mat(obj, "reserved_level")
            attach_props(obj, r)
            created.append(obj)

    if AUTO_FRAME:
        ensure_camera_light(compute_bounds(created))

    print("[Summary]")
    print(f"  walkable_spaces: {len(s5.get('walkable_spaces', []) or [])}")
    print(f"  node_spaces: {len(s5.get('node_spaces', []) or [])}")
    print(f"  reserved_level_spaces: {len(s5.get('reserved_level_spaces', []) or [])}")
    print("[Done] Step5 preview generated")


def main() -> None:
    run(resolve_input())


if __name__ == "__main__":
    main()
