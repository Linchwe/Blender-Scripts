# Bisect_Half.py
# Blender 4.2 ~ 4.5
# Cuts the selected meshes exactly on the world X=0 (or Y, Z) plane and deletes one half.
# Faces that cross the center line are cut in place, so the center line stays clean.
#
# Usage: select mesh(es) in Object Mode (multiple OK) > Scripting tab > New text > Paste
#        > Check the settings below > Run Script
# Save with Ctrl+S before running. (You can also undo with Ctrl+Z)

import bpy
import bmesh
from mathutils import Vector

# ---------------- Settings ----------------
AXIS = 'X'            # Axis to cut on: 'X', 'Y', 'Z'
KEEP_SIDE = '+'       # Side to keep: '+' (plus side of the axis), '-' (minus side)
                      #   On the X axis, '+' = screen right when viewing the character from the front = the character's left
PLANE_OFFSET = 0.0    # Cut position (world coordinate, usually 0)
FILL_CUT = False      # Fill the cut opening with a face (False if you will mirror it back)
ADD_MIRROR = False    # Add a Mirror modifier after cutting (clipping on)
# --------------------------------------

AXIS_VEC = {'X': Vector((1, 0, 0)), 'Y': Vector((0, 1, 0)), 'Z': Vector((0, 0, 1))}


def bisect_object(obj):
    mw = obj.matrix_world
    mw_inv = mw.inverted()

    # Convert the world-space plane to object local space
    n_world = AXIS_VEC[AXIS]
    co_world = n_world * PLANE_OFFSET
    co_local = mw_inv @ co_world
    n_local = (mw.to_3x3().transposed() @ n_world).normalized()

    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    result = bmesh.ops.bisect_plane(
        bm,
        geom=geom,
        dist=0.0001,
        plane_co=co_local,
        plane_no=n_local,
        clear_inner=(KEEP_SIDE == '+'),   # delete the minus side
        clear_outer=(KEEP_SIDE == '-'),   # delete the plus side
    )

    if FILL_CUT:
        cut_edges = [e for e in result["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if cut_edges:
            bmesh.ops.edgeloop_fill(bm, edges=cut_edges)

    bm.to_mesh(me)
    bm.free()
    me.update()

    if ADD_MIRROR:
        mod = obj.modifiers.new(name="Mirror_Half", type='MIRROR')
        mod.use_axis = [AXIS == 'X', AXIS == 'Y', AXIS == 'Z']
        mod.use_clip = True
        mod.use_mirror_merge = True

    print(f"[{obj.name}] Kept the '{KEEP_SIDE}' side of {AXIS}={PLANE_OFFSET}")


def main():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes:
        print("Please select a mesh.")
        return
    for obj in meshes:
        bisect_object(obj)
    print(f"Done: {len(meshes)} object(s)")


main()
