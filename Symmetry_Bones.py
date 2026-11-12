# Symmetry_Bones.py
# Blender 4.2 ~ 4.5
# 아마추어의 왼쪽(Left) 본 위치와 롤(Roll)을 오른쪽(Right) 본에 X축 대칭으로 그대로 복사합니다.
# 왼쪽 본만 손으로 위치를 다듬은 뒤 오른쪽을 똑같이 맞추는 용도입니다.
# (SkinTokens, AccuRIG, Mixamo, Rigify 메타리그 등 블렌더에서 다루는 리그에 사용)
#
#  - 아래 이름 규칙 중 하나로 짝이 되는 Left / Right 본을 자동으로 찾습니다.
#      mixamorig:LeftArm     ↔ mixamorig:RightArm      (Mixamo, SkinTokens Mixamo 규칙)
#      CC_Base_L_Upperarm    ↔ CC_Base_R_Upperarm      (AccuRIG / Character Creator)
#      upperarm_l / arm.l    ↔ upperarm_r / arm.r      (소문자 l/r 규칙. 블렌더에서 만든 리그용)
#      upper_arm.L / Arm_L   ↔ upper_arm.R / Arm_R     (블렌더/Rigify 메타리그 규칙, .L.001 같은 번호도 인식)
#
#  ※ Rigify 는 생성된 리그가 아니라 메타리그에서 실행한 뒤 다시 Generate 하세요.
#  ※ 언리얼에서 가져온 스켈레톤(마네킹, 메타휴먼)은 이름은 인식되지만 이 스크립트로 고치지 마세요.
#     좌우 본 축 규칙이 달라 롤이 틀어질 수 있고, 메타휴먼은 얼굴/보정 리그가 본 위치에 묶여 있습니다.
#  - 오른쪽 본의 head(시작점), tail(끝점)을 왼쪽 본의 X 좌표만 뒤집은 위치로 옮깁니다.
#  - 롤(본이 자기 축으로 비틀린 각도)은 부호를 뒤집어 복사합니다. (블렌더 Symmetrize 와 같은 방식)
#    → 좌우 팔을 같은 값으로 돌렸을 때 양쪽이 거울처럼 같은 방향으로 움직임
#  - 짝이 없는 본(척추, 머리 등 가운데 본)은 건드리지 않습니다.
#
# 주의
#  - 좌표는 아마추어 오브젝트 기준(로컬)입니다. 아마추어 원점이 몸 중앙(X=0)에 있어야 대칭이 맞습니다.
#  - 스킨된 캐릭터의 본 위치를 바꾸면 그만큼 메쉬 변형도 달라집니다. 크게 옮겼다면
#    포즈를 몇 개 잡아 보고 웨이트를 확인하세요.
#
# 사용법: 아마추어를 선택 > Scripting 탭 > 새 텍스트 > 붙여넣기 > 설정 확인 > Run Script
#         (에디트 모드로 자동 전환했다가 끝나면 오브젝트 모드로 돌아갑니다)
# 실행 전에 Ctrl+S 로 저장하세요. Ctrl+Z 로 되돌릴 수 있습니다.

import bpy
import re

# ---------------- 설정 ----------------
SOURCE_SIDE = 'LEFT'   # 'LEFT' : 캐릭터 왼쪽(Left/L) 본을 기준으로 오른쪽에 복사
                       # 'RIGHT': 캐릭터 오른쪽(Right/R) 본을 기준으로 왼쪽에 복사
COPY_ROLL = True       # 롤도 대칭으로 복사할지 (False 면 위치만 복사)
# --------------------------------------

# 이름 규칙: (왼쪽 찾기, 왼쪽→오른쪽 바꿈, 오른쪽 찾기, 오른쪽→왼쪽 바꿈) - 위에서부터 순서대로 시도
NAME_RULES = [
    (r'Left',      'Right',  r'Right',     'Left'),    # mixamorig:LeftArm
    (r'_L_',       '_R_',    r'_R_',       '_L_'),     # CC_Base_L_Upperarm
    (r'^L_',       'R_',     r'^R_',       'L_'),      # L_Arm
    (r'([._])L((?:\.\d+)?)$',  r'\1R\2',   r'([._])R((?:\.\d+)?)$',  r'\1L\2'),   # Arm.L / Arm_L / DEF-upper_arm.L.001
    (r'([._])l((?:\.\d+)?)$',  r'\1r\2',   r'([._])r((?:\.\d+)?)$',  r'\1l\2'),   # upperarm_l
]


def to_other_side(name, from_left):
    """기준 쪽 본 이름이면 반대쪽 이름을 반환, 아니면 None"""
    for left_pat, to_right, right_pat, to_left in NAME_RULES:
        if from_left and re.search(left_pat, name):
            return re.sub(left_pat, to_right, name, count=1)
        if not from_left and re.search(right_pat, name):
            return re.sub(right_pat, to_left, name, count=1)
    return None


arm = bpy.context.object

# 아마추어가 선택돼 있는지 확인
if arm is None or arm.type != 'ARMATURE':
    raise RuntimeError("Armature를 선택한 상태에서 실행하세요.")

# 본 위치/롤은 에디트 모드에서만 바꿀 수 있으므로 에디트 모드로 전환
if arm.mode != 'EDIT':
    bpy.ops.object.mode_set(mode='EDIT')

bones = arm.data.edit_bones
from_left = (SOURCE_SIDE == 'LEFT')

count = 0      # 대칭 복사한 본 개수
skipped = []   # 짝을 못 찾은 본

for src in bones:
    dst_name = to_other_side(src.name, from_left)
    if dst_name is None or dst_name == src.name:
        continue   # 기준 쪽 본이 아님 (가운데 본 또는 반대쪽 본)

    dst = bones.get(dst_name)
    if dst is None:
        skipped.append(src.name)
        continue

    # X 는 부호만 뒤집고, Y/Z 는 그대로 복사
    dst.head = (-src.head.x, src.head.y, src.head.z)
    dst.tail = (-src.tail.x, src.tail.y, src.tail.z)

    # 롤은 부호를 뒤집어 복사 (거울 대칭)
    if COPY_ROLL:
        dst.roll = -src.roll

    count += 1
    print(f"[MIRROR] {src.name} -> {dst.name}")

for name in skipped:
    print(f"[SKIP] 대응 본 없음: {name}")

# 오브젝트 모드로 돌아가면서 바뀐 본 위치가 확정됨
bpy.ops.object.mode_set(mode='OBJECT')

side = "Left → Right" if from_left else "Right → Left"
print(f"완료: {count}개 본을 {side}로 대칭 복사했습니다. (롤 복사: {'켜짐' if COPY_ROLL else '꺼짐'})")
if count == 0:
    print("짝이 되는 본을 하나도 찾지 못했습니다. 본 이름 규칙을 확인해 주세요.")
