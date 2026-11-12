# Symmetry_Bones.py
# Blender 4.2 ~ 4.5
# Copies the armature's Left bone positions and roll to the Right bones, mirrored on the X axis.
# For hand-tuning only the left bones and then matching the right side exactly.
# (For rigs handled in Blender: SkinTokens, AccuRIG, Mixamo, Rigify metarig, etc.)
#
#  - Finds Left / Right bone pairs automatically using one of the naming rules below.
#      mixamorig:LeftArm     ↔ mixamorig:RightArm      (Mixamo, SkinTokens Mixamo convention)
#      CC_Base_L_Upperarm    ↔ CC_Base_R_Upperarm      (AccuRIG / Character Creator)
#      upperarm_l / arm.l    ↔ upperarm_r / arm.r      (lowercase l/r convention, for rigs made in Blender)
#      upper_arm.L / Arm_L   ↔ upper_arm.R / Arm_R     (Blender/Rigify metarig convention, numbers like .L.001 also work)
#
#  ※ For Rigify, run this on the metarig (not the generated rig), then Generate again.
#  ※ Skeletons imported from Unreal (Mannequin, MetaHuman) are recognized by name, but don't fix them with this script.
#     Their left/right bone axis conventions differ so the roll can get twisted, and MetaHuman face/corrective rigs are tied to bone positions.
#  - Moves the right bone's head (start) and tail (end) to the left bone's position with only X flipped.
#  - Roll (how much the bone is twisted around its own axis) is copied with its sign flipped. (Same as Blender's Symmetrize)
#    -> Rotating both arms by the same value moves them in the same mirrored direction
#  - Bones without a pair (spine, head and other center bones) are not touched.
#
# Notes
#  - Coordinates are in armature object (local) space. The armature origin must be at the body center (X=0) for the mirror to match.
#  - Moving bones on a skinned character changes how the mesh deforms by the same amount. If you moved them a lot,
#    try a few poses and check the weights.
#
# Usage: select the armature > Scripting tab > New text > Paste > Check the settings > Run Script
#        (Switches to Edit Mode automatically, then returns to Object Mode when done)
# Save with Ctrl+S before running. You can undo with Ctrl+Z.

import bpy
import re

# ---------------- Settings ----------------
SOURCE_SIDE = 'LEFT'   # 'LEFT' : copy from the character's left (Left/L) bones to the right
                       # 'RIGHT': copy from the character's right (Right/R) bones to the left
COPY_ROLL = True       # Also mirror the roll (False copies position only)
# --------------------------------------

# Naming rules: (find left, left->right replace, find right, right->left replace) - tried from top to bottom
NAME_RULES = [
    (r'Left',      'Right',  r'Right',     'Left'),    # mixamorig:LeftArm
    (r'_L_',       '_R_',    r'_R_',       '_L_'),     # CC_Base_L_Upperarm
    (r'^L_',       'R_',     r'^R_',       'L_'),      # L_Arm
    (r'([._])L((?:\.\d+)?)$',  r'\1R\2',   r'([._])R((?:\.\d+)?)$',  r'\1L\2'),   # Arm.L / Arm_L / DEF-upper_arm.L.001
    (r'([._])l((?:\.\d+)?)$',  r'\1r\2',   r'([._])r((?:\.\d+)?)$',  r'\1l\2'),   # upperarm_l
]


def to_other_side(name, from_left):
    """If the name is a source-side bone, return the opposite side's name, otherwise None"""
    for left_pat, to_right, right_pat, to_left in NAME_RULES:
        if from_left and re.search(left_pat, name):
            return re.sub(left_pat, to_right, name, count=1)
        if not from_left and re.search(right_pat, name):
            return re.sub(right_pat, to_left, name, count=1)
    return None


arm = bpy.context.object

# Make sure an armature is selected
if arm is None or arm.type != 'ARMATURE':
    raise RuntimeError("Run this with an Armature selected.")

# Bone position/roll can only be changed in Edit Mode, so switch to Edit Mode
if arm.mode != 'EDIT':
    bpy.ops.object.mode_set(mode='EDIT')

bones = arm.data.edit_bones
from_left = (SOURCE_SIDE == 'LEFT')

count = 0      # number of bones mirrored
skipped = []   # bones with no pair found

for src in bones:
    dst_name = to_other_side(src.name, from_left)
    if dst_name is None or dst_name == src.name:
        continue   # not a source-side bone (center bone or opposite-side bone)

    dst = bones.get(dst_name)
    if dst is None:
        skipped.append(src.name)
        continue

    # Flip only the sign of X, copy Y/Z as is
    dst.head = (-src.head.x, src.head.y, src.head.z)
    dst.tail = (-src.tail.x, src.tail.y, src.tail.z)

    # Copy the roll with its sign flipped (mirror)
    if COPY_ROLL:
        dst.roll = -src.roll

    count += 1
    print(f"[MIRROR] {src.name} -> {dst.name}")

for name in skipped:
    print(f"[SKIP] No matching bone: {name}")

# Returning to Object Mode commits the changed bone positions
bpy.ops.object.mode_set(mode='OBJECT')

side = "Left → Right" if from_left else "Right → Left"
print(f"Done: mirrored {count} bone(s) to {side}. (Roll copy: {'on' if COPY_ROLL else 'off'})")
if count == 0:
    print("Could not find any bone pairs. Please check the bone naming convention.")
