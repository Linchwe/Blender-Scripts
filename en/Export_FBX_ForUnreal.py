# Export_FBX_ForUnreal.py
# Blender 4.2 ~ 4.5
#
# Purpose
#  Exports a finished rigged character (armature + meshes) as an FBX for Unreal Engine 5 in one click.
#  No need to select objects or set each option in the Export window.
#
# What it does
#  1) Creates an Export folder next to the .blend file and saves "FileName_Unreal.fbx". (Overwrites a file with the same name)
#  2) Exports every armature and mesh in the scene. Cameras, lights and empties are not included.
#  3) Only while exporting, detaches the armatures' actions and poses so they export in the rest pose (Edit Mode pose),
#     then restores actions and poses to their state before running. No animation is exported.
#  4) Export options (※ = differs from the Unity version)
#       Apply Scalings = FBX All, Forward = -Z, Up = Y, Apply Unit on, Use Space Transform on, Apply Transform off
#       Smoothing = Face, Apply Modifiers on, ※ Triangulate on (matches Blender's and Unreal's triangulation to avoid normal map seams)
#       Tangent Space off, Primary/Secondary Bone Axis = Y/X, Armature Node Type = Null
#       Only Deform Bones off, Add Leaf Bones off, Bake Animation off, Path Mode = Copy
#
# Notes
#  - Save the .blend file first.
#  - Meshes hidden in the scene (high-poly etc.) are exported too. Move them to another scene or delete them before running.
#  - Keep the armature object named "Armature". Unreal drops the node with this name and uses the first bone under it
#    (RL_BoneRoot for AccuRIG rigs) as the root bone. If you rename it, you get an extra root bone.
#  - Check these after importing into Unreal.
#      The character height (the UE mannequin is about 180cm). If wrong, adjust Uniform Scale in the import options
#      Normals: use Import Normals (computing them discards the normals made in Blender)
#  - Unreal materials can take Roughness, Metallic and AO separately, or combined into one ORM texture.
#
# Usage
#  1) Scripting tab > New text > Paste > Run Script
#  2) Progress is shown in Window > Toggle System Console.

import bpy

# Settings
OUT_FOLDER = "Export"   # Name of the folder to create next to the .blend
SUFFIX = "Unreal"
EXT = ".fbx"
OPERATOR = bpy.ops.export_scene.fbx


def make_settings(path):
    return dict(
        filepath=path, check_existing=False,
        use_selection=False, use_visible=False, use_active_collection=False,
        object_types={'ARMATURE', 'MESH'}, use_custom_props=False,
        global_scale=1.0, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
        apply_unit_scale=True, use_space_transform=True, bake_space_transform=False,
        mesh_smooth_type='FACE', use_mesh_modifiers=True, use_triangles=True, use_tspace=False,
        primary_bone_axis='Y', secondary_bone_axis='X', armature_nodetype='NULL',
        use_armature_deform_only=False, add_leaf_bones=False,
        bake_anim=False, path_mode='COPY', embed_textures=False, batch_mode='OFF',
    )

import os

# Checks
if not bpy.data.filepath:
    raise RuntimeError("Save the .blend file first. The Export folder is created where it is saved.")
arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not meshes:
    raise RuntimeError("There are no meshes to export.")

out_dir = os.path.join(os.path.dirname(bpy.data.filepath), OUT_FOLDER)
os.makedirs(out_dir, exist_ok=True)
base = bpy.path.display_name_from_filepath(bpy.data.filepath)
path = os.path.join(out_dir, f"{base}_{SUFFIX}{EXT}")

# Switch to Object Mode
if bpy.context.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')


def rest_pose_on():
    # Remember each armature's action, NLA and pose values, and return it to its rest pose (Edit Mode pose)
    saved = []
    for a in arms:
        ad = a.animation_data
        rec = {"obj": a, "pose": {}}
        if ad:
            rec["action"] = ad.action
            rec["slot"] = getattr(ad, "action_slot", None)
            rec["use_nla"] = ad.use_nla
            ad.action = None
            ad.use_nla = False
        for pb in a.pose.bones:
            rec["pose"][pb.name] = (pb.location.copy(), pb.rotation_mode, pb.rotation_quaternion.copy(),
                                    pb.rotation_euler.copy(), pb.rotation_axis_angle[:], pb.scale.copy())
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.rotation_axis_angle = (0, 0, 1, 0)
            pb.scale = (1, 1, 1)
        saved.append(rec)
    bpy.context.view_layer.update()
    return saved


def rest_pose_off(saved):
    # Put the remembered action, NLA and pose values back exactly as they were
    for rec in saved:
        a = rec["obj"]
        for pb in a.pose.bones:
            v = rec["pose"].get(pb.name)
            if v is None:
                continue
            pb.location, pb.rotation_mode, pb.rotation_quaternion, pb.rotation_euler, aa, pb.scale = v
            pb.rotation_axis_angle = aa
        ad = a.animation_data
        if ad and "action" in rec:
            ad.action = rec["action"]
            if rec.get("slot") is not None and hasattr(ad, "action_slot"):
                try:
                    ad.action_slot = rec["slot"]
                except Exception:
                    pass
            ad.use_nla = rec["use_nla"]
    bpy.context.view_layer.update()


def run(op, settings):
    # Leave out options this Blender version does not have
    valid = {p.identifier for p in op.get_rna_type().properties}
    kw = {k: v for k, v in settings.items() if k in valid}
    skipped = [k for k in settings if k not in valid]
    if skipped:
        print(f"Skipped options not available in this Blender version: {', '.join(skipped)}")
    return op(**kw)


print("=" * 60)
print(f"Exporting for {SUFFIX}")
print(f"Armatures: {', '.join(o.name for o in arms) or 'none'}")
print(f"Meshes: {', '.join(o.name for o in meshes)}")
saved = rest_pose_on()
try:
    run(OPERATOR, make_settings(path))
finally:
    rest_pose_off(saved)
print(f"Saved: {path}")
print("Actions and poses were restored to their state before running.")
print("=" * 60)
