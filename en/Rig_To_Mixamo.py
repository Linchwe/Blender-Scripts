# Rig_To_Mixamo.py
# Blender 4.2 ~ 4.5
# Converts the bone names and parent-child hierarchy of any rig to the Mixamo rig layout.
# Use it before applying Mixamo animations to a character rigged in another program, or before feeding it to tools
# that take a Mixamo rig (MoCapAnything, Kimodo, etc.).
#
# Recognized rigs (identified by bone names)
#  - Mixamo                     mixamorig:LeftArm, mixamorig1:LeftArm ...
#  - Unreal Mannequin (UE4, UE5) pelvis, spine_01, upperarm_l, thumb_01_l ...
#  - AccuRIG / Character Creator CC_Base_Hip, CC_Base_L_Upperarm ...
#  - VRoid                      J_Bip_C_Hips, J_Bip_L_UpperArm ...
#  - Blender Rigify (generated)  DEF-spine, DEF-upper_arm.L ...
#  - 3ds Max Biped               Bip01 Pelvis, Bip01 L UpperArm, Bip01 L Finger0 ...
#  - DAZ (Genesis)               hip, lShldrBend, lForearmBend ...
#  - Rigs made in Blender        upper_arm.L, thigh.R, Arm_L ...
#  - Rigs with unknown names     bone_0, bone_1 ... -> finds the pelvis, spine, arms, legs and fingers from the bone hierarchy and positions
#                                (humanoid rigs only)
#
# What it does
#  0) First deletes bones that don't move the mesh (controls with Deform off, IK, end bones, etc.).
#  1) Finds the bones matching the Mixamo bones (Hips, Spine~Spine2, Neck, Head, shoulder~hand, 3 finger joints, thigh~toe),
#     renames them to mixamorig: names and reconnects them with the same parent-child hierarchy as Mixamo.
#     (Vertex group names change with them, so the weights follow)
#  2) Deletes helper bones that Mixamo doesn't have and merges their weights into the nearest Mixamo bone.
#       Twist bones, root bones, palm bones (metacarpal, carpal), extra spine/neck segments, corrective bones, etc.
#       If there are 4 or more spine bones, they are merged into three: Spine, Spine1, Spine2.
#  3) Bones with no Mixamo match (hair, skirt, tail, face, chest, etc.) are kept as they are. (KEEP_EXTRA_BONES)
#     Mixamo animations have no motion for these bones, so they follow their parent bone.
#  4) For rigs without spine, neck or shoulder bones, creates empty bones with no weights to fill the Mixamo hierarchy.
#
# Notes
#  - Assumes the character faces front (-Y) in Blender's Front view and up is +Z. (Character's left = +X)
#  - Rigs without fingers or toes don't get those bones created. (They would need new weights painted)
#  - The root bone is deleted, so Unreal root motion is lost. (In Mixamo, Hips is the top bone)
#  - Rigs like 3ds Max Biped, where the thighs hang under Spine and the clavicles under Neck, are reattached in Mixamo order.
#  - After running, the console (Window > Toggle System Console) lists original name -> Mixamo name, deleted bones, kept bones,
#    and newly created empty bones. If a pairing looks wrong, undo with Ctrl+Z and check that bone's name.
#  - This script only changes names and hierarchy. To also match Mixamo's bone orientation (roll), end bones (HeadTop_End etc.)
#    and units, run SkinTokens_Fix_Bones.py (bone cleanup) and then SkinTokens_Fix_Weights.py (weight cleanup).
#    (Despite the name, they work on any rig with Mixamo names)
#
# Usage: select the armature in Object Mode > Scripting tab > New text > Paste > Check the settings > Run Script
# Save with Ctrl+S before running. You can undo with Ctrl+Z.

import bpy
import re
from mathutils import Vector

# ---------------- Settings ----------------
KEEP_EXTRA_BONES = True          # True : keep bones with no Mixamo match (hair, skirt, tail, etc.)
                                 # False: delete those too and merge their weights into the nearest Mixamo bone
PREFIX           = "mixamorig:"  # Prefix for the new names (Mixamo default)
# --------------------------------------

SIDES = ("Left", "Right")
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")

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


# ---- 0) First delete bones that don't move the mesh (controls, IK, end bones and other bones with Deform off) ---------
#      (For rigs like Rigify where real bones hang under control bones, real bones are linked to each other)
bpy.ops.object.mode_set(mode='EDIT')
_eb = arm.data.edit_bones
_nd = [e.name for e in _eb if not e.use_deform]
if len(_nd) < len(_eb):
    for name in _nd:
        e = _eb[name]
        p = e.parent
        while p is not None and not p.use_deform:
            p = p.parent
        for k in list(e.children):
            k.use_connect = False
            k.parent = p
    for name in _nd:
        _eb.remove(_eb[name])
bpy.ops.object.mode_set(mode='OBJECT')
if _nd:
    print(f"[Cleanup] Deleted {len(_nd)} bones that don't move the mesh (Deform off)")

bones = arm.data.bones
mw = arm.matrix_world
H = {b.name: mw @ b.head_local for b in bones}

# Total weight per bone (bones with weights = bones that actually move the mesh)
wsum = {}
for o in skinned_meshes():
    gname = {g.index: g.name for g in o.vertex_groups}
    for v in o.data.vertices:
        for g in v.groups:
            n = gname.get(g.group)
            if n is not None and g.weight > 0.0:
                wsum[n] = wsum.get(n, 0.0) + g.weight


def weighted(b):
    return wsum.get(b.name, 0.0) > 1e-4


def sub_weighted(b):
    return weighted(b) or any(weighted(k) for k in b.children_recursive)


# ---- Identify bone types by name ------------------------------------------------------------
def strip_prefix(n):
    n = n.split(":")[-1]
    n = re.sub(r"^(CC_Base_|J_Bip_|J_Adj_|J_Sec_|DEF-|ORG-|MCH-|Bip\d+\s*|mixamorig\d*)", "", n, flags=re.I)
    return n


def side_of(name):
    n = strip_prefix(name)
    if re.search(r"left", n, re.I):
        return "Left"
    if re.search(r"right", n, re.I):
        return "Right"
    if re.search(r"(^|[^A-Za-z])[Ll]([^A-Za-z]|$)", n) or re.match(r"^l[A-Z]", n):
        return "Left"
    if re.search(r"(^|[^A-Za-z])[Rr]([^A-Za-z]|$)", n) or re.match(r"^r[A-Z]", n):
        return "Right"
    return None


HELPER_WORDS = ("twist", "roll", "share", "metacarpal", "carpal", "palm", "corrective", "adjust", "helper",
                "nub", "_end", ".end", "end_", "tip", "pole", "target", "ik_", "_ik", "ctrl", "mch", "root",
                "bend_", "jiggle", "adj_")


def plain(name):
    n = strip_prefix(name)
    n = re.sub(r"^[lr](?=[A-Z])", "", n)                              # DAZ: lShldrBend -> ShldrBend
    n = re.sub(r"(left|right)", "", n, flags=re.I)
    n = re.sub(r"(^|[^A-Za-z])[LlRrCc](?=[^A-Za-z]|$)", r"\1", n)    # remove _L_, .L, _l, ' L ' etc.
    return n.lower()


def is_helper(name):
    n = name.lower()
    if re.search(r"(^|[^a-z])(c|l|r)?_?(bend)$", n):
        return False
    return any(w in n for w in HELPER_WORDS) or n.startswith("ik") or n == "root"


def part_of(name):
    """Returns (part, finger index). Fingers are returned as ('Index', joint)"""
    p = plain(name)
    if "toe" in p or "ball" in p:
        return ("toe", None)
    m = re.search(r"finger\s*(\d)(\d)?", p)                         # 3ds Max Biped: Finger0, Finger01 ...
    if m:
        return ("finger", (FINGERS[min(int(m.group(1)), 4)], int(m.group(2) or 0) + 1))
    for words, f in ((("thumb",), "Thumb"), (("index",), "Index"), (("middle", "mid"), "Middle"),
                     (("ring",), "Ring"), (("pinky", "little", "small"), "Pinky")):
        if any(w in p for w in words):
            d = re.findall(r"(\d+)", p)
            return ("finger", (f, int(d[-1]) if d else None))
    if any(w in p for w in ("forearm", "lowerarm", "lower_arm", "elbow")):
        return ("forearm", None)
    if any(w in p for w in ("upperarm", "upper_arm", "uparm", "shldr")):
        return ("arm", None)
    if any(w in p for w in ("shoulder", "clavicle", "collar")):
        return ("shoulder", None)
    if re.search(r"(^|[^a-z])arm([^a-z]|$)", p) or p == "arm":
        return ("arm", None)
    if "hand" in p or "wrist" in p:
        return ("hand", None)
    if any(w in p for w in ("thigh", "upperleg", "upper_leg", "upleg")):
        return ("upleg", None)
    if any(w in p for w in ("calf", "shin", "lowerleg", "lower_leg", "knee")) or re.search(r"(^|[^a-z])leg([^a-z]|$)", p):
        return ("leg", None)
    if "foot" in p or "ankle" in p:
        return ("foot", None)
    if "metatarsal" in p:
        return ("foot", None)
    if "head" in p and "headtop" not in p:
        return ("head", None)
    if "neck" in p:
        return ("neck", None)
    if any(w in p for w in ("hips", "pelvis", "hip")):
        return ("hips", None)
    if any(w in p for w in ("spine", "chest", "waist", "torso", "abdomen", "back")):
        return ("spine", None)
    return (None, None)


INFO = {b.name: (side_of(b.name), part_of(b.name)) for b in bones}


def depth(b):
    d = 0
    while b.parent:
        d += 1
        b = b.parent
    return d


def first(cands):
    cands = [b for b in cands if b is not None]
    return min(cands, key=depth) if cands else None


def find_part(part, side, under=None):
    c = [b for b in bones if INFO[b.name][1][0] == part and INFO[b.name][0] == side
         and not is_helper(b.name) and (under is None or b == under or under in b.parent_recursive)]
    return first(c)


def lca(*bs):
    bs = [b for b in bs if b is not None]
    if not bs:
        return None
    anc = [[b] + list(b.parent_recursive) for b in bs]
    for a in anc[0]:
        if all(a in x for x in anc[1:]):
            return a
    return None


def path_down(top, bottom):
    """From under top down to bottom (excluding top and bottom)"""
    out = []
    b = bottom.parent
    while b is not None and b != top:
        out.append(b)
        b = b.parent
    return list(reversed(out)) if b == top else []


# ---- 1) Find by name ----------------------------------------------------------------------
M = {}                    # Mixamo name (without PREFIX) -> original bone
limb = {}
for s in SIDES:
    a = find_part("arm", s)
    fa = find_part("forearm", s, a) if a else find_part("forearm", s)
    h = find_part("hand", s, fa) if fa else find_part("hand", s)
    ul = find_part("upleg", s)
    lg = find_part("leg", s, ul) if ul else find_part("leg", s)
    ft = find_part("foot", s, lg) if lg else find_part("foot", s)
    limb[s] = dict(Arm=a, ForeArm=fa, Hand=h, UpLeg=ul, Leg=lg, Foot=ft)

named_ok = all(limb[s][k] is not None for s in SIDES for k in ("Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot"))
method = "by name"


# ---- 1') If not found by name, find by bone hierarchy and positions ------------------------------------------
def structural():
    wb = [b for b in bones if sub_weighted(b)]

    def wkids(b):
        return [k for k in b.children if sub_weighted(k)]

    def n_desc(b):
        return sum(1 for k in b.children_recursive if sub_weighted(k))

    def chain(start, n):
        out = [start]
        cur = start
        while len(out) < n:
            ks = wkids(cur)
            if not ks:
                break
            cur = max(ks, key=lambda k: n_desc(k))
            out.append(cur)
        return out

    z = lambda b: H[b.name].z
    x = lambda b: H[b.name].x
    pelvis = next((b for b in sorted(wb, key=depth) if len(wkids(b)) >= 3), None)
    if pelvis is None:
        raise Exception("Could not find the pelvis (the bone where both legs and the spine branch). This doesn't look like a humanoid rig.")
    ks = wkids(pelvis)
    spine_root = max(ks, key=n_desc)
    legs = sorted([k for k in ks if k != spine_root], key=n_desc, reverse=True)[:2]
    chest = spine_root
    while len(wkids(chest)) == 1:
        chest = wkids(chest)[0]
    cks = wkids(chest)
    if len(cks) < 3:
        raise Exception("Could not find the chest (the bone where both arms and the neck branch).")
    neck_root = max(cks, key=z)
    arms = sorted([k for k in cks if k != neck_root], key=lambda k: abs(x(k)), reverse=True)[:2]
    out = {"Hips": pelvis}
    for s, pick in (("Left", max), ("Right", min)):
        l = pick(legs, key=x)
        a = pick(arms, key=x)
        lc = chain(l, 4)
        ac = chain(a, 4)
        if len(ac) == 3:                       # rig without shoulder bones
            ac = [None] + ac
        for nm, b in zip(("UpLeg", "Leg", "Foot", "ToeBase"), lc):
            out[s + nm] = b
        for nm, b in zip(("Shoulder", "Arm", "ForeArm", "Hand"), ac):
            if b is not None:
                out[s + nm] = b
    out["_chest"] = chest
    out["_neck_root"] = neck_root
    return out


if named_ok:
    for s in SIDES:
        for k, b in limb[s].items():
            M[s + k] = b
        t = find_part("toe", s, limb[s]["Foot"])
        if t is not None:
            M[s + "ToeBase"] = t
else:
    method = "by bone hierarchy"
    st = structural()
    for k, v in st.items():
        if not k.startswith("_"):
            M[k] = v

# ---- 2) Body: pelvis, spine, neck, head -----------------------------------------------------------
hips = lca(M["LeftUpLeg"], M["RightUpLeg"], M["LeftArm"], M["RightArm"])
if named_ok:
    hips = lca(M["LeftUpLeg"], M["RightUpLeg"], lca(M["LeftArm"], M["RightArm"]))
# If a bone named pelvis (hips/pelvis) is above it, use that bone as Hips (3ds Max Biped has the thighs under Spine)
p = hips.parent
while p is not None:
    if INFO[p.name][1][0] == "hips" and INFO[p.name][0] is None and weighted(p):
        hips = p
        break
    p = p.parent
M["Hips"] = hips
chest = lca(M["LeftArm"], M["RightArm"])
while chest is not None and INFO[chest.name][1][0] in ("neck", "head") and chest.parent is not None:
    chest = chest.parent                       # 3ds Max Biped has the clavicles under Neck
# Shoulder: the bone between the chest and the upper arm (an empty bone is created later if missing)
for s in SIDES:
    if s + "Shoulder" in M:
        continue
    p = path_down(chest, M[s + "Arm"])
    sh = next((b for b in p if INFO[b.name][1][0] == "shoulder" and not is_helper(b.name)), None)
    if sh is None and p:
        sh = next((b for b in p if not is_helper(b.name)), None)
    if sh is not None:
        M[s + "Shoulder"] = sh

# Head: the bone with head in its name, otherwise the end of the body chain going up from the chest
head = None
if named_ok:
    head = first([b for b in chest.children_recursive if INFO[b.name][1][0] == "head" and INFO[b.name][0] is None
                  and not is_helper(b.name)])
if head is None:
    up = [k for k in chest.children if sub_weighted(k) and k not in
          ([M.get(s + "Shoulder") for s in SIDES] + [M[s + "Arm"] for s in SIDES]) and
          not any(M[s + "Arm"] in k.children_recursive for s in SIDES)]
    if up:
        cur = max(up, key=lambda k: H[k.name].z)
        while True:
            ks = [k for k in cur.children if sub_weighted(k)]
            if len(ks) != 1:
                break
            cur = ks[0]
        head = cur
if head is None:
    raise Exception("Could not find the head bone.")
M["Head"] = head
neck_path = path_down(chest, head)
neck = next((b for b in neck_path if INFO[b.name][1][0] == "neck" and not is_helper(b.name)), None)
if neck is None and neck_path:
    neck = neck_path[0]
if neck is not None:
    M["Neck"] = neck

# Spine: split the chain from above the pelvis up to the chest into Spine, Spine1, Spine2
sp = [b for b in path_down(hips, chest) if not is_helper(b.name)] + [chest]
if len(sp) >= 3:
    M["Spine"], M["Spine1"], M["Spine2"] = sp[0], sp[len(sp) // 2], sp[-1]
elif len(sp) == 2:
    M["Spine"], M["Spine2"] = sp[0], sp[1]
else:
    M["Spine2"] = sp[0]

# ---- 3) Fingers ----------------------------------------------------------------------------
for s in SIDES:
    hand = M[s + "Hand"]
    roots = []
    for f in FINGERS:
        c = [b for b in hand.children_recursive if INFO[b.name][1][0] == "finger" and INFO[b.name][1][1][0] == f
             and not is_helper(b.name) and INFO[b.name][0] in (s, None)]
        c.sort(key=depth)
        c = [b for b in c if sub_weighted(b) or b.use_deform][:3]
        if c:
            roots.append((f, c))
    if not roots:                               # if not found by name, treat the branches under the hand as fingers (Fix_Bones renames them by position)
        ks = [k for k in hand.children if sub_weighted(k)]
        for f, k in zip(FINGERS, ks):
            c = [k]
            while len(c) < 3:
                kk = [x for x in c[-1].children if sub_weighted(x)]
                if not kk:
                    break
                c.append(kk[0])
            roots.append((f, c))
    for f, c in roots:
        for i, b in enumerate(c, 1):
            M[f"{s}Hand{f}{i}"] = b

# Make sure no bone is used for two slots
seen = {}
for k in list(M):
    b = M[k]
    if b.name in seen:
        print(f"[Warning] {b.name} matches both {seen[b.name]} and {k}, so {k} is left empty")
        del M[k]
    else:
        seen[b.name] = k

PARENT = {"Spine": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "Neck": "Spine2", "Head": "Neck"}
for s in SIDES:
    PARENT.update({s + "Shoulder": "Spine2", s + "Arm": s + "Shoulder", s + "ForeArm": s + "Arm",
                   s + "Hand": s + "ForeArm", s + "UpLeg": "Hips", s + "Leg": s + "UpLeg", s + "Foot": s + "Leg",
                   s + "ToeBase": s + "Foot"})
    for f in FINGERS:
        PARENT.update({f"{s}Hand{f}1": s + "Hand", f"{s}Hand{f}2": f"{s}Hand{f}1", f"{s}Hand{f}3": f"{s}Hand{f}2"})

print(f"[Find] Found {len(M)} Mixamo bones {method}")
for k in sorted(M, key=lambda k: depth(M[k])):
    if M[k].name != PREFIX + k:
        print(f"   {M[k].name:40s} -> {PREFIX + k}")

# ---- 4) Split bones to delete and bones to keep, and decide where to merge weights ----------------------------------------
mapped = {b.name for b in M.values()}


def nearest_mapped(b):
    p = b.parent
    while p is not None:
        if p.name in mapped:
            return p.name
        p = p.parent
    return None


delete, keep = {}, []                          # bone to delete -> Mixamo bone to merge its weights into
hips_anc = {b.name for b in M["Hips"].parent_recursive}
for b in bones:
    if b.name in mapped:
        continue
    if b.name in hips_anc:                     # root and other bones above the pelvis
        delete[b.name] = M["Hips"].name
        continue
    tgt = nearest_mapped(b) or M["Hips"].name
    if any(k.name in mapped for k in b.children_recursive):   # extra segments in the middle of a chain (extra spine, twist, etc.)
        delete[b.name] = tgt
        continue
    anat = INFO[b.name][1][0] is not None      # bones with arm/leg/finger names that got no Mixamo slot = helper bones
    if is_helper(b.name) or anat or not sub_weighted(b) or not KEEP_EXTRA_BONES:
        delete[b.name] = tgt
    else:
        keep.append(b.name)

# ---- 5) Merge weights ----------------------------------------------------------------------
merged = 0
for o in skinned_meshes():
    vg = o.vertex_groups
    gname = {g.index: g.name for g in vg}
    add = {}                                   # (vertex, target bone) -> weight to add
    base = {}
    for v in o.data.vertices:
        ws = {gname[e.group]: e.weight for e in v.groups if e.group in gname}
        for n, w in ws.items():
            if n in delete and w > 0.0:
                t = delete[n]
                add[(v.index, t)] = add.get((v.index, t), 0.0) + w
                base[(v.index, t)] = ws.get(t, 0.0)
    for (vi, t), w in add.items():
        g = vg.get(t) or vg.new(name=t)
        g.add([vi], base[(vi, t)] + w, 'REPLACE')
        merged += 1
    for n in delete:
        g = vg.get(n)
        if g is not None:
            vg.remove(g)

MN = {k: b.name for k, b in M.items()}

# ---- 6) Delete bones, reconnect in the Mixamo hierarchy, fill empty bones, rename --------------------------
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones
inv = mw.inverted()
for name in delete:                             # children of deleted bones attach to the nearest remaining ancestor
    e = eb.get(name)
    if e is None:
        continue
    p = e.parent
    while p is not None and p.name in delete:
        p = p.parent
    for k in list(e.children):
        k.use_connect = False
        k.parent = p
for name in delete:
    e = eb.get(name)
    if e is not None:
        eb.remove(e)

mapped_e = {k: eb[n] for k, n in MN.items() if eb.get(n)}
for e in eb:
    e.use_connect = False
# Create empty bones (when there is no spine, neck or shoulder)
created = []


def make(k, head, tail, parent):
    e = eb.new("__new__" + k)
    e.head, e.tail = head, tail
    e.parent = parent
    e.use_deform = True
    mapped_e[k] = e
    created.append(PREFIX + k)


hips_e, chest_e = mapped_e["Hips"], mapped_e["Spine2"]
if "Spine" not in mapped_e:
    make("Spine", hips_e.head.lerp(chest_e.head, 1 / 3), hips_e.head.lerp(chest_e.head, 2 / 3), hips_e)
if "Spine1" not in mapped_e:
    a, b = mapped_e["Spine"].head, chest_e.head
    make("Spine1", a.lerp(b, 0.5), b, mapped_e["Spine"])
if "Neck" not in mapped_e:
    make("Neck", chest_e.head.lerp(mapped_e["Head"].head, 0.6), mapped_e["Head"].head, chest_e)
for s in SIDES:
    if s + "Shoulder" not in mapped_e:
        a = mapped_e[s + "Arm"].head
        make(s + "Shoulder", chest_e.head.lerp(a, 0.35) + (a - chest_e.head) * 0.0, a, chest_e)
for k, e in mapped_e.items():                   # Mixamo parent-child hierarchy
    if k == "Hips":
        e.parent = None
    elif PARENT.get(k) in mapped_e:
        e.parent = mapped_e[PARENT[k]]
for k, e in mapped_e.items():                   # rename (in two passes to avoid clashes)
    e.name = "__tmp__" + k
for k, e in mapped_e.items():
    e.name = PREFIX + k
for e in eb:                                    # if a kept bone lost its parent, attach it to the nearest bone
    if e.parent is None and not e.name.endswith("Hips"):
        e.parent = mapped_e["Hips"]
bpy.ops.object.mode_set(mode='OBJECT')
if "Armature" not in bpy.data.objects:
    arm.name = "Armature"

print(f"[Cleanup] Deleted {len(delete)} helper bones and merged their weights into Mixamo bones ({merged} vertex weights merged)")
if keep:
    print(f"[Cleanup] Kept {len(keep)} bones that Mixamo doesn't have: {', '.join(keep[:12])}{' ...' if len(keep) > 12 else ''}")
if created:
    print(f"[Cleanup] Created empty bones with no weights, missing from the original rig: {', '.join(created)}")
missing = [k for k in PARENT if k not in mapped_e and "Hand" in k and any(f in k for f in FINGERS)]
if missing:
    print(f"[Warning] {len(missing)} finger bones were not created because the original rig doesn't have them")
print(f"[Done] Converted to a Mixamo rig ({len(arm.data.bones)} bones). Next, run SkinTokens_Fix_Bones.py, "
      f"then SkinTokens_Fix_Weights.py.")
