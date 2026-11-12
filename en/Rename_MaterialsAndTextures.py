# Rename_MaterialsAndTextures.py
# Blender 4.x / 5.x
# Based on the selected mesh object's name, renames in one go:
#   - the mesh data
#   - the materials
#   - the image textures connected to the materials (+ the name of the connected channel)
# so they all match.
#
# e.g. if the object is named Veil
#   Mesh data : Veil
#   Material  : Veil  (Veil_01, Veil_02 ... if there are several slots)
#   Textures  : Veil_BaseColor, Veil_MetallicRoughness, Veil_Normal ...
#
# Usage: Scripting tab > New text > Paste > Select meshes > Run Script

import bpy

# ---------------- Settings ----------------
ONLY_SELECTED = True       # Set to False to apply to every mesh in the scene
RENAME_MESH_DATA = True    # Also rename the mesh data to the object name
RENAME_FILEPATH = False    # True: also change the file name in the image's file path (files on disk are not renamed)
# --------------------------------------

# Principled BSDF input name -> suffix added to the texture name
SOCKET_SUFFIX = {
    "Base Color": "BaseColor",
    "Metallic": "Metallic",
    "Roughness": "Roughness",
    "Normal": "Normal",
    "Alpha": "Alpha",
    "Emission Color": "Emission",
    "Emission": "Emission",
    "Specular IOR Level": "Specular",
    "Subsurface Weight": "Subsurface",
    "Coat Weight": "Coat",
    "Transmission Weight": "Transmission",
}


def find_targets(node, visited=None):
    """Start from an image node, follow its links, and collect the shader input names they reach."""
    if visited is None:
        visited = set()
    if node.name in visited:
        return set()
    visited.add(node.name)

    found = set()
    for out in node.outputs:
        for link in out.links:
            to_node = link.to_node
            to_sock = link.to_socket.name
            if to_node.type in {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"}:
                found.add(to_sock)
            elif to_node.type in {"NORMAL_MAP", "BUMP"}:
                found.add("Normal")
            elif to_node.type == "DISPLACEMENT":
                found.add("Displacement")
            else:
                # Keep following through intermediate nodes such as Separate Color, Mix, ColorRamp
                found |= find_targets(to_node, visited)
    return found


def suffix_for(targets):
    names = []
    for t in sorted(targets):
        if t == "Displacement":
            names.append("Height")
        else:
            names.append(SOCKET_SUFFIX.get(t, t.replace(" ", "")))
    # Metallic + roughness in one texture (glTF style)
    if set(names) == {"Metallic", "Roughness"}:
        return "MetallicRoughness"
    return "".join(names) if names else "Texture"


def rename_object(obj, used_images):
    base = obj.name
    log = [f"[{base}]"]

    if RENAME_MESH_DATA and obj.data and obj.data.users == 1:
        obj.data.name = base

    slots = [s for s in obj.material_slots if s.material]
    for i, slot in enumerate(slots):
        mat = slot.material

        # A material shared with other objects is copied so this object gets its own
        if mat.users > 1:
            mat = mat.copy()
            slot.material = mat
            log.append("  Shared material -> copied and separated")

        mat_name = base if len(slots) == 1 else f"{base}_{i + 1:02d}"
        mat.name = mat_name
        log.append(f"  Material: {mat.name}")

        if not mat.use_nodes:
            continue

        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE" or node.image is None:
                continue
            img = node.image
            new_name = f"{mat_name}_{suffix_for(find_targets(node))}"

            # If the same image is used by another material, skip it to avoid a name clash
            if img.name in used_images and used_images[img.name] != mat_name:
                log.append(f"  Texture skipped (shared with another material): {img.name}")
                continue

            img.name = new_name
            used_images[img.name] = mat_name
            node.label = new_name

            if RENAME_FILEPATH and img.filepath:
                ext = img.filepath.rsplit(".", 1)[-1] if "." in img.filepath else "png"
                folder = img.filepath.rsplit("/", 1)[0] if "/" in img.filepath else "//"
                img.filepath = f"{folder}/{new_name}.{ext}"

            log.append(f"  Texture: {img.name}")

    print("\n".join(log))


def main():
    objs = bpy.context.selected_objects if ONLY_SELECTED else bpy.context.scene.objects
    meshes = [o for o in objs if o.type == "MESH"]
    if not meshes:
        print("No mesh object is selected.")
        return

    used_images = {}
    for obj in meshes:
        rename_object(obj, used_images)
    print(f"Done: {len(meshes)} mesh(es)")


main()
