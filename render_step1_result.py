"""
render_step1_result.py

Usage:
1) Blender UI:
   - Open this file in Blender Scripting and Run Script.
2) Command line:
   blender --python render_step1_result.py -- step1_generated_scene.json
   blender --background --python render_step1_result.py -- step1_generated_scene.json
"""

import json
import math
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import bpy
from mathutils import Vector


JSON_PATH = None
CLEANUP = True
ADD_GROUND = True
AUTO_FRAME = True

ROOT_COLLECTION = "Step1ResultPreview"

MATERIALS = {
    "block_fill": (0.35, 0.35, 0.35, 1.0),
    "block_outline": (0.10, 0.10, 0.10, 1.0),
    "frontage_primary": (0.95, 0.30, 0.20, 1.0),
    "frontage_secondary": (0.96, 0.62, 0.20, 1.0),
    "frontage_back": (0.65, 0.65, 0.65, 1.0),
    "corner_transit": (0.20, 0.50, 0.95, 1.0),
    "corner_open_plaza": (0.20, 0.80, 0.35, 1.0),
    "corner_normal": (0.90, 0.90, 0.90, 1.0),
    "transit_influence": (0.20, 0.75, 0.90, 0.40),
    "ground": (0.17, 0.17, 0.17, 1.0),
}


def resolve_input() -> str:
    path = JSON_PATH
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if args and not path:
            path = args[0]

    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base_dir = bpy.path.abspath("//")

    if not path:
        path = os.path.join(base_dir, "step1_generated_scene.json")

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


def set_material(obj: bpy.types.Object, name: str) -> None:
    mat = create_material(name, MATERIALS[name])
    if hasattr(obj.data, "materials"):
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)


def link_only(obj: bpy.types.Object, target: bpy.types.Collection) -> None:
    if obj.name not in target.objects:
        target.objects.link(obj)
    for c in list(obj.users_collection):
        if c != target:
            c.objects.unlink(obj)


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


def polyline_curve(name: str, points: Sequence[Sequence[float]], z: float = 0.06, width: float = 0.04) -> Optional[bpy.types.Object]:
    pts = []
    for p in points or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            q = (float(p[0]), float(p[1]))
            if not pts or q != pts[-1]:
                pts.append(q)
    if len(pts) < 2:
        return None

    curve = bpy.data.curves.new(f"{name}_Curve", type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new(type="POLY")
    spline.points.add(len(pts) - 1)
    for i, (x, y) in enumerate(pts):
        spline.points[i].co = (x, y, z, 1.0)
    spline.use_cyclic_u = False
    curve.bevel_depth = width
    return bpy.data.objects.new(name, curve)


def marker_box(name: str, x: float, y: float, s: float, h: float, z0: float = 0.0) -> bpy.types.Object:
    hx, hy, hz = s * 0.5, s * 0.5, h * 0.5
    verts = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    faces = [[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    me = bpy.data.meshes.new(f"{name}_Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    obj.location = (x, y, z0 + hz)
    return obj


def attach_props(obj: bpy.types.Object, data: dict) -> None:
    if not isinstance(data, dict):
        return
    for k, v in data.items():
        key = f"src__{str(k).replace(' ', '_')}"
        if isinstance(v, (str, int, float, bool)) or v is None:
            obj[key] = v
        else:
            obj[key + "_json"] = json.dumps(v, ensure_ascii=False)


def compute_bounds(objects: List[bpy.types.Object]):
    if not objects:
        return None
    mn = [math.inf, math.inf, math.inf]
    mx = [-math.inf, -math.inf, -math.inf]
    for obj in objects:
        if obj.type not in {"MESH", "CURVE"}:
            continue
        for c in obj.bound_box:
            w = obj.matrix_world @ Vector(c)
            mn[0], mn[1], mn[2] = min(mn[0], w.x), min(mn[1], w.y), min(mn[2], w.z)
            mx[0], mx[1], mx[2] = max(mx[0], w.x), max(mx[1], w.y), max(mx[2], w.z)
    if math.isinf(mn[0]):
        return None
    return (tuple(mn), tuple(mx))


def ensure_camera_light(bounds) -> None:
    scene = bpy.context.scene

    sun = bpy.data.objects.get("Step1ResultSun")
    if sun is None:
        ld = bpy.data.lights.new("Step1ResultSun", "SUN")
        ld.energy = 3.0
        sun = bpy.data.objects.new("Step1ResultSun", ld)
        scene.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 500.0)
    sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))

    cam = bpy.data.objects.get("Step1ResultCamera")
    if cam is None:
        cd = bpy.data.cameras.new("Step1ResultCamera")
        cam = bpy.data.objects.new("Step1ResultCamera", cd)
        scene.collection.objects.link(cam)
        scene.camera = cam

    cam.data.clip_end = 3000.0
    if not bounds:
        cam.location = (200.0, -400.0, 320.0)
        cam.rotation_euler = (math.radians(65), 0.0, math.radians(30))
        return

    (minx, miny, _), (maxx, maxy, maxz) = bounds
    cx, cy = (minx + maxx) * 0.5, (miny + maxy) * 0.5
    ext = max(maxx - minx, maxy - miny, 50.0)
    cam.location = (cx + ext * 0.4, cy - ext * 1.15, maxz + ext * 0.7)
    cam.rotation_euler = (math.radians(62), 0.0, math.radians(30))


def run(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input JSON not found: {path}")

    print(f"[Load] scene: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    step1 = (((data.get("generated", {}) or {}).get("step_1_network", {})) or {})
    if not step1:
        raise ValueError("generated.step_1_network not found")

    root = ensure_collection(ROOT_COLLECTION)
    c_blocks = ensure_collection("Blocks", root)
    c_frontages = ensure_collection("Frontages", root)
    c_corners = ensure_collection("Corners", root)
    c_tiz = ensure_collection("TransitInfluence", root)

    if CLEANUP:
        print("[Cleanup] Removing old result objects")
        for c in [c_blocks, c_frontages, c_corners, c_tiz]:
            clear_collection_objects(c)

    created: List[bpy.types.Object] = []

    for b in step1.get("block_boundaries", []) or []:
        bid = str(b.get("id", "block"))
        poly = b.get("polygon")
        if not poly:
            continue

        fill = polygon_mesh(f"Block_{bid}", poly, z=0.0)
        if fill:
            link_only(fill, c_blocks)
            set_material(fill, "block_fill")
            attach_props(fill, b)
            created.append(fill)

        outline = polyline_curve(f"BlockOutline_{bid}", poly, z=0.03, width=0.03)
        if outline:
            link_only(outline, c_blocks)
            set_material(outline, "block_outline")
            attach_props(outline, b)
            created.append(outline)

    for fseg in step1.get("frontage_segments", []) or []:
        fid = str(fseg.get("id", "frontage"))
        pl = fseg.get("polyline")
        if not pl:
            continue
        obj = polyline_curve(f"Frontage_{fid}", pl, z=0.06, width=0.05)
        if not obj:
            continue

        ftype = str(fseg.get("frontage_type", "back_frontage"))
        mat = "frontage_back"
        if ftype == "primary_frontage":
            mat = "frontage_primary"
        elif ftype == "secondary_frontage":
            mat = "frontage_secondary"

        link_only(obj, c_frontages)
        set_material(obj, mat)
        attach_props(obj, fseg)
        created.append(obj)

    for c in step1.get("corners", []) or []:
        cid = str(c.get("id", "corner"))
        pos = c.get("position")
        if not isinstance(pos, list) or len(pos) < 2:
            continue
        ctype = str(c.get("corner_type", "normal_corner"))
        obj = marker_box(f"Corner_{cid}", float(pos[0]), float(pos[1]), s=2.2, h=0.9, z0=0.05)
        link_only(obj, c_corners)
        if ctype == "transit_corner":
            set_material(obj, "corner_transit")
        elif ctype == "open_plaza_corner":
            set_material(obj, "corner_open_plaza")
        else:
            set_material(obj, "corner_normal")
        attach_props(obj, c)
        created.append(obj)

    for z in step1.get("transit_influence_zones", []) or []:
        zid = str(z.get("id", "tiz"))
        poly = z.get("polygon")
        if not poly:
            continue
        obj = polygon_mesh(f"TransitInfluence_{zid}", poly, z=0.08)
        if not obj:
            continue
        link_only(obj, c_tiz)
        set_material(obj, "transit_influence")
        attach_props(obj, z)
        created.append(obj)

    if ADD_GROUND and created:
        b = compute_bounds(created)
        if b:
            (minx, miny, _), (maxx, maxy, _) = b
            m = 25.0
            gpoly = [[minx - m, miny - m], [maxx + m, miny - m], [maxx + m, maxy + m], [minx - m, maxy + m], [minx - m, miny - m]]
            ground = polygon_mesh("Step1ResultGround", gpoly, z=-0.03)
            if ground:
                link_only(ground, c_blocks)
                set_material(ground, "ground")
                created.append(ground)

    if AUTO_FRAME:
        ensure_camera_light(compute_bounds(created))

    print("[Summary]")
    print(f"  blocks: {len(step1.get('block_boundaries', []) or [])}")
    print(f"  frontages: {len(step1.get('frontage_segments', []) or [])}")
    print(f"  corners: {len(step1.get('corners', []) or [])}")
    print(f"  transit_zones: {len(step1.get('transit_influence_zones', []) or [])}")
    print("[Done] Step1 result preview generated")


def main() -> None:
    path = resolve_input()
    run(path)


if __name__ == "__main__":
    main()
