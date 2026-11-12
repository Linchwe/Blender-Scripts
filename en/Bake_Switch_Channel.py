# Bake_Switch_Channel.py
# Blender 4.2 ~ 4.5
#
# Purpose
#  When baking the high-poly's PBR textures (Base Color, Roughness, Metallic, Normal) to the low-poly,
#  this script rewires the high-poly materials for the map you want to bake, all at once.
#  With MODE = "ALL" it bakes all four maps in order automatically.
#
# What it does
#  1) Adds one BakeEmission node to every material of the selected high-poly objects (all except the active one),
#     connects the value for MODE to Emission, and connects Emission to the Material Output.
#       BASECOLOR : whatever went into Principled BSDF Base Color (including adjustment nodes like Brightness/Contrast)
#       ROUGHNESS : whatever went into Principled BSDF Roughness
#       METALLIC  : whatever went into Principled BSDF Metallic
#       NORMAL    : no Emission; reconnects the Principled BSDF to the Material Output
#       RESTORE   : reconnects the Principled BSDF to the Output as before and deletes the BakeEmission nodes
#       ALL       : connects and bakes BASECOLOR -> ROUGHNESS -> METALLIC -> NORMAL in order,
#                   then does RESTORE and packs the baked images into the .blend file
#     For materials where the value is just a number instead of an image, that number is used as the Emission color.
#  2) In the low-poly (active object) materials, finds the image node whose name contains BaseColor / Roughness / Metallic / Normal
#     and selects it. (Blender bakes into the selected image node)
#  3) Sets the Bake Type. (BASECOLOR, ROUGHNESS, METALLIC = Emit / NORMAL = Normal, Tangent)
#     Also turns on Selected to Active. Extrusion, Margin and sample count are not touched.
#
# Notes
#  - Select the high-poly first, then add the low-poly last so the low-poly is active.
#    The active object has a bright (yellowish) orange outline, the others a dark orange one.
#  - Materials without a Principled BSDF are skipped.
#  - The original nodes and links (on the Principled side) are not deleted, so RESTORE can always put things back.
#  - The low-poly material must already have blank image nodes to bake into. Name them so they contain BaseColor / Roughness /
#    Metallic / Normal. (BaseColor in sRGB, the rest Non-Color)
#  - With ALL, Blender looks frozen while baking. Wait until it finishes.
#  - Baked images exist only inside Blender. ALL packs them, so they are kept when you save the .blend,
#    but if you need PNG files, save them separately with Image > Save As in the Image Editor.
#  - Lowering Render Properties > Sampling > Render > Max Samples to about 16 before baking makes it faster.
#
# Usage
#  1) Select the high-poly and the low-poly (low-poly last = active)
#       In the 3D viewport : click the high-poly -> Shift+click the low-poly
#       In the Outliner    : click the high-poly name -> Ctrl+click the low-poly name
#                           (In the Outliner, Shift+click selects the whole range in between, so be careful)
#     If they overlap and are hard to click in the viewport, the Outliner is easier.
#  2) Scripting tab > New text > Paste > choose MODE below and Run Script
#  3) Bake everything at once : run with MODE = "ALL" and you're done (no need to press Bake)
#     Bake one map at a time  : run with MODE = BASECOLOR -> click Bake in the Render Properties > Bake panel
#                              -> repeat for ROUGHNESS -> METALLIC -> NORMAL -> finally run with RESTORE

import bpy

# Settings
MODE = "ALL"        # ALL / BASECOLOR / ROUGHNESS / METALLIC / NORMAL / RESTORE

SOCKET = {"BASECOLOR": "Base Color", "ROUGHNESS": "Roughness", "METALLIC": "Metallic"}
TARGET_KEY = {"BASECOLOR": "basecolor", "ROUGHNESS": "roughness", "METALLIC": "metallic", "NORMAL": "normal"}
ORDER = ("BASECOLOR", "ROUGHNESS", "METALLIC", "NORMAL")
EMIT_NAME = "BakeEmission"

if MODE not in ("ALL", "BASECOLOR", "ROUGHNESS", "METALLIC", "NORMAL", "RESTORE"):
    raise RuntimeError(f"Invalid MODE value: {MODE}")

low = bpy.context.view_layer.objects.active
highs = [o for o in bpy.context.selected_objects if o != low and o.type == 'MESH']
if low is None or low.type != 'MESH' or not highs:
    raise RuntimeError("Select the high-poly first, then add the low-poly to the selection last "
                       "(Shift+click in the viewport, Ctrl+click in the Outliner).")

mats = []
for o in highs:
    for s in o.material_slots:
        if s.material and s.material.use_nodes and s.material not in mats:
            mats.append(s.material)


def set_links(mode):
    # Rewire the high-poly materials. Returns the names of the changed and skipped materials
    done, skipped = [], []
    for m in mats:
        nt = m.node_tree
        nodes, links = nt.nodes, nt.links
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

        if mode in ("NORMAL", "RESTORE"):
            links.new(bsdf.outputs['BSDF'], surf)
            if mode == "RESTORE" and emit is not None:
                nodes.remove(emit)
            done.append(m.name)
            continue

        if emit is None:
            emit = nodes.new('ShaderNodeEmission')
            emit.name = emit.label = EMIT_NAME
            emit.location = (out.location.x, out.location.y - 200)
        emit.inputs['Strength'].default_value = 1.0
        col = emit.inputs['Color']
        for l in list(col.links):
            links.remove(l)

        src = bsdf.inputs[SOCKET[mode]]
        if src.links:
            links.new(src.links[0].from_socket, col)
        else:
            v = src.default_value
            col.default_value = tuple(v) if mode == "BASECOLOR" else (v, v, v, 1.0)
        links.new(emit.outputs['Emission'], surf)
        done.append(m.name)
    return done, skipped


def select_target(mode):
    # Select the image node to bake into in the low-poly materials. Returns the image found (None if none)
    key = TARGET_KEY[mode]
    found = None
    for s in low.material_slots:
        if not (s.material and s.material.use_nodes):
            continue
        tn = s.material.node_tree.nodes
        cand = [n for n in tn if n.type == 'TEX_IMAGE' and n.image and key in n.image.name.lower()]
        for n in tn:
            n.select = False
        if cand:
            cand[0].select = True
            tn.active = cand[0]
            found = cand[0].image
    return found


def set_bake(mode):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.render.bake.use_selected_to_active = True
    if mode == "NORMAL":
        sc.cycles.bake_type = 'NORMAL'
        sc.render.bake.normal_space = 'TANGENT'
    else:
        sc.cycles.bake_type = 'EMIT'
    return sc.cycles.bake_type


print("=" * 60)
print(f"MODE = {MODE}")

if MODE == "ALL":
    import time
    baked, missing = [], []
    try:
        for mode in ORDER:
            img = select_target(mode)
            if img is None:
                missing.append(mode)
                print(f"[Skipped] {mode}: the low-poly has no image node whose name contains '{TARGET_KEY[mode]}'.")
                continue
            done, skipped = set_links(mode)
            btype = set_bake(mode)
            t0 = time.time()
            print(f"[Baking] {mode} -> {img.name} ({btype}) ...")
            bpy.ops.object.bake(type=btype)
            try:
                img.pack()
            except Exception as e:
                print(f"  Pack failed (save it with Image > Save As): {e}")
            baked.append(img.name)
            print(f"[Done] {mode} -> {img.name}  {time.time() - t0:.0f}s")
    finally:
        done, skipped = set_links("RESTORE")
        print("Restored the high-poly materials.")
    if skipped:
        print(f"Skipped materials without a Principled BSDF: {', '.join(skipped)}")
    print(f"Baked images ({len(baked)}): {', '.join(baked)}")
    if missing:
        print(f"Maps not baked because there is no image node: {', '.join(missing)}")
    print("Packed into the .blend file. Save the file. If you need PNGs, use Image > Save As.")

else:
    done, skipped = set_links(MODE)
    print(f"Changed materials ({len(done)}): {', '.join(done)}")
    if skipped:
        print(f"Skipped materials without a Principled BSDF: {', '.join(skipped)}")
    if MODE == "RESTORE":
        print("Restored the high-poly materials. Save the baked images with Image > Save As.")
    else:
        img = select_target(MODE)
        print(f"Baking into image: {img.name}" if img else
              f"The low-poly material has no image node whose name contains '{TARGET_KEY[MODE]}'. Create one and select it.")
        print(f"Bake Type: {set_bake(MODE)}  ->  Now press the Bake button.")

print("=" * 60)
