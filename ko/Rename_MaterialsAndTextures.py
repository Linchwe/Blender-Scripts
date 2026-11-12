# Rename_MaterialsAndTextures.py
# Blender 4.x / 5.x
#
# 용도
#  선택한 메쉬 오브젝트 이름을 기준으로 메쉬 데이터, 머티리얼, 텍스처 이름을 한 번에 맞춰 줍니다.
#  엔진으로 내보내기 전에 Material.001, Image_0 같은 이름을 정리할 때 씁니다.
#
# 하는 일
#  1) 메쉬 데이터 이름을 오브젝트 이름으로 바꿉니다. (RENAME_MESH_DATA)
#  2) 머티리얼 이름을 오브젝트 이름으로 바꿉니다. 슬롯이 여러 개면 이름_01, 이름_02 ... 로 붙입니다.
#  3) 머티리얼 안의 이미지 텍스처 이름을 "머티리얼이름_채널" 로 바꿉니다. 노드 라벨도 같은 이름으로 바꿉니다.
#     채널은 그 이미지가 연결된 Principled BSDF 입력으로 정합니다. (Separate Color, Mix 같은 중간 노드도 따라감)
#       Base Color → BaseColor, Normal Map/Bump → Normal, Displacement → Height,
#       Metallic 과 Roughness 에 같이 연결된 한 장 → MetallicRoughness (glTF 방식)
#  예) 오브젝트 이름이 Veil 이면
#       메쉬 데이터 : Veil
#       머티리얼    : Veil (슬롯이 여러 개면 Veil_01, Veil_02 ...)
#       텍스처      : Veil_BaseColor, Veil_MetallicRoughness, Veil_Normal ...
#
# 주의
#  - 다른 오브젝트와 같이 쓰는 머티리얼은 이 오브젝트 전용으로 복사한 뒤 이름을 바꿉니다. 머티리얼 개수가 늘어날 수 있습니다.
#  - 다른 오브젝트와 같이 쓰는 메쉬 데이터는 이름을 바꾸지 않습니다.
#  - 같은 이미지를 다른 머티리얼에서도 쓰고 있으면 이름이 겹치지 않게 그 텍스처는 건너뜁니다.
#  - RENAME_FILEPATH = True 는 블렌더 안의 파일 경로 이름만 바꾸고 디스크의 파일 이름은 바꾸지 않습니다.
#    켠 뒤에는 이미지를 다시 저장하거나 디스크 파일 이름을 직접 맞춰야 텍스처가 사라지지 않습니다.
#
# 사용법
#  1) 이름을 맞출 메쉬를 선택합니다. (여러 개 가능)
#  2) Scripting 탭 > 새 텍스트 > 붙여넣기 > 설정 확인 > Run Script
#  3) 바뀐 이름 목록은 Window > Toggle System Console 에 나옵니다.

import bpy

# ---------------- 설정 ----------------
ONLY_SELECTED = True       # False 로 바꾸면 씬의 모든 메쉬에 적용
RENAME_MESH_DATA = True    # 메쉬 데이터 이름도 오브젝트 이름으로
RENAME_FILEPATH = False    # True 면 이미지의 저장 경로 파일명도 같이 변경 (디스크 파일은 안 바뀜)
# --------------------------------------

# Principled BSDF 입력 이름 -> 텍스처 이름 뒤에 붙일 접미사
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
    """이미지 노드에서 출발해 링크를 따라가며 도착하는 셰이더 입력 이름들을 모은다."""
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
                # Separate Color, Mix, ColorRamp 등 중간 노드는 계속 따라간다
                found |= find_targets(to_node, visited)
    return found


def suffix_for(targets):
    names = []
    for t in sorted(targets):
        if t == "Displacement":
            names.append("Height")
        else:
            names.append(SOCKET_SUFFIX.get(t, t.replace(" ", "")))
    # 메탈릭 + 러프니스가 한 장인 경우 (glTF 방식)
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

        # 다른 오브젝트와 같이 쓰는 머티리얼은 이 오브젝트 전용으로 복사
        if mat.users > 1:
            mat = mat.copy()
            slot.material = mat
            log.append("  공유 머티리얼 -> 복사해서 분리")

        mat_name = base if len(slots) == 1 else f"{base}_{i + 1:02d}"
        mat.name = mat_name
        log.append(f"  머티리얼: {mat.name}")

        if not mat.use_nodes:
            continue

        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE" or node.image is None:
                continue
            img = node.image
            new_name = f"{mat_name}_{suffix_for(find_targets(node))}"

            # 같은 이미지를 다른 머티리얼에서도 쓰면 이름 충돌을 피하기 위해 건너뜀
            if img.name in used_images and used_images[img.name] != mat_name:
                log.append(f"  텍스처 건너뜀(다른 머티리얼과 공유): {img.name}")
                continue

            img.name = new_name
            used_images[img.name] = mat_name
            node.label = new_name

            if RENAME_FILEPATH and img.filepath:
                ext = img.filepath.rsplit(".", 1)[-1] if "." in img.filepath else "png"
                folder = img.filepath.rsplit("/", 1)[0] if "/" in img.filepath else "//"
                img.filepath = f"{folder}/{new_name}.{ext}"

            log.append(f"  텍스처: {img.name}")

    print("\n".join(log))


def main():
    objs = bpy.context.selected_objects if ONLY_SELECTED else bpy.context.scene.objects
    meshes = [o for o in objs if o.type == "MESH"]
    if not meshes:
        print("메쉬 오브젝트가 선택되지 않았습니다.")
        return

    used_images = {}
    for obj in meshes:
        rename_object(obj, used_images)
    print(f"완료: 메쉬 {len(meshes)}개")


main()
