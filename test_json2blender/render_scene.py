"""
render_scene.py

Usage:
1) Blender UI:
   - Open this file in Blender's Scripting workspace and run it.
   - Optionally set JSON_PATH below.

2) Command line:
   blender --background --python render_scene.py -- sample_scene.json
"""

import json
import math
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import bmesh
import bpy
from mathutils import Vector


SHOW_FUNCTIONAL_ZONES = True
CLEANUP_GENERATED_COLLECTIONS = True
ADD_GROUND_PLANE = True
AUTO_FRAME_CAMERA = True
JSON_PATH = None

COLLECTION_NAMES = [
    "Blocks",
    "Buildings",
    "OpenSpaces",
    "WalkableSpaces",
    "NodeSpaces",
    "FunctionalZones",
    "Elements",
]

MATERIAL_PALETTE = {
    "building_facade_commercial": (0.75, 0.74, 0.72, 1.0),
    "building_facade_office": (0.64, 0.70, 0.76, 1.0),
    "building_facade_residential": (0.82, 0.78, 0.73, 1.0),
    "pavement_main": (0.42, 0.42, 0.42, 1.0),
    "indoor_floor_mall": (0.60, 0.56, 0.50, 1.0),
    "urban_furniture_default": (0.30, 0.28, 0.25, 1.0),
    "plaza_default": (0.55, 0.52, 0.48, 1.0),
    "atrium_default": (0.76, 0.72, 0.64, 1.0),
    "functional_zone_overlay": (0.95, 0.45, 0.20, 0.40),
    "node_space_default": (0.20, 0.55, 0.78, 1.0),
    "block_outline": (0.15, 0.15, 0.15, 1.0),
    "block_ground": (0.30, 0.30, 0.30, 1.0),
}

WALKABLE_MATERIAL_BY_TYPE = {
    "street_clear_path": "pavement_main",
    "entrance_threshold": "pavement_main",
    "indoor_public_corridor": "indoor_floor_mall",
    "semi_public_frontage_band": "pavement_main",
    "lobby_space": "indoor_floor_mall",
    "atrium_spillout": "atrium_default",
}

BUILDING_MATERIAL_BY_TYPE = {
    "mall": "building_facade_commercial",
    "office": "building_facade_office",
    "residential": "building_facade_residential",
}

ELEMENT_DIMS = {
    "bench": (1.6, 0.5, 0.5),
    "signage": (0.2, 0.8, 2.2),
    "planter": (1.0, 1.0, 0.6),
    "parcel_locker": (1.6, 0.6, 2.0),
    "frontdesk": (2.2, 0.8, 1.1),
}


def load_json(path: str) -> dict:
    print(f"[Load] Reading JSON: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_schema(data: dict) -> None:
    required_top = {"schema_version", "scene_info", "generated", "semantics", "render_bindings"}
    missing = sorted(required_top.difference(data.keys()))
    if missing:
        raise ValueError(f"Missing required top-level keys: {missing}")


def ensure_collection(name: str) -> bpy.types.Collection:
    scene = bpy.context.scene
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        scene.collection.children.link(col)
    elif col.name not in scene.collection.children:
        scene.collection.children.link(col)
    return col


def clear_collection_objects(collection: bpy.types.Collection) -> None:
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def create_material(name: str, rgba: Optional[Tuple[float, float, float, float]] = None) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)

    color = rgba if rgba is not None else MATERIAL_PALETTE.get(name, (0.8, 0.8, 0.8, 1.0))
    if mat.node_tree is None:
        try:
            mat.use_nodes = True
        except Exception:
            pass
    if mat.node_tree is None:
        return mat

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        output = nodes.new(type="ShaderNodeOutputMaterial")
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.75
        bsdf.inputs["Metallic"].default_value = 0.0
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3]

    if color[3] < 1.0:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "NONE"
    return mat


def assign_material(obj: bpy.types.Object, material_name: str) -> None:
    mat = create_material(material_name)
    if obj.data and hasattr(obj.data, "materials"):
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat


def clean_polygon_2d(polygon: Sequence[Sequence[float]]) -> List[Tuple[float, float]]:
    if not polygon:
        return []
    pts = [(float(p[0]), float(p[1])) for p in polygon if len(p) >= 2]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]

    cleaned = []
    for pt in pts:
        if not cleaned or pt != cleaned[-1]:
            cleaned.append(pt)
    return cleaned


def polygon_to_mesh(name: str, polygon: Sequence[Sequence[float]], z: float = 0.0) -> Optional[bpy.types.Object]:
    pts = clean_polygon_2d(polygon)
    if len(pts) < 3:
        print(f"[Skip] {name}: invalid polygon")
        return None

    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    verts = [(x, y, z) for x, y in pts]
    faces = [list(range(len(verts)))]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return obj


def extrude_polygon(name: str, polygon: Sequence[Sequence[float]], height: float) -> Optional[bpy.types.Object]:
    pts = clean_polygon_2d(polygon)
    if len(pts) < 3:
        print(f"[Skip] {name}: invalid footprint")
        return None

    bm = bmesh.new()
    verts = [bm.verts.new((x, y, 0.0)) for x, y in pts]
    bm.verts.ensure_lookup_table()
    try:
        base = bm.faces.new(verts)
    except ValueError:
        bmesh.ops.contextual_create(bm, geom=verts)
        faces = bm.faces[:]
        if not faces:
            bm.free()
            print(f"[Skip] {name}: failed face creation")
            return None
        base = faces[0]

    ext = bmesh.ops.extrude_face_region(bm, geom=[base])
    ext_verts = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, 0.0, float(height)), verts=ext_verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    return obj


def create_outline_curve(name: str, polygon: Sequence[Sequence[float]], z: float = 0.02) -> Optional[bpy.types.Object]:
    pts = clean_polygon_2d(polygon)
    if len(pts) < 2:
        return None

    curve = bpy.data.curves.new(name=f"{name}_Curve", type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new(type="POLY")
    spline.points.add(len(pts) - 1)
    for i, (x, y) in enumerate(pts):
        spline.points[i].co = (x, y, z, 1.0)
    spline.use_cyclic_u = True
    curve.bevel_depth = 0.03

    obj = bpy.data.objects.new(name, curve)
    return obj


def create_polyline_curve(name: str, polyline: Sequence[Sequence[float]], z: float = 0.02) -> Optional[bpy.types.Object]:
    pts = clean_polygon_2d(polyline)
    if len(pts) < 2:
        return None

    curve = bpy.data.curves.new(name=f"{name}_Curve", type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new(type="POLY")
    spline.points.add(len(pts) - 1)
    for i, (x, y) in enumerate(pts):
        spline.points[i].co = (x, y, z, 1.0)
    spline.use_cyclic_u = False
    curve.bevel_depth = 0.02

    obj = bpy.data.objects.new(name, curve)
    return obj


def link_object_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    for col in list(obj.users_collection):
        if col != collection:
            col.objects.unlink(obj)


def build_semantic_index(data: dict) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    semantics = data.get("semantics", {})
    for section in ("space_labels", "element_labels"):
        for item in semantics.get(section, []) or []:
            target_id = item.get("target_id")
            label = item.get("label")
            if not target_id or not label:
                continue
            index.setdefault(target_id, []).append(str(label))

    for k, labels in index.items():
        unique = []
        seen = set()
        for label in labels:
            if label not in seen:
                unique.append(label)
                seen.add(label)
        index[k] = unique
    return index


def attach_semantic_labels(obj: bpy.types.Object, target_id: str, semantic_index: Dict[str, List[str]]) -> None:
    labels = semantic_index.get(target_id, [])
    if labels:
        obj["semantic_label"] = ",".join(labels)


def create_proxy_element(
    name: str,
    element_type: str,
    position: Sequence[float],
    rotation: float = 0.0,
) -> bpy.types.Object:
    dims = ELEMENT_DIMS.get(element_type, (1.0, 1.0, 1.0))
    x = float(position[0])
    y = float(position[1])
    z = dims[2] * 0.5

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z), rotation=(0.0, 0.0, float(rotation)))
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = dims
    return obj


def apply_metadata(obj: bpy.types.Object, item_id: str, render_bindings: dict) -> None:
    mat_map = render_bindings.get("material_classes", {}) or {}
    asset_map = render_bindings.get("asset_classes", {}) or {}
    style_map = render_bindings.get("style_tags", {}) or {}

    if item_id in asset_map:
        obj["asset_class"] = str(asset_map[item_id])
    if item_id in style_map:
        tags = style_map[item_id]
        if isinstance(tags, list):
            obj["style_tags"] = ",".join(str(t) for t in tags)
        else:
            obj["style_tags"] = str(tags)


def material_for_id(item_id: str, default_name: str, render_bindings: dict) -> str:
    mat_map = render_bindings.get("material_classes", {}) or {}
    return str(mat_map.get(item_id, default_name))


def compute_bounds(objects: List[bpy.types.Object]) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    if not objects:
        return None

    min_v = [math.inf, math.inf, math.inf]
    max_v = [-math.inf, -math.inf, -math.inf]

    for obj in objects:
        if obj.type not in {"MESH", "CURVE"}:
            continue
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            min_v[0] = min(min_v[0], w.x)
            min_v[1] = min(min_v[1], w.y)
            min_v[2] = min(min_v[2], w.z)
            max_v[0] = max(max_v[0], w.x)
            max_v[1] = max(max_v[1], w.y)
            max_v[2] = max(max_v[2], w.z)

    if math.isinf(min_v[0]):
        return None
    return (tuple(min_v), tuple(max_v))


def ensure_camera_and_light(bounds: Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]) -> None:
    scene = bpy.context.scene

    sun = bpy.data.objects.get("PreviewSun")
    if sun is None:
        sun_data = bpy.data.lights.new(name="PreviewSun", type="SUN")
        sun_data.energy = 3.0
        sun = bpy.data.objects.new("PreviewSun", sun_data)
        scene.collection.objects.link(sun)
    sun.location = (0.0, 0.0, 80.0)
    sun.rotation_euler = (math.radians(55.0), 0.0, math.radians(35.0))

    cam = bpy.data.objects.get("PreviewCamera")
    if cam is None:
        cam_data = bpy.data.cameras.new(name="PreviewCamera")
        cam = bpy.data.objects.new("PreviewCamera", cam_data)
        scene.collection.objects.link(cam)
        scene.camera = cam

    if not bounds:
        cam.location = (40.0, -80.0, 60.0)
        cam.rotation_euler = (math.radians(65.0), 0.0, math.radians(25.0))
        return

    (min_x, min_y, _), (max_x, max_y, max_z) = bounds
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5
    extent = max(max_x - min_x, max_y - min_y, 20.0)

    cam.location = (cx + extent * 0.45, cy - extent * 1.25, max_z + extent * 0.8)
    cam.rotation_euler = (math.radians(62.0), 0.0, math.radians(30.0))


def make_ground(bounds: Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]], collection: bpy.types.Collection) -> Optional[bpy.types.Object]:
    if not bounds:
        return None

    (min_x, min_y, _), (max_x, max_y, _) = bounds
    margin = 15.0
    polygon = [
        (min_x - margin, min_y - margin),
        (max_x + margin, min_y - margin),
        (max_x + margin, max_y + margin),
        (min_x - margin, max_y + margin),
        (min_x - margin, min_y - margin),
    ]
    obj = polygon_to_mesh("GroundPlane", polygon, z=-0.02)
    if obj is None:
        return None

    link_object_to_collection(obj, collection)
    assign_material(obj, "pavement_main")
    return obj


def resolve_input_path() -> str:
    if JSON_PATH:
        return JSON_PATH

    argv = sys.argv
    if "--" in argv:
        idx = argv.index("--")
        if idx + 1 < len(argv):
            return argv[idx + 1]

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = bpy.path.abspath("//")

    default_path = os.path.join(script_dir, "sample_scene.json")
    return default_path


def run(json_path: str) -> None:
    data = load_json(json_path)
    validate_schema(data)

    generated = data.get("generated", {}) or {}
    render_bindings = data.get("render_bindings", {}) or {}
    semantic_index = build_semantic_index(data)

    collections = {name: ensure_collection(name) for name in COLLECTION_NAMES}
    if CLEANUP_GENERATED_COLLECTIONS:
        print("[Cleanup] Removing old generated objects")
        for col in collections.values():
            clear_collection_objects(col)

    for mat_name, rgba in MATERIAL_PALETTE.items():
        create_material(mat_name, rgba)

    created_objects: List[bpy.types.Object] = []
    counts = {
        "blocks": 0,
        "buildings": 0,
        "walkable_spaces": 0,
        "elements": 0,
    }

    print("[Generate] block_boundaries")
    for item in generated.get("block_boundaries", []) or []:
        item_id = item.get("id")
        polygon = item.get("polygon")
        if not item_id or not polygon:
            print("[Skip] block boundary missing id or polygon")
            continue

        outline = create_outline_curve(f"BlockOutline_{item_id}", polygon, z=0.03)
        if outline:
            link_object_to_collection(outline, collections["Blocks"])
            assign_material(outline, "block_outline")
            outline["source_id"] = item_id
            attach_semantic_labels(outline, item_id, semantic_index)
            created_objects.append(outline)

        fill = polygon_to_mesh(f"Block_{item_id}", polygon, z=0.0)
        if fill:
            link_object_to_collection(fill, collections["Blocks"])
            assign_material(fill, "block_ground")
            fill["source_id"] = item_id
            attach_semantic_labels(fill, item_id, semantic_index)
            created_objects.append(fill)
            counts["blocks"] += 1

    print("[Generate] frontage_segments")
    for item in generated.get("frontage_segments", []) or []:
        item_id = item.get("id")
        polyline = item.get("polyline")
        if not item_id or not polyline:
            continue

        obj = create_polyline_curve(f"Frontage_{item_id}", polyline, z=0.05)
        if obj is None:
            continue

        link_object_to_collection(obj, collections["Blocks"])
        assign_material(obj, "block_outline")
        obj["source_id"] = item_id
        obj["frontage_type"] = str(item.get("frontage_type", "frontage"))
        attach_semantic_labels(obj, item_id, semantic_index)
        created_objects.append(obj)

    print("[Generate] building_masses")
    for item in generated.get("building_masses", []) or []:
        item_id = item.get("id")
        footprint = item.get("footprint")
        if not item_id or not footprint:
            print("[Skip] building missing id or footprint")
            continue

        height = float(item.get("height", 12.0))
        obj = extrude_polygon(f"Bld_{item_id}", footprint, height)
        if obj is None:
            continue

        link_object_to_collection(obj, collections["Buildings"])
        bld_type = str(item.get("building_type", "commercial"))
        default_mat = BUILDING_MATERIAL_BY_TYPE.get(bld_type, "building_facade_commercial")
        mat_name = material_for_id(item_id, default_mat, render_bindings)
        assign_material(obj, mat_name)
        obj["source_id"] = item_id
        obj["building_type"] = bld_type
        apply_metadata(obj, item_id, render_bindings)
        attach_semantic_labels(obj, item_id, semantic_index)

        created_objects.append(obj)
        counts["buildings"] += 1

    print("[Generate] atriums")
    for item in generated.get("atriums", []) or []:
        item_id = item.get("id")
        polygon = item.get("polygon")
        if not item_id or not polygon:
            continue

        obj = polygon_to_mesh(f"Atrium_{item_id}", polygon, z=0.05)
        if obj is None:
            continue

        link_object_to_collection(obj, collections["OpenSpaces"])
        mat_name = material_for_id(item_id, "atrium_default", render_bindings)
        assign_material(obj, mat_name)
        obj["source_id"] = item_id
        obj["atrium"] = True
        apply_metadata(obj, item_id, render_bindings)
        attach_semantic_labels(obj, item_id, semantic_index)

        created_objects.append(obj)

    print("[Generate] reserved_open_spaces")
    for item in generated.get("reserved_open_spaces", []) or []:
        item_id = item.get("id")
        polygon = item.get("polygon")
        if not item_id or not polygon:
            continue

        obj = polygon_to_mesh(f"Open_{item_id}", polygon, z=0.02)
        if obj is None:
            continue

        link_object_to_collection(obj, collections["OpenSpaces"])
        mat_name = material_for_id(item_id, "plaza_default", render_bindings)
        assign_material(obj, mat_name)
        obj["source_id"] = item_id
        obj["open_space_type"] = str(item.get("open_space_type", "open_space"))
        apply_metadata(obj, item_id, render_bindings)
        attach_semantic_labels(obj, item_id, semantic_index)

        created_objects.append(obj)

    print("[Generate] walkable_spaces")
    for item in generated.get("walkable_spaces", []) or []:
        item_id = item.get("id")
        polygon = item.get("polygon")
        if not item_id or not polygon:
            continue

        obj = polygon_to_mesh(f"Walk_{item_id}", polygon, z=0.03)
        if obj is None:
            continue

        link_object_to_collection(obj, collections["WalkableSpaces"])
        space_type = str(item.get("space_type", "street_clear_path"))
        default_mat = WALKABLE_MATERIAL_BY_TYPE.get(space_type, "pavement_main")
        mat_name = material_for_id(item_id, default_mat, render_bindings)
        assign_material(obj, mat_name)
        obj["source_id"] = item_id
        obj["space_type"] = space_type
        apply_metadata(obj, item_id, render_bindings)
        attach_semantic_labels(obj, item_id, semantic_index)

        created_objects.append(obj)
        counts["walkable_spaces"] += 1

    print("[Generate] node_spaces")
    for item in generated.get("node_spaces", []) or []:
        item_id = item.get("id")
        polygon = item.get("polygon")
        if not item_id or not polygon:
            continue

        obj = polygon_to_mesh(f"Node_{item_id}", polygon, z=0.04)
        if obj is None:
            continue

        link_object_to_collection(obj, collections["NodeSpaces"])
        mat_name = material_for_id(item_id, "node_space_default", render_bindings)
        assign_material(obj, mat_name)
        obj["source_id"] = item_id
        obj["node_space_type"] = str(item.get("node_space_type", "node_space"))
        apply_metadata(obj, item_id, render_bindings)
        attach_semantic_labels(obj, item_id, semantic_index)

        created_objects.append(obj)

    if SHOW_FUNCTIONAL_ZONES:
        print("[Generate] functional_zones")
        for item in generated.get("functional_zones", []) or []:
            item_id = item.get("id")
            polygon = item.get("polygon")
            if not item_id or not polygon:
                continue

            obj = polygon_to_mesh(f"FZone_{item_id}", polygon, z=0.06)
            if obj is None:
                continue

            link_object_to_collection(obj, collections["FunctionalZones"])
            mat_name = material_for_id(item_id, "functional_zone_overlay", render_bindings)
            assign_material(obj, mat_name)
            obj["source_id"] = item_id
            obj["zone_type"] = str(item.get("zone_type", "functional_zone"))
            apply_metadata(obj, item_id, render_bindings)
            attach_semantic_labels(obj, item_id, semantic_index)

            created_objects.append(obj)

    print("[Generate] placed_elements")
    for item in generated.get("placed_elements", []) or []:
        item_id = item.get("id")
        element_type = str(item.get("element_type", "bench"))
        pos = item.get("position")
        if not item_id or not isinstance(pos, list) or len(pos) < 2:
            print("[Skip] placed element missing id or position")
            continue

        rot = float(item.get("rotation", 0.0))
        obj = create_proxy_element(f"Elem_{item_id}", element_type, pos, rot)
        link_object_to_collection(obj, collections["Elements"])

        mat_name = material_for_id(item_id, "urban_furniture_default", render_bindings)
        assign_material(obj, mat_name)
        obj["source_id"] = item_id
        obj["element_type"] = element_type
        apply_metadata(obj, item_id, render_bindings)
        attach_semantic_labels(obj, item_id, semantic_index)

        created_objects.append(obj)
        counts["elements"] += 1

    bounds = compute_bounds(created_objects)
    if ADD_GROUND_PLANE:
        ground = make_ground(bounds, collections["Blocks"])
        if ground:
            created_objects.append(ground)
            bounds = compute_bounds(created_objects)

    if AUTO_FRAME_CAMERA:
        ensure_camera_and_light(bounds)

    print("[Summary]")
    print(f"  blocks: {counts['blocks']}")
    print(f"  buildings: {counts['buildings']}")
    print(f"  walkable_spaces: {counts['walkable_spaces']}")
    print(f"  elements: {counts['elements']}")
    print("[Done] Scene generation completed")


def main() -> None:
    path = resolve_input_path()
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input JSON not found: {path}")

    run(path)


if __name__ == "__main__":
    main()
