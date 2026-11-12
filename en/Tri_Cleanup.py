# Tri_Cleanup.py
# Blender 4.2 ~ 4.5
#
# Purpose
#  Cleans up the face layout of a decimated triangle mesh in one run.
#
# What it does
#  [1] Pointless vertices in the middle of an edge (points with only 2 edges) -> dissolve
#  [2] Faces with 4 or more sides -> all split into triangles
#  [3] A triangle split into 3 triangles (3 edges meeting at a center point) -> dissolve the center point
#  [4] The long edge of a very thin triangle -> rotate to the opposite point (Edge Rotate) for evenly shaped triangles
#  [3] and [4] affect each other, so they alternate until nothing changes.
#  When done, the console shows the face count and thin triangle count before and after.
#
# Notes
#  - Meant for triangle meshes. On a mostly-quad mesh, step [2] turns every face into triangles. (For quad meshes use Quad_Cleanup.py)
#  - The whole mesh is processed, not just what is selected in Edit Mode.
#  - Safeguards
#      Points/edges on open borders are not touched by default (DISSOLVE_BOUNDARY)
#      [3] Keeps center points that stick out and form the shape (MAX_HEIGHT_RATIO)
#      [4] Keeps corners/creases, places with no room around them, and places where faces would flip
#      [4] Edges marked Seam / Sharp are not touched
#  - To protect places whose shape must be kept, like joints, paint them in a vertex group and put its name in PROTECT_GROUP (e.g. "Joints"); they are protected from [3].
#    If no group with that name exists, it continues without protection.
#
# Usage
#  1) Select mesh(es) in Object Mode. (Multiple OK)
#  2) Scripting tab > New text > Paste > Check the settings > Run Script
#  3) The result is shown in Window > Toggle System Console.
#  4) Save with Ctrl+S before running. You can undo with Ctrl+Z.

import bpy
import bmesh
from math import radians, degrees
from mathutils import geometry

# ---------------- Settings ----------------
# Steps to run (set to False to skip that step)
DO_VALENCE2 = True        # [1] dissolve middle vertices
DO_TRIANGULATE = True     # [2] 4+ sided faces -> triangles
DO_TRI_POLES = True       # [3] clean up 3 triangles inside a triangle
DO_FLIP_SLIVERS = True    # [4] rotate edges of thin triangles

# [1] Middle vertices
DISSOLVE_BOUNDARY = False   # Also clean points on open borders (veil hem, center line of a half mesh, etc.)
BOUNDARY_STRAIGHT = 170.0   # When the above is True, only remove points whose two edges are this straight (degrees) or more

# [2] Triangulation
QUAD_METHOD = 'BEAUTY'      # 'BEAUTY' (even shapes, recommended) / 'SHORT_EDGE' / 'LONG_EDGE' / 'FIXED'
NGON_METHOD = 'BEAUTY'      # 'BEAUTY' / 'EAR_CLIP'

# [3] 3 triangles inside a triangle
MAX_HEIGHT_RATIO = 0.15     # How far the center point sticks out of the outer triangle's plane / average side length
                            #   If it sticks out more than this, it is treated as a shape-forming point and kept
PROTECT_GROUP = ""          # Enter a vertex group name to keep the points painted in that group (e.g. "Joints")
PROTECT_WEIGHT = 0.5        # Protect points whose PROTECT_GROUP weight is this value or more

# [4] Thin triangles
SLIVER_ANGLE = 130.0        # A triangle whose largest angle is this (degrees) or more counts as "thin"
FLAT_ANGLE = 12.0           # Only fix when the faces on both sides of the edge bend this much (degrees) or less (flat areas only)
                            #   If corners get changed too, use 6~8; if flat areas aren't fixed, use 15~20
MIN_NEW_ANGLE = 15.0        # Only fix when the smallest angle of the two triangles after rotating is this (degrees) or more

MAX_PASSES = 10             # Number of passes (stops automatically when nothing changes)
# --------------------------------------


# ===================== Common =====================

def tri_angles(p0, p1, p2):
    """Angles (radians) at the three corners"""
    out = []
    for a, b, c in ((p0, p1, p2), (p1, p2, p0), (p2, p0, p1)):
        u = b - a
        w = c - a
        if u.length == 0.0 or w.length == 0.0:
            return [0.0, 0.0, 0.0]
        out.append(u.angle(w))
    return out


# ===================== [1] Middle vertices =====================

def boundary_straight(v):
    a, b = (e.other_vert(v) for e in v.link_edges)
    d1 = a.co - v.co
    d2 = b.co - v.co
    if d1.length == 0.0 or d2.length == 0.0:
        return True
    return degrees(d1.angle(d2)) >= BOUNDARY_STRAIGHT


def dissolve_valence2(bm):
    verts = []
    for v in bm.verts:
        if len(v.link_edges) != 2:
            continue
        if v.is_boundary:
            if not DISSOLVE_BOUNDARY or not boundary_straight(v):
                continue
        verts.append(v)
    if verts:
        bmesh.ops.dissolve_verts(bm, verts=verts)
    return len(verts)


# ===================== [2] Triangulation =====================

def triangulate_all(bm):
    targets = [f for f in bm.faces if len(f.verts) > 3]
    if targets:
        bmesh.ops.triangulate(bm, faces=targets,
                              quad_method=QUAD_METHOD, ngon_method=NGON_METHOD)
    return len(targets)


# ===================== [3] 3 triangles inside a triangle =====================

def outer_verts(v):
    return [e.other_vert(v) for e in v.link_edges]


def is_tri_pole(v, deform_layer, group_index):
    if v.is_boundary or not v.is_manifold:
        return False
    if len(v.link_edges) != 3 or len(v.link_faces) != 3:
        return False
    if any(len(f.verts) != 3 for f in v.link_faces):
        return False

    a, b, c = outer_verts(v)
    if set(a.link_faces) & set(b.link_faces) & set(c.link_faces):
        return False

    if deform_layer is not None and group_index is not None:
        if v[deform_layer].get(group_index, 0.0) >= PROTECT_WEIGHT:
            return False

    size = ((a.co - b.co).length + (b.co - c.co).length + (c.co - a.co).length) / 3.0
    if size == 0.0:
        return False
    normal = geometry.normal((a.co, b.co, c.co))
    if normal.length == 0.0:
        return False
    height = abs((v.co - a.co).dot(normal))
    return height / size <= MAX_HEIGHT_RATIO


def dissolve_tri_poles(bm, deform_layer, group_index):
    picked = []
    blocked = set()
    for v in bm.verts:
        if v in blocked:
            continue
        if not is_tri_pole(v, deform_layer, group_index):
            continue
        picked.append(v)
        blocked.add(v)
        for n in outer_verts(v):
            blocked.add(n)
    if picked:
        bmesh.ops.dissolve_verts(bm, verts=picked)
    return len(picked)


# ===================== [4] Thin triangles =====================

def opposite_vert(face, edge):
    for v in face.verts:
        if v is not edge.verts[0] and v is not edge.verts[1]:
            return v
    return None


def check_flip(e, sliver_thr, flat_thr, min_new):
    if not e.is_manifold or e.is_boundary or e.seam or not e.smooth:
        return None
    if len(e.link_faces) != 2:
        return None
    f1, f2 = e.link_faces
    if len(f1.verts) != 3 or len(f2.verts) != 3:
        return None

    a, b = e.verts
    # Rotating removes one connection each from a and b -> if 3 or fewer, a broken face would result, so skip
    if len(a.link_edges) <= 3 or len(b.link_edges) <= 3:
        return None

    c = opposite_vert(f1, e)
    d = opposite_vert(f2, e)
    if c is None or d is None or c is d:
        return None

    if e.calc_face_angle(10.0) > flat_thr:
        return None

    ang_c = (a.co - c.co).angle(b.co - c.co, 0.0)
    ang_d = (a.co - d.co).angle(b.co - d.co, 0.0)
    if max(ang_c, ang_d) < sliver_thr:
        return None

    for le in c.link_edges:
        if le.other_vert(c) is d:
            return None

    old_min = min(min(tri_angles(a.co, b.co, c.co)), min(tri_angles(a.co, b.co, d.co)))
    new_min = min(min(tri_angles(c.co, d.co, a.co)), min(tri_angles(d.co, c.co, b.co)))
    if new_min < min_new or new_min <= old_min:
        return None

    n_old = f1.normal + f2.normal
    if n_old.length == 0.0:
        return None
    n1 = (d.co - c.co).cross(a.co - c.co)
    n2 = (c.co - d.co).cross(b.co - d.co)
    if n1.length == 0.0 or n2.length == 0.0:
        return None
    if n1.dot(n_old) * n2.dot(n_old) <= 0.0:
        return None

    return new_min - old_min


def flip_slivers(bm, sliver_thr, flat_thr, min_new):
    bm.normal_update()
    cands = []
    for e in bm.edges:
        score = check_flip(e, sliver_thr, flat_thr, min_new)
        if score is not None:
            cands.append((score, e))
    cands.sort(key=lambda t: -t[0])

    touched = set()
    count = 0
    for _, e in cands:
        if not e.is_valid:
            continue
        if any(f in touched for f in e.link_faces):
            continue
        new_e = bmesh.utils.edge_rotate(e, False)
        if new_e is None:
            continue
        for f in new_e.link_faces:
            touched.add(f)
        count += 1
    return count


# ===================== Run =====================

def count_slivers(bm, sliver_thr):
    n = 0
    for f in bm.faces:
        if len(f.verts) == 3 and max(tri_angles(*(v.co for v in f.verts))) >= sliver_thr:
            n += 1
    return n


def cleanup(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    deform_layer = None
    group_index = None
    if PROTECT_GROUP:
        vg = obj.vertex_groups.get(PROTECT_GROUP)
        if vg is None:
            print(f"[{obj.name}] No '{PROTECT_GROUP}' vertex group, continuing without protection.")
        else:
            group_index = vg.index
            deform_layer = bm.verts.layers.deform.verify()

    sliver_thr = radians(SLIVER_ANGLE)
    flat_thr = radians(FLAT_ANGLE)
    min_new = radians(MIN_NEW_ANGLE)

    faces_before = len(bm.faces)
    slivers_before = count_slivers(bm, sliver_thr)
    stat = {"val2": 0, "tri": 0, "pole": 0, "flip": 0}

    # [1] → [2]
    if DO_VALENCE2:
        for _ in range(MAX_PASSES):
            c = dissolve_valence2(bm)
            stat["val2"] += c
            if c == 0:
                break
    if DO_TRIANGULATE:
        stat["tri"] += triangulate_all(bm)

    # Alternate [3] <-> [4]
    for _ in range(MAX_PASSES):
        changed = 0
        if DO_TRI_POLES:
            c = dissolve_tri_poles(bm, deform_layer, group_index)
            stat["pole"] += c
            changed += c
        if DO_FLIP_SLIVERS:
            c = flip_slivers(bm, sliver_thr, flat_thr, min_new)
            stat["flip"] += c
            changed += c
        if DO_VALENCE2:
            c = dissolve_valence2(bm)
            stat["val2"] += c
            changed += c
        if DO_TRIANGULATE:
            stat["tri"] += triangulate_all(bm)
        if changed == 0:
            break

    faces_after = len(bm.faces)
    slivers_after = count_slivers(bm, sliver_thr)
    non_tri = sum(1 for f in bm.faces if len(f.verts) != 3)

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.update()
    print(f"[{obj.name}] Faces {faces_before} -> {faces_after} | "
          f"dissolved {stat['val2']} middle vertices, split {stat['tri']} 4+ sided faces, "
          f"cleaned {stat['pole']} triangles-in-triangle, rotated {stat['flip']} thin triangle edges | "
          f"thin triangles {slivers_before} -> {slivers_after}, non-triangle faces {non_tri}")


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
