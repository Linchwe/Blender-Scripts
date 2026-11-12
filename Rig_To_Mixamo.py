# Rig_To_Mixamo.py
# Blender 4.2 ~ 4.5
# 어떤 리그든 본 이름과 부모-자식 관계를 믹사모(Mixamo) 리그 규격으로 바꿉니다.
# 다른 프로그램에서 리깅한 캐릭터에 믹사모 애니메이션을 입히거나, 믹사모 리그를 받는 도구
# (MoCapAnything, Kimodo 등)에 넣기 전에 쓰는 용도입니다.
#
# 알아보는 리그 (본 이름으로 구분)
#  - 믹사모                     mixamorig:LeftArm, mixamorig1:LeftArm ...
#  - 언리얼 마네킹 (UE4, UE5)   pelvis, spine_01, upperarm_l, thumb_01_l ...
#  - AccuRIG / Character Creator CC_Base_Hip, CC_Base_L_Upperarm ...
#  - VRoid                      J_Bip_C_Hips, J_Bip_L_UpperArm ...
#  - 블렌더 Rigify (생성된 리그) DEF-spine, DEF-upper_arm.L ...
#  - 3ds Max Biped               Bip01 Pelvis, Bip01 L UpperArm, Bip01 L Finger0 ...
#  - DAZ (Genesis)               hip, lShldrBend, lForearmBend ...
#  - 블렌더에서 직접 만든 리그   upper_arm.L, thigh.R, Arm_L ...
#  - 이름으로 알 수 없는 리그    bone_0, bone_1 ... → 뼈대 연결 구조와 위치로 골반, 척추, 팔, 다리, 손가락을 찾음
#                                (사람 형태의 리그만 가능)
#
# 하는 일
#  0) 메시를 움직이지 않는 본(Deform 꺼진 컨트롤, IK, 끝 뼈 등)을 먼저 지웁니다.
#  1) 믹사모 본(Hips, Spine~Spine2, Neck, Head, 어깨~손, 손가락 3마디, 허벅지~발끝)에 해당하는 본을 찾아
#     mixamorig: 이름으로 바꾸고 믹사모와 같은 부모-자식 관계로 다시 연결합니다.
#     (버텍스 그룹 이름도 같이 바뀌어 웨이트는 그대로 따라갑니다)
#  2) 믹사모에 없는 보조 본은 지우고, 그 웨이트를 가장 가까운 믹사모 본에 합칩니다.
#       트위스트 본, 루트 본, 손바닥 본(metacarpal, carpal), 남는 척추/목 마디, 보정 본 등
#       척추가 4개 이상이면 Spine, Spine1, Spine2 세 개로 나눠 합칩니다.
#  3) 믹사모에 대응이 없는 본(머리카락, 치마, 꼬리, 얼굴, 가슴 등)은 그대로 남겨 둡니다. (KEEP_EXTRA_BONES)
#     믹사모 애니메이션에는 이 본의 움직임이 없으므로 부모 본을 따라 움직입니다.
#  4) 척추, 목, 어깨 본이 없는 리그는 웨이트 없는 빈 본을 만들어 믹사모 계층을 채웁니다.
#
# 주의
#  - 캐릭터가 블렌더 Front 뷰에서 정면(-Y)을 보고, 위쪽이 +Z 라고 가정합니다. (캐릭터 왼쪽 = +X)
#  - 손가락이나 발가락이 없는 리그는 그 본을 새로 만들지 않습니다. (웨이트를 새로 칠해야 하기 때문)
#  - 루트 본을 지우므로 언리얼 루트 모션 정보는 사라집니다. (믹사모는 Hips 가 가장 위의 본)
#  - 3ds Max Biped 처럼 허벅지가 Spine 아래, 쇄골이 Neck 아래에 붙은 리그도 믹사모 순서로 다시 붙입니다.
#  - 실행 후 콘솔(Window > Toggle System Console)에 원래 이름 → 믹사모 이름 목록, 지운 본, 남긴 본,
#    새로 만든 빈 본이 나옵니다. 이상한 짝이 있으면 Ctrl+Z 로 되돌리고 그 본 이름을 확인하세요.
#  - 이 스크립트는 이름과 계층만 바꿉니다. 본 방향(롤), 끝 뼈(HeadTop_End 등), 단위까지 믹사모와 똑같이
#    맞추려면 이어서 SkinTokens_Fix_Bones.py(본 정리), SkinTokens_Fix_Weights.py(웨이트 정리)를 실행하세요.
#    (이름은 SkinTokens 지만 믹사모 이름 리그면 어떤 리그든 됩니다)
#
# 사용법: 오브젝트 모드에서 아마추어 선택 > Scripting 탭 > 새 텍스트 > 붙여넣기 > 설정 확인 > Run Script
# 실행 전에 Ctrl+S 로 저장하세요. Ctrl+Z 로 되돌릴 수 있습니다.

import bpy
import re
from mathutils import Vector

# ---------------- 설정 ----------------
KEEP_EXTRA_BONES = True          # True : 믹사모에 대응이 없는 본(머리카락, 치마, 꼬리 등)을 남겨 둠
                                 # False: 그 본들도 지우고 웨이트를 가장 가까운 믹사모 본에 합침
PREFIX           = "mixamorig:"  # 바꿀 이름 앞에 붙는 글자 (믹사모 기본값)
# --------------------------------------

SIDES = ("Left", "Right")
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")

arm = bpy.context.active_object
if arm is None or arm.type != 'ARMATURE':
    arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    if len(arms) != 1:
        raise Exception("아마추어 오브젝트를 선택한 뒤 실행하세요.")
    arm = arms[0]
if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm


def skinned_meshes():
    return [o for o in bpy.context.scene.objects if o.type == 'MESH' and
            any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)]


# ---- 0) 메시를 움직이지 않는 본(컨트롤, IK, 끝 뼈 등 Deform 꺼진 본) 먼저 지우기 -------------------------
#      (Rigify 처럼 컨트롤 본 아래에 실제 본이 붙어 있는 리그도 실제 본끼리 연결해서 봄)
bpy.ops.object.mode_set(mode='EDIT')
_eb = arm.data.edit_bones
_nd = [e.name for e in _eb if not e.use_deform]
if len(_nd) < len(_eb):
    for name in _nd:
        e = _eb[name]
        p = e.parent
        while p is not None and not p.use_deform:
            p = p.parent
        for k in list(e.children):
            k.use_connect = False
            k.parent = p
    for name in _nd:
        _eb.remove(_eb[name])
bpy.ops.object.mode_set(mode='OBJECT')
if _nd:
    print(f"[정리] 메시를 움직이지 않는 본(Deform 꺼짐) {len(_nd)}개를 지웠습니다")

bones = arm.data.bones
mw = arm.matrix_world
H = {b.name: mw @ b.head_local for b in bones}

# 본마다 웨이트 합계 (웨이트가 있는 본 = 실제로 메시를 움직이는 본)
wsum = {}
for o in skinned_meshes():
    gname = {g.index: g.name for g in o.vertex_groups}
    for v in o.data.vertices:
        for g in v.groups:
            n = gname.get(g.group)
            if n is not None and g.weight > 0.0:
                wsum[n] = wsum.get(n, 0.0) + g.weight


def weighted(b):
    return wsum.get(b.name, 0.0) > 1e-4


def sub_weighted(b):
    return weighted(b) or any(weighted(k) for k in b.children_recursive)


# ---- 이름으로 본 종류 알아보기 ------------------------------------------------------------
def strip_prefix(n):
    n = n.split(":")[-1]
    n = re.sub(r"^(CC_Base_|J_Bip_|J_Adj_|J_Sec_|DEF-|ORG-|MCH-|Bip\d+\s*|mixamorig\d*)", "", n, flags=re.I)
    return n


def side_of(name):
    n = strip_prefix(name)
    if re.search(r"left", n, re.I):
        return "Left"
    if re.search(r"right", n, re.I):
        return "Right"
    if re.search(r"(^|[^A-Za-z])[Ll]([^A-Za-z]|$)", n) or re.match(r"^l[A-Z]", n):
        return "Left"
    if re.search(r"(^|[^A-Za-z])[Rr]([^A-Za-z]|$)", n) or re.match(r"^r[A-Z]", n):
        return "Right"
    return None


HELPER_WORDS = ("twist", "roll", "share", "metacarpal", "carpal", "palm", "corrective", "adjust", "helper",
                "nub", "_end", ".end", "end_", "tip", "pole", "target", "ik_", "_ik", "ctrl", "mch", "root",
                "bend_", "jiggle", "adj_")


def plain(name):
    n = strip_prefix(name)
    n = re.sub(r"^[lr](?=[A-Z])", "", n)                              # DAZ: lShldrBend -> ShldrBend
    n = re.sub(r"(left|right)", "", n, flags=re.I)
    n = re.sub(r"(^|[^A-Za-z])[LlRrCc](?=[^A-Za-z]|$)", r"\1", n)    # _L_, .L, _l, ' L ' 등 제거
    return n.lower()


def is_helper(name):
    n = name.lower()
    if re.search(r"(^|[^a-z])(c|l|r)?_?(bend)$", n):
        return False
    return any(w in n for w in HELPER_WORDS) or n.startswith("ik") or n == "root"


def part_of(name):
    """(부위, 손가락 번호) 를 돌려줌. 손가락은 ('Index', 마디) 형태"""
    p = plain(name)
    if "toe" in p or "ball" in p:
        return ("toe", None)
    m = re.search(r"finger\s*(\d)(\d)?", p)                         # 3ds Max Biped: Finger0, Finger01 ...
    if m:
        return ("finger", (FINGERS[min(int(m.group(1)), 4)], int(m.group(2) or 0) + 1))
    for words, f in ((("thumb",), "Thumb"), (("index",), "Index"), (("middle", "mid"), "Middle"),
                     (("ring",), "Ring"), (("pinky", "little", "small"), "Pinky")):
        if any(w in p for w in words):
            d = re.findall(r"(\d+)", p)
            return ("finger", (f, int(d[-1]) if d else None))
    if any(w in p for w in ("forearm", "lowerarm", "lower_arm", "elbow")):
        return ("forearm", None)
    if any(w in p for w in ("upperarm", "upper_arm", "uparm", "shldr")):
        return ("arm", None)
    if any(w in p for w in ("shoulder", "clavicle", "collar")):
        return ("shoulder", None)
    if re.search(r"(^|[^a-z])arm([^a-z]|$)", p) or p == "arm":
        return ("arm", None)
    if "hand" in p or "wrist" in p:
        return ("hand", None)
    if any(w in p for w in ("thigh", "upperleg", "upper_leg", "upleg")):
        return ("upleg", None)
    if any(w in p for w in ("calf", "shin", "lowerleg", "lower_leg", "knee")) or re.search(r"(^|[^a-z])leg([^a-z]|$)", p):
        return ("leg", None)
    if "foot" in p or "ankle" in p:
        return ("foot", None)
    if "metatarsal" in p:
        return ("foot", None)
    if "head" in p and "headtop" not in p:
        return ("head", None)
    if "neck" in p:
        return ("neck", None)
    if any(w in p for w in ("hips", "pelvis", "hip")):
        return ("hips", None)
    if any(w in p for w in ("spine", "chest", "waist", "torso", "abdomen", "back")):
        return ("spine", None)
    return (None, None)


INFO = {b.name: (side_of(b.name), part_of(b.name)) for b in bones}


def depth(b):
    d = 0
    while b.parent:
        d += 1
        b = b.parent
    return d


def first(cands):
    cands = [b for b in cands if b is not None]
    return min(cands, key=depth) if cands else None


def find_part(part, side, under=None):
    c = [b for b in bones if INFO[b.name][1][0] == part and INFO[b.name][0] == side
         and not is_helper(b.name) and (under is None or b == under or under in b.parent_recursive)]
    return first(c)


def lca(*bs):
    bs = [b for b in bs if b is not None]
    if not bs:
        return None
    anc = [[b] + list(b.parent_recursive) for b in bs]
    for a in anc[0]:
        if all(a in x for x in anc[1:]):
            return a
    return None


def path_down(top, bottom):
    """top 아래에서 bottom 까지 (top, bottom 제외)"""
    out = []
    b = bottom.parent
    while b is not None and b != top:
        out.append(b)
        b = b.parent
    return list(reversed(out)) if b == top else []


# ---- 1) 이름으로 찾기 ----------------------------------------------------------------------
M = {}                    # 믹사모 이름(PREFIX 없이) -> 원래 본
limb = {}
for s in SIDES:
    a = find_part("arm", s)
    fa = find_part("forearm", s, a) if a else find_part("forearm", s)
    h = find_part("hand", s, fa) if fa else find_part("hand", s)
    ul = find_part("upleg", s)
    lg = find_part("leg", s, ul) if ul else find_part("leg", s)
    ft = find_part("foot", s, lg) if lg else find_part("foot", s)
    limb[s] = dict(Arm=a, ForeArm=fa, Hand=h, UpLeg=ul, Leg=lg, Foot=ft)

named_ok = all(limb[s][k] is not None for s in SIDES for k in ("Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot"))
method = "이름으로"


# ---- 1') 이름으로 못 찾으면 뼈대 구조와 위치로 찾기 ------------------------------------------
def structural():
    wb = [b for b in bones if sub_weighted(b)]

    def wkids(b):
        return [k for k in b.children if sub_weighted(k)]

    def n_desc(b):
        return sum(1 for k in b.children_recursive if sub_weighted(k))

    def chain(start, n):
        out = [start]
        cur = start
        while len(out) < n:
            ks = wkids(cur)
            if not ks:
                break
            cur = max(ks, key=lambda k: n_desc(k))
            out.append(cur)
        return out

    z = lambda b: H[b.name].z
    x = lambda b: H[b.name].x
    pelvis = next((b for b in sorted(wb, key=depth) if len(wkids(b)) >= 3), None)
    if pelvis is None:
        raise Exception("골반(다리 둘과 척추가 갈라지는 본)을 찾을 수 없습니다. 사람 형태의 리그가 아닌 것 같습니다.")
    ks = wkids(pelvis)
    spine_root = max(ks, key=n_desc)
    legs = sorted([k for k in ks if k != spine_root], key=n_desc, reverse=True)[:2]
    chest = spine_root
    while len(wkids(chest)) == 1:
        chest = wkids(chest)[0]
    cks = wkids(chest)
    if len(cks) < 3:
        raise Exception("가슴(팔 둘과 목이 갈라지는 본)을 찾을 수 없습니다.")
    neck_root = max(cks, key=z)
    arms = sorted([k for k in cks if k != neck_root], key=lambda k: abs(x(k)), reverse=True)[:2]
    out = {"Hips": pelvis}
    for s, pick in (("Left", max), ("Right", min)):
        l = pick(legs, key=x)
        a = pick(arms, key=x)
        lc = chain(l, 4)
        ac = chain(a, 4)
        if len(ac) == 3:                       # 어깨 본이 없는 리그
            ac = [None] + ac
        for nm, b in zip(("UpLeg", "Leg", "Foot", "ToeBase"), lc):
            out[s + nm] = b
        for nm, b in zip(("Shoulder", "Arm", "ForeArm", "Hand"), ac):
            if b is not None:
                out[s + nm] = b
    out["_chest"] = chest
    out["_neck_root"] = neck_root
    return out


if named_ok:
    for s in SIDES:
        for k, b in limb[s].items():
            M[s + k] = b
        t = find_part("toe", s, limb[s]["Foot"])
        if t is not None:
            M[s + "ToeBase"] = t
else:
    method = "뼈대 구조로"
    st = structural()
    for k, v in st.items():
        if not k.startswith("_"):
            M[k] = v

# ---- 2) 몸통: 골반, 척추, 목, 머리 -----------------------------------------------------------
hips = lca(M["LeftUpLeg"], M["RightUpLeg"], M["LeftArm"], M["RightArm"])
if named_ok:
    hips = lca(M["LeftUpLeg"], M["RightUpLeg"], lca(M["LeftArm"], M["RightArm"]))
# 이름이 골반(hips/pelvis)인 본이 그 위에 있으면 그 본을 Hips 로 (3ds Max Biped 는 허벅지가 Spine 아래에 붙음)
p = hips.parent
while p is not None:
    if INFO[p.name][1][0] == "hips" and INFO[p.name][0] is None and weighted(p):
        hips = p
        break
    p = p.parent
M["Hips"] = hips
chest = lca(M["LeftArm"], M["RightArm"])
while chest is not None and INFO[chest.name][1][0] in ("neck", "head") and chest.parent is not None:
    chest = chest.parent                       # 3ds Max Biped 는 쇄골이 Neck 아래에 붙음
# 어깨: 가슴과 위팔 사이의 본 (없으면 나중에 빈 본을 만듦)
for s in SIDES:
    if s + "Shoulder" in M:
        continue
    p = path_down(chest, M[s + "Arm"])
    sh = next((b for b in p if INFO[b.name][1][0] == "shoulder" and not is_helper(b.name)), None)
    if sh is None and p:
        sh = next((b for b in p if not is_helper(b.name)), None)
    if sh is not None:
        M[s + "Shoulder"] = sh

# 머리: 이름에 head 가 있는 본, 없으면 가슴 위로 이어지는 몸통 사슬의 끝
head = None
if named_ok:
    head = first([b for b in chest.children_recursive if INFO[b.name][1][0] == "head" and INFO[b.name][0] is None
                  and not is_helper(b.name)])
if head is None:
    up = [k for k in chest.children if sub_weighted(k) and k not in
          ([M.get(s + "Shoulder") for s in SIDES] + [M[s + "Arm"] for s in SIDES]) and
          not any(M[s + "Arm"] in k.children_recursive for s in SIDES)]
    if up:
        cur = max(up, key=lambda k: H[k.name].z)
        while True:
            ks = [k for k in cur.children if sub_weighted(k)]
            if len(ks) != 1:
                break
            cur = ks[0]
        head = cur
if head is None:
    raise Exception("머리 본을 찾을 수 없습니다.")
M["Head"] = head
neck_path = path_down(chest, head)
neck = next((b for b in neck_path if INFO[b.name][1][0] == "neck" and not is_helper(b.name)), None)
if neck is None and neck_path:
    neck = neck_path[0]
if neck is not None:
    M["Neck"] = neck

# 척추: 골반 위 ~ 가슴까지의 사슬을 Spine, Spine1, Spine2 세 개로 나눔
sp = [b for b in path_down(hips, chest) if not is_helper(b.name)] + [chest]
if len(sp) >= 3:
    M["Spine"], M["Spine1"], M["Spine2"] = sp[0], sp[len(sp) // 2], sp[-1]
elif len(sp) == 2:
    M["Spine"], M["Spine2"] = sp[0], sp[1]
else:
    M["Spine2"] = sp[0]

# ---- 3) 손가락 ----------------------------------------------------------------------------
for s in SIDES:
    hand = M[s + "Hand"]
    roots = []
    for f in FINGERS:
        c = [b for b in hand.children_recursive if INFO[b.name][1][0] == "finger" and INFO[b.name][1][1][0] == f
             and not is_helper(b.name) and INFO[b.name][0] in (s, None)]
        c.sort(key=depth)
        c = [b for b in c if sub_weighted(b) or b.use_deform][:3]
        if c:
            roots.append((f, c))
    if not roots:                               # 이름으로 못 찾으면 손 아래 갈래를 손가락으로 (이름은 Fix_Bones 가 위치로 다시 붙임)
        ks = [k for k in hand.children if sub_weighted(k)]
        for f, k in zip(FINGERS, ks):
            c = [k]
            while len(c) < 3:
                kk = [x for x in c[-1].children if sub_weighted(x)]
                if not kk:
                    break
                c.append(kk[0])
            roots.append((f, c))
    for f, c in roots:
        for i, b in enumerate(c, 1):
            M[f"{s}Hand{f}{i}"] = b

# 한 본이 두 자리에 쓰이지 않게 정리
seen = {}
for k in list(M):
    b = M[k]
    if b.name in seen:
        print(f"[주의] {b.name} 이(가) {seen[b.name]} 와 {k} 에 모두 해당해 {k} 는 비워 둡니다")
        del M[k]
    else:
        seen[b.name] = k

PARENT = {"Spine": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "Neck": "Spine2", "Head": "Neck"}
for s in SIDES:
    PARENT.update({s + "Shoulder": "Spine2", s + "Arm": s + "Shoulder", s + "ForeArm": s + "Arm",
                   s + "Hand": s + "ForeArm", s + "UpLeg": "Hips", s + "Leg": s + "UpLeg", s + "Foot": s + "Leg",
                   s + "ToeBase": s + "Foot"})
    for f in FINGERS:
        PARENT.update({f"{s}Hand{f}1": s + "Hand", f"{s}Hand{f}2": f"{s}Hand{f}1", f"{s}Hand{f}3": f"{s}Hand{f}2"})

print(f"[찾기] {method} 믹사모 본 {len(M)}개를 찾았습니다")
for k in sorted(M, key=lambda k: depth(M[k])):
    if M[k].name != PREFIX + k:
        print(f"   {M[k].name:40s} -> {PREFIX + k}")

# ---- 4) 지울 본과 남길 본 나누기, 웨이트 합칠 곳 정하기 ----------------------------------------
mapped = {b.name for b in M.values()}


def nearest_mapped(b):
    p = b.parent
    while p is not None:
        if p.name in mapped:
            return p.name
        p = p.parent
    return None


delete, keep = {}, []                          # 지울 본 -> 웨이트를 합칠 믹사모 본
hips_anc = {b.name for b in M["Hips"].parent_recursive}
for b in bones:
    if b.name in mapped:
        continue
    if b.name in hips_anc:                     # 루트 등 골반 위의 본
        delete[b.name] = M["Hips"].name
        continue
    tgt = nearest_mapped(b) or M["Hips"].name
    if any(k.name in mapped for k in b.children_recursive):   # 사슬 중간의 남는 마디 (남는 척추, 트위스트 등)
        delete[b.name] = tgt
        continue
    anat = INFO[b.name][1][0] is not None      # 팔/다리/손가락 이름인데 믹사모 자리를 못 받은 본 = 보조 본
    if is_helper(b.name) or anat or not sub_weighted(b) or not KEEP_EXTRA_BONES:
        delete[b.name] = tgt
    else:
        keep.append(b.name)

# ---- 5) 웨이트 합치기 ----------------------------------------------------------------------
merged = 0
for o in skinned_meshes():
    vg = o.vertex_groups
    gname = {g.index: g.name for g in vg}
    add = {}                                   # (버텍스, 합칠 본) -> 더할 웨이트
    base = {}
    for v in o.data.vertices:
        ws = {gname[e.group]: e.weight for e in v.groups if e.group in gname}
        for n, w in ws.items():
            if n in delete and w > 0.0:
                t = delete[n]
                add[(v.index, t)] = add.get((v.index, t), 0.0) + w
                base[(v.index, t)] = ws.get(t, 0.0)
    for (vi, t), w in add.items():
        g = vg.get(t) or vg.new(name=t)
        g.add([vi], base[(vi, t)] + w, 'REPLACE')
        merged += 1
    for n in delete:
        g = vg.get(n)
        if g is not None:
            vg.remove(g)

MN = {k: b.name for k, b in M.items()}

# ---- 6) 본 지우기, 믹사모 계층으로 다시 연결, 빈 본 채우기, 이름 바꾸기 --------------------------
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones
inv = mw.inverted()
for name in delete:                             # 지울 본의 자식은 남는 조상에 붙임
    e = eb.get(name)
    if e is None:
        continue
    p = e.parent
    while p is not None and p.name in delete:
        p = p.parent
    for k in list(e.children):
        k.use_connect = False
        k.parent = p
for name in delete:
    e = eb.get(name)
    if e is not None:
        eb.remove(e)

mapped_e = {k: eb[n] for k, n in MN.items() if eb.get(n)}
for e in eb:
    e.use_connect = False
# 빈 본 만들기 (척추, 목, 어깨가 없을 때)
created = []


def make(k, head, tail, parent):
    e = eb.new("__new__" + k)
    e.head, e.tail = head, tail
    e.parent = parent
    e.use_deform = True
    mapped_e[k] = e
    created.append(PREFIX + k)


hips_e, chest_e = mapped_e["Hips"], mapped_e["Spine2"]
if "Spine" not in mapped_e:
    make("Spine", hips_e.head.lerp(chest_e.head, 1 / 3), hips_e.head.lerp(chest_e.head, 2 / 3), hips_e)
if "Spine1" not in mapped_e:
    a, b = mapped_e["Spine"].head, chest_e.head
    make("Spine1", a.lerp(b, 0.5), b, mapped_e["Spine"])
if "Neck" not in mapped_e:
    make("Neck", chest_e.head.lerp(mapped_e["Head"].head, 0.6), mapped_e["Head"].head, chest_e)
for s in SIDES:
    if s + "Shoulder" not in mapped_e:
        a = mapped_e[s + "Arm"].head
        make(s + "Shoulder", chest_e.head.lerp(a, 0.35) + (a - chest_e.head) * 0.0, a, chest_e)
for k, e in mapped_e.items():                   # 믹사모 부모-자식 관계
    if k == "Hips":
        e.parent = None
    elif PARENT.get(k) in mapped_e:
        e.parent = mapped_e[PARENT[k]]
for k, e in mapped_e.items():                   # 이름 바꾸기 (겹치지 않게 두 번에)
    e.name = "__tmp__" + k
for k, e in mapped_e.items():
    e.name = PREFIX + k
for e in eb:                                    # 남긴 본의 부모가 사라졌으면 가장 가까운 본에 붙임
    if e.parent is None and not e.name.endswith("Hips"):
        e.parent = mapped_e["Hips"]
bpy.ops.object.mode_set(mode='OBJECT')
if "Armature" not in bpy.data.objects:
    arm.name = "Armature"

print(f"[정리] 보조 본 {len(delete)}개를 지우고 웨이트를 믹사모 본에 합쳤습니다 (버텍스 웨이트 {merged}개 합침)")
if keep:
    print(f"[정리] 믹사모에 없는 본 {len(keep)}개는 그대로 남겨 두었습니다: {', '.join(keep[:12])}{' ...' if len(keep) > 12 else ''}")
if created:
    print(f"[정리] 원래 리그에 없어서 웨이트 없는 빈 본을 만들었습니다: {', '.join(created)}")
missing = [k for k in PARENT if k not in mapped_e and "Hand" in k and any(f in k for f in FINGERS)]
if missing:
    print(f"[주의] 손가락 본 {len(missing)}개는 원래 리그에 없어서 만들지 않았습니다")
print(f"[완료] 믹사모 리그로 변환했습니다 (본 {len(arm.data.bones)}개). 이어서 SkinTokens_Fix_Bones.py, "
      f"SkinTokens_Fix_Weights.py 를 차례로 실행하세요.")
