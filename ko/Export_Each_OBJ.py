# Export_Each_OBJ.py
# Blender 4.2 ~ 4.5
#
# 용도
#  씬의 메쉬 오브젝트를 오브젝트마다 각각 따로 OBJ 파일로 내보냅니다.
#  Instant Meshes 같은 리메쉬 도구에 파츠를 하나씩 넣을 때처럼, 파일이 오브젝트별로 나뉘어야 할 때 씁니다.
#
# 하는 일
#  1) EXPORT_FOLDER 에 폴더를 만듭니다. 기본값은 .blend 파일이 있는 폴더 안의 "obj_export" 폴더입니다.
#  2) 메쉬마다 "오브젝트이름.obj" 로 저장합니다. 파일 이름에 쓸 수 없는 글자(< > : " / \ | ? *)는 _ 로 바꿉니다.
#  3) 내보내기 옵션
#       Apply Modifiers 켬 (디시메이트, 미러 등이 적용된 모양), UV 켬, Normals 켬, Triangulate 끔
#       Materials 끔 (.mtl 파일을 만들지 않음)
#  4) 끝나면 선택 상태와 활성 오브젝트를 실행 전으로 되돌립니다.
#
# 주의
#  - EXPORT_FOLDER 가 // 로 시작하면 .blend 파일을 먼저 저장해야 합니다. 저장하지 않으려면 절대경로를 적으세요.
#  - 같은 이름의 파일이 있으면 덮어씁니다.
#  - 기본값은 씬의 모든 메쉬입니다. 일부만 내보내려면 ONLY_SELECTED = True 로 바꾸고 선택한 뒤 실행하세요.
#  - 뷰포트에서 숨긴 오브젝트는 기본으로 빠집니다. (ONLY_VISIBLE)
#
# 사용법
#  1) .blend 파일을 먼저 저장합니다.
#  2) Scripting 탭 > 새 텍스트 > 붙여넣기 > 설정 확인 > Run Script
#  3) 저장된 파일 목록은 Window > Toggle System Console 에 나옵니다.

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
