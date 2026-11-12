import bpy
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

# Cleans up the bones (skeleton) of a SkinTokens auto-rig + matches them to the Mixamo rig layout
# Weights are cleaned up by SkinTokens_Fix_Weights.py. Run this script first.
#
# Human rigs (rigged with relabel on in the SkinTokens node, so bones have mixamorig: names)
#  1) Delete meshes without weights (Icosphere etc.)
#  2) Make bone positions left/right symmetric, and place the center bones (Hips~Head) at the mesh's left/right center (usually X = 0) (SYMMETRIZE)
#  2-1) Fit the torso, arm and leg joints to the mesh shape (FIT_BODY_JOINTS)
#     Slices the mesh and places each joint in the middle of the body's thickness. Heights are set as ratios of the crotch~shoulder length
#     (ratios measured from professional auto-rigging AccuRIG results); knees at 52% of hip~ankle, ankles where the shin starts to widen,
#     shoulders found along the center line of the upper arm. Joints follow each mesh's own proportions regardless of height or build.
#     The largest mesh is treated as the body. If the crotch can't be found (long skirt etc.), the torso and legs are skipped and only the arms are fitted.
#     Joints that would have to move too far (more than 12% of the height) are treated as wrong finds and left as they are
#  3) Rename fingers by their actual position (closest to the wrist = thumb, the rest index/middle/ring/pinky from the front)
#     Then move finger joints to the middle of the finger thickness and fit the last segment to the actual fingertip (FIX_FINGERS)
#     Find where the fingers split and the fingertips from mesh slices, and fit the joints to the real hand joint positions (FIT_FINGER_JOINTS)
#     For index~pinky, the knuckle goes inside the palm and the 2nd/3rd joints at the thirds between the split point and the tip;
#     for the thumb, the root goes to the middle of the thumb pad near the wrist and the 2nd joint midway between the root and the 3rd joint (middle of the thumb's thickness)
#  4) (Optional) Straighten the arms into a T-pose and bake the mesh into that pose (T_POSE)
#  5) Set bone tail positions and orientation (roll) using the same rules as Mixamo
#  6) Add the end bones Mixamo has (HeadTop_End, 4th finger joints, Toe_End)
#  7) Connect bones whose ends touch (Connected)
#  8) Change to the same unit/axis structure as a Mixamo FBX (the visible size and look stay the same)
#  For a file exported to FBX and imported again, deletes the "_end" leaf bones Blender added and turns off Deform on the end bones
#
# Animal and other non-human rigs (rigged with relabel off, so bones are named bone_0, bone_1 ...)
#  - 1) Deletes meshes without weights.
#  - Keeps the bone positions (joints) from SkinTokens and only fixes the orientation of bones standing straight up (ORIENT_BONES)
#      With one child, the tail points to that child's head; when it branches, to the child that best continues the incoming direction
#      (like spine -> neck); if there is no such child, toward the child with the most bones down the chain.
#      End bones with no children, like tail tips and toes, point toward the center of the flesh they move (vertices with large weights).
#      Bones whose tail touches a child's head are connected, and roll is set relative to up (+Z). (Bones standing vertical use forward)
#    Only the rest-pose bone orientation changes, so the mesh shape and weights stay the same. Then move on to SkinTokens_Fix_Weights.py.
#    Don't use it on rigs that already have animation (actions). Changing bone orientation breaks existing animation.
#
# Running it several times is fine. After fixing bones by hand, run again with SYMMETRIZE = False: your hand-fixed positions are kept
# and only fingers, roll and connections are refitted. If you fixed finger bones by hand, set FIX_FINGERS to False too.
# This script doesn't change weights.
# Human rigs are assumed to face the direction you see the face from in Blender's Front view (-Y), with up as +Z.

SYMMETRIZE        = True     # False for asymmetric characters
RENAME_FINGERS    = True
FIT_BODY_JOINTS   = True     # Fit torso, arm and leg joints to the mesh shape (human rigs)
FIX_FINGERS       = True     # Move finger joints to the middle of the finger thickness and fit the last segment to the actual fingertip
FIT_FINGER_JOINTS = True     # Find finger joint positions from the mesh shape (when FIX_FINGERS is True)
T_POSE            = False    # True: change to a T-pose with arms straight out (Mixamo uses the pose of the uploaded mesh as is)
ADD_END_BONES     = True
REMOVE_UNSKINNED  = True
ORIENT_BONES      = True     # (Animal and other non-human rigs) lay bones standing straight up toward the next joint and set roll
MIXAMO_UNITS      = True     # Same structure as a Mixamo FBX: armature rotated X 90 degrees + scale 0.01, skeleton data in cm / Y up

FORWARD = Vector((0, -1, 0))
UP      = Vector((0, 0, 1))
RIGHT   = Vector((1, 0, 0))      # the character's left (screen right)
FORWARD_W, UP_W, RIGHT_W = FORWARD, UP, RIGHT
FINGER_WORDS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
FINGER_ORDER = ("Index", "Middle", "Ring", "Pinky")
CENTER_BONES = ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "HeadTop_End")

arm = bpy.context.active_object
if arm is None or arm.type != 'ARMATURE':
    arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    if len(arms) != 1:
        raise Exception("Select an armature object and run again.")
    arm = arms[0]
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm


def skinned_meshes():
    return [o for o in bpy.context.scene.objects if o.type == 'MESH' and
            any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)]


# 1) Delete meshes without weights
def remove_unskinned():
    keep = set(skinned_meshes())
    for o in [o for o in bpy.context.scene.objects if o.type == 'MESH' and o not in keep]:
        print(f"[Cleanup] Deleted mesh without weights: {o.name}")
        bpy.data.objects.remove(o, do_unlink=True)


# Decide if it is a human rig: if there is a Mixamo name (...Hips), it is a human rig
hips = next((b for b in arm.data.bones if b.name.endswith("Hips")), None)


def to_mixamo():
    # Directions in armature local space
    w2l   = arm.matrix_world.to_3x3().inverted()
    fwd   = (w2l @ FORWARD).normalized()
    up    = (w2l @ UP).normalized()
    right = (w2l @ RIGHT).normalized()

    U = 1.0 / arm.matrix_world.to_scale().x     # length of 1m in armature data (100 for a cm structure)


    P = hips.name[:-len("Hips")]          # usually "mixamorig:"


    def N(n):
        return P + n


    # 2) Make bone positions symmetric
    def mirror_name(n):
        for a, c in (("Left", "Right"), ("left", "right"), (".L", ".R"), ("_L", "_R"), (".l", ".r"), ("_l", "_r")):
            if a in n:
                return n.replace(a, c)
            if c in n:
                return n.replace(c, a)
        return None


    def mesh_center_x():
        # World X of the body center (symmetry plane): midpoint between the mesh's leftmost and rightmost points
        lo, hi = None, None
        for o in skinned_meshes():
            n = len(o.data.vertices)
            if n == 0:
                continue
            co = np.empty(n * 3)
            o.data.vertices.foreach_get("co", co)
            M = np.array(o.matrix_world)
            x = co.reshape(-1, 3) @ M[:3, :3].T[:, 0] + M[0, 3]
            lo = x.min() if lo is None else min(lo, x.min())
            hi = x.max() if hi is None else max(hi, x.max())
        return None if lo is None else float(lo + hi) / 2

    if SYMMETRIZE:
        cx = mesh_center_x()
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = arm.data.edit_bones
        for b in ebs:
            b.use_connect = False
        if cx is None:
            center = ebs[hips.name].head.dot(right)
        else:                                               # center bones go on the mesh's symmetry plane (usually X = 0)
            hp = arm.matrix_world @ ebs[hips.name].head
            center = (arm.matrix_world.inverted() @ Vector((cx, hp.y, hp.z))).dot(right)

        def mirror(p):
            return p - right * (2 * (p.dot(right) - center))

        done = set()
        for b in ebs:                                       # left/right pairs go to their average position, center bones to the exact center
            if b.name in done:
                continue
            mn = mirror_name(b.name)
            o = ebs.get(mn) if mn else None
            if o is not None and o is not b:
                avg = (b.head + mirror(o.head)) / 2
                b.head, o.head = avg, mirror(avg)
                done.update({b.name, o.name})
            elif mn is None and b.name[len(P):] in CENTER_BONES:   # only body center bones go to the exact center (hair, tail and other bones stay)
                b.head = b.head - right * (b.head.dot(right) - center)
                done.add(b.name)
        bpy.ops.object.mode_set(mode='OBJECT')
        print("[Symmetry] Made bone positions symmetric and placed the body center bones at " +
              ("the Hips position" if cx is None else f"X = {cx * 100:.2f}cm (mesh left/right center)") + "")

    # 3) Rename fingers
    def replace_finger_word(name, new_word):
        for w in FINGER_WORDS:
            i = name.rfind(w)
            if i != -1:
                return name[:i] + new_word + name[i + len(w):]
        return None


    if RENAME_FINGERS:
        bones = arm.data.bones
        plan = []
        for side in ("Left", "Right"):
            hand = bones.get(N(side + "Hand"))
            if hand is None or len(hand.children) < 4:
                continue
            roots = list(hand.children)
            thumb = min(roots, key=lambda r: (r.head_local - hand.head_local).length)
            others = sorted([r for r in roots if r is not thumb], key=lambda r: r.head_local.dot(fwd), reverse=True)
            print(f"[Fingers] {hand.name}")
            for root, word in [(thumb, "Thumb")] + list(zip(others, FINGER_ORDER)):
                print(f"   {root.name:32s} -> {word}")
                for b in [root] + list(root.children_recursive):
                    new = replace_finger_word(b.name, word)
                    if new and new != b.name:
                        plan.append((b.name, new))
        for old, new in plan:                     # rename in two passes to avoid name clashes (vertex groups are renamed too)
            bones[old].name = "__tmp__" + new
        for old, new in plan:
            bones["__tmp__" + new].name = new
        print(f"[Fingers] Renamed {len(plan)} bones")

    # For computing mesh slices around the hand (vertices, edges, edge-face links, tree for ray checks)
    def hand_geometry(center, radius, objs=None):
        Vs, Es, EFe, EFf, polys = [], [], [], [], []
        voff, eoff, foff = 0, 0, 0
        c = np.array(center)
        for o in (objs or skinned_meshes()):
            me = o.data
            nv, ne, nf, nl = len(me.vertices), len(me.edges), len(me.polygons), len(me.loops)
            if nv == 0 or nf == 0:
                continue
            co = np.empty(nv * 3)
            me.vertices.foreach_get("co", co)
            M = np.array(o.matrix_world)
            co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
            ev = np.empty(ne * 2, dtype=np.int64)
            me.edges.foreach_get("vertices", ev)
            ev = ev.reshape(-1, 2)
            le = np.empty(nl, dtype=np.int64)
            me.loops.foreach_get("edge_index", le)
            lv = np.empty(nl, dtype=np.int64)
            me.loops.foreach_get("vertex_index", lv)
            lt = np.empty(nf, dtype=np.int64)
            me.polygons.foreach_get("loop_total", lt)
            ls = np.empty(nf, dtype=np.int64)
            me.polygons.foreach_get("loop_start", ls)
            near = np.linalg.norm(co - c, axis=1) < radius
            ke = near[ev[:, 0]] & near[ev[:, 1]]
            emap = np.full(ne, -1, dtype=np.int64)
            emap[ke] = np.arange(ke.sum()) + eoff
            lf = np.repeat(np.arange(nf), lt)
            m = emap[le] >= 0
            EFe.append(emap[le][m])
            EFf.append(lf[m] + foff)
            Es.append(ev[ke] + voff)
            Vs.append(co)
            fv = [lv[ls[i]:ls[i] + lt[i]] for i in range(nf)]
            polys += [list(x + voff) for x in fv if near[x].all()]
            voff += nv
            eoff += int(ke.sum())
            foff += nf
        if not Vs or eoff == 0 or not polys:
            return None
        V = np.concatenate(Vs)
        E = np.concatenate(Es)
        Fe, Ff = np.concatenate(EFe), np.concatenate(EFf)
        o_ = np.argsort(Ff, kind="stable")
        bvh = BVHTree.FromPolygons([Vector(p) for p in V], polys)
        return V, E, Fe[o_], Ff[o_], bvh

    def slice_loops(G, c, n, R):
        # Section loops of the mesh cut by the plane through point c perpendicular to n (crossing points sharing a face form one loop)
        V, E, Fe, Ff, bvh = G
        c, n = np.array(c), np.array(n)
        d = (V - c) @ n
        s0, s1 = d[E[:, 0]], d[E[:, 1]]
        cr = np.nonzero(s0 * s1 < 0.0)[0]
        if len(cr) == 0:
            return []
        t = s0[cr] / (s0[cr] - s1[cr])
        P = V[E[cr, 0]] + (V[E[cr, 1]] - V[E[cr, 0]]) * t[:, None]
        k = np.linalg.norm(P - c, axis=1) < R
        cr, P = cr[k], P[k]
        if len(cr) == 0:
            return []
        pos = np.full(len(E), -1, dtype=np.int64)
        pos[cr] = np.arange(len(cr))
        m = pos[Fe] >= 0
        ids, fs = pos[Fe][m], Ff[m]
        par = list(range(len(cr)))

        def root(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        for i in range(1, len(fs)):
            if fs[i] == fs[i - 1]:
                a, b = root(int(ids[i])), root(int(ids[i - 1]))
                if a != b:
                    par[a] = b
        groups = {}
        for i in range(len(cr)):
            groups.setdefault(root(i), []).append(i)
        return [P[g] for g in groups.values() if len(g) >= 3]

    def ray_len(G, p, d):
        # Distance from p in direction d to the mesh surface (only when p is inside the mesh)
        hit = G[4].ray_cast(Vector(p), Vector(d).normalized())
        if hit[0] is None or hit[1].dot(d) <= 0.0:
            return None
        return hit[3]

    # 2-1) Fit torso, arm and leg joints to the mesh shape
    #   Torso joint heights are ratios of crotch~shoulder and shoulder~top of head; front-to-back they sit in the middle of the torso slice.
    #   Limb joints go to the middle of the limb slice; the ankle is where the shin widens into the foot; the toe root is a ratio of the foot length.
    #   Ratios are values measured from professional auto-rigging (AccuRIG) results on human body types
    BODY_RATIO = {"Hips": 0.245, "Spine": 0.415, "Spine1": 0.498, "Spine2": 0.709,   # crotch~shoulder height
                  "UpLeg": 0.186,
                  "Neck": 0.213, "Head": 0.485}                                      # shoulder~top of head height

    def largest_loop_containing(G, c, n, R):
        n = Vector(n).normalized()
        u = n.cross(RIGHT_W) if abs(n.dot(RIGHT_W)) < 0.9 else n.cross(FORWARD_W)
        u.normalize()
        v = n.cross(u)
        best = None
        for P in slice_loops(G, c, n, R):
            q = P - np.array(c)
            pu, pv = q @ np.array(u), q @ np.array(v)
            if pu.min() <= 0.0 <= pu.max() and pv.min() <= 0.0 <= pv.max():
                area = float(np.ptp(pu) * np.ptp(pv))
                if best is None or area > best[0]:
                    best = (area, P, pu, pv, u, v)
        return best

    def center_in(G, c, n, R):
        L = largest_loop_containing(G, c, n, R)
        if L is None:
            return c.copy()
        _, P, pu, pv, u, v = L
        return c + u * float((pu.max() + pu.min()) / 2) + v * float((pv.max() + pv.min()) / 2)

    def midline_center(G, c, R):
        # Front-to-back middle of the combined range of horizontal slices through the body center (left/right center)
        L = [P for P in slice_loops(G, c, UP_W, R) if P[:, 0].min() <= c.x <= P[:, 0].max()]
        if not L:
            return None
        P = np.concatenate(L)
        return Vector((c.x, float(P[:, 1].min() + P[:, 1].max()) / 2, c.z))

    def fit_body():
        body = max(skinned_meshes(), key=lambda o: len(o.data.vertices), default=None)
        if body is None:
            return
        mw = arm.matrix_world
        inv = mw.inverted()
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = arm.data.edit_bones
        Wp = {}
        for b in ebs:
            if b.name.startswith(P):
                Wp[b.name[len(P):]] = mw @ b.head
        need = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"] + \
               [s + k for s in ("Left", "Right") for k in ("Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase")]
        if any(k not in Wp for k in need):
            bpy.ops.object.mode_set(mode='OBJECT')
            print("[Body joints] Not all Mixamo bones are present, skipping")
            return
        hips = Wp["Hips"]
        height = max((Wp["Head"] - hips).length * 3.0, 0.01)
        G = hand_geometry(hips, height, [body])
        if G is None:
            bpy.ops.object.mode_set(mode='OBJECT')
            return
        V = G[0]
        top = float(V[:, 2].max())
        cx = hips.x
        new = {}
        # Arms: the shoulder on the center line of the upper arm flesh, the elbow and wrist at the middle of their slices
        for s in ("Left", "Right"):
            Ar, El, Ha = Wp[s + "Arm"], Wp[s + "ForeArm"], Wp[s + "Hand"]
            ds = (El - Ar).normalized()
            cs = []
            for t in (0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6):
                c = Ar + (El - Ar) * t
                if largest_loop_containing(G, c, ds, 0.5 * (El - Ar).length) is not None:
                    cs.append(np.array(center_in(G, c, ds, 0.5 * (El - Ar).length)))
            if len(cs) >= 4:
                C = np.array(cs)
                O = C.mean(0)
                ax = Vector(np.linalg.svd(C - O)[2][0])
                ax = ax if ax.dot(ds) > 0 else -ax
                O = Vector(O)
                new[s + "Arm"] = O + ax * (Ar - O).dot(ax)
            a2 = new.get(s + "Arm", Ar)
            d1, d2 = (El - a2).normalized(), (Ha - El).normalized()
            new[s + "ForeArm"] = center_in(G, El, d1 + d2, 0.4 * (Ha - El).length)
            new[s + "Hand"] = center_in(G, Ha, d2, 0.3 * (Ha - El).length)
        sh = (new.get("LeftArm", Wp["LeftArm"]).z + new.get("RightArm", Wp["RightArm"]).z) / 2
        # Crotch: going down the body center line, the height where the torso slice breaks apart
        crotch, z = None, hips.z
        step = 0.005 * height
        while z > hips.z - 0.4 * height:
            if largest_loop_containing(G, Vector((cx, hips.y, z)), UP_W, 0.5 * height) is None:
                crotch = z
                break
            z -= step
        if crotch is None or sh - crotch < 0.1 * height:
            print("[Body joints] Could not find the crotch height, leaving the torso and legs as they are (skirt etc.)")
        else:
            span = sh - crotch
            for k in ("Hips", "Spine", "Spine1", "Spine2"):
                m = midline_center(G, Vector((cx, hips.y, crotch + BODY_RATIO[k] * span)), 0.5 * height)
                if m is not None:
                    new[k] = m
            for k in ("Neck", "Head"):
                m = midline_center(G, Vector((cx, Wp[k].y, sh + BODY_RATIO[k] * (top - sh))), 0.3 * height)
                if m is not None:
                    new[k] = m
            # Legs
            zh = crotch + BODY_RATIO["UpLeg"] * span
            L = largest_loop_containing(G, Vector((cx, hips.y, zh)), UP_W, 0.5 * height)
            for s, sg in (("Left", 1.0), ("Right", -1.0)):
                if L is not None:
                    Pp = L[1]
                    hw = float(Pp[:, 0].max() - Pp[:, 0].min()) / 2
                    pc = (Pp.max(0) + Pp.min(0)) / 2
                    hip = Vector((cx + sg * 0.47 * hw, float(pc[1]), zh))
                else:
                    hip = Wp[s + "UpLeg"]
                new[s + "UpLeg"] = hip
                # Ankle: below the thinnest point of the shin, at 63% of how much the slice widens toward the foot
                K, An = Wp[s + "Leg"], Wp[s + "Foot"]
                d = (An - K).normalized()
                Ls = (An - K).length
                prof = []
                for i in range(int(0.4 / 0.0125), int(1.4 / 0.0125) + 1):
                    t = i * 0.0125
                    c = K + d * (Ls * t)
                    Lp_ = largest_loop_containing(G, c, d, 0.5 * Ls)
                    prof.append((t, None if Lp_ is None else float(np.ptp(Lp_[1] @ np.array(FORWARD_W)))))
                ok = [p for p in prof if p[1] is not None and p[0] <= 1.0]
                ank = None
                if ok:
                    nar = min(ok, key=lambda p: p[1])
                    after = []
                    for p in prof:
                        if p[0] <= nar[0]:
                            continue
                        if p[1] is None or (after and p[1] < 0.6 * after[-1][1]):
                            break
                        after.append(p)
                    if after:
                        dmax = max(a[1] for a in after)
                        if dmax > 1.15 * nar[1]:
                            thr = nar[1] + 0.63 * (dmax - nar[1])
                            ta = next(a[0] for a in after if a[1] >= thr)
                            ank = center_in(G, K + d * (Ls * ta), d, 0.5 * Ls)
                if ank is None:
                    ank = center_in(G, An, d, 0.5 * Ls)
                new[s + "Foot"] = ank
                # Knee: 52% of hip~ankle, middle of the leg slice
                kn = hip + (ank - hip) * 0.52
                n1, n2 = (kn - hip).normalized(), (ank - kn).normalized()
                new[s + "Leg"] = center_in(G, kn, n1 + n2, 0.5 * Ls)
                # Toe root: 60% of heel~toe length, at 25% height from the bottom of the foot slice
                fm = (np.abs(V[:, 0] - ank.x) < 0.25 * Ls) & (V[:, 2] < ank.z) & (np.abs(V[:, 1] - ank.y) < 0.8 * Ls)
                if fm.sum() > 20:
                    fy = V[fm, 1]
                    fwd_sign = -1.0 if FORWARD_W.y < 0 else 1.0
                    heel = float(fy.max()) if fwd_sign < 0 else float(fy.min())
                    toe = float(fy.min()) if fwd_sign < 0 else float(fy.max())
                    ty = heel + 0.6 * (toe - heel)
                    Lt = largest_loop_containing(G, Vector((ank.x, ty, float(V[fm, 2].min()) + 0.02 * Ls)), Vector((0, 1, 0)), 0.5 * Ls)
                    if Lt is not None:
                        q = Lt[1]
                        new[s + "ToeBase"] = Vector((float(q[:, 0].max() + q[:, 0].min()) / 2, ty,
                                                     float(q[:, 2].min() + 0.25 * (q[:, 2].max() - q[:, 2].min()))))
        # Clavicle: slightly above the shoulder joint height, 43% of the way from the body center to the shoulder
        for s in ("Left", "Right"):
            a = new.get(s + "Arm", Wp[s + "Arm"])
            new[s + "Shoulder"] = Vector((cx + 0.43 * (a.x - cx), a.y, a.z + 0.015 * (top - (crotch or hips.z))))
        if SYMMETRIZE:                                # symmetric: average of the left and right results
            for k in list(new):
                if k.startswith("Left") and "Right" + k[4:] in new:
                    a, b = new[k], new["Right" + k[4:]]
                    m = (a + Vector((2 * cx - b.x, b.y, b.z))) / 2
                    new[k], new["Right" + k[4:]] = m, Vector((2 * cx - m.x, m.y, m.z))
        # If it moves too far (mesh isn't human-shaped or the slice was found wrong), keep the original position
        moved = 0
        for k, p in new.items():
            if (p - Wp[k]).length > 0.12 * height:
                print(f"[Body joints] {k}: found position is too far from the original, leaving it")
                continue
            ebs[P + k].head = inv @ p
            moved += 1
        bpy.ops.object.mode_set(mode='OBJECT')
        print(f"[Body joints] Fitted {moved} joints to the mesh shape (crotch height {'-' if crotch is None else f'{(crotch - V[:, 2].min()) / (top - V[:, 2].min()) * 100:.0f}%'})")

    # 3-1) Move finger joints to the middle of the finger thickness
    tips = {}                                       # last finger segment name -> fingertip position (armature local)

    def fix_fingers():
        meshes = skinned_meshes()
        if not meshes:
            return
        mw = arm.matrix_world
        inv = mw.inverted()
        recs = []                                   # [mesh, index, world position, {bone: weight}]
        for o in meshes:
            gname = {g.index: g.name for g in o.vertex_groups}
            for v in o.data.vertices:
                w = {gname[g.group]: g.weight for g in v.groups if g.group in gname and g.weight > 0.0}
                if w:
                    recs.append([o, v.index, o.matrix_world @ v.co, w])
        bones = arm.data.bones
        moved = 0
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = arm.data.edit_bones
        for side in ("Left", "Right"):
            hand = ebs.get(N(side + "Hand"))
            if hand is None:
                continue
            chains = {}
            for f in FINGER_WORDS:
                ch = [ebs.get(N(f"{side}Hand{f}{i}")) for i in (1, 2, 3)]
                if all(ch):
                    chains[f] = ch
            if len(chains) < 2:
                continue
            HW = {b.name: mw @ b.head for ch in chains.values() for b in ch}
            hw = mw @ hand.head
            mids = [HW[ch[0].name] for ch in chains.values()]
            fwd_h = (sum(mids, Vector((0, 0, 0))) / len(mids) - hw).normalized()
            fs = list(chains)
            lat = HW[chains[fs[1]][0].name] - HW[chains[fs[-1]][0].name]
            lat = (lat - fwd_h * lat.dot(fwd_h)).normalized()
            palm_n = fwd_h.cross(lat).normalized()       # palm/back-of-hand direction
            fitted = set()                               # fingers whose joints were fitted from mesh slices
            reach = 0.0

            def finger_verts(f):
                names = {b.name for b in chains[f]}
                out = []
                for r in recs:
                    w = r[3]
                    k = max(w, key=w.get)
                    if k in names:
                        out.append(r[2])
                return out

            def center_pass():
                n_moved = 0
                for f, ch in chains.items():
                    P = finger_verts(f)
                    if len(P) < 8:
                        continue
                    pts = [HW[b.name] for b in ch]
                    corr = [None, None, None]
                    for i in range(3):
                        if i == 0:
                            ax = (pts[1] - pts[0])
                        elif i == 1:
                            ax = (pts[1] - pts[0]).normalized() + (pts[2] - pts[1]).normalized()
                        else:
                            ax = (pts[2] - pts[1])
                        if ax.length < 1e-6:
                            continue
                        ax.normalize()
                        u = (palm_n - ax * palm_n.dot(ax)).normalized()
                        v = ax.cross(u)
                        seg = (pts[1] - pts[0]).length if i == 0 else (pts[i] - pts[i - 1]).length
                        half = 0.15 * seg
                        sl = []
                        for tries in range(2):
                            sl = [p - pts[i] for p in P if abs((p - pts[i]).dot(ax)) < half]
                            if len(sl) >= 5:
                                break
                            half *= 2.0
                        if len(sl) < 5:
                            continue
                        # Drop vertices off to one side (neighboring fingers etc.); the midpoint of the remaining slice's ends = middle of the finger thickness
                        us = sorted(p.dot(u) for p in sl)
                        vs = sorted(p.dot(v) for p in sl)
                        mu, mv = us[len(us) // 2], vs[len(vs) // 2]
                        rad = sorted(((p.dot(u) - mu) ** 2 + (p.dot(v) - mv) ** 2) ** 0.5 for p in sl)
                        lim = 2.5 * rad[len(rad) // 2] + 1e-9
                        keep = [p for p in sl if ((p.dot(u) - mu) ** 2 + (p.dot(v) - mv) ** 2) ** 0.5 <= lim]
                        if len(keep) < 5:
                            continue
                        ku = [p.dot(u) for p in keep]
                        kv = [p.dot(v) for p in keep]
                        corr[i] = u * ((min(ku) + max(ku)) / 2) + v * ((min(kv) + max(kv)) / 2)
                    if f in fitted:                      # keep root positions found from mesh slices (and the thumb's 2nd joint)
                        corr[0] = None
                        if f == "Thumb":
                            corr[1] = None
                    elif corr[1] is not None:            # the finger root (knuckle) slice is inaccurate because palm flesh mixes in, so move it along with the next joint
                        corr[0] = corr[1]
                    for i, b in enumerate(ch):
                        if corr[i] is not None and corr[i].length > 1e-6:
                            HW[b.name] = HW[b.name] + corr[i]
                            b.head = inv @ HW[b.name]
                            n_moved += 1
                    # Fingertip: the last segment points toward the center of its flesh, not along the previous segment (works for curved fingers like the thumb)
                    p2, p3 = HW[ch[1].name], HW[ch[2].name]
                    names3 = ch[2].name
                    D = [r[2] for r in recs if max(r[3], key=r[3].get) == names3]
                    D = [q for q in D if (q - p3).dot(p3 - p2) > 0.0] or D
                    d = (p3 - p2).normalized()
                    if len(D) >= 5:
                        c3 = sum(D, Vector((0, 0, 0))) / len(D)
                        if (c3 - p3).length > 1e-5:
                            d = (c3 - p3).normalized()
                        for _ in range(2):                       # adjust once more to aim at the middle of the slice near the tip
                            far = max((q - p3).dot(d) for q in D)
                            sl = [q for q in D if 0.55 * far < (q - p3).dot(d) < 0.95 * far]
                            if len(sl) < 3:
                                break
                            u = (palm_n - d * palm_n.dot(d)).normalized()
                            v = d.cross(u)
                            ku = [(q - p3).dot(u) for q in sl]
                            kv = [(q - p3).dot(v) for q in sl]
                            m = p3 + d * (0.75 * far) + u * ((min(ku) + max(ku)) / 2) + v * ((min(kv) + max(kv)) / 2)
                            d = (m - p3).normalized()
                    far = max((q - p3).dot(d) for q in (D or P))
                    if far > 1e-4:
                        tips[ch[2].name] = inv @ (p3 + d * far)
                return n_moved

            def section(G, c, t):
                # Among slices through c perpendicular to t, the loop closest to c: (size, center, distance from c)
                best = None
                u = (palm_n - t * palm_n.dot(t)).normalized()
                v = t.cross(u)
                for P in slice_loops(G, c, t, reach):
                    q = P - np.array(c)
                    pu, pv = q @ np.array(u), q @ np.array(v)
                    mid = c + u * float((pu.min() + pu.max()) / 2) + v * float((pv.min() + pv.max()) / 2)
                    size = float(max(pu.max() - pu.min(), pv.max() - pv.min()))
                    dist = (mid - c).length
                    if best is None or dist < best[2]:
                        best = (size, mid, dist)
                return best

            def point_on(line, s):              # the point at length s from the start along a polyline
                for a, b in zip(line, line[1:]):
                    l = (b - a).length
                    if s <= l and l > 1e-9:
                        return a + (b - a) * (s / l)
                    s -= l
                return line[-1].copy()

            def length_of(line):
                return sum((b - a).length for a, b in zip(line, line[1:]))

            def fit_joints():
                # Find where the fingers split (web) and the fingertip from mesh slices, and divide between them by real finger joint ratios
                nonlocal reach
                ends = [mw @ tips[ch[2].name] for ch in chains.values() if ch[2].name in tips]
                if not ends:
                    return 0
                reach = max((e - hw).length for e in ends)
                G = hand_geometry(hw + fwd_h * (0.5 * reach), 0.9 * reach)
                if G is None:
                    return 0
                n_fit = 0
                for f, ch in chains.items():
                    if ch[2].name not in tips:
                        continue
                    j = [HW[b.name].copy() for b in ch] + [mw @ tips[ch[2].name]]
                    segl = [(j[i + 1] - j[i]).length for i in range(3)]
                    if min(segl) < 1e-6:
                        continue
                    L = sum(segl)

                    if f == "Thumb":
                        # Thumb: keep the 3rd joint (IP) and tip; the root (CMC) goes inside the thumb pad near the wrist,
                        # the 2nd joint (MCP) midway between the root and the 3rd joint, in the middle of the thumb's outer thickness
                        ip, tip = j[2], j[3]
                        sec = section(G, (j[1] + j[2]) / 2, (j[2] - j[1]).normalized())
                        if sec is None or sec[2] > 0.5 * segl[1]:
                            print(f"[Finger joints] {ch[0].name}: could not find a thumb slice, leaving it")
                            continue
                        fd = sec[0]                                  # thumb thickness
                        Lm = 2.25 * segl[2]                          # root~3rd joint = about 2.25 times the last segment length

                        def to_middle(p, out):                       # out inward from the thumb's outer surface, midway between palm and back of hand
                            dr = ray_len(G, p, lat)
                            if dr is not None and dr > out:
                                p = p + lat * (dr - out)
                            a_, b_ = ray_len(G, p, palm_n), ray_len(G, p, -palm_n)
                            if a_ is not None and b_ is not None:
                                p = p + palm_n * ((a_ - b_) / 2)
                            return p

                        cmc = ip + (hw - ip).normalized() * Lm
                        for _ in range(3):
                            cmc = to_middle(cmc, 0.6 * fd)
                            cmc = ip + (cmc - ip).normalized() * Lm
                        if (cmc - hw).dot(fwd_h) < 0.0:              # don't go past the wrist
                            cmc = cmc - fwd_h * (cmc - hw).dot(fwd_h)
                        mcp = (cmc + ip) / 2
                        for _ in range(2):
                            mcp = to_middle(mcp, 0.5 * fd)
                        new = [cmc, mcp, None]
                        msg = "root inside the thumb pad, 2nd joint at the middle of the thumb"
                    else:
                        # 1) Slice along the current joint line to roughly find the finger thickness, fingertip and split point
                        d0 = (j[1] - j[0]).normalized()
                        d3 = (j[3] - j[2]).normalized()

                        def along(s):
                            if s <= 0.0:
                                return j[0] + d0 * s, d0
                            for i in range(3):
                                if s <= segl[i]:
                                    return j[i] + (j[i + 1] - j[i]) * (s / segl[i]), (j[i + 1] - j[i]).normalized()
                                s -= segl[i]
                            return j[3] + d3 * s, d3

                        step = L / 80.0
                        prof = []
                        for k in range(int(-0.6 * L / step), int(1.15 * L / step) + 1):
                            c, t = along(k * step)
                            sec = section(G, c, t)
                            if sec is not None:
                                prof.append((k * step,) + sec)       # (s, size, center, distance)
                        good = [p for p in prof if p[3] < 0.25 * L]
                        mids = [p[1] for p in good if 0.3 * L < p[0] < 0.8 * L]
                        if len(mids) < 5:
                            print(f"[Finger joints] {ch[0].name}: could not find finger slices, leaving it")
                            continue
                        fd = sorted(mids)[len(mids) // 2]                       # finger thickness
                        tip_s = None                                            # last unbroken slice from the finger middle = fingertip
                        for p in sorted(good, key=lambda p: p[0]):
                            if p[0] < 0.5 * L:
                                continue
                            if tip_s is not None and (p[0] - tip_s > 2.5 * step or p[1] > 1.5 * fd or p[3] > 0.5 * fd):
                                break
                            tip_s = p[0]
                        if tip_s is None:
                            print(f"[Finger joints] {ch[0].name}: could not find the fingertip, leaving it")
                            continue
                        web_s = next((p[0] for p in sorted(prof, key=lambda p: -p[0])
                                      if p[0] < tip_s and p[1] > 1.7 * fd), None)
                        if web_s is None or not (0.5 * L < tip_s - web_s < 1.6 * L):
                            print(f"[Finger joints] {ch[0].name}: could not find the finger split point, leaving it")
                            continue
                        Lf = tip_s - web_s
                        # 2) Slice again along the center line of the first segment's flesh (finger direction from the mesh) to find the split point accurately
                        base = [p[2] for p in good if web_s + 0.08 * Lf <= p[0] <= web_s + 0.35 * Lf]
                        if len(base) < 4:
                            print(f"[Finger joints] {ch[0].name}: not enough first-segment slices, leaving it")
                            continue
                        B = np.array([list(p) for p in base])
                        O = B.mean(0)
                        ax = Vector(np.linalg.svd(B - O)[2][0])
                        if ax.dot(j[3] - j[0]) < 0:
                            ax = -ax
                        O = Vector(O)
                        t0 = (along(web_s)[0] - O).dot(ax)
                        web_t = None
                        for k in range(0, int(1.2 * L / step)):
                            t = t0 + 0.3 * Lf - k * step * 0.5
                            sec = section(G, O + ax * t, ax)
                            if sec is not None and sec[0] > 1.7 * fd:
                                web_t = t
                                break
                        if web_t is None:
                            print(f"[Finger joints] {ch[0].name}: could not find the finger split point, leaving it")
                            continue
                        web_p = O + ax * web_t
                        # 3) Divide split point ~ fingertip along the finger center line. On a real hand, split point ~ tip is split almost into thirds
                        #    by two joints (PIP, DIP), and the knuckle (MCP) sits slightly inside the palm from the split point (1st segment about 1.3x the 2nd)
                        cen = [p[2] for p in good if web_s + 0.08 * Lf < p[0] <= tip_s and (p[2] - web_p).dot(ax) > 0]
                        line = [web_p] + [sum(cen[i:i + 5], Vector((0, 0, 0))) / len(cen[i:i + 5])
                                          for i in range(0, max(len(cen) - 4, 1), 3)] + [along(tip_s)[0]]
                        Lc = length_of(line)
                        knk = web_p - ax * (0.12 * Lc)                         # knuckle (MCP): inside the palm from the split point
                        a_, b_ = ray_len(G, knk, palm_n), ray_len(G, knk, -palm_n)
                        if a_ is not None and b_ is not None:                  # midway between the palm surface and the back of the hand
                            knk = knk + palm_n * ((a_ - b_) / 2)
                        new = [knk, point_on(line, 0.33 * Lc), point_on(line, 0.68 * Lc)]
                        msg = "knuckle inside the palm, joints by joint ratios"
                    for i, b in enumerate(ch):
                        if new[i] is not None:
                            HW[b.name] = new[i]
                            b.head = inv @ new[i]
                    fitted.add(f)
                    n_fit += 1
                    print(f"[Finger joints] {ch[0].name[:-1]:30s} fitted: {msg}")
                return n_fit
            moved += center_pass()
            if FIT_FINGER_JOINTS:
                fit_joints()
            moved += center_pass()                  # once more from the moved positions
            moved += center_pass()
        bpy.ops.object.mode_set(mode='OBJECT')
        print(f"[Finger joints] Moved joints to the middle of the finger thickness {moved} times, fitted the last segments to the fingertips")

    if FIT_BODY_JOINTS:
        fit_body()
    if FIX_FINGERS:
        fix_fingers()


    # 4) Straighten into a T-pose and bake the mesh too
    if T_POSE:
        for o in skinned_meshes():
            if o.data.shape_keys:
                raise Exception(f"{o.name} has shape keys, so it can't be baked into a T-pose. Run with T_POSE = False.")
        bpy.ops.object.mode_set(mode='POSE')
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        pbs = arm.pose.bones

        def aim(name, target_name, direction):
            pb, tg = pbs.get(N(name)), pbs.get(N(target_name))
            if pb is None or tg is None:
                return
            d = tg.head - pb.head
            if d.length < 1e-6:
                return
            q = d.normalized().rotation_difference(direction)
            h = pb.head.copy()
            pb.matrix = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h) @ pb.matrix
            bpy.context.view_layer.update()

        for side, s in (("Left", 1.0), ("Right", -1.0)):
            out = right * s
            aim(side + "Arm", side + "ForeArm", out)              # upper arm horizontal
            aim(side + "ForeArm", side + "Hand", out)             # forearm horizontal
            aim(side + "Hand", side + "HandMiddle1", out)         # hand horizontal with the palm facing down

        bpy.ops.object.mode_set(mode='OBJECT')
        for o in skinned_meshes():                                # bake the mesh into the current pose and reconnect the Armature modifier
            mod = next(m for m in o.modifiers if m.type == 'ARMATURE' and m.object == arm)
            name, vg, env = mod.name, mod.use_vertex_groups, mod.use_bone_envelopes
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = o
            o.select_set(True)
            bpy.ops.object.modifier_apply(modifier=name)
            m = o.modifiers.new(name, 'ARMATURE')
            m.object, m.use_vertex_groups, m.use_bone_envelopes = arm, vg, env
            while o.modifiers.find(name) > 0:                     # back to the top, as before
                bpy.ops.object.modifier_move_up(modifier=name)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = arm
        arm.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.armature_apply(selected=False)               # make the current pose the rest pose
        bpy.ops.object.mode_set(mode='OBJECT')
        print("[T-pose] Straightened the arms horizontally and baked it as the rest pose")
        tips.clear()                                              # the pose changed, so fingertip positions aren't recomputed; default rules are used


    # Vertices attached to each bone (for computing tail length)
    arm_inv = arm.matrix_world.inverted()
    bone_verts = {}
    weighted = set()
    for o in skinned_meshes():
        mat = arm_inv @ o.matrix_world
        gname = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            for g in v.groups:
                n = gname.get(g.group)
                if n is not None and g.weight > 0.0:
                    weighted.add(n)
                if n is not None and g.weight > 0.3:
                    bone_verts.setdefault(n, []).append(mat @ v.co)


    # 5), 6) Tail positions, end bones, roll
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = arm.data.edit_bones
    for b in ebs:
        b.use_connect = False

    PREFERRED = {"Hips": "Spine", "Spine2": "Neck", "LeftHand": "LeftHandMiddle1", "RightHand": "RightHandMiddle1"}


    def short(b):
        return b.name[len(P):] if b.name.startswith(P) else b.name


    def extent(b, d, fallback):
        vs = bone_verts.get(b.name)
        L = max(((co - b.head).dot(d) for co in vs), default=0.0) if vs else 0.0
        return L if L > 0.005 * U else fallback


    def end_name(b):                                # name of the Mixamo end bone attached at this bone's end
        s = short(b)
        if s == "Head":
            return "HeadTop_End"
        if s.endswith("ToeBase"):
            return s.replace("ToeBase", "Toe_End")
        if s[-1:] == "3" and any(w in s for w in FINGER_WORDS):
            return s[:-1] + "4"
        return None

    def is_end(b):                                  # end bone already attached (a file this script was run on before)
        return (not b.use_deform) and b.parent is not None and end_name(b.parent) == short(b)

    # A file exported to FBX and imported again: delete the "_end" leaf bones Blender added, and turn off Deform on Mixamo end bones without weights
    removed = 0
    for b in list(ebs):
        if (b.name.endswith("_end") and not b.children and b.name not in weighted
                and b.parent is not None and b.name[:-4] == b.parent.name):
            ebs.remove(b)
            removed += 1
    for b in ebs:
        if b.use_deform and b.name not in weighted and b.parent is not None and end_name(b.parent) == short(b):
            b.use_deform = False
    if removed:
        print(f"[Cleanup] Deleted {removed} FBX leaf bones (_end)")

    tails = {}
    for b in ebs:
        if is_end(b):
            continue
        s = short(b)
        kids = [k for k in b.children if (k.head - b.head).length > 1e-6 and not is_end(k)
                and (k.name.startswith(P) or not b.name.startswith(P))]   # Mixamo bone tails point to their Mixamo child (other bones like hair are ignored)
        pref = ebs.get(N(PREFERRED[s])) if s in PREFERRED else None
        if pref is not None:
            tails[b.name] = pref.head.copy()
        elif len(kids) == 1:
            tails[b.name] = kids[0].head.copy()
        elif kids:
            tails[b.name] = max(kids, key=lambda k: (k.head - b.head).length).head.copy()
        elif s == "Head":
            tails[b.name] = b.head + up * extent(b, up, 0.2 * U)
        elif s.endswith("ToeBase"):
            d = fwd - up * fwd.dot(up)
            tails[b.name] = b.head + d.normalized() * extent(b, d.normalized(), 0.05 * U)
        elif b.name in tips and (tips[b.name] - b.head).length > 1e-5 * U:
            tails[b.name] = tips[b.name].copy()                     # last finger segment: to the actual fingertip
        else:                                                       # last finger segment: extended along the previous segment
            pd = (b.head - b.parent.head) if b.parent else up
            tails[b.name] = b.head + pd.normalized() * max(pd.length * 0.9, 0.005 * U)
    for b in ebs:
        if b.name in tails and (tails[b.name] - b.head).length > 1e-5 * U:
            b.tail = tails[b.name]

    added = 0
    if ADD_END_BONES:
        for b in [b for b in ebs if not is_end(b)]:
            new = end_name(b)
            if new is None or any(not is_end(k) and k.name.startswith(P) for k in b.children):
                continue
            e = ebs.get(N(new))
            if e is None:                            # create it if missing; if it exists (re-run), just refit its position
                e = ebs.new(N(new))
                added += 1
            e.use_connect = False
            e.head = b.tail.copy()
            if b.name in tips:
                e.tail = b.tail + (b.tail - b.head) * 0.2    # short, starting at the fingertip (so it doesn't stick far out of the finger)
            else:
                e.tail = b.tail + (b.tail - b.head)          # like Mixamo, end bone length = parent bone length
            e.parent = b
            e.use_deform = False

    # Same roll as Mixamo: torso Z axis forward, feet up. For arms, hands, fingers and legs, the direction set in Mixamo's reference pose (arms out horizontal, legs down)
    # (arms down = palm side, legs forward) rotated by the minimum rotation to the current bone direction (matches Mixamo even in an A-pose)
    def canon_roll(bd, cdir, cz):
        q = cdir.rotation_difference(bd)
        return q @ cz


    for b in ebs:
        s = short(b)
        bd = (b.tail - b.head).normalized()
        side = 1.0 if s.startswith("Left") else -1.0
        if any(k in s for k in ("Foot", "Toe")):
            b.align_roll(up)
        elif any(k in s for k in ("Shoulder", "Arm", "Hand")):
            b.align_roll(canon_roll(bd, right * side, -up))
        elif any(k in s for k in ("UpLeg", "Leg")):
            b.align_roll(canon_roll(bd, -up, fwd))
        else:
            b.align_roll(fwd)

    # 7) Connect bones that touch
    joined = 0
    for b in ebs:
        p = b.parent
        if p is not None and (b.head - p.tail).length < 1e-4 * U:
            b.use_connect = True
            joined += 1
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"[Connect] Connected {joined} bones")
    print(f"[Mixamo layout] Added {added} end bones, tails and roll done ({len(arm.data.bones)} bones)")
    # 8) Same unit/axis structure as Mixamo
    if MIXAMO_UNITS and abs(arm.matrix_world.to_scale().x - 1.0) < 1e-3 and arm.matrix_world.to_3x3().is_orthogonal:
        import math
        C = Matrix.Rotation(-math.pi / 2, 4, 'X') @ Matrix.Scale(100.0, 4)   # Z up -> Y up, m -> cm
        objs = [arm] + skinned_meshes()
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = arm
        arm.matrix_world = C @ arm.matrix_world
        bpy.context.view_layer.update()
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        arm.matrix_world = C.inverted() @ arm.matrix_world                # rotate the object the opposite way so it looks the same
        bpy.context.view_layer.update()
        print("[Units] Changed to the same structure as Mixamo (armature X 90 degrees, scale 0.01, skeleton in cm)")
    if "Armature" not in bpy.data.objects:
        arm.name = "Armature"



# Animal and other non-human rigs: fix bone orientation (tail, roll). Joint positions stay as they are
def orient_bones():
    inv = arm.matrix_world.inverted()
    up = (arm.matrix_world.to_3x3().inverted() @ UP_W).normalized()
    fwd = (arm.matrix_world.to_3x3().inverted() @ FORWARD_W).normalized()

    # For each bone, the center of the flesh it mainly moves (used for end bone direction)
    acc = {}
    for o in skinned_meshes():
        M = inv @ o.matrix_world
        names = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            for g in v.groups:
                if g.weight >= 0.5 and g.group in names:
                    s = acc.setdefault(names[g.group], [Vector((0, 0, 0)), 0.0])
                    s[0] += (M @ v.co) * g.weight
                    s[1] += g.weight
    cen = {n: s[0] / s[1] for n, s in acc.items() if s[1] > 0.0}

    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones
    head = {b.name: b.head.copy() for b in eb}

    def count(b):
        return 1 + sum(count(c) for c in b.children)

    plan = {}
    for b in eb:
        h = head[b.name]
        kids = [c for c in b.children if (head[c.name] - h).length > 1e-5]
        inc = (h - head[b.parent.name]) if b.parent is not None else None
        if inc is not None and inc.length < 1e-6:
            inc = None
        target, link = None, None
        if len(kids) == 1:
            target, link = head[kids[0].name], kids[0]
        elif kids:
            best = None
            if inc is not None:                      # the child that best continues the incoming direction (spine -> neck)
                best = max(kids, key=lambda c: (head[c.name] - h).normalized().dot(inc.normalized()))
                if (head[best.name] - h).normalized().dot(inc.normalized()) < 0.5:
                    best = None
            if best is None:                         # the child with the most bones down its chain (root bone -> spine)
                ranked = sorted(kids, key=count, reverse=True)
                if count(ranked[0]) > count(ranked[1]):
                    best = ranked[0]
            if best is not None:
                target, link = head[best.name], best
            else:
                target = sum((head[c.name] for c in kids), Vector((0, 0, 0))) / len(kids)
        else:                                        # end bone: toward the center of the flesh it moves
            Lp = inc.length if inc is not None else (b.tail - b.head).length
            d = None
            if b.name in cen and (cen[b.name] - h).length > 1e-5:
                d = cen[b.name] - h
            elif inc is not None:
                d = inc
            if d is not None:
                L = min(max(2.0 * (cen[b.name] - h).length if b.name in cen else 0.5 * Lp, 0.25 * Lp), Lp)
                target = h + d.normalized() * L
        if target is not None and (target - h).length > 1e-5:
            plan[b.name] = (target, link)

    for n, (target, link) in plan.items():
        eb[n].tail = target
    joined = 0
    for n, (target, link) in plan.items():
        if link is not None and not link.use_connect and (head[link.name] - target).length < 1e-6:
            link.use_connect = True
            joined += 1
    for b in eb:
        y = b.vector.normalized()
        b.align_roll(fwd if abs(y.dot(up)) > 0.9 else up)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"[Bone orientation] Pointed the tails of {len(plan)} bones toward the next joint (end bones toward the flesh center), set roll, connected {joined}")


if REMOVE_UNSKINNED:
    remove_unskinned()
if hips is not None:
    print(f"[Detected] Human rig ({hips.name}) - cleaning up bones and matching the Mixamo layout")
    to_mixamo()
    print("[Done] Bone cleanup finished. Next, run SkinTokens_Fix_Weights.py.")
else:
    print("[Detected] Rig without Mixamo names (Hips) (animals etc.) - keeping joint positions and fixing bone orientation only.")
    if ORIENT_BONES:
        orient_bones()
    print("[Done] Next, run SkinTokens_Fix_Weights.py.")
