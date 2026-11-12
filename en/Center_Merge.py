# Center_Merge.py
# Blender 4.2 ~ 4.5
# On a symmetric mesh, vertices crowded together on the center line (X=0)
# are grouped with their close neighbors and merged into one. (Cleanup after Decimate Symmetry)
#
# - Only points on the center line are merged with each other, so regular left/right vertices are not touched.
# - Merged points are snapped back to exactly X=0, so symmetry is kept.
# - "Close" is measured as a ratio of the mesh's typical edge length,
#   so the same settings work regardless of object size (scale).
#
# Usage: select mesh(es) in Object Mode (multiple OK) > Scripting tab > New text > Paste
#        > Check the settings > Run Script
# Save with Ctrl+S before running. You can undo with Ctrl+Z.

import bpy
import bmesh
from mathutils.kdtree import KDTree

# ---------------- Settings ----------------
AXIS = 'X'            # Symmetry axis (usually 'X')
CENTER_TOL = 0.02     # Center line width: within how many typical edge lengths counts as "on the center line"
MERGE_RATIO = 0.5     # Merge threshold: center points closer than this multiple of the typical edge length are merged
                      #   If too few merge, raise to 0.6~0.7; if too many merge, lower to 0.3~0.4
MAX_PASSES = 5        # How many times to re-check after merging (stops automatically when nothing changes)
# --------------------------------------

AXIS_INDEX = {'X': 0, 'Y': 1, 'Z': 2}[AXIS]


def median_edge_length(bm):
    lengths = sorted(e.calc_length() for e in bm.edges)
    if not lengths:
        return 0.0
    return lengths[len(lengths) // 2]


def center_verts(bm, tol):
    return [v for v in bm.verts if abs(v.co[AXIS_INDEX]) <= tol]


def merge_pass(bm, merge_dist, tol):
    """Merge groups of center-line points closer than merge_dist into one. Returns the number of merged points"""
    verts = center_verts(bm, tol)
    if len(verts) < 2:
        return 0

    kd = KDTree(len(verts))
    for i, v in enumerate(verts):
        kd.insert(v.co, i)
    kd.balance()

    used = [False] * len(verts)
    targetmap = {}
    for i, v in enumerate(verts):
        if used[i]:
            continue
        used[i] = True
        # Use v as the anchor and merge nearby center-line points into v
        cluster = [v]
        for co, j, dist in kd.find_range(v.co, merge_dist):
            if not used[j]:
                used[j] = True
                cluster.append(verts[j])
        if len(cluster) > 1:
            # Move the anchor to the group's average position, then merge the rest
            avg = sum((c.co for c in cluster), v.co * 0) / len(cluster)
            v.co = avg
            for c in cluster[1:]:
                targetmap[c] = v

    if not targetmap:
        return 0
    bmesh.ops.weld_verts(bm, targetmap=targetmap)
    return len(targetmap)


def cleanup(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    base = median_edge_length(bm)
    if base == 0.0:
        bm.free()
        print(f"[{obj.name}] The mesh has no edges.")
        return

    tol = base * CENTER_TOL
    merge_dist = base * MERGE_RATIO

    before_center = len(center_verts(bm, tol))
    before_total = len(bm.verts)

    merged = 0
    for _ in range(MAX_PASSES):
        c = merge_pass(bm, merge_dist, tol)
        merged += c
        if c == 0:
            break

    # Clean up degenerate faces/edges created by merging
    bmesh.ops.dissolve_degenerate(bm, dist=base * 0.001, edges=bm.edges[:])

    # Snap center-line points to exactly 0 (keeps symmetry)
    for v in center_verts(bm, tol):
        co = v.co.copy()
        co[AXIS_INDEX] = 0.0
        v.co = co

    after_center = len(center_verts(bm, tol))
    after_total = len(bm.verts)

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.update()
    print(f"[{obj.name}] Center-line vertices {before_center} -> {after_center} "
          f"(total {before_total} -> {after_total}), reference edge length {base:.5f}")


def main():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes:
        print("Please select a mesh.")
        return
    for obj in meshes:
        cleanup(obj)


main()
