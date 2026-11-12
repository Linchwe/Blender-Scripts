# Quad_Cleanup.py
# Blender 4.2 ~ 4.5
# Instant Meshes 등 자동 리토폴로지 결과의 지저분한 부분을 한 번에 정리합니다.
#
#  [2] 엣지 중간에 낀 의미 없는 버텍스(선이 2개만 연결된 점) → 디졸브
#  [3] 평행한 두 엣지의 "중간"끼리만 이어 주는 의미 없는 엣지 → 제거
#  [1] 엣지 흐름이 다른 엣지 중간에 수직으로 닿고 끝나는 곳(T자 교차)
#      → 그 점에서 진행 방향 반대편 버텍스로 선을 이어 N-gon을 없앰
#
# 사용법: 오브젝트 모드에서 메쉬 선택(여러 개 가능) > Scripting 탭 > 새 텍스트 > 붙여넣기
#         > 설정 확인 > Run Script
# 실행 전에 Ctrl+S 로 저장하세요. Ctrl+Z 로 되돌릴 수 있습니다.

import bpy
import bmesh
from math import radians, degrees

# ---------------- 설정 ----------------
STRAIGHT_ANGLE = 150.0     # 두 엣지가 이 각도(도) 이상이면 "일직선"으로 봄 (T자 판정 기준)
T_SPLIT_MODE = 'BOTH'      # [1] 처리 방식
                           #   'BOTH'     : 반대편 양쪽 버텍스로 선 2개 (요청하신 방식)
                           #   'QUAD_TRI' : 선 1개만 (오각형이면 쿼드 1개 + 삼각형 1개)
DISSOLVE_BOUNDARY = False  # 뚫린 테두리(반쪽 메쉬 중앙선 등) 위의 점도 정리할지
MAX_PASSES = 10            # 반복 정리 횟수 (더 이상 바뀌는 게 없으면 자동으로 멈춤)
# --------------------------------------


def tangent_dir(v, other):
    """v 에서 other 방향 벡터를 v 의 노멀 평면에 투영"""
    d = other.co - v.co
    n = v.normal
    d = d - n * d.dot(n)
    if d.length < 1e-9:
        return None
    return d.normalized()


def t_info(v):
    """v 가 T자 교차점이면 (bar 엣지 2개, stem 엣지, bar 쪽 N-gon 면) 반환, 아니면 None"""
    if not v.is_valid or v.is_boundary or len(v.link_edges) != 3:
        return None
    dirs = []
    for e in v.link_edges:
        d = tangent_dir(v, e.other_vert(v))
        if d is None:
            return None
        dirs.append((e, d))

    best = None
    for i in range(3):
        for j in range(i + 1, 3):
            ang = degrees(dirs[i][1].angle(dirs[j][1]))
            if best is None or ang > best[0]:
                best = (ang, i, j)
    if best[0] < STRAIGHT_ANGLE:
        return None

    _, i, j = best
    bar = (dirs[i][0], dirs[j][0])
    stem = dirs[3 - i - j][0]

    ngon = None
    for f in v.link_faces:
        fe = set(f.edges)
        if bar[0] in fe and bar[1] in fe:
            ngon = f
            break
    if ngon is None or len(ngon.verts) < 5:
        return None
    return bar, stem, ngon


def dissolve_valence2(bm):
    """[2] 선이 2개만 연결된 점 디졸브"""
    verts = []
    for v in bm.verts:
        if len(v.link_edges) != 2:
            continue
        if v.is_boundary and not DISSOLVE_BOUNDARY:
            continue
        verts.append(v)
    if verts:
        bmesh.ops.dissolve_verts(bm, verts=verts)
    return len(verts)


def remove_mid_to_mid_edges(bm):
    """[3] 양 끝이 모두 다른 엣지의 중간(T자)에 걸친 엣지 제거"""
    bm.normal_update()
    edges = []
    for e in bm.edges:
        a, b = e.verts
        ia = t_info(a)
        if ia is None or ia[1] is not e:
            continue
        ib = t_info(b)
        if ib is None or ib[1] is not e:
            continue
        edges.append(e)
    if edges:
        bmesh.ops.dissolve_edges(bm, edges=edges, use_verts=True, use_face_split=False)
    return len(edges)


def split_t_junctions(bm):
    """[1] T자 교차점에서 반대편 버텍스로 선을 이어 N-gon 분할"""
    bm.normal_update()
    count = 0
    candidates = [v for v in bm.verts]
    for v in candidates:
        info = t_info(v)   # 직전 분할로 모양이 바뀌었을 수 있으니 매번 새로 판정
        if info is None:
            continue
        _, _, face = info

        # v 에서 시작하는 면의 버텍스 순서
        start = None
        for l in face.loops:
            if l.vert is v:
                start = l
                break
        if start is None:
            continue
        seq = []
        l = start
        for _ in range(len(face.loops)):
            seq.append(l.vert)
            l = l.link_loop_next
        n = len(seq)

        if n % 2 == 0:
            targets = [seq[n // 2]]                       # 육각형 → 쿼드 2개
        elif T_SPLIT_MODE == 'BOTH':
            targets = [seq[(n - 1) // 2], seq[(n + 1) // 2]]
        else:
            targets = [seq[(n - 1) // 2]]

        made = False
        for t in targets:
            if not t.is_valid or t is v:
                continue
            # 이미 연결돼 있으면 건너뜀
            if any(e.other_vert(v) is t for e in v.link_edges):
                continue
            # 같은 면에 있을 때만 연결
            shared = set(v.link_faces) & set(t.link_faces)
            if not shared:
                continue
            res = bmesh.ops.connect_verts(bm, verts=[v, t])
            if res["edges"]:
                made = True
        if made:
            count += 1
            bm.normal_update()
    return count


def cleanup(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    total = {"vert": 0, "edge": 0, "tsplit": 0}
    for _ in range(MAX_PASSES):
        c2a = dissolve_valence2(bm)
        c3 = remove_mid_to_mid_edges(bm)
        c2b = dissolve_valence2(bm)
        c1 = split_t_junctions(bm)
        total["vert"] += c2a + c2b
        total["edge"] += c3
        total["tsplit"] += c1
        if c2a + c3 + c2b + c1 == 0:
            break

    bm.to_mesh(me)
    bm.free()
    me.update()
    print(f"[{obj.name}] 중간 버텍스 {total['vert']}개 디졸브, "
          f"의미 없는 엣지 {total['edge']}개 제거, T자 교차 {total['tsplit']}곳 분할")


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
