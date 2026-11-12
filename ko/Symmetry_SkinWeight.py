# Symmetry_SkinWeight.py
# Blender 4.2 ~ 4.5
# 캐릭터 왼쪽(Left)의 스킨 웨이트를 오른쪽(Right)에 X축 대칭으로 복사합니다.
# 왼쪽만 웨이트를 다듬은 뒤 오른쪽을 똑같이 맞추는 용도입니다.
# SkinTokens 결과뿐 아니라 직접 리깅한 리그에도 쓸 수 있습니다. 좌우 짝은 본 이름 규칙으로 찾습니다.
#      mixamorig:LeftArm     ↔ mixamorig:RightArm      (Mixamo, SkinTokens Mixamo 규칙)
#      CC_Base_L_Upperarm    ↔ CC_Base_R_Upperarm      (AccuRIG / Character Creator)
#      L_Arm                 ↔ R_Arm
#      upper_arm.L / Arm_L   ↔ upper_arm.R / Arm_R     (블렌더/Rigify 규칙, .L.001 같은 번호도 인식)
#      upperarm_l / arm.l    ↔ upperarm_r / arm.r      (소문자 l/r 규칙)
#  ※ Rigify 는 생성된 리그의 DEF- 본 그룹에 웨이트가 들어 있으므로, 생성된 리그로 스킨된 메쉬에서 실행하면 됩니다.
#
#  1) 메쉬의 오른쪽(X-) 버텍스마다, X 를 뒤집은 위치에 가장 가까운 왼쪽(X+) 버텍스를 찾아 짝을 짓습니다.
#     (거리가 허용 거리보다 멀면 대칭점이 없는 것으로 보고 짝을 짓지 않음)
#  2) 짝을 지은 오른쪽 버텍스는 본 웨이트를 왼쪽 짝의 웨이트로 통째로 바꿉니다.
#       왼쪽 본 웨이트   → 이름이 짝인 오른쪽 본 그룹으로 (예: LeftArm → RightArm, upper_arm.L → upper_arm.R)
#       오른쪽 본 웨이트 → 왼쪽 본 그룹으로 (왼쪽에 반대쪽 웨이트가 조금 섞여 있던 경우)
#       가운데 본(척추, 목, 머리 등 이름에 좌우 표시가 없는 본) 웨이트 → 같은 그룹 그대로
#     그래서 왼쪽에서 팔 본과 가슴 본 사이를 조정한 것도 오른쪽에 똑같이 들어갑니다.
#  3) 짝을 못 찾은 오른쪽 버텍스(비대칭 옷, 홀스터 등)는 원래 웨이트를 그대로 둡니다.
#
# 좌우 기준 (캐릭터 정면에서 봤을 때)
#  - X > 0 = 화면 오른쪽 = 캐릭터의 왼쪽(Left)  → 복사 원본
#  - X < 0 = 화면 왼쪽  = 캐릭터의 오른쪽(Right) → 복사 대상
#
# 주의
#  - 좌표는 메쉬 로컬 기준입니다. 오브젝트 원점이 몸 중앙(X=0)에 있어야 짝이 맞습니다.
#  - 본 웨이트 그룹(아마추어에 있는 본 이름의 그룹)만 바꿉니다. 다른 버텍스 그룹(마스크 등)은 건드리지 않습니다.
#  - 아마추어 모디파이어가 있어야 본 그룹을 알 수 있습니다. 없으면 mixamorig: 이름 그룹만 다룹니다.
#  - 좌우 표시가 위 규칙과 다른 이름(예: 팔_왼쪽)은 가운데 본으로 보고 같은 그룹에 복사하므로 오른쪽이 망가집니다.
#    콘솔에 좌우 짝 그룹 수가 0 이면 이름 규칙이 안 맞는 것이니 Ctrl+Z 로 되돌리세요.
#  - 정확히 X=0 인 중앙선 버텍스는 건드리지 않습니다.
#  - 선택한(활성) 메쉬 하나만 처리합니다. 몸, 옷, 머리카락이 따로 된 메쉬면 메쉬마다 실행하세요.
#  - 메쉬가 좌우 대칭이 아닌 부분(비대칭 옷, 홀스터 등)은 짝이 없어서 원래 웨이트로 남습니다. 그 부분은 손으로 확인하세요.
#
# 사용법: 오브젝트 모드나 웨이트 페인트 모드에서 스킨된 메쉬 선택 > Scripting 탭 > 새 텍스트 > 붙여넣기
#         > 설정 확인 > Run Script
# 실행 전에 Ctrl+S 로 저장하세요. Ctrl+Z 로 되돌릴 수 있습니다.

import bpy
import re
from mathutils import kdtree

# 설정
TOLERANCE = 0      # 대칭점을 찾을 때 허용 거리 (메쉬 단위). 0 이면 메쉬 크기(키)의 0.5% 로 자동
                   #   m 단위 메쉬 1.8m 캐릭터면 약 0.009, cm 단위 메쉬(믹사모 FBX, 4번 스크립트를 실행한 메쉬)면 약 0.9
                   #   짝을 못 찾는 버텍스가 많으면 올리고, 엉뚱한 버텍스와 짝지어지면 내리세요

# 이름 규칙: (왼쪽 찾기, 왼쪽→오른쪽 바꿈, 오른쪽 찾기, 오른쪽→왼쪽 바꿈) - 위에서부터 순서대로 시도 (6번 본 대칭과 같음)
NAME_RULES = [
    (r'Left',      'Right',  r'Right',     'Left'),    # mixamorig:LeftArm
    (r'_L_',       '_R_',    r'_R_',       '_L_'),     # CC_Base_L_Upperarm
    (r'^L_',       'R_',     r'^R_',       'L_'),      # L_Arm
    (r'([._])L((?:\.\d+)?)$',  r'\1R\2',   r'([._])R((?:\.\d+)?)$',  r'\1L\2'),   # Arm.L / Arm_L / DEF-upper_arm.L.001
    (r'([._])l((?:\.\d+)?)$',  r'\1r\2',   r'([._])r((?:\.\d+)?)$',  r'\1l\2'),   # upperarm_l
]

obj = bpy.context.object

# 메쉬가 선택돼 있는지 확인
if obj is None or obj.type != 'MESH':
    raise RuntimeError("메시를 선택하세요.")

# 버텍스 그룹 수정은 오브젝트 모드에서 해야 바로 반영됨
mode = obj.mode
if mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')

verts = obj.data.vertices
groups = obj.vertex_groups

# 1) 본 웨이트 그룹 고르기: 아마추어 모디파이어의 본 이름과 같은 그룹 (아마추어가 없으면 mixamorig: 그룹)
arms = [m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object is not None]
if arms:
    bone_names = {b.name for a in arms for b in a.data.bones}
    is_bone = lambda n: n in bone_names
else:
    is_bone = lambda n: n.startswith("mixamorig:")


def other_side(name):
    # 왼쪽 그룹 이름 → 오른쪽 그룹 이름 (반대도), 좌우 표시가 없는 가운데 본은 그대로
    for left_pat, to_right, right_pat, to_left in NAME_RULES:
        if re.search(left_pat, name):
            return re.sub(left_pat, to_right, name, count=1)
        if re.search(right_pat, name):
            return re.sub(right_pat, to_left, name, count=1)
    return name


# 2) 허용 거리
if TOLERANCE > 0:
    tol = TOLERANCE
else:
    size = max(max(v.co[k] for v in verts) - min(v.co[k] for v in verts) for k in range(3))
    tol = size * 0.005

# 3) 오른쪽(X-) 버텍스마다 대칭 위치에 가장 가까운 왼쪽(X+) 버텍스 찾기
#  KDTree: "이 위치에서 가장 가까운 버텍스"를 빠르게 찾기 위한 구조
left_verts = [v for v in verts if v.co.x > 0]
if not left_verts:
    raise RuntimeError("X > 0 쪽 버텍스가 없습니다. 메쉬 원점이 몸 중앙에 있는지 확인하세요.")
kd = kdtree.KDTree(len(left_verts))
for v in left_verts:
    kd.insert(v.co, v.index)
kd.balance()

pairs = {}      # {오른쪽 버텍스 번호: 왼쪽 버텍스 번호}
right_total = 0
for v in verts:
    if v.co.x >= 0:
        continue
    right_total += 1
    co, li, dist = kd.find((-v.co.x, v.co.y, v.co.z))
    if li is not None and dist <= tol:
        pairs[v.index] = li

# 4) 짝지은 오른쪽 버텍스의 본 웨이트를 왼쪽 짝의 웨이트로 바꾸기
# 버텍스마다 붙어 있는 웨이트를 미리 읽어 둠 (바꾸는 중에 원본이 바뀌지 않도록)
names = {g.index: g.name for g in groups}
bone_idx = [g.index for g in groups if is_bone(g.name)]
left_w = {}
for li in set(pairs.values()):
    left_w[li] = [(names[g.group], g.weight) for g in verts[li].groups
                  if g.weight > 0 and is_bone(names[g.group])]

# 오른쪽 짝 버텍스의 기존 본 웨이트 지우기 (짝이 없는 버텍스는 그대로 둠)
targets = list(pairs.keys())
for gi in bone_idx:
    groups[gi].remove(targets)

created = []
for ri, li in pairs.items():
    for name, w in left_w[li]:
        dst = other_side(name)
        g = groups.get(dst)
        if g is None:
            g = groups.new(name=dst)
            created.append(dst)
        g.add([ri], w, 'REPLACE')

if mode != 'OBJECT':
    bpy.ops.object.mode_set(mode=mode)

side_pairs = sum(1 for gi in bone_idx if other_side(names[gi]) != names[gi] and groups.get(other_side(names[gi])))

print("=" * 60)
print("LEFT → RIGHT WEIGHT MIRROR")
print("=" * 60)
print(f"허용 거리: {tol:.4f}")
print(f"좌우 짝이 맞는 본 그룹 수: {side_pairs // 2}쌍")
if side_pairs == 0:
    print("좌우 짝 그룹을 하나도 찾지 못했습니다. 본 이름 규칙을 확인하고 Ctrl+Z 로 되돌리세요.")
print(f"오른쪽 버텍스 {right_total}개 중 {len(pairs)}개를 왼쪽 웨이트로 바꿨습니다.")
if right_total - len(pairs):
    print(f"짝을 못 찾은 {right_total - len(pairs)}개는 원래 웨이트를 그대로 뒀습니다. (비대칭 부분이면 정상)")
for n in created:
    print(f"새로 만든 그룹: {n}")
print("=" * 60)
