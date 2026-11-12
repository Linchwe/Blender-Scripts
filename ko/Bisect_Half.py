# Bisect_Half.py
# Blender 4.2 ~ 4.5
#
# 용도
#  좌우 대칭 모델을 반쪽만 남기고 싶을 때, 선택한 메쉬를 월드 X=0 (또는 Y, Z) 평면에서 정확히 잘라 한쪽 반을 지웁니다.
#  반쪽만 고친 뒤 Mirror 모디파이어로 다시 대칭을 만들 때 씁니다.
#
# 하는 일
#  1) 선택한 메쉬마다 월드 기준 평면(AXIS, PLANE_OFFSET)을 오브젝트 좌표로 바꿔서 그 자리에서 자릅니다.
#     면이 중앙선에 걸쳐 있어도 그 자리에서 잘라 주므로 중앙선이 깔끔하게 남습니다.
#  2) KEEP_SIDE 에 정한 쪽만 남기고 반대쪽을 지웁니다.
#  3) FILL_CUT 을 켜면 잘린 단면을 면으로 막습니다.
#  4) ADD_MIRROR 를 켜면 Mirror_Half 라는 Mirror 모디파이어를 추가합니다. (Clipping, Merge 켬)
#
# 주의
#  - 오브젝트의 위치, 회전과 상관없이 월드 좌표 평면으로 자릅니다. 캐릭터가 월드 X=0 가운데에 서 있어야 합니다.
#  - Mirror 모디파이어는 오브젝트 원점을 기준으로 대칭을 만듭니다. ADD_MIRROR 를 켤 때는 오브젝트 원점도 X=0 에 두세요.
#  - 모디파이어는 적용하지 않고 원본 메쉬 데이터를 자릅니다.
#  - 메쉬 데이터를 같이 쓰는 오브젝트(Alt+D 링크 복제)는 함께 잘립니다.
#
# 사용법
#  1) 오브젝트 모드에서 메쉬를 선택합니다. (여러 개 가능)
#  2) Scripting 탭 > 새 텍스트 > 붙여넣기 > 아래 설정 확인 > Run Script
#  3) 실행 전에 Ctrl+S 로 저장하세요. Ctrl+Z 로 되돌릴 수 있습니다.

import bpy
import bmesh
from mathutils import Vector

# ---------------- 설정 ----------------
AXIS = 'X'            # 자를 축: 'X', 'Y', 'Z'
KEEP_SIDE = '+'       # 남길 쪽: '+' (축의 플러스 쪽), '-' (마이너스 쪽)
                      #   X축 기준 '+' = 캐릭터 정면에서 봤을 때 화면 오른쪽 = 캐릭터의 왼쪽
PLANE_OFFSET = 0.0    # 자르는 위치 (월드 좌표, 보통 0)
FILL_CUT = False      # 잘린 단면을 면으로 막을지 (미러로 다시 붙일 거면 False)
ADD_MIRROR = False    # 자른 뒤 Mirror 모디파이어를 추가할지 (클리핑 켜짐)
# --------------------------------------

AXIS_VEC = {'X': Vector((1, 0, 0)), 'Y': Vector((0, 1, 0)), 'Z': Vector((0, 0, 1))}


def bisect_object(obj):
    mw = obj.matrix_world
    mw_inv = mw.inverted()

    # 월드 기준 평면을 오브젝트 로컬 좌표로 변환
    n_world = AXIS_VEC[AXIS]
    co_world = n_world * PLANE_OFFSET
    co_local = mw_inv @ co_world
    n_local = (mw.to_3x3().transposed() @ n_world).normalized()

    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    result = bmesh.ops.bisect_plane(
        bm,
        geom=geom,
        dist=0.0001,
        plane_co=co_local,
        plane_no=n_local,
        clear_inner=(KEEP_SIDE == '+'),   # 마이너스 쪽 삭제
        clear_outer=(KEEP_SIDE == '-'),   # 플러스 쪽 삭제
    )

    if FILL_CUT:
        cut_edges = [e for e in result["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if cut_edges:
            bmesh.ops.edgeloop_fill(bm, edges=cut_edges)

    bm.to_mesh(me)
    bm.free()
    me.update()

    if ADD_MIRROR:
        mod = obj.modifiers.new(name="Mirror_Half", type='MIRROR')
        mod.use_axis = [AXIS == 'X', AXIS == 'Y', AXIS == 'Z']
        mod.use_clip = True
        mod.use_mirror_merge = True

    print(f"[{obj.name}] {AXIS}={PLANE_OFFSET} 기준으로 '{KEEP_SIDE}' 쪽만 남김")


def main():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes:
        print("메쉬를 선택해 주세요.")
        return
    for obj in meshes:
        bisect_object(obj)
    print(f"완료: {len(meshes)}개")


main()
