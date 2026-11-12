# Center_Merge.py
# Blender 4.2 ~ 4.5
#
# 용도
#  디시메이트 Symmetry 등으로 만든 좌우 대칭 메쉬에서, 중앙선(X=0) 위에 다닥다닥 몰린 버텍스들을 정리합니다.
#
# 하는 일
#  1) 메쉬의 보통 엣지 길이(중간값)를 재서 기준 길이로 씁니다.
#     "중앙선 위"와 "가까움"을 이 길이에 대한 비율로 정하므로 오브젝트 크기와 상관없이 같은 설정을 쓸 수 있습니다.
#  2) 중앙선 위의 점 중 서로 가까운 것끼리 묶어서, 묶음의 평균 위치로 하나로 합칩니다.
#     중앙선 위의 점끼리만 합치므로 좌우의 일반 버텍스는 건드리지 않습니다.
#  3) 합치면서 생긴 찌그러진 면과 엣지를 정리하고, 바뀐 게 없을 때까지(최대 MAX_PASSES 번) 반복합니다.
#  4) 중앙선 위의 점을 정확히 X=0 으로 다시 맞춰서 대칭이 깨지지 않게 합니다.
#
# 주의
#  - 오브젝트 로컬 좌표 기준입니다. 오브젝트 원점이 몸 가운데(X=0)에 있어야 합니다.
#  - MERGE_RATIO 를 너무 크게 하면 중앙선 위에서 가까이 붙은 다른 부분(윗입술과 아랫입술 등)까지 합쳐질 수 있습니다.
#  - 메쉬 전체를 처리합니다. 에디트 모드에서 고른 부분만 처리하지는 않습니다.
#
# 사용법
#  1) 오브젝트 모드에서 메쉬를 선택합니다. (여러 개 가능)
#  2) Scripting 탭 > 새 텍스트 > 붙여넣기 > 설정 확인 > Run Script
#  3) 결과는 Window > Toggle System Console 에 나옵니다. (중앙선 버텍스 수가 몇 개에서 몇 개로 줄었는지)
#  4) 실행 전에 Ctrl+S 로 저장하세요. Ctrl+Z 로 되돌릴 수 있습니다.

import bpy
import bmesh
from mathutils.kdtree import KDTree

# ---------------- 설정 ----------------
AXIS = 'X'            # 대칭 축 (보통 'X')
CENTER_TOL = 0.02     # 중앙선 판정 폭: 보통 엣지 길이의 몇 배 안쪽을 "중앙선 위"로 볼지
MERGE_RATIO = 0.5     # 합치기 기준: 중앙선 위 점끼리 거리가 보통 엣지 길이의 이 배수보다 가까우면 합침
                      #   덜 합쳐지면 0.6~0.7 로 올리고, 너무 많이 합쳐지면 0.3~0.4 로 내리세요
MAX_PASSES = 5        # 합친 뒤 다시 검사하는 횟수 (바뀐 게 없으면 자동으로 멈춤)
# --------------------------------------

AXIS_INDEX = {'X': 0, 'Y': 1, 'Z': 2}[AXIS]


def median_edge_length(bm):
    lengths = sorted(e.calc_length() for e in bm.edges)
    if not lengths:
        return 0.0
    return lengths[len(lengths) // 2]


def center_verts(bm, tol):
    return [v for v in bm.verts if abs(v.co[AXIS_INDEX]) <= tol]


def merge_pass(bm, merge_dist, tol):
    """중앙선 위 점들 중 merge_dist 보다 가까운 묶음을 하나로 합침. 합친 점 개수 반환"""
    verts = center_verts(bm, tol)
    if len(verts) < 2:
        return 0

    kd = KDTree(len(verts))
    for i, v in enumerate(verts):
        kd.insert(v.co, i)
    kd.balance()

    used = [False] * len(verts)
    targetmap = {}
    for i, v in enumerate(verts):
        if used[i]:
            continue
        used[i] = True
        # v 를 기준점으로, 가까운 중앙선 점들을 v 로 합침
        cluster = [v]
        for co, j, dist in kd.find_range(v.co, merge_dist):
            if not used[j]:
                used[j] = True
                cluster.append(verts[j])
        if len(cluster) > 1:
            # 묶음의 평균 위치로 기준점을 옮긴 뒤 나머지를 합침
            avg = sum((c.co for c in cluster), v.co * 0) / len(cluster)
            v.co = avg
            for c in cluster[1:]:
                targetmap[c] = v

    if not targetmap:
        return 0
    bmesh.ops.weld_verts(bm, targetmap=targetmap)
    return len(targetmap)


def cleanup(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    base = median_edge_length(bm)
    if base == 0.0:
        bm.free()
        print(f"[{obj.name}] 엣지가 없습니다.")
        return

    tol = base * CENTER_TOL
    merge_dist = base * MERGE_RATIO

    before_center = len(center_verts(bm, tol))
    before_total = len(bm.verts)

    merged = 0
    for _ in range(MAX_PASSES):
        c = merge_pass(bm, merge_dist, tol)
        merged += c
        if c == 0:
            break

    # 합쳐지면서 생긴 찌그러진 면/엣지 정리
    bmesh.ops.dissolve_degenerate(bm, dist=base * 0.001, edges=bm.edges[:])

    # 중앙선 위 점은 정확히 0 으로 맞춤 (대칭 유지)
    for v in center_verts(bm, tol):
        co = v.co.copy()
        co[AXIS_INDEX] = 0.0
        v.co = co

    after_center = len(center_verts(bm, tol))
    after_total = len(bm.verts)

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.update()
    print(f"[{obj.name}] 중앙선 버텍스 {before_center} → {after_center}개 "
          f"(전체 {before_total} → {after_total}), 기준 엣지 길이 {base:.5f}")


def main():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes:
        print("메쉬를 선택해 주세요.")
        return
    for obj in meshes:
        cleanup(obj)


main()
