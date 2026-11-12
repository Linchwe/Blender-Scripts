# Symmetry_SkinWeight.py
# Blender 4.2 ~ 4.5
# Copies the skin weights of the character's Left side to the Right side, mirrored on the X axis.
# For tuning weights on the left side only and then matching the right side exactly.
# Works on your own rigs as well as SkinTokens results. Left/right pairs are found by bone naming convention.
#      mixamorig:LeftArm     ↔ mixamorig:RightArm      (Mixamo, SkinTokens Mixamo convention)
#      CC_Base_L_Upperarm    ↔ CC_Base_R_Upperarm      (AccuRIG / Character Creator)
#      L_Arm                 ↔ R_Arm
#      upper_arm.L / Arm_L   ↔ upper_arm.R / Arm_R     (Blender/Rigify convention, numbers like .L.001 also work)
#      upperarm_l / arm.l    ↔ upperarm_r / arm.r      (lowercase l/r convention)
#  ※ For Rigify, weights live in the generated rig's DEF- bone groups, so run it on the mesh skinned to the generated rig.
#
#  1) For each right-side (X-) vertex, finds the closest left-side (X+) vertex to its X-flipped position and pairs them.
#     (If the distance is larger than the tolerance, it is treated as having no mirror point and is not paired)
#  2) Each paired right-side vertex gets all its bone weights replaced with its left partner's weights.
#       Left bone weights   -> to the matching right bone group (e.g. LeftArm -> RightArm, upper_arm.L -> upper_arm.R)
#       Right bone weights  -> to the left bone group (when the left side had a little weight from the other side)
#       Center bone weights (spine, neck, head and other bones with no side marker) -> same group as is
#     So any balancing you did on the left, e.g. between the arm and chest bones, is copied to the right too.
#  3) Right-side vertices with no pair (asymmetric clothing, holsters, etc.) keep their original weights.
#
# Left/right (viewing the character from the front)
#  - X > 0 = screen right = the character's Left   -> copy source
#  - X < 0 = screen left  = the character's Right  -> copy target
#
# Notes
#  - Coordinates are in mesh local space. The object origin must be at the body center (X=0) for pairs to match.
#  - Only bone weight groups (groups named after bones in the armature) are changed. Other vertex groups (masks etc.) are not touched.
#  - An Armature modifier is needed to know the bone groups. Without one, only mixamorig: groups are handled.
#  - Names whose side marker doesn't follow the rules above are treated as center bones and copied to the same group, which breaks the right side.
#    If the console shows 0 left/right group pairs, the naming convention doesn't match, so undo with Ctrl+Z.
#  - Center-line vertices at exactly X=0 are not touched.
#  - Only the selected (active) mesh is processed. If the body, clothes and hair are separate meshes, run it for each mesh.
#  - Parts of the mesh that aren't symmetric (asymmetric clothing, holsters, etc.) have no pair and keep their original weights. Check those by hand.
#
# Usage: select the skinned mesh in Object Mode or Weight Paint Mode > Scripting tab > New text > Paste
#        > Check the settings > Run Script
# Save with Ctrl+S before running. You can undo with Ctrl+Z.

import bpy
import re
from mathutils import kdtree

# Settings
TOLERANCE = 0      # Tolerance when finding mirror points (mesh units). 0 = automatic, 0.5% of the mesh size (height)
                   #   About 0.009 for a 1.8m character in meters, about 0.9 for a mesh in cm (Mixamo FBX, or a mesh after SkinTokens_Fix_Bones)
                   #   Raise it if many vertices find no pair, lower it if vertices pair with the wrong ones

# Naming rules: (find left, left->right replace, find right, right->left replace) - tried from top to bottom (same as Symmetry_Bones)
NAME_RULES = [
    (r'Left',      'Right',  r'Right',     'Left'),    # mixamorig:LeftArm
    (r'_L_',       '_R_',    r'_R_',       '_L_'),     # CC_Base_L_Upperarm
    (r'^L_',       'R_',     r'^R_',       'L_'),      # L_Arm
    (r'([._])L((?:\.\d+)?)$',  r'\1R\2',   r'([._])R((?:\.\d+)?)$',  r'\1L\2'),   # Arm.L / Arm_L / DEF-upper_arm.L.001
    (r'([._])l((?:\.\d+)?)$',  r'\1r\2',   r'([._])r((?:\.\d+)?)$',  r'\1l\2'),   # upperarm_l
]

obj = bpy.context.object

# Make sure a mesh is selected
if obj is None or obj.type != 'MESH':
    raise RuntimeError("Please select a mesh.")

# Vertex group edits apply immediately only in Object Mode
mode = obj.mode
if mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')

verts = obj.data.vertices
groups = obj.vertex_groups

# 1) Pick the bone weight groups: groups named like the Armature modifier's bones (mixamorig: groups if there is no armature)
arms = [m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object is not None]
if arms:
    bone_names = {b.name for a in arms for b in a.data.bones}
    is_bone = lambda n: n in bone_names
else:
    is_bone = lambda n: n.startswith("mixamorig:")


def other_side(name):
    # Left group name -> right group name (and back); center bones with no side marker stay as is
    for left_pat, to_right, right_pat, to_left in NAME_RULES:
        if re.search(left_pat, name):
            return re.sub(left_pat, to_right, name, count=1)
        if re.search(right_pat, name):
            return re.sub(right_pat, to_left, name, count=1)
    return name


# 2) Tolerance
if TOLERANCE > 0:
    tol = TOLERANCE
else:
    size = max(max(v.co[k] for v in verts) - min(v.co[k] for v in verts) for k in range(3))
    tol = size * 0.005

# 3) For each right-side (X-) vertex, find the closest left-side (X+) vertex to its mirrored position
#  KDTree: a structure for quickly finding "the vertex closest to this position"
left_verts = [v for v in verts if v.co.x > 0]
if not left_verts:
    raise RuntimeError("There are no vertices on the X > 0 side. Check that the mesh origin is at the body center.")
kd = kdtree.KDTree(len(left_verts))
for v in left_verts:
    kd.insert(v.co, v.index)
kd.balance()

pairs = {}      # {right vertex index: left vertex index}
right_total = 0
for v in verts:
    if v.co.x >= 0:
        continue
    right_total += 1
    co, li, dist = kd.find((-v.co.x, v.co.y, v.co.z))
    if li is not None and dist <= tol:
        pairs[v.index] = li

# 4) Replace the bone weights of paired right-side vertices with their left partner's weights
# Read each vertex's weights first (so the source doesn't change while we write)
names = {g.index: g.name for g in groups}
bone_idx = [g.index for g in groups if is_bone(g.name)]
left_w = {}
for li in set(pairs.values()):
    left_w[li] = [(names[g.group], g.weight) for g in verts[li].groups
                  if g.weight > 0 and is_bone(names[g.group])]

# Clear the existing bone weights of paired right-side vertices (unpaired vertices are left alone)
targets = list(pairs.keys())
for gi in bone_idx:
    groups[gi].remove(targets)

created = []
for ri, li in pairs.items():
    for name, w in left_w[li]:
        dst = other_side(name)
        g = groups.get(dst)
        if g is None:
            g = groups.new(name=dst)
            created.append(dst)
        g.add([ri], w, 'REPLACE')

if mode != 'OBJECT':
    bpy.ops.object.mode_set(mode=mode)

side_pairs = sum(1 for gi in bone_idx if other_side(names[gi]) != names[gi] and groups.get(other_side(names[gi])))

print("=" * 60)
print("LEFT → RIGHT WEIGHT MIRROR")
print("=" * 60)
print(f"Tolerance: {tol:.4f}")
print(f"Left/right bone group pairs: {side_pairs // 2}")
if side_pairs == 0:
    print("Could not find any left/right group pairs. Check the bone naming convention and undo with Ctrl+Z.")
print(f"Replaced {len(pairs)} of {right_total} right-side vertices with left-side weights.")
if right_total - len(pairs):
    print(f"{right_total - len(pairs)} vertices with no pair kept their original weights. (Normal for asymmetric parts)")
for n in created:
    print(f"New groups created: {n}")
print("=" * 60)
