# Export_Each_OBJ.py
# Blender 4.2 ~ 4.5
# 씬의 메쉬 오브젝트를 오브젝트마다 각각 따로 OBJ 파일로 내보냅니다.
# 파일 이름 = 오브젝트 이름.obj
#
# 사용법: .blend 파일을 먼저 저장 > Scripting 탭 > 새 텍스트 > 붙여넣기 > 설정 확인 > Run Script
# 결과: .blend 파일이 있는 폴더 안에 "obj_export" 폴더가 생기고 그 안에 저장됩니다.

import bpy
import os

# ---------------- 설정 ----------------
EXPORT_FOLDER = "//obj_export"   # // = .blend 파일이 있는 폴더 기준. 절대경로도 가능 (예: r"D:\Export\obj")
ONLY_SELECTED = False            # True: 선택한 오브젝트만 / False: 씬의 모든 메쉬
ONLY_VISIBLE = True              # True: 뷰포트에서 숨긴 오브젝트는 제외
APPLY_MODIFIERS = True           # 모디파이어(디시메이트, 미러 등) 적용된 모양으로 내보내기
EXPORT_MATERIALS = False         # .mtl 파일도 같이 만들지 (Instant Meshes 등 리메쉬용이면 False 권장)
EXPORT_UV = True
EXPORT_NORMALS = True
# --------------------------------------


def safe_name(name):
    bad = '<>:"/\\|?*'
    return "".join("_" if c in bad else c for c in name)


def main():
    if bpy.data.filepath == "" and EXPORT_FOLDER.startswith("//"):
        print(".blend 파일을 먼저 저장하거나 EXPORT_FOLDER를 절대경로로 지정해 주세요.")
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
        print("내보낼 메쉬가 없습니다.")
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
        print(f"저장: {path}")

    # 원래 선택 상태로 복구
    bpy.ops.object.select_all(action='DESELECT')
    for o in prev_selected:
        o.select_set(True)
    view_layer.objects.active = prev_active

    print(f"완료: {count}개 → {folder}")


main()
