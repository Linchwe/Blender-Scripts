# Tri_Cleanup.py
# Blender 4.2 ~ 4.5
# 디시메이트가 끝난 삼각형 메쉬의 면 형태를 한 번에 정리합니다.
#
#  [1] 엣지 중간에 낀 의미 없는 버텍스(선이 2개만 연결된 점) → 디졸브
#  [2] 4각형 이상 면 → 전부 삼각형으로 분할
#  [3] 삼각형 하나 안에 삼각형 3개가 들어간 모양(가운데 점에 선 3개) → 가운데 점 디졸브
#  [4] 아주 얇은 삼각형의 긴 엣지 → 반대쪽 점으로 돌려서(Edge Rotate) 고른 삼각형으로
#
#  [3][4] 는 서로 영향을 주므로 더 이상 바뀌는 게 없을 때까지 번갈아 반복합니다.
#
# 안전장치
#  - 뚫린 테두리 위의 점/엣지는 기본적으로 건드리지 않음
#  - [3] 가운데 점이 튀어나와 형태를 만드는 곳은 남김
#  - [4] 모서리/주름처럼 꺾인 곳, 주변 여유가 없는 곳, 면이 뒤집힐 곳은 남김
#  - [4] Seam / Sharp 로 표시된 엣지는 건드리지 않음
#  - PROTECT_GROUP 에 "Joints" 를 넣으면 관절에 칠한 부분은 [3] 에서 보호
#
# 사용법: 오브젝트 모드에서 메쉬 선택(여러 개 가능) > Scripting 탭 > 새 텍스트 > 붙여넣기
#         > 설정 확인 > Run Script
# 실행 전에 Ctrl+S 로 저장하세요. Ctrl+Z 로 되돌릴 수 있습니다.

import bpy
import bmesh
from math import radians, degrees
from mathutils import geometry

# ---------------- 설정 ----------------
# 실행할 단계 (False 로 끄면 그 단계는 건너뜀)
DO_VALENCE2 = True        # [1] 중간 버텍스 디졸브
DO_TRIANGULATE = True     # [2] 4각형 이상 → 삼각형
DO_TRI_POLES = True       # [3] 삼각형 안 삼각형 3개 정리
DO_FLIP_SLIVERS = True    # [4] 얇은 삼각형 엣지 돌리기

# [1] 중간 버텍스
DISSOLVE_BOUNDARY = False   # 뚫린 테두리(베일 밑단, 반쪽 메쉬 중앙선 등) 위의 점도 정리할지
BOUNDARY_STRAIGHT = 170.0   # 위가 True 일 때, 양쪽 엣지가 이 각도(도) 이상 일직선인 점만 지움

# [2] 삼각형 분할
QUAD_METHOD = 'BEAUTY'      # 'BEAUTY'(고른 쪽, 권장) / 'SHORT_EDGE' / 'LONG_EDGE' / 'FIXED'
NGON_METHOD = 'BEAUTY'      # 'BEAUTY' / 'EAR_CLIP'

# [3] 삼각형 안 삼각형 3개
MAX_HEIGHT_RATIO = 0.15     # 가운데 점이 바깥 삼각형 평면에서 튀어나온 높이 / 변 길이 평균
                            #   이 값보다 튀어나오면 형태를 만드는 점으로 보고 남김
PROTECT_GROUP = ""          # 버텍스 그룹 이름을 넣으면 그 그룹에 칠해진 점은 남김 (예: "Joints")
PROTECT_WEIGHT = 0.5        # PROTECT_GROUP 웨이트가 이 값 이상이면 보호

# [4] 얇은 삼각형
SLIVER_ANGLE = 130.0        # 삼각형의 가장 큰 각이 이 값(도) 이상이면 "얇은 삼각형"
FLAT_ANGLE = 12.0           # 엣지 양쪽 면이 꺾인 각도가 이 값(도) 이하일 때만 수정 (평평한 곳만)
                            #   모서리까지 고쳐지면 6~8, 평평한데 안 고쳐지면 15~20
MIN_NEW_ANGLE = 15.0        # 돌린 뒤 두 삼각형의 가장 작은 각이 이 값(도) 이상일 때만 수정

MAX_PASSES = 10             # 반복 횟수 (더 이상 바뀌는 게 없으면 자동으로 멈춤)
# --------------------------------------


# ===================== 공통 =====================

def tri_angles(p0, p1, p2):
    """세 꼭짓점의 각도(라디안)"""
    out = []
    for a, b, c in ((p0, p1, p2), (p1, p2, p0), (p2, p0, p1)):
        u = b - a
        w = c - a
        if u.length == 0.0 or w.length == 0.0:
            return [0.0, 0.0, 0.0]
        out.append(u.angle(w))
    return out


# ===================== [1] 중간 버텍스 =====================

def boundary_straight(v):
    a, b = (e.other_vert(v) for e in v.link_edges)
    d1 = a.co - v.co
    d2 = b.co - v.co
    if d1.length == 0.0 or d2.length == 0.0:
        return True
    return degrees(d1.angle(d2)) >= BOUNDARY_STRAIGHT


def dissolve_valence2(bm):
    verts = []
    for v in bm.verts:
        if len(v.link_edges) != 2:
            continue
        if v.is_boundary:
            if not DISSOLVE_BOUNDARY or not boundary_straight(v):
                continue
        verts.append(v)
    if verts:
        bmesh.ops.dissolve_verts(bm, verts=verts)
    return len(verts)


# ===================== [2] 삼각형 분할 =====================

def triangulate_all(bm):
    targets = [f for f in bm.faces if len(f.verts) > 3]
    if targets:
        bmesh.ops.triangulate(bm, faces=targets,
                              quad_method=QUAD_METHOD, ngon_method=NGON_METHOD)
    return len(targets)


# ===================== [3] 삼각형 안 삼각형 3개 =====================

def outer_verts(v):
    return [e.other_vert(v) for e in v.link_edges]


def is_tri_pole(v, deform_layer, group_index):
    if v.is_boundary or not v.is_manifold:
        return False
    if len(v.link_edges) != 3 or len(v.link_faces) != 3:
        return False
    if any(len(f.verts) != 3 for f in v.link_faces):
        return False

    a, b, c = outer_verts(v)
    if set(a.link_faces) & set(b.link_faces) & set(c.link_faces):
        return False

    if deform_layer is not None and group_index is not None:
        if v[deform_layer].get(group_index, 0.0) >= PROTECT_WEIGHT:
            return False

    size = ((a.co - b.co).length + (b.co - c.co).length + (c.co - a.co).length) / 3.0
    if size == 0.0:
        return False
    normal = geometry.normal((a.co, b.co, c.co))
    if normal.length == 0.0:
        return False
    height = abs((v.co - a.co).dot(normal))
    return height / size <= MAX_HEIGHT_RATIO


def dissolve_tri_poles(bm, deform_layer, group_index):
    picked = []
    blocked = set()
    for v in bm.verts:
        if v in blocked:
            continue
        if not is_tri_pole(v, deform_layer, group_index):
            continue
        picked.append(v)
        blocked.add(v)
        for n in outer_verts(v):
            blocked.add(n)
    if picked:
        bmesh.ops.dissolve_verts(bm, verts=picked)
    return len(picked)


# ===================== [4] 얇은 삼각형 =====================

def opposite_vert(face, edge):
    for v in face.verts:
        if v is not edge.verts[0] and v is not edge.verts[1]:
            return v
    return None


def check_flip(e, sliver_thr, flat_thr, min_new):
    if not e.is_manifold or e.is_boundary or e.seam or not e.smooth:
        return None
    if len(e.link_faces) != 2:
        return None
    f1, f2 = e.link_faces
    if len(f1.verts) != 3 or len(f2.verts) != 3:
        return None

    a, b = e.verts
    # 돌리면 a, b 의 연결선이 하나씩 줄어듦 → 3개 이하면 망가진 면이 생기므로 제외
    if len(a.link_edges) <= 3 or len(b.link_edges) <= 3:
        return None

    c = opposite_vert(f1, e)
    d = opposite_vert(f2, e)
    if c is None or d is None or c is d:
        return None

    if e.calc_face_angle(10.0) > flat_thr:
        return None

    ang_c = (a.co - c.co).angle(b.co - c.co, 0.0)
    ang_d = (a.co - d.co).angle(b.co - d.co, 0.0)
    if max(ang_c, ang_d) < sliver_thr:
        return None

    for le in c.link_edges:
        if le.other_vert(c) is d:
            return None

    old_min = min(min(tri_angles(a.co, b.co, c.co)), min(tri_angles(a.co, b.co, d.co)))
    new_min = min(min(tri_angles(c.co, d.co, a.co)), min(tri_angles(d.co, c.co, b.co)))
    if new_min < min_new or new_min <= old_min:
        return None

    n_old = f1.normal + f2.normal
    if n_old.length == 0.0:
        return None
    n1 = (d.co - c.co).cross(a.co - c.co)
    n2 = (c.co - d.co).cross(b.co - d.co)
    if n1.length == 0.0 or n2.length == 0.0:
        return None
    if n1.dot(n_old) * n2.dot(n_old) <= 0.0:
        return None

    return new_min - old_min


def flip_slivers(bm, sliver_thr, flat_thr, min_new):
    bm.normal_update()
    cands = []
    for e in bm.edges:
        score = check_flip(e, sliver_thr, flat_thr, min_new)
        if score is not None:
            cands.append((score, e))
    cands.sort(key=lambda t: -t[0])

    touched = set()
    count = 0
    for _, e in cands:
        if not e.is_valid:
            continue
        if any(f in touched for f in e.link_faces):
            continue
        new_e = bmesh.utils.edge_rotate(e, False)
        if new_e is None:
            continue
        for f in new_e.link_faces:
            touched.add(f)
        count += 1
    return count


# ===================== 실행 =====================

def count_slivers(bm, sliver_thr):
    n = 0
    for f in bm.faces:
        if len(f.verts) == 3 and max(tri_angles(*(v.co for v in f.verts))) >= sliver_thr:
            n += 1
    return n


def cleanup(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    deform_layer = None
    group_index = None
    if PROTECT_GROUP:
        vg = obj.vertex_groups.get(PROTECT_GROUP)
        if vg is None:
            print(f"[{obj.name}] '{PROTECT_GROUP}' 버텍스 그룹이 없어 보호 없이 진행합니다.")
        else:
            group_index = vg.index
            deform_layer = bm.verts.layers.deform.verify()

    sliver_thr = radians(SLIVER_ANGLE)
    flat_thr = radians(FLAT_ANGLE)
    min_new = radians(MIN_NEW_ANGLE)

    faces_before = len(bm.faces)
    slivers_before = count_slivers(bm, sliver_thr)
    stat = {"val2": 0, "tri": 0, "pole": 0, "flip": 0}

    # [1] → [2]
    if DO_VALENCE2:
        for _ in range(MAX_PASSES):
            c = dissolve_valence2(bm)
            stat["val2"] += c
            if c == 0:
                break
    if DO_TRIANGULATE:
        stat["tri"] += triangulate_all(bm)

    # [3] ↔ [4] 번갈아 반복
    for _ in range(MAX_PASSES):
        changed = 0
        if DO_TRI_POLES:
            c = dissolve_tri_poles(bm, deform_layer, group_index)
            stat["pole"] += c
            changed += c
        if DO_FLIP_SLIVERS:
            c = flip_slivers(bm, sliver_thr, flat_thr, min_new)
            stat["flip"] += c
            changed += c
        if DO_VALENCE2:
            c = dissolve_valence2(bm)
            stat["val2"] += c
            changed += c
        if DO_TRIANGULATE:
            stat["tri"] += triangulate_all(bm)
        if changed == 0:
            break

    faces_after = len(bm.faces)
    slivers_after = count_slivers(bm, sliver_thr)
    non_tri = sum(1 for f in bm.faces if len(f.verts) != 3)

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.update()
    print(f"[{obj.name}] 면 {faces_before} → {faces_after} | "
          f"중간 버텍스 {stat['val2']}개 디졸브, 4각형 이상 {stat['tri']}개 분할, "
          f"삼각형 안 삼각형 {stat['pole']}곳 정리, 얇은 삼각형 엣지 {stat['flip']}개 돌림 | "
          f"얇은 삼각형 {slivers_before} → {slivers_after}개, 삼각형 아닌 면 {non_tri}개")


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
