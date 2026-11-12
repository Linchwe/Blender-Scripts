# Export_GLB_ForGodot.py
# Blender 4.2 ~ 4.5
#
# Purpose
#  Exports a finished rigged character (armature + meshes) as a GLB (glTF 2.0) for Godot 4 in one click.
#  Godot officially recommends glTF over FBX. (FBX works from 4.3 but adds an extra conversion step)
#
# What it does
#  1) Creates an Export folder next to the .blend file and saves "FileName_Godot.glb". (Overwrites a file with the same name)
#     Textures are packed inside the GLB file.
#  2) Exports every armature and mesh in the scene. Cameras and lights are not included.
#  3) Only while exporting, detaches the armatures' actions and poses so they export in the rest pose, then restores them.
#     No animation is exported.
#  4) Export options
#       Format = glTF Binary (.glb), +Y Up on, UV / Normals / Tangents on
#       Skinning on, 4 bone influences (Godot compatible), Deformation Bones Only off, Use Rest Position Armature on
#       Shape Keys on, Materials = Export, Images = Automatic, Draco compression off (Godot can't read it)
#       Animations off
#  5) The material's Roughness and Metallic are automatically combined into one texture per the glTF spec,
#     and Opacity connected to Alpha is included as is. Godot uses this material directly.
#
# Notes
#  - Save the .blend file first.
#  - Meshes hidden in the scene (high-poly etc.) are exported too. Move them to another scene or delete them before running.
#  - After importing into Godot, pick Skeleton3D in Advanced Import Settings and set BoneMap to
#    SkeletonProfileHumanoid to retarget animations from other characters.
#    AccuRIG's CC_Base names only partly auto-map, so fill in the empty slots by hand.
#    For A-pose rigs, turning on Fix Silhouette improves the retarget result.
#
# Usage
#  1) Scripting tab > New text > Paste > Run Script
#  2) Progress is shown in Window > Toggle System Console.

import bpy

# Settings
OUT_FOLDER = "Export"   # Name of the folder to create next to the .blend
SUFFIX = "Godot"
EXT = ".glb"
OPERATOR = bpy.ops.export_scene.gltf


def make_settings(path):
    return dict(
        filepath=path, check_existing=False, export_format='GLB',
        use_selection=False, use_visible=False, use_renderable=False, use_active_collection=False,
        export_cameras=False, export_lights=False, export_extras=False,
        export_yup=True, export_apply=False,
        export_texcoords=True, export_normals=True, export_tangents=True,
        export_materials='EXPORT', export_image_format='AUTO',
        export_skins=True, export_all_influences=False, export_influence_nb=4,
        export_def_bones=False, export_leaf_bone=False, export_rest_position_armature=True,
        export_morph=True, export_animations=False,
        export_draco_mesh_compression_enable=False,
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
