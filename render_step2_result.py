"""
render_step2_result.py

Usage:
1) Blender UI:
   - Open and run in Scripting workspace.
2) Command line:
   blender --python render_step2_result.py -- step2_generated_scene.json
   blender --background --python render_step2_result.py -- step2_generated_scene.json
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
ADD_GROUND = True
AUTO_FRAME = True
ROOT_COLLECTION = "Step2ResultPreview"

MATERIALS = {
    "buildable_zone": (0.30, 0.85, 0.35, 0.30),
    "building_mall": (0.78, 0.74, 0.70, 1.0),
    "building_office": (0.58, 0.66, 0.75, 1.0),
    "building_residential": (0.74, 0.70, 0.66, 1.0),
    "building_residential_podium": (0.92, 0.56, 0.26, 1.0),
    "atrium": (0.95, 0.82, 0.35, 1.0),
    "core": (0.30, 0.36, 0.48, 1.0),
    "podium_band": (0.90, 0.52, 0.25, 1.0),
    "open_space": (0.20, 0.70, 0.90, 0.45),
    "grid_line": (0.95, 0.95, 0.95, 1.0),
    "ground": (0.18, 0.18, 0.18, 1.0),
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
        path = os.path.join(base, "step2_generated_scene.json")
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


def extrude_polygon(name: str, poly: Sequence[Sequence[float]], height: float) -> Optional[bpy.types.Object]:
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
    bmesh.ops.translate(bm, vec=(0.0, 0.0, float(height)), verts=exv)
    me = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def extrude_polygon_at_z(name: str, poly: Sequence[Sequence[float]], z0: float, height: float) -> Optional[bpy.types.Object]:
    obj = extrude_polygon(name, poly, height)
    if obj:
        obj.location.z = float(z0)
    return obj


def extrude_multi_polygons(name: str, polys: Sequence[Sequence[Sequence[float]]], height: float) -> Optional[bpy.types.Object]:
    bm = bmesh.new()
    created_face = False
    for poly in polys or []:
        pts = clean_ring(poly)
        if len(pts) < 3:
            continue
        vs = [bm.verts.new((x, y, 0.0)) for x, y in pts]
        bm.verts.ensure_lookup_table()
        try:
            face = bm.faces.new(vs)
        except ValueError:
            r = bmesh.ops.contextual_create(bm, geom=vs)
            fs = [g for g in r.get("geom", []) if isinstance(g, bmesh.types.BMFace)]
            face = fs[0] if fs else None
        if face is None:
            continue
        created_face = True
        ex = bmesh.ops.extrude_face_region(bm, geom=[face])
        exv = [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=(0.0, 0.0, float(height)), verts=exv)
    if not created_face:
        bm.free()
        return None
    me = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def extrude_multi_polygons_at_z(name: str, polys: Sequence[Sequence[Sequence[float]]], z0: float, height: float) -> Optional[bpy.types.Object]:
    obj = extrude_multi_polygons(name, polys, height)
    if obj:
        obj.location.z = float(z0)
    return obj


def line_curve(name: str, p0: Tuple[float, float], p1: Tuple[float, float], z: float = 0.02, w: float = 0.02) -> bpy.types.Object:
    cu = bpy.data.curves.new(f"{name}_Curve", type="CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new(type="POLY")
    sp.points.add(1)
    sp.points[0].co = (p0[0], p0[1], z, 1.0)
    sp.points[1].co = (p1[0], p1[1], z, 1.0)
    cu.bevel_depth = w
    return bpy.data.objects.new(name, cu)


def attach_props(obj: bpy.types.Object, d: dict) -> None:
    if not isinstance(d, dict):
        return
    for k, v in d.items():
        key = "src__" + str(k).replace(" ", "_")
        if isinstance(v, (str, int, float, bool)) or v is None:
            obj[key] = v
        else:
            obj[key + "_json"] = json.dumps(v, ensure_ascii=False)


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
    sun = bpy.data.objects.get("Step2Sun")
    if sun is None:
        ld = bpy.data.lights.new("Step2Sun", "SUN")
        ld.energy = 3.0
        sun = bpy.data.objects.new("Step2Sun", ld)
        sc.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 600.0)
    sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))

    cam = bpy.data.objects.get("Step2Camera")
    if cam is None:
        cd = bpy.data.cameras.new("Step2Camera")
        cam = bpy.data.objects.new("Step2Camera", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
    cam.data.clip_end = 5000.0

    if not bounds:
        cam.location = (220.0, -460.0, 360.0)
        cam.rotation_euler = (math.radians(63), 0.0, math.radians(30))
        return
    (minx, miny, _), (maxx, maxy, maxz) = bounds
    cx, cy = (minx + maxx) * 0.5, (miny + maxy) * 0.5
    ext = max(maxx - minx, maxy - miny, 50.0)
    cam.location = (cx + ext * 0.45, cy - ext * 1.25, maxz + ext * 0.8)
    cam.rotation_euler = (math.radians(62), 0.0, math.radians(30))


def run(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input JSON not found: {path}")
    print(f"[Load] scene: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    step2 = (((data.get("generated", {}) or {}).get("step_2_massing", {})) or {})
    if not step2:
        raise ValueError("generated.step_2_massing not found")

    root = ensure_collection(ROOT_COLLECTION)
    cols = {
        "BuildableZones": ensure_collection("BuildableZones", root),
        "SolveGrid": ensure_collection("SolveGrid", root),
        "Buildings": ensure_collection("Buildings", root),
        "Atriums": ensure_collection("Atriums", root),
        "Cores": ensure_collection("Cores", root),
        "PodiumBands": ensure_collection("PodiumBands", root),
        "OpenSpaces": ensure_collection("OpenSpaces", root),
    }
    if CLEANUP:
        print("[Cleanup] Removing old Step2 result objects")
        for c in cols.values():
            clear_collection_objects(c)

    created: List[bpy.types.Object] = []

    for bz in step2.get("buildable_zones", []) or []:
        obj = polygon_mesh(f"BZ_{bz.get('id','')}", bz.get("polygon", []), z=0.02)
        if obj:
            link_only(obj, cols["BuildableZones"])
            set_mat(obj, "buildable_zone")
            attach_props(obj, bz)
            created.append(obj)

    for g in step2.get("solve_grids", []) or []:
        bbox = g.get("bbox")
        gs = float(g.get("grid_size", 5.0))
        if not isinstance(bbox, list) or len(bbox) < 4:
            continue
        x0, y0, x1, y1 = map(float, bbox[:4])
        x = x0
        while x <= x1 + 1e-6:
            o = line_curve(f"GridV_{g.get('id','')}_{int(round((x-x0)/max(gs,1e-6)))}", (x, y0), (x, y1), z=0.025, w=0.01)
            link_only(o, cols["SolveGrid"])
            set_mat(o, "grid_line")
            created.append(o)
            x += gs
        y = y0
        while y <= y1 + 1e-6:
            o = line_curve(f"GridH_{g.get('id','')}_{int(round((y-y0)/max(gs,1e-6)))}", (x0, y), (x1, y), z=0.025, w=0.01)
            link_only(o, cols["SolveGrid"])
            set_mat(o, "grid_line")
            created.append(o)
            y += gs

    for b in step2.get("building_masses", []) or []:
        total_h = max(0.1, float(b.get("height", 12.0)))
        levels = max(1, int(b.get("levels_above_ground", 1)))
        floor_h = total_h / float(levels)
        comp = b.get("component_polygons")
        bt = str(b.get("building_type", "mall"))
        if bt == "mall":
            mat = "building_mall"
        elif bt in {"office", "office_tower", "office_podium"}:
            mat = "building_office"
        elif bt == "residential_podium" or bool(b.get("is_podium_mass", False)):
            mat = "building_residential_podium"
        else:
            mat = "building_residential"

        for fi in range(levels):
            z0 = fi * floor_h
            floor_name = f"Bld_{b.get('id','')}_F{fi + 1:02d}"
            if isinstance(comp, list) and comp:
                obj = extrude_multi_polygons_at_z(floor_name, comp, z0, floor_h)
            else:
                obj = extrude_polygon_at_z(floor_name, b.get("footprint", []), z0, floor_h)
            if not obj:
                continue
            link_only(obj, cols["Buildings"])
            set_mat(obj, mat)
            attach_props(obj, b)
            obj["src__floor_index"] = fi + 1
            obj["src__floor_count"] = levels
            obj["src__floor_height"] = round(floor_h, 4)
            created.append(obj)

    for a in step2.get("atriums", []) or []:
        obj = polygon_mesh(f"Atrium_{a.get('id','')}", a.get("polygon", []), z=0.06)
        if obj:
            link_only(obj, cols["Atriums"])
            set_mat(obj, "atrium")
            attach_props(obj, a)
            created.append(obj)

    for c in step2.get("cores", []) or []:
        obj = polygon_mesh(f"Core_{c.get('id','')}", c.get("polygon", []), z=0.07)
        if obj:
            link_only(obj, cols["Cores"])
            set_mat(obj, "core")
            attach_props(obj, c)
            created.append(obj)

    for p in step2.get("podium_retail_bands", []) or []:
        obj = polygon_mesh(f"Podium_{p.get('id','')}", p.get("polygon", []), z=0.08)
        if obj:
            link_only(obj, cols["PodiumBands"])
            set_mat(obj, "podium_band")
            attach_props(obj, p)
            created.append(obj)

    for o in step2.get("reserved_open_spaces", []) or []:
        obj = polygon_mesh(f"Open_{o.get('id','')}", o.get("polygon", []), z=0.04)
        if obj:
            link_only(obj, cols["OpenSpaces"])
            set_mat(obj, "open_space")
            attach_props(obj, o)
            created.append(obj)

    if ADD_GROUND and created:
        b = compute_bounds(created)
        if b:
            (minx, miny, _), (maxx, maxy, _) = b
            m = 25.0
            g = polygon_mesh("Step2Ground", [[minx - m, miny - m], [maxx + m, miny - m], [maxx + m, maxy + m], [minx - m, maxy + m], [minx - m, miny - m]], z=-0.02)
            if g:
                link_only(g, cols["Buildings"])
                set_mat(g, "ground")
                created.append(g)

    if AUTO_FRAME:
        ensure_camera_light(compute_bounds(created))

    print("[Summary]")
    print(f"  buildable_zones: {len(step2.get('buildable_zones', []) or [])}")
    print(f"  building_masses: {len(step2.get('building_masses', []) or [])}")
    print(f"  atriums: {len(step2.get('atriums', []) or [])}")
    print(f"  cores: {len(step2.get('cores', []) or [])}")
    print(f"  podium_retail_bands: {len(step2.get('podium_retail_bands', []) or [])}")
    print(f"  reserved_open_spaces: {len(step2.get('reserved_open_spaces', []) or [])}")
    print("[Done] Step2 result preview generated")


def main() -> None:
    run(resolve_input())


if __name__ == "__main__":
    main()
