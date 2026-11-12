# Export_Each_OBJ.py
# Blender 4.2 ~ 4.5
# Exports each mesh object in the scene to its own separate OBJ file.
# File name = object name.obj
#
# Usage: save the .blend file first > Scripting tab > New text > Paste > Check the settings > Run Script
# Result: an "obj_export" folder is created next to the .blend file and the files are saved there.

import bpy
import os

# ---------------- Settings ----------------
EXPORT_FOLDER = "//obj_export"   # // = relative to the .blend file's folder. Absolute paths also work (e.g. r"D:\Export\obj")
ONLY_SELECTED = False            # True: selected objects only / False: all meshes in the scene
ONLY_VISIBLE = True              # True: skip objects hidden in the viewport
APPLY_MODIFIERS = True           # Export the shape with modifiers (Decimate, Mirror, etc.) applied
EXPORT_MATERIALS = False         # Also write .mtl files (False recommended for remeshing in Instant Meshes etc.)
EXPORT_UV = True
EXPORT_NORMALS = True
# --------------------------------------


def safe_name(name):
    bad = '<>:"/\\|?*'
    return "".join("_" if c in bad else c for c in name)


def main():
    if bpy.data.filepath == "" and EXPORT_FOLDER.startswith("//"):
        print("Save the .blend file first, or set EXPORT_FOLDER to an absolute path.")
        return

    folder = bpy.path.abspath(EXPORT_FOLDER)
    os.makedirs(folder, exist_ok=True)

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    view_layer = bpy.context.view_layer
    source = bpy.context.selected_objects if ONLY_SELECTED else bpy.context.scene.objects
    targets = [o for o in source
               if o.type == 'MESH' and (not ONLY_VISIBLE or o.visible_get())]

    if not targets:
        print("There are no meshes to export.")
        return

    prev_selected = list(bpy.context.selected_objects)
    prev_active = view_layer.objects.active

    count = 0
    for obj in targets:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        view_layer.objects.active = obj

        path = os.path.join(folder, safe_name(obj.name) + ".obj")
        bpy.ops.wm.obj_export(
            filepath=path,
            export_selected_objects=True,
            apply_modifiers=APPLY_MODIFIERS,
            export_materials=EXPORT_MATERIALS,
            export_uv=EXPORT_UV,
            export_normals=EXPORT_NORMALS,
            export_triangulated_mesh=False,
        )
        count += 1
        print(f"Saved: {path}")

    # Restore the original selection
    bpy.ops.object.select_all(action='DESELECT')
    for o in prev_selected:
        o.select_set(True)
    view_layer.objects.active = prev_active

    print(f"Done: {count} file(s) -> {folder}")


main()
