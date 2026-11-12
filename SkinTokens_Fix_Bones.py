import bpy
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

# [4번] SkinTokens 리깅 결과의 본(뼈대) 정리 + 믹사모(Mixamo) 리그 규격으로 맞추기
# 웨이트는 5번 스크립트(SkinTokens_Fix_Weights.py)에서 정리합니다. 이 스크립트를 먼저 실행하세요.
#
# 사람 리그 (SkinTokens 노드에서 relabel 을 켜서 mixamorig: 이름이 붙은 리그)
#  1) 웨이트가 없는 메시(Icosphere 등) 지우기
#  2) 본 위치 좌우 대칭 맞추기, 몸 가운데 본(Hips~Head)은 메시의 좌우 가운데(보통 X = 0)에 놓기 (SYMMETRIZE)
#  2-1) 몸통, 팔, 다리 관절을 메시 모양에 맞추기 (FIT_BODY_JOINTS)
#     메시를 잘라 본 단면으로 각 관절을 몸 두께의 가운데에 놓습니다. 높이는 가랑이~어깨 길이에 대한 비율로 정하고
#     (전문 오토리깅 AccuRIG 결과에서 잰 비율), 무릎은 엉덩이~발목의 52%, 발목은 정강이가 굵어지기 시작하는 곳,
#     어깨는 위팔 가운데 선을 따라 찾습니다. 키나 체형이 달라도 그 메시의 비율에 맞춰 놓입니다.
#     가장 큰 메시를 몸으로 보고 씁니다. 긴 치마 등으로 가랑이를 못 찾으면 몸통과 다리는 건너뛰고 팔만 맞춥니다.
#     너무 멀리(키의 12% 넘게) 옮겨야 하는 관절은 잘못 찾은 것으로 보고 그대로 둡니다
#  3) 손가락 이름을 실제 위치로 다시 붙이기 (손목에 제일 가까운 것 = 엄지, 나머지는 앞에서부터 검지/중지/약지/소지)
#     그리고 손가락 관절을 손가락 두께의 가운데로 옮기고, 끝 마디를 실제 손끝에 맞추기 (FIX_FINGERS)
#     메시 단면으로 손가락 갈림 지점과 손끝을 찾아 마디 위치를 실제 손 관절 위치로 맞추기 (FIT_FINGER_JOINTS)
#     검지~소지는 너클을 손바닥 안으로, 두 번째/세 번째 관절은 갈림 지점~손끝을 3등분한 곳으로,
#     엄지는 뿌리를 손목 쪽 엄지 두덩 안 가운데로, 두 번째 마디를 뿌리와 세 번째 마디의 가운데(엄지 굵기의 가운데)로 옮깁니다
#  4) (선택) 팔을 T포즈로 펴고, 메시까지 그 자세로 굳히기 (T_POSE)
#  5) 뼈 끝(tail) 위치와 방향(롤)을 믹사모와 같은 규칙으로 맞추기
#  6) 믹사모에 있는 끝 뼈 추가 (HeadTop_End, 손가락 4번째 마디, Toe_End)
#  7) 끝과 끝이 맞닿은 본끼리 연결 (Connected)
#  8) 믹사모 FBX 와 같은 단위/축 구조로 바꾸기 (보이는 크기와 모습은 그대로)
#  FBX 로 내보냈다가 다시 불러온 파일이면 블렌더가 붙인 "_end" 잎 뼈를 지우고 끝 뼈의 변형(Deform)을 끕니다
#
# 동물 등 사람이 아닌 리그 (relabel 을 끄고 리깅해서 본 이름이 bone_0, bone_1 ... 인 리그)
#  - 1) 웨이트 없는 메시를 지웁니다.
#  - 본 위치(관절)는 SkinTokens 결과 그대로 두고, 위로 서 있는 본의 방향만 정리합니다 (ORIENT_BONES)
#      자식 본이 하나면 뼈 끝(tail)을 그 자식의 시작점으로, 여러 개로 갈라지면 들어온 방향을 가장 잘 잇는 자식
#      (척추 → 목처럼)으로, 그런 자식이 없으면 가장 많은 본이 이어진 자식 쪽으로 돌립니다.
#      꼬리 끝, 발끝처럼 자식이 없는 끝 본은 그 본이 움직이는 살(웨이트가 큰 버텍스)의 가운데 쪽으로 돌립니다.
#      뼈 끝이 자식 시작점과 맞닿은 본끼리 연결하고, 롤은 위쪽(+Z) 기준으로 맞춥니다. (위아래로 선 본은 앞쪽 기준)
#    쉬는 자세(rest)의 본 방향만 바꾸므로 메시 모양과 웨이트는 그대로입니다. 이어서 5번 웨이트 정리로 넘어가세요.
#    이미 애니메이션(액션)이 들어 있는 리그에는 쓰지 마세요. 본 방향이 바뀌면 기존 애니메이션이 틀어집니다.
#
# 여러 번 실행해도 됩니다. 본을 손으로 고친 뒤에는 SYMMETRIZE = False 로 다시 실행하면 손으로 고친 위치는 두고
# 손가락, 롤, 연결만 다시 맞춥니다. 손가락 본을 손으로 고쳤다면 FIX_FINGERS 도 False 로 하세요.
# 이 스크립트는 웨이트를 바꾸지 않습니다.
# 사람 리그는 블렌더 Front 뷰에서 얼굴이 보이는 방향(-Y)을 보고, 위쪽이 +Z 라고 가정합니다.

SYMMETRIZE        = True     # 좌우 비대칭 캐릭터는 False
RENAME_FINGERS    = True
FIT_BODY_JOINTS   = True     # 몸통, 팔, 다리 관절을 메시 모양에 맞춤 (사람 리그)
FIX_FINGERS       = True     # 손가락 관절을 손가락 두께의 가운데로 옮기고, 끝 마디를 실제 손끝에 맞춤
FIT_FINGER_JOINTS = True     # 메시 모양으로 손가락 마디 위치를 찾음 (FIX_FINGERS 가 True 일 때)
T_POSE            = False    # True: 팔을 수평으로 편 T포즈로 바꿈 (믹사모는 올린 메시의 자세를 그대로 씀)
ADD_END_BONES     = True
REMOVE_UNSKINNED  = True
ORIENT_BONES      = True     # (동물 등 사람이 아닌 리그) 위로 서 있는 본을 다음 관절 쪽으로 눕히고 롤을 맞춤
MIXAMO_UNITS      = True     # 믹사모 FBX 와 같은 구조: 아마추어 X 90도 회전 + 스케일 0.01, 뼈대 데이터는 cm / Y 위

FORWARD = Vector((0, -1, 0))
UP      = Vector((0, 0, 1))
RIGHT   = Vector((1, 0, 0))      # 캐릭터의 왼쪽 (화면에서는 오른쪽)
FORWARD_W, UP_W, RIGHT_W = FORWARD, UP, RIGHT
FINGER_WORDS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
FINGER_ORDER = ("Index", "Middle", "Ring", "Pinky")
CENTER_BONES = ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "HeadTop_End")

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


# 1) 웨이트 없는 메시 지우기
def remove_unskinned():
    keep = set(skinned_meshes())
    for o in [o for o in bpy.context.scene.objects if o.type == 'MESH' and o not in keep]:
        print(f"[정리] 웨이트 없는 메시 삭제: {o.name}")
        bpy.data.objects.remove(o, do_unlink=True)


# 사람 리그인지 판단: 믹사모 이름(…Hips)이 있으면 사람 리그
hips = next((b for b in arm.data.bones if b.name.endswith("Hips")), None)


def to_mixamo():
    # 아마추어 로컬 좌표 기준 방향
    w2l   = arm.matrix_world.to_3x3().inverted()
    fwd   = (w2l @ FORWARD).normalized()
    up    = (w2l @ UP).normalized()
    right = (w2l @ RIGHT).normalized()

    U = 1.0 / arm.matrix_world.to_scale().x     # 아마추어 데이터에서 1m 의 길이 (cm 구조면 100)


    P = hips.name[:-len("Hips")]          # 보통 "mixamorig:"


    def N(n):
        return P + n


    # 2) 본 위치 좌우 대칭
    def mirror_name(n):
        for a, c in (("Left", "Right"), ("left", "right"), (".L", ".R"), ("_L", "_R"), (".l", ".r"), ("_l", "_r")):
            if a in n:
                return n.replace(a, c)
            if c in n:
                return n.replace(c, a)
        return None


    def mesh_center_x():
        # 몸 가운데(좌우 대칭면)의 월드 X: 메시 전체의 왼쪽 끝과 오른쪽 끝의 가운데
        lo, hi = None, None
        for o in skinned_meshes():
            n = len(o.data.vertices)
            if n == 0:
                continue
            co = np.empty(n * 3)
            o.data.vertices.foreach_get("co", co)
            M = np.array(o.matrix_world)
            x = co.reshape(-1, 3) @ M[:3, :3].T[:, 0] + M[0, 3]
            lo = x.min() if lo is None else min(lo, x.min())
            hi = x.max() if hi is None else max(hi, x.max())
        return None if lo is None else float(lo + hi) / 2

    if SYMMETRIZE:
        cx = mesh_center_x()
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = arm.data.edit_bones
        for b in ebs:
            b.use_connect = False
        if cx is None:
            center = ebs[hips.name].head.dot(right)
        else:                                               # 몸 가운데 본은 메시의 좌우 대칭면(보통 X = 0)에 놓음
            hp = arm.matrix_world @ ebs[hips.name].head
            center = (arm.matrix_world.inverted() @ Vector((cx, hp.y, hp.z))).dot(right)

        def mirror(p):
            return p - right * (2 * (p.dot(right) - center))

        done = set()
        for b in ebs:                                       # 왼쪽/오른쪽 짝은 평균 위치로, 가운데 본은 정중앙으로
            if b.name in done:
                continue
            mn = mirror_name(b.name)
            o = ebs.get(mn) if mn else None
            if o is not None and o is not b:
                avg = (b.head + mirror(o.head)) / 2
                b.head, o.head = avg, mirror(avg)
                done.update({b.name, o.name})
            elif mn is None and b.name[len(P):] in CENTER_BONES:   # 몸 가운데 본만 정중앙으로 (머리카락, 꼬리 등 다른 본은 그대로)
                b.head = b.head - right * (b.head.dot(right) - center)
                done.add(b.name)
        bpy.ops.object.mode_set(mode='OBJECT')
        print("[대칭] 본 위치를 좌우 대칭으로 맞추고, 몸 가운데 본을 " +
              ("Hips 위치" if cx is None else f"X = {cx * 100:.2f}cm (메시 좌우 가운데)") + " 에 놓았습니다")

    # 3) 손가락 이름 다시 붙이기
    def replace_finger_word(name, new_word):
        for w in FINGER_WORDS:
            i = name.rfind(w)
            if i != -1:
                return name[:i] + new_word + name[i + len(w):]
        return None


    if RENAME_FINGERS:
        bones = arm.data.bones
        plan = []
        for side in ("Left", "Right"):
            hand = bones.get(N(side + "Hand"))
            if hand is None or len(hand.children) < 4:
                continue
            roots = list(hand.children)
            thumb = min(roots, key=lambda r: (r.head_local - hand.head_local).length)
            others = sorted([r for r in roots if r is not thumb], key=lambda r: r.head_local.dot(fwd), reverse=True)
            print(f"[손가락] {hand.name}")
            for root, word in [(thumb, "Thumb")] + list(zip(others, FINGER_ORDER)):
                print(f"   {root.name:32s} -> {word}")
                for b in [root] + list(root.children_recursive):
                    new = replace_finger_word(b.name, word)
                    if new and new != b.name:
                        plan.append((b.name, new))
        for old, new in plan:                     # 이름이 겹치지 않게 두 번에 나눠 바꿈 (버텍스 그룹도 같이 바뀜)
            bones[old].name = "__tmp__" + new
        for old, new in plan:
            bones["__tmp__" + new].name = new
        print(f"[손가락] {len(plan)}개 본 이름 변경")

    # 손 주변 메시 단면 계산용 (정점, 모서리, 모서리-면 연결, 광선 검사용 트리)
    def hand_geometry(center, radius, objs=None):
        Vs, Es, EFe, EFf, polys = [], [], [], [], []
        voff, eoff, foff = 0, 0, 0
        c = np.array(center)
        for o in (objs or skinned_meshes()):
            me = o.data
            nv, ne, nf, nl = len(me.vertices), len(me.edges), len(me.polygons), len(me.loops)
            if nv == 0 or nf == 0:
                continue
            co = np.empty(nv * 3)
            me.vertices.foreach_get("co", co)
            M = np.array(o.matrix_world)
            co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
            ev = np.empty(ne * 2, dtype=np.int64)
            me.edges.foreach_get("vertices", ev)
            ev = ev.reshape(-1, 2)
            le = np.empty(nl, dtype=np.int64)
            me.loops.foreach_get("edge_index", le)
            lv = np.empty(nl, dtype=np.int64)
            me.loops.foreach_get("vertex_index", lv)
            lt = np.empty(nf, dtype=np.int64)
            me.polygons.foreach_get("loop_total", lt)
            ls = np.empty(nf, dtype=np.int64)
            me.polygons.foreach_get("loop_start", ls)
            near = np.linalg.norm(co - c, axis=1) < radius
            ke = near[ev[:, 0]] & near[ev[:, 1]]
            emap = np.full(ne, -1, dtype=np.int64)
            emap[ke] = np.arange(ke.sum()) + eoff
            lf = np.repeat(np.arange(nf), lt)
            m = emap[le] >= 0
            EFe.append(emap[le][m])
            EFf.append(lf[m] + foff)
            Es.append(ev[ke] + voff)
            Vs.append(co)
            fv = [lv[ls[i]:ls[i] + lt[i]] for i in range(nf)]
            polys += [list(x + voff) for x in fv if near[x].all()]
            voff += nv
            eoff += int(ke.sum())
            foff += nf
        if not Vs or eoff == 0 or not polys:
            return None
        V = np.concatenate(Vs)
        E = np.concatenate(Es)
        Fe, Ff = np.concatenate(EFe), np.concatenate(EFf)
        o_ = np.argsort(Ff, kind="stable")
        bvh = BVHTree.FromPolygons([Vector(p) for p in V], polys)
        return V, E, Fe[o_], Ff[o_], bvh

    def slice_loops(G, c, n, R):
        # 점 c 를 지나고 n 에 수직인 면으로 메시를 자른 단면 고리들 (면을 공유하는 교차점끼리 한 고리)
        V, E, Fe, Ff, bvh = G
        c, n = np.array(c), np.array(n)
        d = (V - c) @ n
        s0, s1 = d[E[:, 0]], d[E[:, 1]]
        cr = np.nonzero(s0 * s1 < 0.0)[0]
        if len(cr) == 0:
            return []
        t = s0[cr] / (s0[cr] - s1[cr])
        P = V[E[cr, 0]] + (V[E[cr, 1]] - V[E[cr, 0]]) * t[:, None]
        k = np.linalg.norm(P - c, axis=1) < R
        cr, P = cr[k], P[k]
        if len(cr) == 0:
            return []
        pos = np.full(len(E), -1, dtype=np.int64)
        pos[cr] = np.arange(len(cr))
        m = pos[Fe] >= 0
        ids, fs = pos[Fe][m], Ff[m]
        par = list(range(len(cr)))

        def root(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        for i in range(1, len(fs)):
            if fs[i] == fs[i - 1]:
                a, b = root(int(ids[i])), root(int(ids[i - 1]))
                if a != b:
                    par[a] = b
        groups = {}
        for i in range(len(cr)):
            groups.setdefault(root(i), []).append(i)
        return [P[g] for g in groups.values() if len(g) >= 3]

    def ray_len(G, p, d):
        # p 에서 d 방향으로 메시 겉면까지 거리 (p 가 메시 안에 있을 때만)
        hit = G[4].ray_cast(Vector(p), Vector(d).normalized())
        if hit[0] is None or hit[1].dot(d) <= 0.0:
            return None
        return hit[3]

    # 2-1) 몸통, 팔, 다리 관절을 메시 모양에 맞추기
    #   몸통 관절 높이는 가랑이~어깨, 어깨~정수리 사이를 비율로 나누고, 앞뒤로는 몸통 단면의 가운데에 놓음.
    #   팔다리 관절은 팔다리 단면의 가운데로, 발목은 정강이가 발로 넓어지는 곳, 발가락 뿌리는 발 길이 비율로 찾음.
    #   비율은 전문 오토리깅(AccuRIG) 결과를 사람 체형 기준으로 잰 값
    BODY_RATIO = {"Hips": 0.245, "Spine": 0.415, "Spine1": 0.498, "Spine2": 0.709,   # 가랑이~어깨 높이
                  "UpLeg": 0.186,
                  "Neck": 0.213, "Head": 0.485}                                      # 어깨~정수리 높이

    def largest_loop_containing(G, c, n, R):
        n = Vector(n).normalized()
        u = n.cross(RIGHT_W) if abs(n.dot(RIGHT_W)) < 0.9 else n.cross(FORWARD_W)
        u.normalize()
        v = n.cross(u)
        best = None
        for P in slice_loops(G, c, n, R):
            q = P - np.array(c)
            pu, pv = q @ np.array(u), q @ np.array(v)
            if pu.min() <= 0.0 <= pu.max() and pv.min() <= 0.0 <= pv.max():
                area = float(np.ptp(pu) * np.ptp(pv))
                if best is None or area > best[0]:
                    best = (area, P, pu, pv, u, v)
        return best

    def center_in(G, c, n, R):
        L = largest_loop_containing(G, c, n, R)
        if L is None:
            return c.copy()
        _, P, pu, pv, u, v = L
        return c + u * float((pu.max() + pu.min()) / 2) + v * float((pv.max() + pv.min()) / 2)

    def midline_center(G, c, R):
        # 몸 가운데(좌우 중심)를 지나는 수평 단면들을 합친 범위의 앞뒤 가운데
        L = [P for P in slice_loops(G, c, UP_W, R) if P[:, 0].min() <= c.x <= P[:, 0].max()]
        if not L:
            return None
        P = np.concatenate(L)
        return Vector((c.x, float(P[:, 1].min() + P[:, 1].max()) / 2, c.z))

    def fit_body():
        body = max(skinned_meshes(), key=lambda o: len(o.data.vertices), default=None)
        if body is None:
            return
        mw = arm.matrix_world
        inv = mw.inverted()
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = arm.data.edit_bones
        Wp = {}
        for b in ebs:
            if b.name.startswith(P):
                Wp[b.name[len(P):]] = mw @ b.head
        need = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"] + \
               [s + k for s in ("Left", "Right") for k in ("Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase")]
        if any(k not in Wp for k in need):
            bpy.ops.object.mode_set(mode='OBJECT')
            print("[몸 관절] 믹사모 본이 다 있지 않아 건너뜁니다")
            return
        hips = Wp["Hips"]
        height = max((Wp["Head"] - hips).length * 3.0, 0.01)
        G = hand_geometry(hips, height, [body])
        if G is None:
            bpy.ops.object.mode_set(mode='OBJECT')
            return
        V = G[0]
        top = float(V[:, 2].max())
        cx = hips.x
        new = {}
        # 팔: 어깨는 위팔 살의 가운데 선 위로, 팔꿈치와 손목은 단면 가운데로
        for s in ("Left", "Right"):
            Ar, El, Ha = Wp[s + "Arm"], Wp[s + "ForeArm"], Wp[s + "Hand"]
            ds = (El - Ar).normalized()
            cs = []
            for t in (0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6):
                c = Ar + (El - Ar) * t
                if largest_loop_containing(G, c, ds, 0.5 * (El - Ar).length) is not None:
                    cs.append(np.array(center_in(G, c, ds, 0.5 * (El - Ar).length)))
            if len(cs) >= 4:
                C = np.array(cs)
                O = C.mean(0)
                ax = Vector(np.linalg.svd(C - O)[2][0])
                ax = ax if ax.dot(ds) > 0 else -ax
                O = Vector(O)
                new[s + "Arm"] = O + ax * (Ar - O).dot(ax)
            a2 = new.get(s + "Arm", Ar)
            d1, d2 = (El - a2).normalized(), (Ha - El).normalized()
            new[s + "ForeArm"] = center_in(G, El, d1 + d2, 0.4 * (Ha - El).length)
            new[s + "Hand"] = center_in(G, Ha, d2, 0.3 * (Ha - El).length)
        sh = (new.get("LeftArm", Wp["LeftArm"]).z + new.get("RightArm", Wp["RightArm"]).z) / 2
        # 가랑이: 몸 가운데 선을 따라 내려가다 몸통 단면이 끊기는 높이
        crotch, z = None, hips.z
        step = 0.005 * height
        while z > hips.z - 0.4 * height:
            if largest_loop_containing(G, Vector((cx, hips.y, z)), UP_W, 0.5 * height) is None:
                crotch = z
                break
            z -= step
        if crotch is None or sh - crotch < 0.1 * height:
            print("[몸 관절] 가랑이 높이를 찾지 못해 몸통과 다리는 그대로 둡니다 (치마 등)")
        else:
            span = sh - crotch
            for k in ("Hips", "Spine", "Spine1", "Spine2"):
                m = midline_center(G, Vector((cx, hips.y, crotch + BODY_RATIO[k] * span)), 0.5 * height)
                if m is not None:
                    new[k] = m
            for k in ("Neck", "Head"):
                m = midline_center(G, Vector((cx, Wp[k].y, sh + BODY_RATIO[k] * (top - sh))), 0.3 * height)
                if m is not None:
                    new[k] = m
            # 다리
            zh = crotch + BODY_RATIO["UpLeg"] * span
            L = largest_loop_containing(G, Vector((cx, hips.y, zh)), UP_W, 0.5 * height)
            for s, sg in (("Left", 1.0), ("Right", -1.0)):
                if L is not None:
                    Pp = L[1]
                    hw = float(Pp[:, 0].max() - Pp[:, 0].min()) / 2
                    pc = (Pp.max(0) + Pp.min(0)) / 2
                    hip = Vector((cx + sg * 0.47 * hw, float(pc[1]), zh))
                else:
                    hip = Wp[s + "UpLeg"]
                new[s + "UpLeg"] = hip
                # 발목: 정강이에서 가장 가는 곳 아래로, 발 쪽으로 단면이 넓어지는 정도의 63% 지점
                K, An = Wp[s + "Leg"], Wp[s + "Foot"]
                d = (An - K).normalized()
                Ls = (An - K).length
                prof = []
                for i in range(int(0.4 / 0.0125), int(1.4 / 0.0125) + 1):
                    t = i * 0.0125
                    c = K + d * (Ls * t)
                    Lp_ = largest_loop_containing(G, c, d, 0.5 * Ls)
                    prof.append((t, None if Lp_ is None else float(np.ptp(Lp_[1] @ np.array(FORWARD_W)))))
                ok = [p for p in prof if p[1] is not None and p[0] <= 1.0]
                ank = None
                if ok:
                    nar = min(ok, key=lambda p: p[1])
                    after = []
                    for p in prof:
                        if p[0] <= nar[0]:
                            continue
                        if p[1] is None or (after and p[1] < 0.6 * after[-1][1]):
                            break
                        after.append(p)
                    if after:
                        dmax = max(a[1] for a in after)
                        if dmax > 1.15 * nar[1]:
                            thr = nar[1] + 0.63 * (dmax - nar[1])
                            ta = next(a[0] for a in after if a[1] >= thr)
                            ank = center_in(G, K + d * (Ls * ta), d, 0.5 * Ls)
                if ank is None:
                    ank = center_in(G, An, d, 0.5 * Ls)
                new[s + "Foot"] = ank
                # 무릎: 엉덩이~발목의 52% 지점, 다리 단면 가운데
                kn = hip + (ank - hip) * 0.52
                n1, n2 = (kn - hip).normalized(), (ank - kn).normalized()
                new[s + "Leg"] = center_in(G, kn, n1 + n2, 0.5 * Ls)
                # 발가락 뿌리: 발뒤꿈치~발끝 길이의 60% 지점, 발 단면 아래쪽 25% 높이
                fm = (np.abs(V[:, 0] - ank.x) < 0.25 * Ls) & (V[:, 2] < ank.z) & (np.abs(V[:, 1] - ank.y) < 0.8 * Ls)
                if fm.sum() > 20:
                    fy = V[fm, 1]
                    fwd_sign = -1.0 if FORWARD_W.y < 0 else 1.0
                    heel = float(fy.max()) if fwd_sign < 0 else float(fy.min())
                    toe = float(fy.min()) if fwd_sign < 0 else float(fy.max())
                    ty = heel + 0.6 * (toe - heel)
                    Lt = largest_loop_containing(G, Vector((ank.x, ty, float(V[fm, 2].min()) + 0.02 * Ls)), Vector((0, 1, 0)), 0.5 * Ls)
                    if Lt is not None:
                        q = Lt[1]
                        new[s + "ToeBase"] = Vector((float(q[:, 0].max() + q[:, 0].min()) / 2, ty,
                                                     float(q[:, 2].min() + 0.25 * (q[:, 2].max() - q[:, 2].min()))))
        # 쇄골: 어깨 관절 높이보다 조금 위, 몸 가운데에서 어깨까지의 43% 지점
        for s in ("Left", "Right"):
            a = new.get(s + "Arm", Wp[s + "Arm"])
            new[s + "Shoulder"] = Vector((cx + 0.43 * (a.x - cx), a.y, a.z + 0.015 * (top - (crotch or hips.z))))
        if SYMMETRIZE:                                # 좌우 대칭: 왼쪽과 오른쪽 결과의 평균
            for k in list(new):
                if k.startswith("Left") and "Right" + k[4:] in new:
                    a, b = new[k], new["Right" + k[4:]]
                    m = (a + Vector((2 * cx - b.x, b.y, b.z))) / 2
                    new[k], new["Right" + k[4:]] = m, Vector((2 * cx - m.x, m.y, m.z))
        # 너무 많이 움직이면(메시가 사람 모양이 아니거나 단면을 잘못 찾음) 원래 위치 유지
        moved = 0
        for k, p in new.items():
            if (p - Wp[k]).length > 0.12 * height:
                print(f"[몸 관절] {k}: 찾은 위치가 원래 위치와 너무 멀어 그대로 둡니다")
                continue
            ebs[P + k].head = inv @ p
            moved += 1
        bpy.ops.object.mode_set(mode='OBJECT')
        print(f"[몸 관절] 관절 {moved}개를 메시 모양에 맞춤 (가랑이 높이 {'-' if crotch is None else f'{(crotch - V[:, 2].min()) / (top - V[:, 2].min()) * 100:.0f}%'})")

    # 3-1) 손가락 관절을 손가락 두께의 가운데로 맞추기
    tips = {}                                       # 손가락 끝 마디 이름 -> 손끝 위치 (아마추어 로컬)

    def fix_fingers():
        meshes = skinned_meshes()
        if not meshes:
            return
        mw = arm.matrix_world
        inv = mw.inverted()
        recs = []                                   # [메시, 번호, 월드 위치, {본: 웨이트}]
        for o in meshes:
            gname = {g.index: g.name for g in o.vertex_groups}
            for v in o.data.vertices:
                w = {gname[g.group]: g.weight for g in v.groups if g.group in gname and g.weight > 0.0}
                if w:
                    recs.append([o, v.index, o.matrix_world @ v.co, w])
        bones = arm.data.bones
        moved = 0
        bpy.ops.object.mode_set(mode='EDIT')
        ebs = arm.data.edit_bones
        for side in ("Left", "Right"):
            hand = ebs.get(N(side + "Hand"))
            if hand is None:
                continue
            chains = {}
            for f in FINGER_WORDS:
                ch = [ebs.get(N(f"{side}Hand{f}{i}")) for i in (1, 2, 3)]
                if all(ch):
                    chains[f] = ch
            if len(chains) < 2:
                continue
            HW = {b.name: mw @ b.head for ch in chains.values() for b in ch}
            hw = mw @ hand.head
            mids = [HW[ch[0].name] for ch in chains.values()]
            fwd_h = (sum(mids, Vector((0, 0, 0))) / len(mids) - hw).normalized()
            fs = list(chains)
            lat = HW[chains[fs[1]][0].name] - HW[chains[fs[-1]][0].name]
            lat = (lat - fwd_h * lat.dot(fwd_h)).normalized()
            palm_n = fwd_h.cross(lat).normalized()       # 손바닥/손등 방향
            fitted = set()                               # 메시 단면으로 마디를 맞춘 손가락
            reach = 0.0

            def finger_verts(f):
                names = {b.name for b in chains[f]}
                out = []
                for r in recs:
                    w = r[3]
                    k = max(w, key=w.get)
                    if k in names:
                        out.append(r[2])
                return out

            def center_pass():
                n_moved = 0
                for f, ch in chains.items():
                    P = finger_verts(f)
                    if len(P) < 8:
                        continue
                    pts = [HW[b.name] for b in ch]
                    corr = [None, None, None]
                    for i in range(3):
                        if i == 0:
                            ax = (pts[1] - pts[0])
                        elif i == 1:
                            ax = (pts[1] - pts[0]).normalized() + (pts[2] - pts[1]).normalized()
                        else:
                            ax = (pts[2] - pts[1])
                        if ax.length < 1e-6:
                            continue
                        ax.normalize()
                        u = (palm_n - ax * palm_n.dot(ax)).normalized()
                        v = ax.cross(u)
                        seg = (pts[1] - pts[0]).length if i == 0 else (pts[i] - pts[i - 1]).length
                        half = 0.15 * seg
                        sl = []
                        for tries in range(2):
                            sl = [p - pts[i] for p in P if abs((p - pts[i]).dot(ax)) < half]
                            if len(sl) >= 5:
                                break
                            half *= 2.0
                        if len(sl) < 5:
                            continue
                        # 한쪽으로 튄 정점(옆 손가락 등)을 빼고, 남은 단면의 양 끝 중간점 = 손가락 두께의 가운데
                        us = sorted(p.dot(u) for p in sl)
                        vs = sorted(p.dot(v) for p in sl)
                        mu, mv = us[len(us) // 2], vs[len(vs) // 2]
                        rad = sorted(((p.dot(u) - mu) ** 2 + (p.dot(v) - mv) ** 2) ** 0.5 for p in sl)
                        lim = 2.5 * rad[len(rad) // 2] + 1e-9
                        keep = [p for p in sl if ((p.dot(u) - mu) ** 2 + (p.dot(v) - mv) ** 2) ** 0.5 <= lim]
                        if len(keep) < 5:
                            continue
                        ku = [p.dot(u) for p in keep]
                        kv = [p.dot(v) for p in keep]
                        corr[i] = u * ((min(ku) + max(ku)) / 2) + v * ((min(kv) + max(kv)) / 2)
                    if f in fitted:                      # 메시 단면으로 찾은 뿌리 위치는 그대로 둠 (엄지는 두 번째 마디도)
                        corr[0] = None
                        if f == "Thumb":
                            corr[1] = None
                    elif corr[1] is not None:            # 손가락 뿌리(너클)는 손바닥 살이 섞여 단면이 부정확해서 다음 마디만큼 같이 옮김
                        corr[0] = corr[1]
                    for i, b in enumerate(ch):
                        if corr[i] is not None and corr[i].length > 1e-6:
                            HW[b.name] = HW[b.name] + corr[i]
                            b.head = inv @ HW[b.name]
                            n_moved += 1
                    # 손끝: 끝 마디 방향은 앞 마디의 연장선이 아니라 끝 마디 살의 중심 쪽 (엄지처럼 휜 손가락도 맞게)
                    p2, p3 = HW[ch[1].name], HW[ch[2].name]
                    names3 = ch[2].name
                    D = [r[2] for r in recs if max(r[3], key=r[3].get) == names3]
                    D = [q for q in D if (q - p3).dot(p3 - p2) > 0.0] or D
                    d = (p3 - p2).normalized()
                    if len(D) >= 5:
                        c3 = sum(D, Vector((0, 0, 0))) / len(D)
                        if (c3 - p3).length > 1e-5:
                            d = (c3 - p3).normalized()
                        for _ in range(2):                       # 손끝 쪽 단면의 가운데를 향하도록 한 번 더 맞춤
                            far = max((q - p3).dot(d) for q in D)
                            sl = [q for q in D if 0.55 * far < (q - p3).dot(d) < 0.95 * far]
                            if len(sl) < 3:
                                break
                            u = (palm_n - d * palm_n.dot(d)).normalized()
                            v = d.cross(u)
                            ku = [(q - p3).dot(u) for q in sl]
                            kv = [(q - p3).dot(v) for q in sl]
                            m = p3 + d * (0.75 * far) + u * ((min(ku) + max(ku)) / 2) + v * ((min(kv) + max(kv)) / 2)
                            d = (m - p3).normalized()
                    far = max((q - p3).dot(d) for q in (D or P))
                    if far > 1e-4:
                        tips[ch[2].name] = inv @ (p3 + d * far)
                return n_moved

            def section(G, c, t):
                # c 를 지나 t 에 수직인 단면 중 c 에 가장 가까운 고리: (크기, 가운데, c 에서 떨어진 거리)
                best = None
                u = (palm_n - t * palm_n.dot(t)).normalized()
                v = t.cross(u)
                for P in slice_loops(G, c, t, reach):
                    q = P - np.array(c)
                    pu, pv = q @ np.array(u), q @ np.array(v)
                    mid = c + u * float((pu.min() + pu.max()) / 2) + v * float((pv.min() + pv.max()) / 2)
                    size = float(max(pu.max() - pu.min(), pv.max() - pv.min()))
                    dist = (mid - c).length
                    if best is None or dist < best[2]:
                        best = (size, mid, dist)
                return best

            def point_on(line, s):              # 점들을 이은 선 위에서 처음부터 길이 s 만큼 간 점
                for a, b in zip(line, line[1:]):
                    l = (b - a).length
                    if s <= l and l > 1e-9:
                        return a + (b - a) * (s / l)
                    s -= l
                return line[-1].copy()

            def length_of(line):
                return sum((b - a).length for a, b in zip(line, line[1:]))

            def fit_joints():
                # 메시 단면으로 손가락 갈림 지점(web)과 손끝을 찾고, 그 사이를 실제 손가락 관절 비율로 나눔
                nonlocal reach
                ends = [mw @ tips[ch[2].name] for ch in chains.values() if ch[2].name in tips]
                if not ends:
                    return 0
                reach = max((e - hw).length for e in ends)
                G = hand_geometry(hw + fwd_h * (0.5 * reach), 0.9 * reach)
                if G is None:
                    return 0
                n_fit = 0
                for f, ch in chains.items():
                    if ch[2].name not in tips:
                        continue
                    j = [HW[b.name].copy() for b in ch] + [mw @ tips[ch[2].name]]
                    segl = [(j[i + 1] - j[i]).length for i in range(3)]
                    if min(segl) < 1e-6:
                        continue
                    L = sum(segl)

                    if f == "Thumb":
                        # 엄지: 세 번째 마디(IP)와 손끝은 그대로 두고, 뿌리(CMC)는 손목 쪽 엄지 두덩 안으로,
                        # 두 번째 마디(MCP)는 뿌리와 세 번째 마디의 가운데, 엄지 바깥쪽 굵기의 가운데로
                        ip, tip = j[2], j[3]
                        sec = section(G, (j[1] + j[2]) / 2, (j[2] - j[1]).normalized())
                        if sec is None or sec[2] > 0.5 * segl[1]:
                            print(f"[손가락 마디] {ch[0].name}: 엄지 단면을 찾지 못해 그대로 둡니다")
                            continue
                        fd = sec[0]                                  # 엄지 굵기
                        Lm = 2.25 * segl[2]                          # 뿌리~세 번째 마디 = 끝 마디 길이의 2.25 배 정도

                        def to_middle(p, out):                       # 엄지 쪽 바깥면에서 out 만큼 안쪽, 손바닥과 손등의 가운데
                            dr = ray_len(G, p, lat)
                            if dr is not None and dr > out:
                                p = p + lat * (dr - out)
                            a_, b_ = ray_len(G, p, palm_n), ray_len(G, p, -palm_n)
                            if a_ is not None and b_ is not None:
                                p = p + palm_n * ((a_ - b_) / 2)
                            return p

                        cmc = ip + (hw - ip).normalized() * Lm
                        for _ in range(3):
                            cmc = to_middle(cmc, 0.6 * fd)
                            cmc = ip + (cmc - ip).normalized() * Lm
                        if (cmc - hw).dot(fwd_h) < 0.0:              # 손목을 넘어가지 않게
                            cmc = cmc - fwd_h * (cmc - hw).dot(fwd_h)
                        mcp = (cmc + ip) / 2
                        for _ in range(2):
                            mcp = to_middle(mcp, 0.5 * fd)
                        new = [cmc, mcp, None]
                        msg = "뿌리는 엄지 두덩 안, 두 번째 마디는 엄지 가운데로"
                    else:
                        # 1) 지금 마디 선을 따라 잘라서 손가락 굵기, 손끝, 갈림 지점을 대략 찾음
                        d0 = (j[1] - j[0]).normalized()
                        d3 = (j[3] - j[2]).normalized()

                        def along(s):
                            if s <= 0.0:
                                return j[0] + d0 * s, d0
                            for i in range(3):
                                if s <= segl[i]:
                                    return j[i] + (j[i + 1] - j[i]) * (s / segl[i]), (j[i + 1] - j[i]).normalized()
                                s -= segl[i]
                            return j[3] + d3 * s, d3

                        step = L / 80.0
                        prof = []
                        for k in range(int(-0.6 * L / step), int(1.15 * L / step) + 1):
                            c, t = along(k * step)
                            sec = section(G, c, t)
                            if sec is not None:
                                prof.append((k * step,) + sec)       # (s, 크기, 가운데, 거리)
                        good = [p for p in prof if p[3] < 0.25 * L]
                        mids = [p[1] for p in good if 0.3 * L < p[0] < 0.8 * L]
                        if len(mids) < 5:
                            print(f"[손가락 마디] {ch[0].name}: 손가락 단면을 찾지 못해 그대로 둡니다")
                            continue
                        fd = sorted(mids)[len(mids) // 2]                       # 손가락 굵기
                        tip_s = None                                            # 손가락 가운데부터 끊기지 않고 이어진 마지막 단면 = 손끝
                        for p in sorted(good, key=lambda p: p[0]):
                            if p[0] < 0.5 * L:
                                continue
                            if tip_s is not None and (p[0] - tip_s > 2.5 * step or p[1] > 1.5 * fd or p[3] > 0.5 * fd):
                                break
                            tip_s = p[0]
                        if tip_s is None:
                            print(f"[손가락 마디] {ch[0].name}: 손끝을 찾지 못해 그대로 둡니다")
                            continue
                        web_s = next((p[0] for p in sorted(prof, key=lambda p: -p[0])
                                      if p[0] < tip_s and p[1] > 1.7 * fd), None)
                        if web_s is None or not (0.5 * L < tip_s - web_s < 1.6 * L):
                            print(f"[손가락 마디] {ch[0].name}: 손가락 갈림 지점을 찾지 못해 그대로 둡니다")
                            continue
                        Lf = tip_s - web_s
                        # 2) 첫 마디 살의 가운데 선(메시로 정한 손가락 방향)으로 다시 잘라서 갈림 지점을 정확히 찾음
                        base = [p[2] for p in good if web_s + 0.08 * Lf <= p[0] <= web_s + 0.35 * Lf]
                        if len(base) < 4:
                            print(f"[손가락 마디] {ch[0].name}: 첫 마디 단면이 부족해 그대로 둡니다")
                            continue
                        B = np.array([list(p) for p in base])
                        O = B.mean(0)
                        ax = Vector(np.linalg.svd(B - O)[2][0])
                        if ax.dot(j[3] - j[0]) < 0:
                            ax = -ax
                        O = Vector(O)
                        t0 = (along(web_s)[0] - O).dot(ax)
                        web_t = None
                        for k in range(0, int(1.2 * L / step)):
                            t = t0 + 0.3 * Lf - k * step * 0.5
                            sec = section(G, O + ax * t, ax)
                            if sec is not None and sec[0] > 1.7 * fd:
                                web_t = t
                                break
                        if web_t is None:
                            print(f"[손가락 마디] {ch[0].name}: 손가락 갈림 지점을 찾지 못해 그대로 둡니다")
                            continue
                        web_p = O + ax * web_t
                        # 3) 갈림 지점 ~ 손끝을 손가락 가운데 선을 따라 나눔. 실제 손에서 갈림 지점~손끝은 두 관절(PIP, DIP)로
                        #    거의 3등분되고, 너클(MCP)은 갈림 지점보다 조금 손바닥 안쪽 (첫 마디가 두 번째 마디의 1.3 배 정도)
                        cen = [p[2] for p in good if web_s + 0.08 * Lf < p[0] <= tip_s and (p[2] - web_p).dot(ax) > 0]
                        line = [web_p] + [sum(cen[i:i + 5], Vector((0, 0, 0))) / len(cen[i:i + 5])
                                          for i in range(0, max(len(cen) - 4, 1), 3)] + [along(tip_s)[0]]
                        Lc = length_of(line)
                        knk = web_p - ax * (0.12 * Lc)                         # 너클(MCP): 갈림 지점보다 손바닥 안쪽
                        a_, b_ = ray_len(G, knk, palm_n), ray_len(G, knk, -palm_n)
                        if a_ is not None and b_ is not None:                  # 손바닥 면과 손등 면의 가운데
                            knk = knk + palm_n * ((a_ - b_) / 2)
                        new = [knk, point_on(line, 0.33 * Lc), point_on(line, 0.68 * Lc)]
                        msg = "너클은 손바닥 안, 마디는 관절 비율로"
                    for i, b in enumerate(ch):
                        if new[i] is not None:
                            HW[b.name] = new[i]
                            b.head = inv @ new[i]
                    fitted.add(f)
                    n_fit += 1
                    print(f"[손가락 마디] {ch[0].name[:-1]:30s} {msg} 맞춤")
                return n_fit
            moved += center_pass()
            if FIT_FINGER_JOINTS:
                fit_joints()
            moved += center_pass()                  # 옮긴 위치 기준으로 한 번 더
            moved += center_pass()
        bpy.ops.object.mode_set(mode='OBJECT')
        print(f"[손가락 관절] 관절 위치 {moved}번 손가락 두께의 가운데로 맞춤, 끝 마디를 손끝에 맞춤")

    if FIT_BODY_JOINTS:
        fit_body()
    if FIX_FINGERS:
        fix_fingers()


    # 4) T포즈로 펴고 메시까지 굳히기
    if T_POSE:
        for o in skinned_meshes():
            if o.data.shape_keys:
                raise Exception(f"{o.name} 에 셰이프 키가 있어 T포즈로 굳힐 수 없습니다. T_POSE = False 로 실행하세요.")
        bpy.ops.object.mode_set(mode='POSE')
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        pbs = arm.pose.bones

        def aim(name, target_name, direction):
            pb, tg = pbs.get(N(name)), pbs.get(N(target_name))
            if pb is None or tg is None:
                return
            d = tg.head - pb.head
            if d.length < 1e-6:
                return
            q = d.normalized().rotation_difference(direction)
            h = pb.head.copy()
            pb.matrix = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h) @ pb.matrix
            bpy.context.view_layer.update()

        for side, s in (("Left", 1.0), ("Right", -1.0)):
            out = right * s
            aim(side + "Arm", side + "ForeArm", out)              # 위팔 수평
            aim(side + "ForeArm", side + "Hand", out)             # 아래팔 수평
            aim(side + "Hand", side + "HandMiddle1", out)         # 손바닥이 아래를 보게 손 수평

        bpy.ops.object.mode_set(mode='OBJECT')
        for o in skinned_meshes():                                # 메시를 지금 자세로 굳히고 아마추어 모디파이어 다시 연결
            mod = next(m for m in o.modifiers if m.type == 'ARMATURE' and m.object == arm)
            name, vg, env = mod.name, mod.use_vertex_groups, mod.use_bone_envelopes
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = o
            o.select_set(True)
            bpy.ops.object.modifier_apply(modifier=name)
            m = o.modifiers.new(name, 'ARMATURE')
            m.object, m.use_vertex_groups, m.use_bone_envelopes = arm, vg, env
            while o.modifiers.find(name) > 0:                     # 원래처럼 맨 위로
                bpy.ops.object.modifier_move_up(modifier=name)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = arm
        arm.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.armature_apply(selected=False)               # 지금 자세를 기본 자세(Rest)로
        bpy.ops.object.mode_set(mode='OBJECT')
        print("[T포즈] 팔을 수평으로 펴서 기본 자세로 굳혔습니다")
        tips.clear()                                              # 자세가 바뀌어 손끝 위치는 다시 계산하지 않고 기본 규칙 사용


    # 본마다 붙은 버텍스 (뼈 끝 길이 계산용)
    arm_inv = arm.matrix_world.inverted()
    bone_verts = {}
    weighted = set()
    for o in skinned_meshes():
        mat = arm_inv @ o.matrix_world
        gname = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            for g in v.groups:
                n = gname.get(g.group)
                if n is not None and g.weight > 0.0:
                    weighted.add(n)
                if n is not None and g.weight > 0.3:
                    bone_verts.setdefault(n, []).append(mat @ v.co)


    # 5), 6) 뼈 끝 위치, 끝 뼈, 롤
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = arm.data.edit_bones
    for b in ebs:
        b.use_connect = False

    PREFERRED = {"Hips": "Spine", "Spine2": "Neck", "LeftHand": "LeftHandMiddle1", "RightHand": "RightHandMiddle1"}


    def short(b):
        return b.name[len(P):] if b.name.startswith(P) else b.name


    def extent(b, d, fallback):
        vs = bone_verts.get(b.name)
        L = max(((co - b.head).dot(d) for co in vs), default=0.0) if vs else 0.0
        return L if L > 0.005 * U else fallback


    def end_name(b):                                # 이 본 끝에 붙는 믹사모 끝 뼈 이름
        s = short(b)
        if s == "Head":
            return "HeadTop_End"
        if s.endswith("ToeBase"):
            return s.replace("ToeBase", "Toe_End")
        if s[-1:] == "3" and any(w in s for w in FINGER_WORDS):
            return s[:-1] + "4"
        return None

    def is_end(b):                                  # 이미 붙어 있는 끝 뼈 (전에 이 스크립트를 돌린 파일)
        return (not b.use_deform) and b.parent is not None and end_name(b.parent) == short(b)

    # FBX 로 내보냈다가 다시 불러온 파일: 블렌더가 붙인 "_end" 잎 뼈는 지우고, 웨이트 없는 믹사모 끝 뼈는 변형(Deform)을 끔
    removed = 0
    for b in list(ebs):
        if (b.name.endswith("_end") and not b.children and b.name not in weighted
                and b.parent is not None and b.name[:-4] == b.parent.name):
            ebs.remove(b)
            removed += 1
    for b in ebs:
        if b.use_deform and b.name not in weighted and b.parent is not None and end_name(b.parent) == short(b):
            b.use_deform = False
    if removed:
        print(f"[정리] FBX 잎 뼈(_end) {removed}개 삭제")

    tails = {}
    for b in ebs:
        if is_end(b):
            continue
        s = short(b)
        kids = [k for k in b.children if (k.head - b.head).length > 1e-6 and not is_end(k)
                and (k.name.startswith(P) or not b.name.startswith(P))]   # 믹사모 본의 끝은 믹사모 자식 쪽으로 (머리카락 등 다른 본은 무시)
        pref = ebs.get(N(PREFERRED[s])) if s in PREFERRED else None
        if pref is not None:
            tails[b.name] = pref.head.copy()
        elif len(kids) == 1:
            tails[b.name] = kids[0].head.copy()
        elif kids:
            tails[b.name] = max(kids, key=lambda k: (k.head - b.head).length).head.copy()
        elif s == "Head":
            tails[b.name] = b.head + up * extent(b, up, 0.2 * U)
        elif s.endswith("ToeBase"):
            d = fwd - up * fwd.dot(up)
            tails[b.name] = b.head + d.normalized() * extent(b, d.normalized(), 0.05 * U)
        elif b.name in tips and (tips[b.name] - b.head).length > 1e-5 * U:
            tails[b.name] = tips[b.name].copy()                     # 손가락 끝 마디: 실제 손끝까지
        else:                                                       # 손가락 끝 마디: 앞 마디 방향으로 연장
            pd = (b.head - b.parent.head) if b.parent else up
            tails[b.name] = b.head + pd.normalized() * max(pd.length * 0.9, 0.005 * U)
    for b in ebs:
        if b.name in tails and (tails[b.name] - b.head).length > 1e-5 * U:
            b.tail = tails[b.name]

    added = 0
    if ADD_END_BONES:
        for b in [b for b in ebs if not is_end(b)]:
            new = end_name(b)
            if new is None or any(not is_end(k) and k.name.startswith(P) for k in b.children):
                continue
            e = ebs.get(N(new))
            if e is None:                            # 없으면 새로 만들고, 이미 있으면(다시 실행) 위치만 다시 맞춤
                e = ebs.new(N(new))
                added += 1
            e.use_connect = False
            e.head = b.tail.copy()
            if b.name in tips:
                e.tail = b.tail + (b.tail - b.head) * 0.2    # 손끝에서 시작해 짧게 (손가락 밖으로 길게 튀어나오지 않게)
            else:
                e.tail = b.tail + (b.tail - b.head)          # 믹사모처럼 끝 뼈 길이 = 부모 뼈 길이
            e.parent = b
            e.use_deform = False

    # 믹사모와 같은 롤: 몸통은 Z축이 앞, 발은 위. 팔·손·손가락·다리는 믹사모 기준 자세(팔은 옆으로 수평, 다리는 아래)에서
    # 정한 방향(팔은 아래=손바닥 쪽, 다리는 앞)을 지금 뼈 방향까지 최소 회전으로 돌린 방향 (A포즈에서도 믹사모와 같게)
    def canon_roll(bd, cdir, cz):
        q = cdir.rotation_difference(bd)
        return q @ cz


    for b in ebs:
        s = short(b)
        bd = (b.tail - b.head).normalized()
        side = 1.0 if s.startswith("Left") else -1.0
        if any(k in s for k in ("Foot", "Toe")):
            b.align_roll(up)
        elif any(k in s for k in ("Shoulder", "Arm", "Hand")):
            b.align_roll(canon_roll(bd, right * side, -up))
        elif any(k in s for k in ("UpLeg", "Leg")):
            b.align_roll(canon_roll(bd, -up, fwd))
        else:
            b.align_roll(fwd)

    # 7) 맞닿은 본 연결
    joined = 0
    for b in ebs:
        p = b.parent
        if p is not None and (b.head - p.tail).length < 1e-4 * U:
            b.use_connect = True
            joined += 1
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"[연결] {joined}개 본 연결")
    print(f"[믹사모 규격] 끝 뼈 {added}개 추가, 뼈 끝과 롤 정리 완료 (본 {len(arm.data.bones)}개)")
    # 8) 믹사모와 같은 단위/축 구조
    if MIXAMO_UNITS and abs(arm.matrix_world.to_scale().x - 1.0) < 1e-3 and arm.matrix_world.to_3x3().is_orthogonal:
        import math
        C = Matrix.Rotation(-math.pi / 2, 4, 'X') @ Matrix.Scale(100.0, 4)   # Z 위 -> Y 위, m -> cm
        objs = [arm] + skinned_meshes()
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = arm
        arm.matrix_world = C @ arm.matrix_world
        bpy.context.view_layer.update()
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        arm.matrix_world = C.inverted() @ arm.matrix_world                # 오브젝트는 반대로 돌려 보이는 모습은 그대로
        bpy.context.view_layer.update()
        print("[단위] 믹사모와 같은 구조로 변경 (아마추어 X 90도, 스케일 0.01, 뼈대 cm)")
    if "Armature" not in bpy.data.objects:
        arm.name = "Armature"



# 동물 등 사람이 아닌 리그: 본 방향(뼈 끝, 롤) 정리. 관절 위치는 그대로
def orient_bones():
    inv = arm.matrix_world.inverted()
    up = (arm.matrix_world.to_3x3().inverted() @ UP_W).normalized()
    fwd = (arm.matrix_world.to_3x3().inverted() @ FORWARD_W).normalized()

    # 본마다 그 본이 주로 움직이는 살의 가운데 (끝 본 방향에 씀)
    acc = {}
    for o in skinned_meshes():
        M = inv @ o.matrix_world
        names = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            for g in v.groups:
                if g.weight >= 0.5 and g.group in names:
                    s = acc.setdefault(names[g.group], [Vector((0, 0, 0)), 0.0])
                    s[0] += (M @ v.co) * g.weight
                    s[1] += g.weight
    cen = {n: s[0] / s[1] for n, s in acc.items() if s[1] > 0.0}

    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones
    head = {b.name: b.head.copy() for b in eb}

    def count(b):
        return 1 + sum(count(c) for c in b.children)

    plan = {}
    for b in eb:
        h = head[b.name]
        kids = [c for c in b.children if (head[c.name] - h).length > 1e-5]
        inc = (h - head[b.parent.name]) if b.parent is not None else None
        if inc is not None and inc.length < 1e-6:
            inc = None
        target, link = None, None
        if len(kids) == 1:
            target, link = head[kids[0].name], kids[0]
        elif kids:
            best = None
            if inc is not None:                      # 들어온 방향을 가장 잘 잇는 자식 (척추 → 목)
                best = max(kids, key=lambda c: (head[c.name] - h).normalized().dot(inc.normalized()))
                if (head[best.name] - h).normalized().dot(inc.normalized()) < 0.5:
                    best = None
            if best is None:                         # 가장 많은 본이 이어진 자식 (뿌리 본 → 척추)
                ranked = sorted(kids, key=count, reverse=True)
                if count(ranked[0]) > count(ranked[1]):
                    best = ranked[0]
            if best is not None:
                target, link = head[best.name], best
            else:
                target = sum((head[c.name] for c in kids), Vector((0, 0, 0))) / len(kids)
        else:                                        # 끝 본: 움직이는 살의 가운데 쪽
            Lp = inc.length if inc is not None else (b.tail - b.head).length
            d = None
            if b.name in cen and (cen[b.name] - h).length > 1e-5:
                d = cen[b.name] - h
            elif inc is not None:
                d = inc
            if d is not None:
                L = min(max(2.0 * (cen[b.name] - h).length if b.name in cen else 0.5 * Lp, 0.25 * Lp), Lp)
                target = h + d.normalized() * L
        if target is not None and (target - h).length > 1e-5:
            plan[b.name] = (target, link)

    for n, (target, link) in plan.items():
        eb[n].tail = target
    joined = 0
    for n, (target, link) in plan.items():
        if link is not None and not link.use_connect and (head[link.name] - target).length < 1e-6:
            link.use_connect = True
            joined += 1
    for b in eb:
        y = b.vector.normalized()
        b.align_roll(fwd if abs(y.dot(up)) > 0.9 else up)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"[본 방향] 본 {len(plan)}개의 뼈 끝을 다음 관절(끝 본은 살 가운데) 쪽으로 돌리고 롤을 맞춤, {joined}개 연결")


if REMOVE_UNSKINNED:
    remove_unskinned()
if hips is not None:
    print(f"[판단] 사람 리그 ({hips.name}) - 본 정리와 믹사모 규격 맞추기를 합니다")
    to_mixamo()
    print("[완료] 본 정리 완료. 이어서 5번 웨이트 정리 스크립트를 실행하세요.")
else:
    print("[판단] 믹사모 이름(Hips)이 없는 리그(동물 등) - 관절 위치는 그대로 두고 본 방향만 정리합니다.")
    if ORIENT_BONES:
        orient_bones()
    print("[완료] 이어서 5번 웨이트 정리 스크립트를 실행하세요.")
