# FaceSets_to_VertexColor.py
# Blender 4.2 ~ 4.5
#
# 용도
#  선택한 메쉬의 페이스셋(Face Set)을 그대로 버텍스 컬러(Color Attribute)로 바꿉니다.
#  스컬프트 모드에서 나눈 파츠 구분을 ID 맵으로 굽거나, 텍스처 작업에서 마스크로 쓸 때 씁니다.
#
# 하는 일
#  1) 페이스셋마다 서로 잘 구분되는 색을 자동으로 정합니다. (색상을 황금비 간격으로 돌리고 밝기를 3단계로 섞음)
#  2) "FaceSetID" 라는 컬러 속성(Face Corner, Byte Color)을 만들고, 면마다 그 페이스셋의 색을 채웁니다.
#  3) 이 속성을 활성 컬러와 렌더 컬러로 지정합니다.
#
# 주의
#  - 페이스셋이 없는 메쉬는 건너뜁니다. 스컬프트 모드에서 먼저 페이스셋을 나누세요.
#  - 같은 이름(ATTR_NAME)의 컬러 속성이 이미 있으면 지우고 새로 만듭니다.
#  - 색은 페이스셋 번호 순서로 정해집니다. 페이스셋을 추가하거나 지운 뒤 다시 실행하면 다른 페이스셋의 색도 바뀔 수 있습니다.
#
# 사용법
#  1) 오브젝트 모드에서 메쉬를 선택합니다. (여러 개 가능)
#  2) Scripting 탭 > 새 텍스트 > 붙여넣기 > Run Script
#  3) 뷰포트 Solid 모드의 Color 를 Attribute 로 바꾸면 결과를 볼 수 있습니다.

import bpy
import colorsys

ATTR_NAME = "FaceSetID"   # 만들어질 컬러 속성 이름
SATURATION = 0.85
VALUE = 0.95


def distinct_color(index):
    # 황금비 간격으로 색상(Hue)을 돌려서 이웃 번호끼리도 색이 확실히 다르게
    hue = (index * 0.618033988749895) % 1.0
    # 밝기를 3단계로 섞어서 색이 많을 때도 구분되게
    val = VALUE - (index % 3) * 0.2
    r, g, b = colorsys.hsv_to_rgb(hue, SATURATION, val)
    return (r, g, b, 1.0)


def convert(obj):
    mesh = obj.data
    fs_attr = mesh.attributes.get(".sculpt_face_set")
    if fs_attr is None:
        print(f"[{obj.name}] 페이스 셋이 없습니다. 스컬프트 모드에서 먼저 칠해 주세요.")
        return

    face_count = len(mesh.polygons)
    face_sets = [0] * face_count
    fs_attr.data.foreach_get("value", face_sets)

    # 페이스 셋 번호 → 색
    ids = sorted(set(face_sets))
    color_of = {fid: distinct_color(i) for i, fid in enumerate(ids)}

    # 기존 같은 이름 속성은 지우고 새로 만들기
    old = mesh.color_attributes.get(ATTR_NAME)
    if old is not None:
        mesh.color_attributes.remove(old)
    col_attr = mesh.color_attributes.new(name=ATTR_NAME, type='BYTE_COLOR', domain='CORNER')

    # 면마다 그 면의 코너(루프)들에 같은 색을 채움
    loop_totals = [0] * face_count
    mesh.polygons.foreach_get("loop_total", loop_totals)
    flat = []
    for fid, total in zip(face_sets, loop_totals):
        c = color_of[fid]
        flat.extend(c * total)
    col_attr.data.foreach_set("color_srgb", flat)

    mesh.color_attributes.active_color = col_attr
    mesh.color_attributes.render_color_index = mesh.color_attributes.find(ATTR_NAME)
    mesh.update()
    print(f"[{obj.name}] 페이스 셋 {len(ids)}개 → '{ATTR_NAME}' 컬러 속성으로 변환 완료")


def main():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes:
        print("메쉬를 선택해 주세요.")
        return
    for obj in meshes:
        convert(obj)


main()
