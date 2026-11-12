import bpy
import numpy as np
from mathutils import Vector

# Cleans up the skin weights of a SkinTokens auto-rig (both humans and animals)
# Run SkinTokens_Fix_Bones.py first, then this. Weights are cleaned up to match the bone positions.
#
#  1) (Human rigs only) Move weights that leaked to a neighboring finger to the closest finger (FIX_FINGER_WEIGHTS)
#  2) Fit weights to the joints: at every joint where a parent and child bone meet, only where the weight transition is off
#     the joint or cut off sharply, the weights are redistributed smoothly around the joint position with a width matching
#     the joint thickness. Joints that are already fine are not touched. Animal rigs work the same way without bone names.
#     SkinTokens_Fix_Bones.py moves the finger knuckles inside the palm, so the palm flesh in front of the knuckles also gets finger weights.
#     Human rigs (Mixamo names) use per-joint transition positions and blend widths measured from professional auto-rigging (AccuRIG) results (HUMAN_BLEND),
#     and every joint that differs from them is redistributed. Sharply bent joints like the ankle are cut along the parent bone so the heel stays with the foot.
#     The torso (Hips~Head) is a chain of short bones, so it is divided along the torso height all at once rather than joint by joint (SPINE_BLEND)
#     If the upper arm weights spread wide into the chest and below the armpit, they are reduced and given back to the chest bone (so the chest isn't dragged up when raising the arm)
#  3) Blend with the surroundings only where bones that aren't parent-child (chest and upper arm etc.) touch and the weights cut off sharply (SMOOTH_SEAMS)
#  4) Remove small weights, limit the number of bones per vertex, normalize to a sum of 1
#
# It assumes the joints (bone positions) are correct, so if a bone isn't where the body actually bends, move the bone first and run again from SkinTokens_Fix_Bones.py.
# Don't re-run this script after fixing weights by hand. Your hand-fixed weights may be changed again.

FIX_FINGER_WEIGHTS = True   # Clean up weights that leaked to neighboring fingers (human rigs with finger bone names only)
BLEND              = 1.0    # Width of weight blending at joints (1.0 = joint thickness. Smoother: 0.5~2.0)
MAX_INFLUENCES     = 4      # Max number of bones influencing one vertex (game engine default 4)
PRUNE              = 0.01   # Weights smaller than this are removed
SMOOTH_SEAMS       = True   # Smoothly blend sharp weight cut-offs where bones that aren't parent-child touch

FINGER_WORDS = ("Thumb", "Index", "Middle", "Ring", "Pinky")

# Per-joint weight blending for human rigs (Mixamo names): (transition position, blend width), both as ratios of the joint thickness (diameter)
# Transition position + is toward the child bone, - toward the parent bone. Values from professional auto-rigging (AccuRIG) results divided by joint thickness
HUMAN_BLEND = {
    "Spine": (-0.09, 0.94), "Spine1": (0.0, 0.9), "Spine2": (-0.17, 0.21),
    "Neck": (0.15, 1.54), "Head": (-0.26, 1.38),
    "Shoulder": (0.35, 0.64), "Arm": (-0.42, 2.07), "ForeArm": (-0.17, 1.15), "Hand": (0.0, 0.79),
    "UpLeg": (0.24, 0.49), "Leg": (-0.03, 0.77), "Foot": (-0.03, 0.84), "ToeBase": (0.05, 2.2),
    "Thumb1": (0.04, 0.57), "Thumb2": (-0.2, 1.83), "Thumb3": (0.0, 1.15),
    "Finger1": (-0.05, 2.44), "Finger2": (0.05, 1.33), "Finger3": (0.0, 1.15),
}


# Human rig torso (Hips~Head): the torso is a chain of short bones, so it is divided along the whole torso height at once rather than joint by joint
# (joint name: transition position, blend width) both as ratios of the Hips~Head length; a negative transition position is below the joint
SPINE_CHAIN = ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head")
SPINE_BLEND = {"Spine": (-0.056, 0.21), "Spine1": (-0.043, 0.19), "Spine2": (-0.049, 0.25),
               "Neck": (0.018, 0.26), "Head": (-0.092, 0.27)}


def human_key(name):
    s = name.split(":")[-1]
    for side in ("Left", "Right"):
        if s.startswith(side):
            s = s[len(side):]
    for f in FINGER_WORDS:
        if s.startswith("Hand" + f) and s[-1:] in "123":
            return ("Thumb" if f == "Thumb" else "Finger") + s[-1]
    return s

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


# Helper functions
def _smooth(t):
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * (3.0 - 2.0 * t)


def _seg_dist(p, a, b):
    ab = b - a
    L2 = ab.dot(ab)
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / L2))
    return (p - (a + ab * t)).length


# 1) Clean up weights that leaked to neighboring fingers (human rigs only)
def fix_finger_weights():
    mw = arm.matrix_world
    bones = arm.data.bones
    byname = {}
    for b in bones:
        for side in ("Left", "Right"):
            for f in FINGER_WORDS:
                for i in (1, 2, 3):
                    if b.name.endswith(f"{side}Hand{f}{i}"):
                        byname[(side, f, i)] = b.name
    total = 0
    for side in ("Left", "Right"):
        chains = {f: [byname.get((side, f, i)) for i in (1, 2, 3)] for f in FINGER_WORDS}
        chains = {f: ch for f, ch in chains.items() if all(ch)}
        if len(chains) < 2:
            continue
        H = {n: mw @ bones[n].head_local for ch in chains.values() for n in ch}
        T3 = {ch[2]: mw @ bones[ch[2]].tail_local for ch in chains.values()}
        fing_of = {n: f for f, ch in chains.items() for n in ch}

        def segs(f):
            a, b, c = (H[n] for n in chains[f])
            return [(a, b), (b, c), (c, T3[chains[f][2]])]

        for o in skinned_meshes():
            gname = {g.index: g.name for g in o.vertex_groups}
            for v in o.data.vertices:
                w = {gname[g.group]: g.weight for g in v.groups if g.group in gname and g.weight > 0.0}
                if not w:
                    continue
                k = max(w, key=w.get)
                f = fing_of.get(k)
                if f is None:
                    continue
                co = o.matrix_world @ v.co
                nf = min(chains, key=lambda c: min(_seg_dist(co, a, b) for a, b in segs(c)))
                if nf == f:
                    continue
                ss = segs(nf)
                j = min(range(3), key=lambda t: _seg_dist(co, *ss[t]))
                target = chains[nf][j]
                moving = sum(x for n, x in w.items() if fing_of.get(n) == f)
                for n in [n for n in w if fing_of.get(n) == f]:
                    o.vertex_groups[n].remove([v.index])
                g = o.vertex_groups.get(target) or o.vertex_groups.new(name=target)
                g.add([v.index], w.get(target, 0.0) + moving, 'REPLACE')
                total += 1
    print(f"[Finger weights] Moved {total} vertices with neighboring-finger weights to the closest finger")
    return total



# 2) Fit weights to the joints (humans and animals alike. Uses the parent-child bone structure, not bone names)
def fix_weights():
    meshes = skinned_meshes()
    if not meshes:
        print("[Weights] No mesh is connected to the armature, skipping")
        return
    mw = arm.matrix_world
    bones = arm.data.bones
    deform = {b.name for b in bones if b.use_deform}
    H = {b.name: mw @ b.head_local for b in bones}
    TL = {b.name: mw @ b.tail_local for b in bones}

    # Per vertex: (mesh, index, world position, {bone name: weight})
    recs = []
    total = {}
    for o in meshes:
        gname = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            w = {}
            for g in v.groups:
                n = gname.get(g.group)
                if n in deform and g.weight > 0.0:
                    w[n] = w.get(n, 0.0) + g.weight
                    total[n] = total.get(n, 0.0) + g.weight
            recs.append([o, v.index, o.matrix_world @ v.co, w, False])
    weighted = {n for n, t in total.items() if t > 1e-3}
    acc = {}
    for r in recs:                                   # per bone, the center of the vertices it mainly moves
        w = r[3]
        if w:
            k = max(w, key=w.get)
            if w[k] >= 0.5 * sum(w.values()):
                a = acc.setdefault(k, [Vector((0, 0, 0)), 0])
                a[0] += r[2]
                a[1] += 1
    cen = {k: a[0] / a[1] for k, a in acc.items() if a[1] >= 3}

    sub_cache = {}

    def subtree(b):
        if b.name not in sub_cache:
            sub_cache[b.name] = {b.name} | {k.name for k in b.children_recursive}
        return sub_cache[b.name]

    def has_weight(b):
        return bool(subtree(b) & weighted)

    def bone_dir(b):
        kids = [k for k in b.children if has_weight(k) and (H[k.name] - H[b.name]).length > 1e-6]
        if len(kids) == 1:
            return H[kids[0].name] - H[b.name]
        if kids:
            c = Vector((0, 0, 0))
            for k in kids:
                c += H[k.name]
            return c / len(kids) - H[b.name]
        # End bones (toes, fingertips, head, tail tip, etc.): the tail direction isn't reliable, so the direction toward the center
        # of the vertices this bone mainly moves is used as the bone direction
        if b.name in cen:
            d = (cen[b.name] - H[b.name]) * 2.0
            if d.length > 1e-6:
                return d
        if b.parent is not None and (H[b.name] - H[b.parent.name]).length > 1e-6:
            return (H[b.name] - H[b.parent.name]) * 0.5
        return TL[b.name] - H[b.name]

    def segments(b):
        out = []
        for n in subtree(b):
            bb = bones[n]
            out.append((H[n], H[n] + bone_dir(bb)))
        return out

    fixed, kept = [], 0
    arm_cap = {}

    # Divide the human rig torso all at once
    chain = []
    if HUMANOID:
        for key in SPINE_CHAIN:
            b = next((b for b in bones if b.name.split(":")[-1] == key), None)
            chain.append(b.name if b is not None and b.name in weighted else None)
        if not all(chain):
            chain = []
    if chain:
        pts = [H[n] for n in chain] + [TL[chain[-1]]]
        segl = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
        Lch = sum(segl[:-1])
        pos = [0.0]
        for l in segl:
            pos.append(pos[-1] + l)

        def along(p):                                # position along the torso line (length measured from Hips)
            best = None
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                ab = b - a
                t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-12)))
                d = (p - (a + ab * t)).length
                if best is None or d < best[0]:
                    best = (d, pos[i] + t * segl[i])
            if best[1] <= 0.0:                       # below Hips
                return (p - pts[0]).dot((pts[1] - pts[0]).normalized())
            return best[1]

        cset = set(chain)
        n_ch = 0
        for r in recs:
            w = r[3]
            tot = sum(w.values())
            S = sum(w.get(n, 0.0) for n in chain)
            if tot <= 0.0 or S < 0.05 * tot:             # if there is any torso weight, only that share is redistributed by height
                continue
            t = along(r[2])
            f, prev = [], 1.0
            for i, key in enumerate(SPINE_CHAIN[1:], start=1):
                off, wid = SPINE_BLEND[key]
                x = _smooth((t - (pos[i] + off * Lch)) / max(wid * Lch, 1e-9) + 0.5)
                prev = min(prev, x)
                f.append(prev)
            parts = [1.0 - f[0]] + [f[i] - f[i + 1] for i in range(len(f) - 1)] + [f[-1]]
            for n, q in zip(chain, parts):
                if q * S > 1e-6:
                    w[n] = q * S
                elif n in w:
                    del w[n]
            r[4] = True
            n_ch += 1
        print(f"[Weights] Smoothly redistributed {n_ch} torso (Hips~Head) vertices along the torso height")
    for c in bones:                                  # parent -> child order
        p = c.parent
        if p is None or c.name not in weighted or p.name not in weighted:
            continue
        if chain and c.name in chain:                # the torso was already divided above
            continue
        dp, dc = H[c.name] - H[p.name], bone_dir(c)
        Lp, Lc = dp.length, dc.length
        if Lp < 1e-6 or Lc < 1e-6:
            continue
        sibs = [k for k in p.children if has_weight(k)]
        branching = len(sibs) > 1
        n = dp.normalized() + dc.normalized()
        if branching or n.length < 1e-3:
            n = dc.normalized()
        elif dp.normalized().dot(dc.normalized()) < 0.2:   # bent joints like the ankle: cut along the parent bone (so the heel stays with the foot)
            n = dp.normalized()
        else:
            n.normalize()
        human = HUMAN_BLEND.get(human_key(c.name)) if HUMANOID else None
        sub = subtree(c)
        sib_segs = {k.name: segments(k) for k in sibs} if branching else None
        # Finger roots: when SkinTokens_Fix_Bones.py moves the knuckles inside the palm, the palm flesh in between must follow the finger too,
        # so palm vertices with no finger weight yet are also candidates if they are close to this finger
        palm = branching and len(sibs) >= 4 and any(w in c.name for w in FINGER_WORDS)
        extra = []

        # Vertices handled at this joint: most of their weight is on the upper/lower bone and (at a branching joint) they are closest to this branch
        cand = []
        for r in recs:
            w = r[3]
            tot = sum(w.values())
            if tot <= 0.0:
                continue
            S = w.get(p.name, 0.0) + w.get(c.name, 0.0)
            if S < 0.5 * tot:
                continue
            outside = False
            if branching:
                if sum(w.get(k, 0.0) for k in sub) < 0.01 * tot:
                    if not palm:
                        continue
                    s = (r[2] - H[c.name]).dot(n)
                    if s < -0.5 * Lc or s > Lc:
                        continue
                    outside = True
                co = r[2]
                near = min(sib_segs, key=lambda k: min(_seg_dist(co, a, b) for a, b in sib_segs[k]))
                if near != c.name:
                    continue
            s = (r[2] - H[c.name]).dot(n)
            (extra if outside else cand).append((r, S, s))
        if len(cand) < 4:
            continue

        # The blend width is set by the joint thickness (radius)
        rad = sorted(((r[2] - H[c.name]) - n * s).length for r, S, s in cand if abs(s) < 0.5 * min(Lp, Lc))
        R = rad[len(rad) // 2] if rad else 0.25 * min(Lp, Lc)
        if human:
            W = min(BLEND * human[1] * 2.0 * R, 3.0 * min(Lp, Lc))
            off = human[0] * 2.0 * R
        else:
            W = min(BLEND * 2.0 * R, 0.8 * min(Lp, Lc))
            off = 0.0
        if W < 1e-6:
            continue
        cand += [(r, S, s) for r, S, s in extra
                 if s > -0.5 * W and ((r[2] - H[c.name]) - n * s).length < 2.0 * R]

        if human and human_key(c.name) == "Arm":
            arm_cap[c.name] = (n, W, off, R, p.parent if p.parent is not None and p.parent.name in weighted else p)

        # Measure the current state: the point where it crosses half and half (cross) and the blend width (width)
        ratio = [(s, r[3].get(c.name, 0.0) / S) for r, S, s in cand if S > 0.0]
        mid = sorted(s for s, q in ratio if abs(q - 0.5) < 0.15)
        bl = sorted(s for s, q in ratio if 0.1 < q < 0.9)
        cross = mid[len(mid) // 2] if mid else None
        width = (bl[int(len(bl) * 0.95) - 1] - bl[int(len(bl) * 0.05)]) if len(bl) > 3 else 0.0
        bad = cross is None or abs(cross - off) > 0.25 * W or width < 0.4 * W or (human and width > 1.6 * W)
        if not bad:
            kept += 1
            continue

        for r, S, s in cand:
            q = _smooth((s - off) / W + 0.5)
            w = r[3]
            nc = S * q
            if abs(nc - w.get(c.name, 0.0)) > 1e-4:
                w[c.name] = nc
                w[p.name] = S - nc
                r[4] = True
        fixed.append((c.name, cross, width, W))

    # Reduce upper arm weights that reach too wide into the chest/below the armpit and give them back to the chest (the clavicle's parent, usually Spine2).
    # The upper arm's share shrinks toward the body from the arm joint, and outward past the arm thickness (chest, below the armpit).
    # Prevents the chest from being dragged up and bulging when raising the arm
    n_cap = 0
    for name, (n, W, off, R, gp) in arm_cap.items():
        a0 = H[name]
        for r in recs:
            w = r[3]
            a = w.get(name, 0.0)
            if a <= 0.0:
                continue
            v = r[2] - a0
            s = v.dot(n)
            if s > off + 0.5 * W:
                continue
            rad = (v - n * s).length
            cap = sum(w.values()) * _smooth((s - off) / W + 0.5) * _smooth((1.3 * R - rad) / (0.8 * R) + 0.5)
            if a > cap + 1e-4:
                w[name] = cap
                w[gp.name] = w.get(gp.name, 0.0) + a - cap
                r[4] = True
                n_cap += 1
    if n_cap:
        print(f"[Weights] Gave {n_cap} vertices that the upper arm reached too wide toward the chest/armpit back to the chest bone")

    # Smooth sharp seams: only where two bones that aren't parent-child (e.g. chest Spine2 and upper arm Arm) touch and the weights switch
    # as if cut with a knife, blend with the surroundings. Prevents faces there from tearing and stretching in big poses
    seam_fixed = 0
    if SMOOTH_SEAMS:
        scale = max((H[b.name] - H[bones[0].name]).length for b in bones) or 1.0
        by_obj = {}
        for r in recs:
            by_obj.setdefault(r[0], {})[r[1]] = r

        def related(a, b):
            if a == b:
                return True
            ba, bb = bones.get(a), bones.get(b)
            return ba is not None and bb is not None and (ba.parent == bb or bb.parent == ba)

        for o, rv in by_obj.items():
            ev = np.empty(len(o.data.edges) * 2, dtype=np.int64)
            o.data.edges.foreach_get("vertices", ev)
            ev = ev.reshape(-1, 2)
            nbr = {}
            seam = set()
            elen = []
            for a, b in ev:
                ra, rb = rv.get(int(a)), rv.get(int(b))
                if ra is None or rb is None or not ra[3] or not rb[3]:
                    continue
                nbr.setdefault(int(a), []).append(int(b))
                nbr.setdefault(int(b), []).append(int(a))
                elen.append((ra[2] - rb[2]).length)
                wa, wb = ra[3], rb[3]
                ta, tb = sum(wa.values()), sum(wb.values())
                d = 0.5 * sum(abs(wa.get(k, 0.0) / ta - wb.get(k, 0.0) / tb) for k in set(wa) | set(wb))
                if d > 0.5 and not related(max(wa, key=wa.get), max(wb, key=wb.get)):
                    seam.update((int(a), int(b)))
            if not seam or not elen:
                continue
            e_mean = sum(elen) / len(elen)
            rings = max(1, min(6, int(round(0.02 * scale * 3 / max(e_mean, 1e-9)))))
            region = set(seam)
            front = set(seam)
            for _ in range(rings):
                front = {n for v in front for n in nbr.get(v, ()) if n not in region}
                region |= front
            for _ in range(rings * rings):
                upd = {}
                for v in region:
                    acc_w = dict(rv[v][3])
                    cnt = 1
                    for n in nbr.get(v, ()):
                        for k, x in rv[n][3].items():
                            acc_w[k] = acc_w.get(k, 0.0) + x
                        cnt += 1
                    upd[v] = {k: x / cnt for k, x in acc_w.items()}
                for v, w in upd.items():
                    rv[v][3] = w
                    rv[v][4] = True
            seam_fixed += len(region)
        if seam_fixed:
            print(f"[Weights] Smoothly blended {seam_fixed} vertices around sharp seams between bones that aren't parent-child")

    # Clean up small weights, limit bone count, normalize to a sum of 1
    pruned = 0
    for r in recs:
        w = r[3]
        if not w:
            continue
        tot = sum(w.values())
        keep = sorted(((k, x) for k, x in w.items() if x >= PRUNE * tot), key=lambda kv: -kv[1])[:MAX_INFLUENCES]
        if not keep:
            keep = [max(w.items(), key=lambda kv: kv[1])]
        if len(keep) != len(w):
            pruned += len(w) - len(keep)
            r[4] = True
        if r[4]:
            t = sum(x for k, x in keep)
            r[3] = {k: x / t for k, x in keep}

    changed = 0
    for o, idx, co, w, dirty in recs:
        if not dirty:
            continue
        changed += 1
        for g in o.vertex_groups:
            if g.name in deform and g.name not in w:
                g.remove([idx])
        for k, x in w.items():
            g = o.vertex_groups.get(k) or o.vertex_groups.new(name=k)
            g.add([idx], x, 'REPLACE')

    u = 100.0                                            # cm for display
    for name, cross, width, W in fixed:
        cs = "no transition" if cross is None else f"transition {cross * u:+.1f}cm"
        print(f"[Weights] {name:32s} {cs}, blend width {width * u:.1f}cm -> at joint, width {W * u:.1f}cm")
    print(f"[Weights] Fixed {len(fixed)} joints, {kept} were already fine and left as is. "
          f"Changed {changed} vertices, removed {pruned} small weights")


if not skinned_meshes():
    raise Exception("No mesh is connected to this armature. Select the Armature in the SkinTokens result file and run again.")
has_fingers = any(b.name.endswith("HandIndex1") for b in arm.data.bones)
HUMANOID = any(b.name.endswith("Hips") for b in arm.data.bones) and any(b.name.endswith("LeftUpLeg") for b in arm.data.bones)
if FIX_FINGER_WEIGHTS and has_fingers:
    fix_finger_weights()
fix_weights()
print("[Done] Weight cleanup finished. When exporting to FBX, turn off Armature > Add Leaf Bones.")
