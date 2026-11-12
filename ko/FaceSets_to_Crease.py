# FaceSets_to_Crease.py
# Blender 4.2 ~ 4.5
#
# 용도
#  스컬프트 모드에서 나눈 페이스셋(Face Set)의 경계 엣지에 크리즈(Crease)를 자동으로 넣습니다.
#  Subdivision Surface 를 걸어도 페이스셋 경계(옷 솔기, 파츠 경계 등)가 뭉개지지 않고 각이 살아 있게 하는 용도입니다.
#
# 하는 일
#  1) 서로 다른 페이스셋에 속한 두 면이 맞닿은 엣지(페이스셋 경계)를 찾아 크리즈를 CREASE_VALUE 로 넣습니다.
#  2) 같은 페이스셋 안쪽 엣지는 건드리지 않습니다.
#  3) INCLUDE_OPEN_EDGES 를 켜면 메시의 뚫린 테두리(면이 한쪽에만 붙은 엣지)에도 크리즈를 넣습니다.
#  4) 잠시 오브젝트 모드로 바꿔서 처리한 뒤, 끝나면 원래 모드(스컬프트, 에디트 등)로 돌아갑니다.
#
# 주의
#  - 페이스셋을 한 번도 만들지 않은 메시는 페이스셋 데이터가 없어서 건너뜁니다.
#  - 기본은 기존 크리즈를 유지하고 경계 엣지만 덮어씁니다. 처음부터 다시 하려면 CLEAR_EXISTING = True.
#  - 크리즈는 Subdivision Surface 모디파이어가 있을 때만 눈에 보입니다.
#
# 사용법
#  1) 메시를 선택합니다. (여러 개 가능, 스컬프트 모드에서 바로 실행해도 됨)
#  2) Scripting 탭 > 새 텍스트 > 붙여넣기 > 설정 확인 > Run Script
#  3) 실행 전에 Ctrl+S 로 저장하세요. Ctrl+Z 로 되돌릴 수 있습니다.

import bpy
import numpy as np

# ---------------- 설정 ----------------
CREASE_VALUE = 1.0          # 부여할 크리즈 값 (0.0 ~ 1.0, 1.0 = 완전히 날카롭게)
INCLUDE_OPEN_EDGES = False  # True 면 메시의 뚫린 테두리(면이 한쪽에만 붙은 엣지)에도 크리즈
CLEAR_EXISTING = False      # True 면 기존 크리즈를 모두 0으로 지운 뒤 새로 적용
# --------------------------------------


def apply_crease(obj):
    mesh = obj.data

    # 페이스셋은 숨김 속성 ".sculpt_face_set" 에 면마다 정수로 저장됨
    fs_attr = mesh.attributes.get(".sculpt_face_set")
    if fs_attr is None:
        print(f"[{obj.name}] 페이스셋 데이터가 없어 건너뜁니다.")
        return

    n_poly = len(mesh.polygons)
    n_edge = len(mesh.edges)
    n_loop = len(mesh.loops)

    # ---- 1) 면별 페이스셋 번호 ----
    fs_vals = np.empty(n_poly, dtype=np.int32)
    fs_attr.data.foreach_get("value", fs_vals)

    # ---- 2) 루프(면의 꼭짓점 모서리)마다 "어느 엣지 / 어느 면" 인지 ----
    loop_edge = np.empty(n_loop, dtype=np.int32)
    mesh.loops.foreach_get("edge_index", loop_edge)

    loop_total = np.empty(n_poly, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", loop_total)
    loop_face = np.repeat(np.arange(n_poly, dtype=np.int32), loop_total)

    loop_fs = fs_vals[loop_face]   # 루프마다 그 면의 페이스셋 번호

    # ---- 3) 엣지마다 붙은 면들의 페이스셋 최솟값 / 최댓값 / 면 개수 ----
    big = np.iinfo(np.int32).max
    e_min = np.full(n_edge, big, dtype=np.int64)
    e_max = np.full(n_edge, -big, dtype=np.int64)
    e_cnt = np.zeros(n_edge, dtype=np.int32)

    np.minimum.at(e_min, loop_edge, loop_fs)
    np.maximum.at(e_max, loop_edge, loop_fs)
    np.add.at(e_cnt, loop_edge, 1)

    # 경계 엣지: 면이 2개 이상 붙어 있고, 그 면들의 페이스셋 번호가 서로 다름
    boundary = (e_cnt >= 2) & (e_min != e_max)
    if INCLUDE_OPEN_EDGES:
        boundary |= (e_cnt == 1)   # 면이 한쪽에만 붙은 뚫린 테두리

    # ---- 4) 크리즈 기록 ----
    #  Blender 4.0 부터 엣지 크리즈는 "crease_edge" 엣지 속성에 저장됨 (없으면 새로 만듦)
    crease_attr = mesh.attributes.get("crease_edge")
    if crease_attr is None:
        crease_attr = mesh.attributes.new("crease_edge", 'FLOAT', 'EDGE')

    crease = np.zeros(n_edge, dtype=np.float32)
    if not CLEAR_EXISTING:
        crease_attr.data.foreach_get("value", crease)   # 기존 값 유지

    crease[boundary] = CREASE_VALUE
    crease_attr.data.foreach_set("value", crease)
    mesh.update()

    print(f"[{obj.name}] 크리즈 적용 엣지 {int(boundary.sum())}개 / 전체 {n_edge}개 "
          f"(페이스셋 {len(np.unique(fs_vals))}개)")


def main():
    active = bpy.context.view_layer.objects.active
    prev_mode = active.mode if active else 'OBJECT'

    # 스컬프트/에디트 모드의 변경 내용을 메시에 반영하려면 오브젝트 모드여야 함
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes and active and active.type == 'MESH':
        meshes = [active]
    if not meshes:
        print("메쉬를 선택해 주세요.")
        return

    for obj in meshes:
        apply_crease(obj)

    # 원래 모드로 복귀
    if active and prev_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode=prev_mode)


main()
