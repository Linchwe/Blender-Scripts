# Bake_PBR_HighToLow.py
# Blender 4.2 ~ 4.5
#
# Purpose
#  Bakes the high-poly's PBR textures (Base Color, Roughness, Metallic, Normal) plus AO and Opacity onto the low-poly in one run.
#  Select and press Run Script once: baking, PNG saving and connecting them to the low-poly material are all done.
#
# What it does
#  0) Sets up the bake settings automatically. (Render engine, device, sample count and AO distance are restored afterwards)
#       Render Engine = Cycles, Device = GPU Compute, Max Samples = 16 (128 for AO only),
#       Selected to Active on, Extrusion 0.02, Max Ray Distance 0, Margin 16, Clear Image on
#     If Edit > Preferences > System > Cycles Render Devices is None, it looks for OptiX -> CUDA -> HIP -> oneAPI
#     in that order and turns it on. (If one is already chosen, it is kept) Without a GPU it bakes on the CPU.
#  1) Creates 6 blank 4096 x 4096 images in the low-poly material. (Base Color is sRGB, the rest Non-Color)
#  2) Bakes each map in turn by rewiring all of the high-poly's materials for that map.
#       Base Color / Roughness / Metallic : connects the value going into Principled BSDF to Emission and bakes as Emit
#                                           (values passing through adjustment nodes such as Brightness/Contrast are baked as is)
#       Normal                            : bakes the Principled BSDF as is to Normal (Tangent, OpenGL)
#       AO                                : bakes directly with Cycles from the high-poly shape (the AO in a Pixal3D ORM is not used)
#                                           Only while baking, unselected objects (floor, props, other characters, etc.)
#                                           are briefly excluded from rendering so their shadows don't bleed in, then turned back on
#       Opacity                           : bakes the Principled BSDF Alpha as Emit, with Margin 0.
#                                           Where the high-poly has holes (torn cloth, belt holes), rays miss and those spots are black,
#                                           everything else is white. With no holes it is all white.
#                                           For this map only, the ray distance is limited to EXTRUSION x 2 so rays don't hit the body behind the holes.
#                                           After baking, it pads MARGIN (16) pixels outside the UV borders itself.
#                                             Black border pixels spread black, white ones spread white,
#                                             and where black and white meet, black wins.
#                                           Holes inside the UVs get no padding and stay black.
#                                           The UV area is found by baking the low-poly alone once more in white.
#                                           For that, the high-poly is briefly deselected and then selected again.
#  3) When all bakes are done, restores the high-poly materials. (Also restored if an error happens midway)
#  4) Creates a "Baked Textures" folder next to the .blend file and saves PNGs there.
#       File names : LowPolyName_BaseColor.png / _Roughness.png / _Metallic.png / _Normal.png / _AO.png / _Opacity.png
#       Files with the same name are overwritten.
#  5) Connects them to the low-poly material's Principled BSDF. (Normal through a Normal Map node, Opacity to Alpha)
#     Principled BSDF has no AO input, so the AO image node is added but not connected. Plug it into the AO slot in your engine.
#
# Notes
#  - Save the .blend file first. (The Baked Textures folder is created where it is saved)
#  - The high-poly and low-poly must overlap in the same place, and the low-poly must have unwrapped UVs.
#  - High-poly materials without a Principled BSDF are skipped.
#  - Blender looks frozen while baking. It is six 4096 maps and AO uses many samples, so wait until it finishes.
#    Progress is shown in Window > Toggle System Console.
#  - If the result has holes or black smudges, raise EXTRUSION below to 0.02 ~ 0.05;
#    if colors from other parts bleed in, lower it and run again.
#  - If AO is dark over too wide an area, lower AO_DISTANCE; if wrinkles and gaps don't show, raise it. If it is blotchy, raise AO_SAMPLES.
#  - The normal map is OpenGL style. Unity and Godot use it as is; in Unreal, turn on Flip Green Channel when importing.
#
# Usage
#  1) Select the high-poly and the low-poly. Select the low-poly last so it is active.
#       In the 3D viewport : click the high-poly -> Shift+click the low-poly
#       In the Outliner    : click the high-poly name -> Ctrl+click the low-poly name
#                           (In the Outliner, Shift+click selects the whole range in between, so be careful)
#     The active object (low-poly) has a bright orange outline, the high-poly a dark orange one.
#     If they overlap and are hard to click in the viewport, the Outliner is easier.
#  2) Scripting tab > New text > Paste > Run Script
#  3) When it finishes, save the .blend (Ctrl+S). The textures are in the Baked Textures folder.

import bpy
import os
import time
import numpy as np

# Settings
SIZE      = 4096    # Texture size (pixels)
EXTRUSION = 0.02    # Ray casting distance (m). Raise if holes appear, lower if colors from other parts bleed in
MARGIN    = 16      # Width of color spread outside the UV borders (pixels). Prevents seams
SAMPLES   = 16      # Bake samples. 16 is enough for Base Color, Roughness, Metallic, Normal, Opacity
AO_SAMPLES  = 128   # AO samples. AO is noisy, so use more
AO_DISTANCE = 0.1   # AO distance (m). Other faces within this distance darken it. 0.05 ~ 0.3 for a human-sized character

MAPS = [  # (map name, Principled input, bake type, sRGB or not)
    ("BaseColor", "Base Color", 'EMIT',   True),
    ("Roughness", "Roughness",  'EMIT',   False),
    ("Metallic",  "Metallic",   'EMIT',   False),
    ("Normal",    "Normal",     'NORMAL', False),
    ("AO",        None,         'AO',     False),
    ("Opacity",   "Alpha",      'EMIT',   False),
]
EMIT_NAME = "BakeEmission"

# Check the selection
if not bpy.data.filepath:
    raise RuntimeError("Save the .blend file first. The Baked Textures folder is created where it is saved.")
low = bpy.context.view_layer.objects.active
highs = [o for o in bpy.context.selected_objects if o != low and o.type == 'MESH']
if low is None or low.type != 'MESH' or not highs:
    raise RuntimeError("Select the high-poly first, then add the low-poly to the selection last "
                       "(Shift+click in the viewport, Ctrl+click in the Outliner).")
if not low.data.uv_layers:
    raise RuntimeError(f"The low-poly '{low.name}' has no UVs. Unwrap the UVs first.")

out_dir = os.path.join(os.path.dirname(bpy.data.filepath), "Baked Textures")
os.makedirs(out_dir, exist_ok=True)

# High-poly material list
high_mats = []
for o in highs:
    for s in o.material_slots:
        if s.material and s.material.use_nodes and s.material not in high_mats:
            high_mats.append(s.material)

# Prepare the low-poly materials (created if missing)
if not low.material_slots or low.material_slots[0].material is None:
    m = bpy.data.materials.new(f"{low.name}_Baked")
    m.use_nodes = True
    if low.material_slots:
        low.material_slots[0].material = m
    else:
        low.data.materials.append(m)
low_mats = []
for s in low.material_slots:
    if s.material and s.material not in low_mats:
        s.material.use_nodes = True
        low_mats.append(s.material)


def make_image(map_name, srgb):
    # Add (Baked) to the end of the image name so it doesn't clash with the high-poly's original texture names
    name = f"{low.name}_{map_name} (Baked)"
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, SIZE, SIZE, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    return img


def target_nodes(img):
    # Add an image node to every low-poly material (reuse it if present) and select it
    result = []
    for m in low_mats:
        nodes = m.node_tree.nodes
        tag = f"Baked_{img.name}"
        n = nodes.get(tag)
        if n is None:
            n = nodes.new('ShaderNodeTexImage')
            n.name = n.label = tag
        n.image = img
        for x in nodes:
            x.select = False
        n.select = True
        nodes.active = n
        result.append(n)
    return result


def set_high(mode_input):
    # If mode_input is None, restore (Principled -> Output); otherwise connect that input to Emission
    skipped = []
    for m in high_mats:
        nodes, links = m.node_tree.nodes, m.node_tree.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None) \
            or next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if bsdf is None or out is None:
            skipped.append(m.name)
            continue
        surf = out.inputs['Surface']
        for l in list(surf.links):
            links.remove(l)
        emit = nodes.get(EMIT_NAME)
        if mode_input is None:
            links.new(bsdf.outputs['BSDF'], surf)
            if emit is not None:
                nodes.remove(emit)
            continue
        if emit is None:
            emit = nodes.new('ShaderNodeEmission')
            emit.name = emit.label = EMIT_NAME
            emit.location = (out.location.x, out.location.y - 200)
        emit.inputs['Strength'].default_value = 1.0
        col = emit.inputs['Color']
        for l in list(col.links):
            links.remove(l)
        src = bsdf.inputs[mode_input]
        if src.links:
            links.new(src.links[0].from_socket, col)
        else:
            v = src.default_value
            col.default_value = tuple(v) if mode_input == "Base Color" else (v, v, v, 1.0)
        links.new(emit.outputs['Emission'], surf)
    return skipped


def connect_low(images):
    # Connect the baked textures to the low-poly Principled BSDF
    for m in low_mats:
        nodes, links = m.node_tree.nodes, m.node_tree.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        for i, (map_name, socket, btype, srgb) in enumerate(MAPS):
            img = images.get(map_name)
            if img is None:
                continue
            tex = nodes.get(f"Baked_{img.name}")
            tex.location = (bsdf.location.x - 700, bsdf.location.y - i * 300)
            if socket is None:
                continue
            if map_name == "Normal":
                nm = nodes.get("Baked_NormalMap") or nodes.new('ShaderNodeNormalMap')
                nm.name = nm.label = "Baked_NormalMap"
                nm.location = (bsdf.location.x - 300, bsdf.location.y - i * 300)
                links.new(tex.outputs['Color'], nm.inputs['Color'])
                links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
            else:
                links.new(tex.outputs['Color'], bsdf.inputs[socket])


GEOM_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES', 'POINTCLOUD', 'VOLUME'}


def isolate_render(on, hidden):
    # on=True: exclude unselected shape objects from rendering and remember them / on=False: turn back on only the remembered ones
    if on:
        keep = set(highs) | {low}
        for o in bpy.context.view_layer.objects:
            if o.type in GEOM_TYPES and o not in keep and not o.hide_render:
                o.hide_render = True
                hidden.append(o)
    else:
        for o in hidden:
            o.hide_render = False
        hidden.clear()
    bpy.context.view_layer.update()


def shift(a, dy, dx, fill):
    # Shift the array by dy, dx cells (edges filled with fill, no wrap-around)
    out = np.full_like(a, fill)
    h, w = a.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = \
        a[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def uv_mask():
    # Pixels covered by the low-poly UVs are True, empty ones False
    # Found by baking white Emission on the low-poly alone with Margin 0 (selection and nodes are restored afterwards)
    mimg = bpy.data.images.new("BakeTempMask", SIZE, SIZE, alpha=False, float_buffer=False)
    mimg.colorspace_settings.name = 'Non-Color'
    target_nodes(mimg)
    saved = []
    for m in low_mats:
        nodes, links = m.node_tree.nodes, m.node_tree.links
        out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None) \
            or next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if out is None:
            out = nodes.new('ShaderNodeOutputMaterial')
        surf = out.inputs['Surface']
        old_from = surf.links[0].from_socket if surf.links else None
        e = nodes.new('ShaderNodeEmission')
        e.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        e.inputs['Strength'].default_value = 1.0
        links.new(e.outputs['Emission'], surf)
        saved.append((m, out, e, old_from))
    sel = list(bpy.context.selected_objects)
    for o in sel:
        if o != low:
            o.select_set(False)
    bk.use_selected_to_active = False
    bk.margin = 0
    try:
        bpy.ops.object.bake(type='EMIT')
    finally:
        bk.use_selected_to_active = True
        for o in sel:
            o.select_set(True)
        bpy.context.view_layer.objects.active = low
        for m, out, e, old_from in saved:
            m.node_tree.nodes.remove(e)
            if old_from is not None:
                m.node_tree.links.new(old_from, out.inputs['Surface'])
            tn = m.node_tree.nodes.get(f"Baked_{mimg.name}")
            if tn is not None:
                m.node_tree.nodes.remove(tn)
    px = np.empty(SIZE * SIZE * 4, np.float32)
    mimg.pixels.foreach_get(px)
    bpy.data.images.remove(mimg)
    return px.reshape(SIZE, SIZE, 4)[:, :, 0] > 0.5


def pad_black_first(img, covered, width):
    # Pad width pixels outside the UVs. Takes the darkest neighboring UV pixel (black wins)
    px = np.empty(SIZE * SIZE * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(SIZE, SIZE, 4)
    v = np.where(covered, px[:, :, 0], 2.0).astype(np.float32)   # 2.0 = still-empty pixel
    for _ in range(width):
        best = np.full_like(v, 2.0)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    np.minimum(best, shift(v, dy, dx, 2.0), out=best)
        new = (v > 1.5) & (best < 1.5)
        if not new.any():
            break
        v[new] = best[new]
    v[v > 1.5] = 0.0     # empty area outside the padding is black
    px[:, :, 0] = px[:, :, 1] = px[:, :, 2] = v
    px[:, :, 3] = 1.0
    img.pixels.foreach_set(px.ravel())
    img.update()


def use_gpu():
    # Find and enable a GPU in Preferences > Cycles Render Devices. Returns the device name, or None if not found
    addon = bpy.context.preferences.addons.get('cycles')
    if addon is None:
        return None
    cp = addon.preferences
    if cp.compute_device_type == 'NONE':
        for t in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
            try:
                cp.compute_device_type = t
            except TypeError:
                continue
            cp.get_devices()
            if any(d.type == t for d in cp.devices):
                break
        else:
            cp.compute_device_type = 'NONE'
            return None
    cp.get_devices()
    gpus = [d for d in cp.devices if d.type == cp.compute_device_type]
    if not gpus:
        return None
    for d in gpus:
        d.use = True
    return f"{cp.compute_device_type} ({', '.join(d.name for d in gpus)})"


# Bake settings (restored to the original values afterwards)
sc = bpy.context.scene
old = (sc.render.engine, sc.cycles.samples, sc.cycles.bake_type, sc.cycles.device)
temp_world = sc.world is None
if temp_world:
    sc.world = bpy.data.worlds.new("BakeTempWorld")
old_ao_dist = sc.world.light_settings.distance
sc.render.engine = 'CYCLES'
gpu = use_gpu()
sc.cycles.device = 'GPU' if gpu else 'CPU'
sc.cycles.samples = SAMPLES
bk = sc.render.bake
bk.use_selected_to_active = True
bk.cage_extrusion = EXTRUSION
bk.max_ray_distance = 0.0
bk.margin = MARGIN
bk.use_clear = True
bk.normal_space = 'TANGENT'

print("=" * 60)
print(f"High-poly: {', '.join(o.name for o in highs)}  ->  Low-poly: {low.name}")
print(f"Size {SIZE}, save location: {out_dir}")
print(f"Device: GPU {gpu}" if gpu else "No GPU found, baking on the CPU. (Takes a long time)")

images, skipped, start = {}, [], time.time()
hidden = []
try:
    for map_name, socket, btype, srgb in MAPS:
        img = make_image(map_name, srgb)
        target_nodes(img)
        skipped = set_high(socket if btype == 'EMIT' else None)
        if map_name == "Opacity":
            bk.margin = 0                       # so white doesn't spread into the holes
            bk.max_ray_distance = EXTRUSION * 2  # so rays don't hit the body behind the holes
        else:
            bk.margin = MARGIN
            bk.max_ray_distance = 0.0
        if btype == 'AO':
            sc.cycles.samples = AO_SAMPLES
            sc.world.light_settings.distance = AO_DISTANCE
            isolate_render(True, hidden)
            if hidden:
                print(f"  Objects briefly excluded from rendering during AO: {len(hidden)}: {', '.join(o.name for o in hidden)}")
        else:
            sc.cycles.samples = SAMPLES
        t0 = time.time()
        print(f"[Baking] {map_name} ...")
        bpy.ops.object.bake(type=btype)
        if hidden:
            isolate_render(False, hidden)
        if map_name == "Opacity":
            print("  Adding UV border padding ...")
            pad_black_first(img, uv_mask(), MARGIN)

        path = os.path.join(out_dir, f"{low.name}_{map_name}.png")
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        img.source = 'FILE'
        img.filepath = bpy.path.relpath(path)
        img.reload()
        img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
        images[map_name] = img
        print(f"[Done] {map_name} -> {os.path.basename(path)}  ({time.time() - t0:.0f}s)")
finally:
    if hidden:
        isolate_render(False, hidden)
    set_high(None)
    sc.render.engine, sc.cycles.samples, sc.cycles.bake_type, sc.cycles.device = old
    sc.world.light_settings.distance = old_ao_dist
    bk.margin = MARGIN
    bk.max_ray_distance = 0.0
    if temp_world:
        w = sc.world
        sc.world = None
        bpy.data.worlds.remove(w)

connect_low(images)

print(f"Restored the high-poly materials.")
if skipped:
    print(f"Skipped materials without a Principled BSDF: {', '.join(skipped)}")
print(f"Saved {len(images)} baked textures and connected them to the low-poly material. ({time.time() - start:.0f}s)")
print("Now save the .blend file (Ctrl+S).")
print("=" * 60)
