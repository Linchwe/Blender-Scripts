# FaceSets_to_VertexColor.py
# Blender 4.2 ~ 4.5
# Converts the Face Sets of the selected meshes into vertex colors (Color Attribute).
# Each Face Set automatically gets a clearly distinct color. (For ID map baking)
#
# Usage: select a mesh in Object Mode > Scripting tab > New text > Paste > Run Script
# Result: a color attribute named "FaceSetID" is created and set as the active/render color.

import bpy
import colorsys

ATTR_NAME = "FaceSetID"   # Name of the color attribute to create
SATURATION = 0.85
VALUE = 0.95


def distinct_color(index):
    # Step the hue by the golden ratio so even neighboring indices get clearly different colors
    hue = (index * 0.618033988749895) % 1.0
    # Mix 3 brightness levels so colors stay distinguishable even when there are many
    val = VALUE - (index % 3) * 0.2
    r, g, b = colorsys.hsv_to_rgb(hue, SATURATION, val)
    return (r, g, b, 1.0)


def convert(obj):
    mesh = obj.data
    fs_attr = mesh.attributes.get(".sculpt_face_set")
    if fs_attr is None:
        print(f"[{obj.name}] No Face Sets. Paint them in Sculpt Mode first.")
        return

    face_count = len(mesh.polygons)
    face_sets = [0] * face_count
    fs_attr.data.foreach_get("value", face_sets)

    # Face Set index -> color
    ids = sorted(set(face_sets))
    color_of = {fid: distinct_color(i) for i, fid in enumerate(ids)}

    # Remove any existing attribute with the same name and create a new one
    old = mesh.color_attributes.get(ATTR_NAME)
    if old is not None:
        mesh.color_attributes.remove(old)
    col_attr = mesh.color_attributes.new(name=ATTR_NAME, type='BYTE_COLOR', domain='CORNER')

    # Fill all corners (loops) of each face with the same color
    loop_totals = [0] * face_count
    mesh.polygons.foreach_get("loop_total", loop_totals)
    flat = []
    for fid, total in zip(face_sets, loop_totals):
        c = color_of[fid]
        flat.extend(c * total)
    col_attr.data.foreach_set("color_srgb", flat)

    mesh.color_attributes.active_color = col_attr
    mesh.color_attributes.render_color_index = mesh.color_attributes.find(ATTR_NAME)
    mesh.update()
    print(f"[{obj.name}] Converted {len(ids)} Face Sets to the '{ATTR_NAME}' color attribute")


def main():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes:
        print("Please select a mesh.")
        return
    for obj in meshes:
        convert(obj)


main()
