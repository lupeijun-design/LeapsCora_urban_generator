"""
render_step1_input.py

Usage:
1) Blender UI:
   - Open this file in Blender Scripting and Run Script.

2) Command line:
   blender --python render_step1_input.py -- step1_test_input.json setting.yaml
   blender --background --python render_step1_input.py -- step1_test_input.json setting.yaml
"""

import json
import math
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import bpy
from mathutils import Vector


JSON_PATH = None
SETTINGS_PATH = None
CLEANUP = True
ADD_GROUND = True
AUTO_FRAME = True

ROOT_COLLECTION = "Step1InputPreview"

ROAD_CLASS_COLORS = {
    "expressway": (1.00, 0.68, 0.68, 1.0),
    "primary": (1.00, 0.68, 0.68, 1.0),
    "secondary": (1.00, 0.68, 0.68, 1.0),
    "local": (1.00, 0.68, 0.68, 1.0),
    "tree-lined avenue": (1.00, 0.68, 0.68, 1.0),
    "internal road": (1.00, 0.68, 0.68, 1.0),
    "default": (1.00, 0.68, 0.68, 1.0),
}

NODE_COLORS = {
    "metro": (0.20, 0.48, 0.98, 1.0),
    "bus": (0.20, 0.48, 0.98, 1.0),
    "default": (0.20, 0.48, 0.98, 1.0),
}

LAND_USE_COLORS = {
    "B1": (0.98, 0.56, 0.20, 1.0),
    "B2": (0.98, 0.56, 0.20, 1.0),
    "R": (0.98, 0.56, 0.20, 1.0),
    "default": (0.98, 0.56, 0.20, 1.0),
}

BASE_MATERIALS = {
    "intersection": (0.95, 0.12, 0.12, 1.0),
    "ground": (0.20, 0.20, 0.20, 1.0),
    "centerline": (0.95, 0.12, 0.12, 1.0),
}


def _to_prop_key(key: str) -> str:
    return str(key).replace(" ", "_")


def attach_all_properties(obj: bpy.types.Object, data: dict, prefix: str = "") -> None:
    if not isinstance(data, dict):
        return

    for k, v in data.items():
        key = f"{prefix}{_to_prop_key(k)}"
        if isinstance(v, (str, int, float, bool)) or v is None:
            obj[key] = v
        elif isinstance(v, dict):
            obj[f"{key}_json"] = json.dumps(v, ensure_ascii=False)
            attach_all_properties(obj, v, prefix=f"{key}__")
        elif isinstance(v, list):
            obj[f"{key}_json"] = json.dumps(v, ensure_ascii=False)
        else:
            obj[key] = str(v)


def resolve_inputs() -> Tuple[str, Optional[str]]:
    json_path = JSON_PATH
    settings_path = SETTINGS_PATH

    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if args and not json_path:
            json_path = args[0]
        if len(args) > 1 and not settings_path:
            settings_path = args[1]

    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base_dir = bpy.path.abspath("//")

    if not json_path:
        json_path = os.path.join(base_dir, "step1_test_input.json")
    if not settings_path:
        candidate = os.path.join(base_dir, "setting.yaml")
        if os.path.exists(candidate):
            settings_path = candidate

    if not os.path.isabs(json_path):
        json_path = os.path.join(os.getcwd(), json_path)
    if settings_path and not os.path.isabs(settings_path):
        settings_path = os.path.join(os.getcwd(), settings_path)

    return json_path, settings_path


def parse_simple_yaml_widths(path: str) -> Dict[str, float]:
    widths: Dict[str, float] = {}
    if not path or not os.path.exists(path):
        return widths

    in_section = False
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if not in_section:
                if stripped.startswith("default_road_width_by_class:"):
                    in_section = True
                continue

            if line and not line.startswith(" ") and not line.startswith("\t"):
                break

            if ":" not in stripped:
                continue

            k, v = stripped.split(":", 1)
            key = k.strip().strip('"').strip("'")
            val = v.strip()
            if not val:
                continue
            try:
                widths[key] = float(val)
            except ValueError:
                pass

    return widths


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
        output = nodes.new(type="ShaderNodeOutputMaterial")
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

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


def assign_material(obj: bpy.types.Object, mat_name: str, rgba: Tuple[float, float, float, float]) -> None:
    mat = create_material(mat_name, rgba)
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


def polyline_to_curve(name: str, points: Sequence[Sequence[float]], z: float, thickness: float) -> Optional[bpy.types.Object]:
    pts = []
    for p in points or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            q = (float(p[0]), float(p[1]))
            if not pts or q != pts[-1]:
                pts.append(q)
    if len(pts) < 2:
        return None

    curve = bpy.data.curves.new(name=f"{name}_Curve", type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new(type="POLY")
    spline.points.add(len(pts) - 1)
    for i, (x, y) in enumerate(pts):
        spline.points[i].co = (x, y, z, 1.0)
    spline.use_cyclic_u = False
    curve.bevel_depth = thickness
    return bpy.data.objects.new(name, curve)


def quad_segment(name: str, p0: Tuple[float, float], p1: Tuple[float, float], half_w: float, z: float = 0.0) -> Optional[bpy.types.Object]:
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    dy = y1 - y0
    seg_len = math.hypot(dx, dy)
    if seg_len < 1e-6:
        return None

    nx = -dy / seg_len
    ny = dx / seg_len

    verts = [
        (x0 + nx * half_w, y0 + ny * half_w, z),
        (x1 + nx * half_w, y1 + ny * half_w, z),
        (x1 - nx * half_w, y1 - ny * half_w, z),
        (x0 - nx * half_w, y0 - ny * half_w, z),
    ]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(verts, [], [[0, 1, 2, 3]])
    mesh.update()
    return bpy.data.objects.new(name, mesh)


def marker_box(name: str, x: float, y: float, sx: float, sy: float, sz: float, z0: float = 0.0) -> bpy.types.Object:
    hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
    verts = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    faces = [[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, z0 + hz)
    return obj


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

    sun = bpy.data.objects.get("InputPreviewSun")
    if sun is None:
        light = bpy.data.lights.new("InputPreviewSun", "SUN")
        light.energy = 3.0
        sun = bpy.data.objects.new("InputPreviewSun", light)
        scene.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 500.0)
    sun.rotation_euler = (math.radians(55), 0.0, math.radians(35))

    cam = bpy.data.objects.get("InputPreviewCamera")
    if cam is None:
        cam_data = bpy.data.cameras.new("InputPreviewCamera")
        cam = bpy.data.objects.new("InputPreviewCamera", cam_data)
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.clip_end = 3000.0

    if not bounds:
        cam.location = (300.0, -600.0, 450.0)
        cam.rotation_euler = (math.radians(65), 0.0, math.radians(30))
        return

    (minx, miny, _), (maxx, maxy, maxz) = bounds
    cx, cy = (minx + maxx) * 0.5, (miny + maxy) * 0.5
    ext = max(maxx - minx, maxy - miny, 50.0)
    cam.location = (cx + ext * 0.35, cy - ext * 1.1, maxz + ext * 0.65)
    cam.rotation_euler = (math.radians(62), 0.0, math.radians(30))


def run(json_path: str, settings_path: Optional[str]) -> None:
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Input JSON not found: {json_path}")

    print(f"[Load] scene: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    settings_widths: Dict[str, float] = {}
    if settings_path:
        settings_widths = parse_simple_yaml_widths(settings_path)
        print(f"[Load] settings: {settings_path} (road_width_classes={len(settings_widths)})")

    widths = ((data.get("global_settings", {}) or {}).get("default_road_width_by_class", {}) or {}).copy()
    widths.update(settings_widths)

    root = ensure_collection(ROOT_COLLECTION)
    col_roads = ensure_collection("Roads", root)
    col_center = ensure_collection("RoadCenterlines", root)
    col_inter = ensure_collection("Intersections", root)
    col_transit = ensure_collection("TransitNodes", root)
    col_planning = ensure_collection("PlanningControls", root)

    if CLEANUP:
        print("[Cleanup] Removing old preview objects")
        for c in [col_roads, col_center, col_inter, col_transit, col_planning]:
            clear_collection_objects(c)

    created = []

    roads = (data.get("inputs", {}) or {}).get("roads", []) or []
    for road in roads:
        rid = str(road.get("id", "road"))
        rclass = str(road.get("road_class", "default"))
        centerline = road.get("centerline") or []
        if len(centerline) < 2:
            print(f"[Skip] road {rid}: invalid centerline")
            continue

        custom_width = road.get("custom_width")
        if custom_width is not None:
            width = float(custom_width)
        else:
            width = float(widths.get(rclass, widths.get("local", 8.0)))

        for i in range(len(centerline) - 1):
            p0 = (float(centerline[i][0]), float(centerline[i][1]))
            p1 = (float(centerline[i + 1][0]), float(centerline[i + 1][1]))
            surf = quad_segment(f"Road_{rid}_seg{i+1}", p0, p1, half_w=width * 0.5, z=0.0)
            if surf:
                link_only(surf, col_roads)
                color = ROAD_CLASS_COLORS.get(rclass, ROAD_CLASS_COLORS["default"])
                assign_material(surf, f"road_{rclass}", color)
                surf["source_id"] = rid
                surf["road_class"] = rclass
                surf["road_width"] = width
                surf["segment_index"] = i + 1
                attach_all_properties(surf, road, prefix="src__")
                created.append(surf)

        cl = polyline_to_curve(f"Centerline_{rid}", centerline, z=0.08, thickness=0.18)
        if cl:
            link_only(cl, col_center)
            assign_material(cl, "centerline", BASE_MATERIALS["centerline"])
            cl["source_id"] = rid
            attach_all_properties(cl, road, prefix="src__")
            created.append(cl)

    intersections = (data.get("inputs", {}) or {}).get("intersections", []) or []
    for inter in intersections:
        iid = str(inter.get("id", "int"))
        pos = inter.get("position")
        if not isinstance(pos, list) or len(pos) < 2:
            continue
        obj = marker_box(f"Intersection_{iid}", float(pos[0]), float(pos[1]), 2.0, 2.0, 0.4, z0=0.05)
        link_only(obj, col_inter)
        assign_material(obj, "intersection", BASE_MATERIALS["intersection"])
        obj["source_id"] = iid
        attach_all_properties(obj, inter, prefix="src__")
        created.append(obj)

    transit_nodes = (data.get("inputs", {}) or {}).get("transit_nodes", []) or []
    for n in transit_nodes:
        nid = str(n.get("id", "node"))
        ntype = str(n.get("type", "default"))
        pos = n.get("position")
        if not isinstance(pos, list) or len(pos) < 2:
            continue

        if ntype == "metro":
            obj = marker_box(f"Transit_{nid}", float(pos[0]), float(pos[1]), 3.0, 3.0, 1.8, z0=0.08)
        else:
            obj = marker_box(f"Transit_{nid}", float(pos[0]), float(pos[1]), 2.2, 2.2, 1.2, z0=0.08)

        link_only(obj, col_transit)
        color = NODE_COLORS.get(ntype, NODE_COLORS["default"])
        assign_material(obj, f"transit_{ntype}", color)
        obj["source_id"] = nid
        obj["node_type"] = ntype
        attach_all_properties(obj, n, prefix="src__")
        created.append(obj)

    planning_controls = (data.get("inputs", {}) or {}).get("planning_controls", {}) or {}
    parcel_controls = planning_controls.get("parcel_controls", [])
    if not parcel_controls and planning_controls.get("parcel_id"):
        parcel_controls = [planning_controls]

    for pc in parcel_controls or []:
        pid = str(pc.get("parcel_id", "parcel"))
        land_use = str(pc.get("land_use", "default"))
        center = pc.get("center")
        if not isinstance(center, list) or len(center) < 2:
            continue

        obj = marker_box(f"ParcelCtrl_{pid}", float(center[0]), float(center[1]), 6.0, 6.0, 2.2, z0=0.10)
        link_only(obj, col_planning)
        color = LAND_USE_COLORS.get(land_use, LAND_USE_COLORS["default"])
        assign_material(obj, f"planning_{land_use}", color)
        obj["source_id"] = pid
        obj["land_use"] = land_use
        attach_all_properties(obj, pc, prefix="src__")
        created.append(obj)

    if ADD_GROUND and created:
        b = compute_bounds(created)
        if b:
            (minx, miny, _), (maxx, maxy, _) = b
            margin = 40.0
            verts = [
                (minx - margin, miny - margin, -0.05),
                (maxx + margin, miny - margin, -0.05),
                (maxx + margin, maxy + margin, -0.05),
                (minx - margin, maxy + margin, -0.05),
            ]
            mesh = bpy.data.meshes.new("InputGround_Mesh")
            mesh.from_pydata(verts, [], [[0, 1, 2, 3]])
            mesh.update()
            ground = bpy.data.objects.new("InputGround", mesh)
            link_only(ground, col_roads)
            assign_material(ground, "ground", BASE_MATERIALS["ground"])
            ground.hide_set(True)
            ground.hide_render = True
            created.append(ground)

    if AUTO_FRAME:
        ensure_camera_light(compute_bounds(created))

    print("[Summary]")
    print(f"  roads: {len(roads)}")
    print(f"  intersections: {len(intersections)}")
    print(f"  transit_nodes: {len(transit_nodes)}")
    print(f"  parcel_controls: {len(parcel_controls or [])}")
    print("[Done] Step1 input preview generated")


def main() -> None:
    json_path, settings_path = resolve_inputs()
    run(json_path, settings_path)


if __name__ == "__main__":
    main()
