# Bisect_Half.py
# Blender 4.2 ~ 4.5
# 선택한 메쉬를 월드 X=0 (또는 Y, Z) 평면에서 정확히 잘라 한쪽 반을 지웁니다.
# 면이 중앙선에 걸쳐 있어도 그 자리에서 잘라 주므로 중앙선이 깔끔하게 남습니다.
#
# 사용법: 오브젝트 모드에서 메쉬 선택(여러 개 가능) > Scripting 탭 > 새 텍스트 > 붙여넣기
#         > 아래 설정 확인 > Run Script
# 실행 전에 Ctrl+S 로 저장해 두세요. (Ctrl+Z 로 되돌리기도 가능합니다)

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
