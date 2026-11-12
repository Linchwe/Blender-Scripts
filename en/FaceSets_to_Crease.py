# FaceSets_to_Crease.py
# Blender 4.2 ~ 4.5
#
# Purpose
#  Automatically adds Crease to the boundary edges between Face Sets made in Sculpt Mode.
#  Keeps Face Set borders (clothing seams, part borders, etc.) sharp instead of smoothed out under Subdivision Surface.
#
# What it does
#  1) Finds edges where two faces from different Face Sets meet (Face Set boundaries) and sets their crease to CREASE_VALUE.
#  2) Edges inside the same Face Set are not touched.
#  3) With INCLUDE_OPEN_EDGES on, also creases the mesh's open borders (edges with a face on only one side).
#  4) Switches to Object Mode briefly to process, then returns to the original mode (Sculpt, Edit, etc.).
#
# Notes
#  - Meshes that never had Face Sets created have no Face Set data and are skipped.
#  - By default existing creases are kept and only boundary edges are overwritten. To start over, set CLEAR_EXISTING = True.
#  - Crease is only visible when there is a Subdivision Surface modifier.
#
# Usage
#  1) Select mesh(es). (Multiple OK, can run directly from Sculpt Mode)
#  2) Scripting tab > New text > Paste > Check the settings > Run Script
#  3) Save with Ctrl+S before running. You can undo with Ctrl+Z.

import bpy
import numpy as np

# ---------------- Settings ----------------
CREASE_VALUE = 1.0          # Crease value to apply (0.0 ~ 1.0, 1.0 = fully sharp)
INCLUDE_OPEN_EDGES = False  # True: also crease the mesh's open borders (edges with a face on only one side)
CLEAR_EXISTING = False      # True: reset all existing creases to 0, then apply
# --------------------------------------


def apply_crease(obj):
    mesh = obj.data

    # Face Sets are stored as one integer per face in the hidden attribute ".sculpt_face_set"
    fs_attr = mesh.attributes.get(".sculpt_face_set")
    if fs_attr is None:
        print(f"[{obj.name}] No Face Set data, skipped.")
        return

    n_poly = len(mesh.polygons)
    n_edge = len(mesh.edges)
    n_loop = len(mesh.loops)

    # ---- 1) Face Set index per face ----
    fs_vals = np.empty(n_poly, dtype=np.int32)
    fs_attr.data.foreach_get("value", fs_vals)

    # ---- 2) For each loop (face corner): which edge / which face ----
    loop_edge = np.empty(n_loop, dtype=np.int32)
    mesh.loops.foreach_get("edge_index", loop_edge)

    loop_total = np.empty(n_poly, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", loop_total)
    loop_face = np.repeat(np.arange(n_poly, dtype=np.int32), loop_total)

    loop_fs = fs_vals[loop_face]   # Face Set index of each loop's face

    # ---- 3) Per edge: min / max Face Set index of attached faces, and face count ----
    big = np.iinfo(np.int32).max
    e_min = np.full(n_edge, big, dtype=np.int64)
    e_max = np.full(n_edge, -big, dtype=np.int64)
    e_cnt = np.zeros(n_edge, dtype=np.int32)

    np.minimum.at(e_min, loop_edge, loop_fs)
    np.maximum.at(e_max, loop_edge, loop_fs)
    np.add.at(e_cnt, loop_edge, 1)

    # Boundary edge: 2 or more attached faces, and their Face Set indices differ
    boundary = (e_cnt >= 2) & (e_min != e_max)
    if INCLUDE_OPEN_EDGES:
        boundary |= (e_cnt == 1)   # open border with a face on only one side

    # ---- 4) Write crease ----
    #  Since Blender 4.0, edge crease is stored in the "crease_edge" edge attribute (created if missing)
    crease_attr = mesh.attributes.get("crease_edge")
    if crease_attr is None:
        crease_attr = mesh.attributes.new("crease_edge", 'FLOAT', 'EDGE')

    crease = np.zeros(n_edge, dtype=np.float32)
    if not CLEAR_EXISTING:
        crease_attr.data.foreach_get("value", crease)   # keep existing values

    crease[boundary] = CREASE_VALUE
    crease_attr.data.foreach_set("value", crease)
    mesh.update()

    print(f"[{obj.name}] Creased {int(boundary.sum())} of {n_edge} edges "
          f"({len(np.unique(fs_vals))} Face Sets)")


def main():
    active = bpy.context.view_layer.objects.active
    prev_mode = active.mode if active else 'OBJECT'

    # Must be in Object Mode for Sculpt/Edit Mode changes to reach the mesh data
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes and active and active.type == 'MESH':
        meshes = [active]
    if not meshes:
        print("Please select a mesh.")
        return

    for obj in meshes:
        apply_crease(obj)

    # Return to the original mode
    if active and prev_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode=prev_mode)


main()
