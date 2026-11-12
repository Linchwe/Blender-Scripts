# Quad_Cleanup.py
# Blender 4.2 ~ 4.5
#
# Purpose
#  Cleans up the messy parts of auto-retopology results (Instant Meshes etc.) in one run.
#
# What it does
#  [2] Pointless vertices in the middle of an edge (points with only 2 edges) -> dissolve
#  [3] Pointless edges that only connect the "middles" of two parallel edges -> remove
#  [1] Places where an edge flow ends by hitting the middle of another edge at a right angle (T-junction)
#      -> connect that point to the vertex on the opposite side to remove the N-gon
#      T_SPLIT_MODE = 'BOTH' makes 2 cuts to both opposite vertices, 'QUAD_TRI' makes 1 cut (a pentagon becomes 1 quad + 1 triangle)
#  The steps above repeat until nothing changes (up to MAX_PASSES times).
#
# Notes
#  - The whole mesh is processed, not just what is selected in Edit Mode.
#  - Points on open borders (e.g. the center line of a half mesh) are not touched by default. To clean them, set DISSOLVE_BOUNDARY = True.
#  - A T-junction is only detected when two edges are nearly straight (STRAIGHT_ANGLE degrees or more). If too few are caught on curved surfaces, lower it a little.
#  - Cuts are only made between vertices on the same face. Already connected vertices are skipped.
#
# Usage
#  1) Select mesh(es) in Object Mode. (Multiple OK)
#  2) Scripting tab > New text > Paste > Check the settings > Run Script
#  3) The result is shown in Window > Toggle System Console.
#  4) Save with Ctrl+S before running. You can undo with Ctrl+Z.

import bpy
import bmesh
from math import radians, degrees

# ---------------- Settings ----------------
STRAIGHT_ANGLE = 150.0     # Two edges at this angle (degrees) or more count as "straight" (T-junction test)
T_SPLIT_MODE = 'BOTH'      # How [1] is handled
                           #   'BOTH'     : 2 cuts, to both opposite vertices
                           #   'QUAD_TRI' : 1 cut only (a pentagon becomes 1 quad + 1 triangle)
DISSOLVE_BOUNDARY = False  # Also clean points on open borders (e.g. the center line of a half mesh)
MAX_PASSES = 10            # Number of cleanup passes (stops automatically when nothing changes)
# --------------------------------------


def tangent_dir(v, other):
    """Project the direction vector from v to other onto v's normal plane"""
    d = other.co - v.co
    n = v.normal
    d = d - n * d.dot(n)
    if d.length < 1e-9:
        return None
    return d.normalized()


def t_info(v):
    """If v is a T-junction, return (2 bar edges, stem edge, N-gon face on the bar side), otherwise None"""
    if not v.is_valid or v.is_boundary or len(v.link_edges) != 3:
        return None
    dirs = []
    for e in v.link_edges:
        d = tangent_dir(v, e.other_vert(v))
        if d is None:
            return None
        dirs.append((e, d))

    best = None
    for i in range(3):
        for j in range(i + 1, 3):
            ang = degrees(dirs[i][1].angle(dirs[j][1]))
            if best is None or ang > best[0]:
                best = (ang, i, j)
    if best[0] < STRAIGHT_ANGLE:
        return None

    _, i, j = best
    bar = (dirs[i][0], dirs[j][0])
    stem = dirs[3 - i - j][0]

    ngon = None
    for f in v.link_faces:
        fe = set(f.edges)
        if bar[0] in fe and bar[1] in fe:
            ngon = f
            break
    if ngon is None or len(ngon.verts) < 5:
        return None
    return bar, stem, ngon


def dissolve_valence2(bm):
    """[2] Dissolve points with only 2 edges"""
    verts = []
    for v in bm.verts:
        if len(v.link_edges) != 2:
            continue
        if v.is_boundary and not DISSOLVE_BOUNDARY:
            continue
        verts.append(v)
    if verts:
        bmesh.ops.dissolve_verts(bm, verts=verts)
    return len(verts)


def remove_mid_to_mid_edges(bm):
    """[3] Remove edges whose both ends sit in the middle (T) of other edges"""
    bm.normal_update()
    edges = []
    for e in bm.edges:
        a, b = e.verts
        ia = t_info(a)
        if ia is None or ia[1] is not e:
            continue
        ib = t_info(b)
        if ib is None or ib[1] is not e:
            continue
        edges.append(e)
    if edges:
        bmesh.ops.dissolve_edges(bm, edges=edges, use_verts=True, use_face_split=False)
    return len(edges)


def split_t_junctions(bm):
    """[1] Split N-gons by connecting T-junctions to the opposite vertices"""
    bm.normal_update()
    count = 0
    candidates = [v for v in bm.verts]
    for v in candidates:
        info = t_info(v)   # Re-check every time, since the previous split may have changed the shape
        if info is None:
            continue
        _, _, face = info

        # Vertex order of the face starting from v
        start = None
        for l in face.loops:
            if l.vert is v:
                start = l
                break
        if start is None:
            continue
        seq = []
        l = start
        for _ in range(len(face.loops)):
            seq.append(l.vert)
            l = l.link_loop_next
        n = len(seq)

        if n % 2 == 0:
            targets = [seq[n // 2]]                       # hexagon -> 2 quads
        elif T_SPLIT_MODE == 'BOTH':
            targets = [seq[(n - 1) // 2], seq[(n + 1) // 2]]
        else:
            targets = [seq[(n - 1) // 2]]

        made = False
        for t in targets:
            if not t.is_valid or t is v:
                continue
            # Skip if already connected
            if any(e.other_vert(v) is t for e in v.link_edges):
                continue
            # Only connect when on the same face
            shared = set(v.link_faces) & set(t.link_faces)
            if not shared:
                continue
            res = bmesh.ops.connect_verts(bm, verts=[v, t])
            if res["edges"]:
                made = True
        if made:
            count += 1
            bm.normal_update()
    return count


def cleanup(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    total = {"vert": 0, "edge": 0, "tsplit": 0}
    for _ in range(MAX_PASSES):
        c2a = dissolve_valence2(bm)
        c3 = remove_mid_to_mid_edges(bm)
        c2b = dissolve_valence2(bm)
        c1 = split_t_junctions(bm)
        total["vert"] += c2a + c2b
        total["edge"] += c3
        total["tsplit"] += c1
        if c2a + c3 + c2b + c1 == 0:
            break

    bm.to_mesh(me)
    bm.free()
    me.update()
    print(f"[{obj.name}] Dissolved {total['vert']} middle vertices, "
          f"removed {total['edge']} pointless edges, split {total['tsplit']} T-junctions")


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
