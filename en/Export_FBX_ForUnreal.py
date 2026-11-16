# Export_FBX_ForUnreal.py
# Blender 4.2 ~ 4.5
#
# Purpose
#  Exports a finished rigged character (armature + meshes) as an FBX and textures for Unreal Engine 5 in one click.
#  No need to select objects or set each option in the Export window.
#
# What it does
#  1) Creates an Export folder next to the .blend file and saves "FileName_Unreal.fbx". (Overwrites a file with the same name)
#  2) Exports every armature and mesh in the scene. Cameras, lights and empties are not included.
#  3) Only while exporting, detaches the armatures' actions and poses so they export in the rest pose (Edit Mode pose),
#     then restores actions and poses to their state before running. No animation is exported.
#  4) Export options (differences from the Unity preset marked with *)
#       Apply Scalings = FBX All, Forward = -Z, Up = Y, Apply Unit on, Use Space Transform on, Apply Transform off
#       Smoothing = Face, Apply Modifiers on, * Triangulate on (same triangulation in Blender and Unreal, avoids normal map seams)
#       Tangent Space off, Primary/Secondary Bone Axis = Y/X, Armature Node Type = Null
#       Only Deform Bones off, Add Leaf Bones off, Bake Animation off
#       Path Mode = Strip (textures are not embedded or copied; the TGAs from 5) are used instead)
#  5) For each material, packs textures for Unreal materials and saves them as TGA in Export\FileName_Unreal_Textures.
#       MaterialName_BaseColor.tga : RGB color, A opacity (saved without A when nothing is transparent)
#       MaterialName_ORM.tga       : R AO, G roughness, B metallic
#       MaterialName_Normal.tga    : normal. Green channel flipped to DirectX (Unreal uses DirectX)
#     Reads the images connected to the Principled BSDF (also through Normal Map and Separate Color nodes) and an
#     unconnected AO image node (with AO in its name). Materials baked with Bake_PBR_HighToLow.py are read as they are.
#     Maps without an image are filled with the socket value; a missing AO is filled with white (no occlusion).
#     Images of different sizes are scaled to the largest one. The Blender materials and source images are not changed.
#
# Notes
#  - Save the .blend file first.
#  - Meshes hidden in the scene (high-poly etc.) are exported too. Move them to another scene or delete them before running.
#  - Keep the armature object name "Armature". Unreal drops a node with this name and uses the first bone under it
#    (RL_BoneRoot for AccuRIG rigs) as the root bone. With another name, an extra root bone is added.
#  - If a Math, Brightness/Contrast or other adjustment node sits in front of the Principled BSDF, that input cannot be
#    read and is filled with a value (shown as [warning] in the console). In that case, bake with Bake_PBR_HighToLow.py first.
#  - Check these after importing into Unreal.
#      Character height (the UE mannequin is about 180 cm). If wrong, adjust Uniform Scale in the import options
#      Normals via Import Normals (computing them drops the normals made in Blender)
#      Textures : ORM with sRGB off and Compression Settings = Masks. Normal is already DirectX; do not turn on Flip Green Channel.
#      Material : connect R of ORM to Ambient Occlusion, G to Roughness, B to Metallic.
#                 If anything is transparent, set Blend Mode = Masked and connect A of BaseColor to Opacity Mask
#
# Usage
#  1) Scripting tab > New text > Paste > Run Script
#  2) Progress is shown in Window > Toggle System Console.

import bpy
import os

# Settings
OUT_FOLDER = "Export"   # folder created next to the .blend
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
        bake_anim=False, path_mode='STRIP', embed_textures=False, batch_mode='OFF',
    )

# Checks
if not bpy.data.filepath:
    raise RuntimeError("Save the .blend file first. The Export folder is created next to it.")
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

# ---------------------------------------------------------------------------------------------
# Texture packing (combine channels for the engine)
# ---------------------------------------------------------------------------------------------
import re
import numpy as np

TEX_DIR = f"{base}_{SUFFIX}_Textures"


def srgb(c):
    # Linear to sRGB
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def find_tex(sock):
    # Finds the image and channel connected to a socket. Returns (image, channel) / None (not linked) / "complex" (unreadable nodes)
    if not sock.is_linked:
        return None
    link = sock.links[0]
    node, out = link.from_node, link.from_socket.name
    for _ in range(4):
        if node.type == 'TEX_IMAGE':
            if node.image is None:
                return None
            return (node.image, 'A' if out == 'Alpha' else 'RGB')
        if node.type == 'NORMAL_MAP':
            nxt = node.inputs['Color']
            ch = None
        elif node.type in ('SEPARATE_COLOR', 'SEPRGB') and getattr(node, "mode", 'RGB') == 'RGB':
            nxt = node.inputs[0]
            ch = {'Red': 'R', 'Green': 'G', 'Blue': 'B', 'R': 'R', 'G': 'G', 'B': 'B'}.get(out)
        else:
            return "complex"
        if not nxt.is_linked:
            return None
        link = nxt.links[0]
        node, out = link.from_node, link.from_socket.name
        if ch and node.type == 'TEX_IMAGE' and node.image is not None:
            return (node.image, ch)
    return "complex"


AO_NAME = re.compile(r'(^|[^A-Za-z])AO([^A-Za-z]|$)', re.IGNORECASE)


def find_ao(mat):
    # AO image node: the one linked to Occlusion of glTF Material Output, otherwise an image node with AO in its name
    nodes = mat.node_tree.nodes
    for n in nodes:
        if n.type == 'GROUP' and n.node_tree and n.node_tree.name in ("glTF Material Output", "glTF Settings"):
            occ = n.inputs.get("Occlusion")
            if occ is not None:
                r = find_tex(occ)
                if isinstance(r, tuple):
                    return r
    for n in nodes:
        if n.type == 'TEX_IMAGE' and n.image is not None:
            if AO_NAME.search(n.image.name) or AO_NAME.search(n.label) or AO_NAME.search(n.name):
                return (n.image, 'RGB')
    return None


def read(img, size, channel, rgb=False, to_srgb=False):
    # Reads an image at size and returns one channel (H,W) or RGB (H,W,3). Kept in Blender's bottom-up order
    w, h = size
    src = img
    tmp = None
    if tuple(img.size) != (w, h):
        tmp = img.copy()
        tmp.scale(w, h)
        src = tmp
    try:
        n = src.size[0] * src.size[1] * 4
        if n == 0:
            return None
        a = np.empty(n, np.float32)
        src.pixels.foreach_get(a)
        a = a.reshape(h, w, 4)
        if to_srgb and src.is_float:
            a[..., :3] = srgb(a[..., :3])
    except Exception:
        return None
    finally:
        if tmp is not None:
            bpy.data.images.remove(tmp)
    if channel == 'RGB':
        return a[..., :3].copy() if rgb else a[..., 0].copy()
    return a[..., 'RGBA'.index(channel)].copy()


def gather(mat):
    # Collects Base Color, Alpha, Roughness, Metallic, Normal and AO from a material
    if not mat or not mat.use_nodes:
        return None
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return None
    src = {}
    warn = []
    for key, sock in (("color", "Base Color"), ("alpha", "Alpha"), ("rough", "Roughness"),
                      ("metal", "Metallic"), ("normal", "Normal")):
        r = find_tex(bsdf.inputs[sock])
        if r == "complex":
            warn.append(sock)
            r = None
        src[key] = r
    src["ao"] = find_ao(mat)
    imgs = [v[0] for v in src.values() if isinstance(v, tuple)]
    sizes = [tuple(i.size) for i in imgs if i.size[0] > 0]
    size = max(sizes, key=lambda s: s[0] * s[1]) if sizes else (256, 256)
    w, h = size

    def plane(key, default):
        v = src.get(key)
        if isinstance(v, tuple):
            p = read(v[0], size, v[1])
            if p is not None:
                return p
            warn.append(v[0].name)
        return np.full((h, w), default, np.float32)

    col = None
    if isinstance(src["color"], tuple):
        col = read(src["color"][0], size, src["color"][1], rgb=True, to_srgb=True)
        if col is not None and col.ndim == 2:
            col = np.repeat(col[..., None], 3, axis=2)
    if col is None:
        c = np.array(bsdf.inputs["Base Color"].default_value[:3], np.float32)
        col = np.broadcast_to(srgb(c), (h, w, 3)).copy()
    nrm = None
    if isinstance(src["normal"], tuple):
        nrm = read(src["normal"][0], size, 'RGB', rgb=True) if src["normal"][1] == 'RGB' else None
    return {
        "size": size, "color": col,
        "alpha": plane("alpha", bsdf.inputs["Alpha"].default_value),
        "rough": plane("rough", bsdf.inputs["Roughness"].default_value),
        "metal": plane("metal", bsdf.inputs["Metallic"].default_value),
        "ao": plane("ao", 1.0),
        "normal": nrm, "warn": warn,
        "found": [k for k, v in src.items() if isinstance(v, tuple)],
    }


def save_tga(path, chans, alpha=None):
    # Saves 3 or 4 (H,W) channels as TGA. 24-bit RGB when alpha is None
    h, w = chans[0].shape
    rgba = np.ones((h, w, 4), np.float32)
    for i, c in enumerate(chans[:3]):
        rgba[..., i] = np.clip(c, 0, 1)
    if alpha is not None:
        rgba[..., 3] = np.clip(alpha, 0, 1)
    img = bpy.data.images.new("_PackTemp", w, h, alpha=alpha is not None)
    try:
        img.colorspace_settings.name = 'Non-Color'
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = path
        img.file_format = 'TARGA'
        img.save()
    finally:
        bpy.data.images.remove(img)


def safe(name):
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "Material"


def export_textures():
    folder = os.path.join(out_dir, TEX_DIR)
    os.makedirs(folder, exist_ok=True)
    mats = []
    for o in meshes:
        for slot in o.material_slots:
            if slot.material and slot.material not in mats:
                mats.append(slot.material)
    done = 0
    for m in mats:
        d = gather(m)
        if d is None:
            print(f"  [skipped] {m.name} : no Principled BSDF.")
            continue
        has_alpha = bool((d["alpha"] < 0.999).any())
        files = pack(os.path.join(folder, safe(m.name)), d, has_alpha)
        done += 1
        print(f"  {m.name} ({d['size'][0]}x{d['size'][1]}) : {', '.join(files)}")
        labels = {"color": "Base Color", "rough": "Roughness", "metal": "Metallic", "normal": "Normal", "ao": "AO"}
        missing = [labels[k] for k in labels if k not in d["found"]]
        if missing:
            print(f"    maps filled with a value (no image): {', '.join(missing)}")
        if d["warn"]:
            print(f"    [warning] inputs not read because of complex nodes: {', '.join(d['warn'])} (filled with a value)")
    print(f"Textures saved: {folder} ({done} materials)")


def pack(stem, d, has_alpha):
    c = d["color"]
    save_tga(stem + "_BaseColor.tga", [c[..., 0], c[..., 1], c[..., 2]], d["alpha"] if has_alpha else None)
    save_tga(stem + "_ORM.tga", [d["ao"], d["rough"], d["metal"]])
    out = ["BaseColor", "ORM"]
    if d["normal"] is not None:
        n = d["normal"]
        save_tga(stem + "_Normal.tga", [n[..., 0], 1.0 - n[..., 1], n[..., 2]])   # DirectX: flip green
        out.append("Normal (DirectX)")
    return out


def rest_pose_on():
    # Remember each armature's action, NLA and pose values, then go to the rest pose (Edit Mode pose)
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
    # Restore the remembered action, NLA and pose values
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
    # Run without options this Blender version doesn't have
    valid = {p.identifier for p in op.get_rna_type().properties}
    kw = {k: v for k, v in settings.items() if k in valid}
    skipped = [k for k in settings if k not in valid]
    if skipped:
        print(f"Options skipped (not in this Blender version): {', '.join(skipped)}")
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
export_textures()
print("=" * 60)
