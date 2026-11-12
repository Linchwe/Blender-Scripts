import bpy
import numpy as np
from mathutils import Vector

# [5번] SkinTokens 리깅 결과의 웨이트 정리 (사람, 동물 모두)
# 4번 본 정리 스크립트(SkinTokens_Fix_Bones.py)를 먼저 실행한 뒤 실행하세요. 웨이트는 본 위치에 맞춰 정리됩니다.
#
#  1) (사람 리그만) 옆 손가락으로 샌 웨이트를 가장 가까운 손가락으로 옮기기 (FIX_FINGER_WEIGHTS)
#  2) 웨이트를 관절에 맞추기: 부모 본과 자식 본이 만나는 모든 관절에서, 웨이트가 넘어가는 지점이 관절에서
#     벗어나 있거나 칼로 자른 듯 끊긴 곳만 골라, 관절 위치를 중심으로 관절 굵기에 맞는 폭으로 부드럽게
#     다시 나눕니다. 이미 괜찮은 관절은 건드리지 않습니다. 동물 리그도 본 이름 없이 똑같이 됩니다.
#     손가락 뿌리는 4번에서 너클을 손바닥 안으로 옮기므로, 너클 앞쪽 손바닥 살도 손가락 웨이트를 받게 합니다.
#     사람 리그(믹사모 이름)는 전문 오토리깅(AccuRIG) 결과에서 잰 관절별 경계 위치와 섞이는 폭(HUMAN_BLEND)을 쓰고,
#     이 기준과 다른 관절은 모두 다시 나눕니다. 발목처럼 크게 꺾인 관절은 부모 본 방향으로 잘라 뒤꿈치가 발에 남게 합니다.
#     몸통(Hips~Head)은 짧은 본이 이어져 있어 관절 하나씩이 아니라 몸통 높이를 따라 한꺼번에 나눕니다 (SPINE_BLEND)
#     위팔 웨이트가 가슴, 겨드랑이 아래까지 넓게 퍼져 있으면 줄여서 가슴 본으로 돌립니다 (팔을 들 때 가슴이 끌려 올라가지 않게)
#  3) 부모-자식이 아닌 본끼리(가슴과 위팔 등) 맞닿아 웨이트가 뚝 끊긴 곳만 주변과 섞기 (SMOOTH_SEAMS)
#  4) 작은 웨이트 지우기, 버텍스 하나에 붙는 본 개수 제한, 합 1 로 맞추기
#
# 관절(본 위치)이 맞다고 보고 맞추므로, 본 위치가 실제로 굽는 곳과 다르면 본을 먼저 옮기고 4번부터 다시 실행하세요.
# 웨이트를 손으로 고친 뒤에는 이 스크립트를 다시 실행하지 마세요. 손으로 고친 웨이트가 다시 바뀔 수 있습니다.

FIX_FINGER_WEIGHTS = True   # 옆 손가락으로 샌 웨이트 정리 (손가락 본 이름이 있는 사람 리그만)
BLEND              = 1.0    # 관절에서 웨이트가 섞이는 폭 (1.0 = 관절 굵기만큼. 더 부드럽게 0.5~2.0)
MAX_INFLUENCES     = 4      # 버텍스 하나에 영향을 주는 본 최대 개수 (게임 엔진 기본값 4)
PRUNE              = 0.01   # 이보다 작은 웨이트는 지움
SMOOTH_SEAMS       = True   # 부모-자식이 아닌 본끼리 맞닿아 웨이트가 뚝 끊긴 곳을 부드럽게 섞음

FINGER_WORDS = ("Thumb", "Index", "Middle", "Ring", "Pinky")

# 사람 리그(믹사모 이름)의 관절별 웨이트 섞임: (경계 위치, 섞이는 폭), 둘 다 관절 굵기(지름) 기준 비율
# 경계 위치 + 는 자식 본 쪽, - 는 부모 본 쪽. 전문 오토리깅(AccuRIG) 결과를 관절 굵기로 나눠 맞춘 값
HUMAN_BLEND = {
    "Spine": (-0.09, 0.94), "Spine1": (0.0, 0.9), "Spine2": (-0.17, 0.21),
    "Neck": (0.15, 1.54), "Head": (-0.26, 1.38),
    "Shoulder": (0.35, 0.64), "Arm": (-0.42, 2.07), "ForeArm": (-0.17, 1.15), "Hand": (0.0, 0.79),
    "UpLeg": (0.24, 0.49), "Leg": (-0.03, 0.77), "Foot": (-0.03, 0.84), "ToeBase": (0.05, 2.2),
    "Thumb1": (0.04, 0.57), "Thumb2": (-0.2, 1.83), "Thumb3": (0.0, 1.15),
    "Finger1": (-0.05, 2.44), "Finger2": (0.05, 1.33), "Finger3": (0.0, 1.15),
}


# 사람 리그 몸통(Hips~Head): 몸통은 짧은 본이 이어져 있어서 관절 하나씩이 아니라 몸통 전체 높이를 따라 한꺼번에 나눔
# (관절 이름: 경계 위치, 섞이는 폭) 둘 다 Hips~Head 길이 기준 비율, 경계 위치 - 는 관절보다 아래
SPINE_CHAIN = ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head")
SPINE_BLEND = {"Spine": (-0.056, 0.21), "Spine1": (-0.043, 0.19), "Spine2": (-0.049, 0.25),
               "Neck": (0.018, 0.26), "Head": (-0.092, 0.27)}


def human_key(name):
    s = name.split(":")[-1]
    for side in ("Left", "Right"):
        if s.startswith(side):
            s = s[len(side):]
    for f in FINGER_WORDS:
        if s.startswith("Hand" + f) and s[-1:] in "123":
            return ("Thumb" if f == "Thumb" else "Finger") + s[-1]
    return s

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


# 계산용 함수
def _smooth(t):
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * (3.0 - 2.0 * t)


def _seg_dist(p, a, b):
    ab = b - a
    L2 = ab.dot(ab)
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / L2))
    return (p - (a + ab * t)).length


# 1) 옆 손가락으로 샌 웨이트 정리 (사람 리그만)
def fix_finger_weights():
    mw = arm.matrix_world
    bones = arm.data.bones
    byname = {}
    for b in bones:
        for side in ("Left", "Right"):
            for f in FINGER_WORDS:
                for i in (1, 2, 3):
                    if b.name.endswith(f"{side}Hand{f}{i}"):
                        byname[(side, f, i)] = b.name
    total = 0
    for side in ("Left", "Right"):
        chains = {f: [byname.get((side, f, i)) for i in (1, 2, 3)] for f in FINGER_WORDS}
        chains = {f: ch for f, ch in chains.items() if all(ch)}
        if len(chains) < 2:
            continue
        H = {n: mw @ bones[n].head_local for ch in chains.values() for n in ch}
        T3 = {ch[2]: mw @ bones[ch[2]].tail_local for ch in chains.values()}
        fing_of = {n: f for f, ch in chains.items() for n in ch}

        def segs(f):
            a, b, c = (H[n] for n in chains[f])
            return [(a, b), (b, c), (c, T3[chains[f][2]])]

        for o in skinned_meshes():
            gname = {g.index: g.name for g in o.vertex_groups}
            for v in o.data.vertices:
                w = {gname[g.group]: g.weight for g in v.groups if g.group in gname and g.weight > 0.0}
                if not w:
                    continue
                k = max(w, key=w.get)
                f = fing_of.get(k)
                if f is None:
                    continue
                co = o.matrix_world @ v.co
                nf = min(chains, key=lambda c: min(_seg_dist(co, a, b) for a, b in segs(c)))
                if nf == f:
                    continue
                ss = segs(nf)
                j = min(range(3), key=lambda t: _seg_dist(co, *ss[t]))
                target = chains[nf][j]
                moving = sum(x for n, x in w.items() if fing_of.get(n) == f)
                for n in [n for n in w if fing_of.get(n) == f]:
                    o.vertex_groups[n].remove([v.index])
                g = o.vertex_groups.get(target) or o.vertex_groups.new(name=target)
                g.add([v.index], w.get(target, 0.0) + moving, 'REPLACE')
                total += 1
    print(f"[손가락 웨이트] 옆 손가락 웨이트를 받은 버텍스 {total}개를 가까운 손가락으로 옮김")
    return total



# 2) 웨이트를 관절에 맞추기 (사람, 동물 공통. 본 이름은 보지 않고 부모-자식 본 구조로 처리)
def fix_weights():
    meshes = skinned_meshes()
    if not meshes:
        print("[웨이트] 아마추어에 연결된 메시가 없어 건너뜁니다")
        return
    mw = arm.matrix_world
    bones = arm.data.bones
    deform = {b.name for b in bones if b.use_deform}
    H = {b.name: mw @ b.head_local for b in bones}
    TL = {b.name: mw @ b.tail_local for b in bones}

    # 버텍스마다 (메시, 번호, 월드 위치, {본 이름: 웨이트})
    recs = []
    total = {}
    for o in meshes:
        gname = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            w = {}
            for g in v.groups:
                n = gname.get(g.group)
                if n in deform and g.weight > 0.0:
                    w[n] = w.get(n, 0.0) + g.weight
                    total[n] = total.get(n, 0.0) + g.weight
            recs.append([o, v.index, o.matrix_world @ v.co, w, False])
    weighted = {n for n, t in total.items() if t > 1e-3}
    acc = {}
    for r in recs:                                   # 본마다 그 본이 주로 움직이는 버텍스들의 중심
        w = r[3]
        if w:
            k = max(w, key=w.get)
            if w[k] >= 0.5 * sum(w.values()):
                a = acc.setdefault(k, [Vector((0, 0, 0)), 0])
                a[0] += r[2]
                a[1] += 1
    cen = {k: a[0] / a[1] for k, a in acc.items() if a[1] >= 3}

    sub_cache = {}

    def subtree(b):
        if b.name not in sub_cache:
            sub_cache[b.name] = {b.name} | {k.name for k in b.children_recursive}
        return sub_cache[b.name]

    def has_weight(b):
        return bool(subtree(b) & weighted)

    def bone_dir(b):
        kids = [k for k in b.children if has_weight(k) and (H[k.name] - H[b.name]).length > 1e-6]
        if len(kids) == 1:
            return H[kids[0].name] - H[b.name]
        if kids:
            c = Vector((0, 0, 0))
            for k in kids:
                c += H[k.name]
            return c / len(kids) - H[b.name]
        # 끝 본(발끝, 손가락 끝, 머리, 꼬리 끝 등): 뼈 끝(tail) 방향은 믿을 수 없어서, 이 본이 주로 움직이는
        # 버텍스들의 중심 쪽을 본 방향으로 씀
        if b.name in cen:
            d = (cen[b.name] - H[b.name]) * 2.0
            if d.length > 1e-6:
                return d
        if b.parent is not None and (H[b.name] - H[b.parent.name]).length > 1e-6:
            return (H[b.name] - H[b.parent.name]) * 0.5
        return TL[b.name] - H[b.name]

    def segments(b):
        out = []
        for n in subtree(b):
            bb = bones[n]
            out.append((H[n], H[n] + bone_dir(bb)))
        return out

    fixed, kept = [], 0
    arm_cap = {}

    # 사람 리그 몸통 한꺼번에 나누기
    chain = []
    if HUMANOID:
        for key in SPINE_CHAIN:
            b = next((b for b in bones if b.name.split(":")[-1] == key), None)
            chain.append(b.name if b is not None and b.name in weighted else None)
        if not all(chain):
            chain = []
    if chain:
        pts = [H[n] for n in chain] + [TL[chain[-1]]]
        segl = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
        Lch = sum(segl[:-1])
        pos = [0.0]
        for l in segl:
            pos.append(pos[-1] + l)

        def along(p):                                # 몸통 선 위의 위치 (Hips 에서 잰 길이)
            best = None
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                ab = b - a
                t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.dot(ab), 1e-12)))
                d = (p - (a + ab * t)).length
                if best is None or d < best[0]:
                    best = (d, pos[i] + t * segl[i])
            if best[1] <= 0.0:                       # Hips 아래쪽
                return (p - pts[0]).dot((pts[1] - pts[0]).normalized())
            return best[1]

        cset = set(chain)
        n_ch = 0
        for r in recs:
            w = r[3]
            tot = sum(w.values())
            S = sum(w.get(n, 0.0) for n in chain)
            if tot <= 0.0 or S < 0.05 * tot:             # 몸통 웨이트가 조금이라도 있으면 그 몫만 높이에 맞게 다시 나눔
                continue
            t = along(r[2])
            f, prev = [], 1.0
            for i, key in enumerate(SPINE_CHAIN[1:], start=1):
                off, wid = SPINE_BLEND[key]
                x = _smooth((t - (pos[i] + off * Lch)) / max(wid * Lch, 1e-9) + 0.5)
                prev = min(prev, x)
                f.append(prev)
            parts = [1.0 - f[0]] + [f[i] - f[i + 1] for i in range(len(f) - 1)] + [f[-1]]
            for n, q in zip(chain, parts):
                if q * S > 1e-6:
                    w[n] = q * S
                elif n in w:
                    del w[n]
            r[4] = True
            n_ch += 1
        print(f"[웨이트] 몸통(Hips~Head) 버텍스 {n_ch}개를 몸통 높이를 따라 부드럽게 다시 나눔")
    for c in bones:                                  # 부모 -> 자식 순서
        p = c.parent
        if p is None or c.name not in weighted or p.name not in weighted:
            continue
        if chain and c.name in chain:                # 몸통은 위에서 이미 나눔
            continue
        dp, dc = H[c.name] - H[p.name], bone_dir(c)
        Lp, Lc = dp.length, dc.length
        if Lp < 1e-6 or Lc < 1e-6:
            continue
        sibs = [k for k in p.children if has_weight(k)]
        branching = len(sibs) > 1
        n = dp.normalized() + dc.normalized()
        if branching or n.length < 1e-3:
            n = dc.normalized()
        elif dp.normalized().dot(dc.normalized()) < 0.2:   # 발목처럼 꺾인 관절: 부모 본 방향으로 자름 (뒤꿈치가 발에 남도록)
            n = dp.normalized()
        else:
            n.normalize()
        human = HUMAN_BLEND.get(human_key(c.name)) if HUMANOID else None
        sub = subtree(c)
        sib_segs = {k.name: segments(k) for k in sibs} if branching else None
        # 손가락 뿌리: 4번에서 너클을 손바닥 안으로 옮기면 그 사이 손바닥 살도 손가락을 따라 움직여야 해서,
        # 아직 손가락 웨이트가 없는 손바닥 버텍스도 이 손가락 쪽에 가까우면 후보로 넣음
        palm = branching and len(sibs) >= 4 and any(w in c.name for w in FINGER_WORDS)
        extra = []

        # 이 관절에서 다룰 버텍스: 대부분의 웨이트가 위/아래 본에 있고, (갈라지는 관절이면) 이 갈래에 가장 가까운 것
        cand = []
        for r in recs:
            w = r[3]
            tot = sum(w.values())
            if tot <= 0.0:
                continue
            S = w.get(p.name, 0.0) + w.get(c.name, 0.0)
            if S < 0.5 * tot:
                continue
            outside = False
            if branching:
                if sum(w.get(k, 0.0) for k in sub) < 0.01 * tot:
                    if not palm:
                        continue
                    s = (r[2] - H[c.name]).dot(n)
                    if s < -0.5 * Lc or s > Lc:
                        continue
                    outside = True
                co = r[2]
                near = min(sib_segs, key=lambda k: min(_seg_dist(co, a, b) for a, b in sib_segs[k]))
                if near != c.name:
                    continue
            s = (r[2] - H[c.name]).dot(n)
            (extra if outside else cand).append((r, S, s))
        if len(cand) < 4:
            continue

        # 관절 굵기(반지름)로 섞이는 폭을 정함
        rad = sorted(((r[2] - H[c.name]) - n * s).length for r, S, s in cand if abs(s) < 0.5 * min(Lp, Lc))
        R = rad[len(rad) // 2] if rad else 0.25 * min(Lp, Lc)
        if human:
            W = min(BLEND * human[1] * 2.0 * R, 3.0 * min(Lp, Lc))
            off = human[0] * 2.0 * R
        else:
            W = min(BLEND * 2.0 * R, 0.8 * min(Lp, Lc))
            off = 0.0
        if W < 1e-6:
            continue
        cand += [(r, S, s) for r, S, s in extra
                 if s > -0.5 * W and ((r[2] - H[c.name]) - n * s).length < 2.0 * R]

        if human and human_key(c.name) == "Arm":
            arm_cap[c.name] = (n, W, off, R, p.parent if p.parent is not None and p.parent.name in weighted else p)

        # 지금 상태 측정: 반반 넘어가는 지점(cross)과 섞이는 폭(width)
        ratio = [(s, r[3].get(c.name, 0.0) / S) for r, S, s in cand if S > 0.0]
        mid = sorted(s for s, q in ratio if abs(q - 0.5) < 0.15)
        bl = sorted(s for s, q in ratio if 0.1 < q < 0.9)
        cross = mid[len(mid) // 2] if mid else None
        width = (bl[int(len(bl) * 0.95) - 1] - bl[int(len(bl) * 0.05)]) if len(bl) > 3 else 0.0
        bad = cross is None or abs(cross - off) > 0.25 * W or width < 0.4 * W or (human and width > 1.6 * W)
        if not bad:
            kept += 1
            continue

        for r, S, s in cand:
            q = _smooth((s - off) / W + 0.5)
            w = r[3]
            nc = S * q
            if abs(nc - w.get(c.name, 0.0)) > 1e-4:
                w[c.name] = nc
                w[p.name] = S - nc
                r[4] = True
        fixed.append((c.name, cross, width, W))

    # 위팔이 가슴/겨드랑이 아래까지 너무 넓게 잡은 웨이트를 줄여서 가슴(쇄골 본의 부모, 보통 Spine2)으로 돌려줌.
    # 팔 관절에서 몸 쪽으로 갈수록, 그리고 팔 굵기 바깥(가슴, 겨드랑이 아래)으로 갈수록 위팔 몫을 줄임.
    # 팔을 들 때 가슴이 팔에 끌려 부풀어 오르는 것을 막음
    n_cap = 0
    for name, (n, W, off, R, gp) in arm_cap.items():
        a0 = H[name]
        for r in recs:
            w = r[3]
            a = w.get(name, 0.0)
            if a <= 0.0:
                continue
            v = r[2] - a0
            s = v.dot(n)
            if s > off + 0.5 * W:
                continue
            rad = (v - n * s).length
            cap = sum(w.values()) * _smooth((s - off) / W + 0.5) * _smooth((1.3 * R - rad) / (0.8 * R) + 0.5)
            if a > cap + 1e-4:
                w[name] = cap
                w[gp.name] = w.get(gp.name, 0.0) + a - cap
                r[4] = True
                n_cap += 1
    if n_cap:
        print(f"[웨이트] 위팔이 가슴/겨드랑이 쪽으로 너무 넓게 잡은 버텍스 {n_cap}개를 가슴 본으로 돌림")

    # 끊긴 경계 부드럽게: 부모-자식이 아닌 두 본(예: 가슴 Spine2 와 위팔 Arm)이 맞닿아 웨이트가 칼로 자른 듯
    # 바뀌는 곳만 골라 주변과 섞음. 자세를 크게 바꿀 때 그 자리 면이 찢어지듯 늘어나는 것을 막음
    seam_fixed = 0
    if SMOOTH_SEAMS:
        scale = max((H[b.name] - H[bones[0].name]).length for b in bones) or 1.0
        by_obj = {}
        for r in recs:
            by_obj.setdefault(r[0], {})[r[1]] = r

        def related(a, b):
            if a == b:
                return True
            ba, bb = bones.get(a), bones.get(b)
            return ba is not None and bb is not None and (ba.parent == bb or bb.parent == ba)

        for o, rv in by_obj.items():
            ev = np.empty(len(o.data.edges) * 2, dtype=np.int64)
            o.data.edges.foreach_get("vertices", ev)
            ev = ev.reshape(-1, 2)
            nbr = {}
            seam = set()
            elen = []
            for a, b in ev:
                ra, rb = rv.get(int(a)), rv.get(int(b))
                if ra is None or rb is None or not ra[3] or not rb[3]:
                    continue
                nbr.setdefault(int(a), []).append(int(b))
                nbr.setdefault(int(b), []).append(int(a))
                elen.append((ra[2] - rb[2]).length)
                wa, wb = ra[3], rb[3]
                ta, tb = sum(wa.values()), sum(wb.values())
                d = 0.5 * sum(abs(wa.get(k, 0.0) / ta - wb.get(k, 0.0) / tb) for k in set(wa) | set(wb))
                if d > 0.5 and not related(max(wa, key=wa.get), max(wb, key=wb.get)):
                    seam.update((int(a), int(b)))
            if not seam or not elen:
                continue
            e_mean = sum(elen) / len(elen)
            rings = max(1, min(6, int(round(0.02 * scale * 3 / max(e_mean, 1e-9)))))
            region = set(seam)
            front = set(seam)
            for _ in range(rings):
                front = {n for v in front for n in nbr.get(v, ()) if n not in region}
                region |= front
            for _ in range(rings * rings):
                upd = {}
                for v in region:
                    acc_w = dict(rv[v][3])
                    cnt = 1
                    for n in nbr.get(v, ()):
                        for k, x in rv[n][3].items():
                            acc_w[k] = acc_w.get(k, 0.0) + x
                        cnt += 1
                    upd[v] = {k: x / cnt for k, x in acc_w.items()}
                for v, w in upd.items():
                    rv[v][3] = w
                    rv[v][4] = True
            seam_fixed += len(region)
        if seam_fixed:
            print(f"[웨이트] 부모-자식이 아닌 본끼리 끊긴 경계 주변 버텍스 {seam_fixed}개를 부드럽게 섞음")

    # 작은 웨이트 정리, 본 개수 제한, 합 1 로 맞추기
    pruned = 0
    for r in recs:
        w = r[3]
        if not w:
            continue
        tot = sum(w.values())
        keep = sorted(((k, x) for k, x in w.items() if x >= PRUNE * tot), key=lambda kv: -kv[1])[:MAX_INFLUENCES]
        if not keep:
            keep = [max(w.items(), key=lambda kv: kv[1])]
        if len(keep) != len(w):
            pruned += len(w) - len(keep)
            r[4] = True
        if r[4]:
            t = sum(x for k, x in keep)
            r[3] = {k: x / t for k, x in keep}

    changed = 0
    for o, idx, co, w, dirty in recs:
        if not dirty:
            continue
        changed += 1
        for g in o.vertex_groups:
            if g.name in deform and g.name not in w:
                g.remove([idx])
        for k, x in w.items():
            g = o.vertex_groups.get(k) or o.vertex_groups.new(name=k)
            g.add([idx], x, 'REPLACE')

    u = 100.0                                            # 표시용 cm
    for name, cross, width, W in fixed:
        cs = "경계 없음" if cross is None else f"경계 {cross * u:+.1f}cm"
        print(f"[웨이트] {name:32s} {cs}, 섞이는 폭 {width * u:.1f}cm -> 관절 위치, 폭 {W * u:.1f}cm")
    print(f"[웨이트] 관절 {len(fixed)}곳 수정, {kept}곳은 이미 괜찮아서 그대로. "
          f"버텍스 {changed}개 변경, 작은 웨이트 {pruned}개 정리")


if not skinned_meshes():
    raise Exception("이 아마추어에 연결된 메시가 없습니다. SkinTokens 결과 파일에서 Armature 를 선택하고 실행하세요.")
has_fingers = any(b.name.endswith("HandIndex1") for b in arm.data.bones)
HUMANOID = any(b.name.endswith("Hips") for b in arm.data.bones) and any(b.name.endswith("LeftUpLeg") for b in arm.data.bones)
if FIX_FINGER_WEIGHTS and has_fingers:
    fix_finger_weights()
fix_weights()
print("[완료] 웨이트 정리 완료. FBX 로 내보낼 때 Armature > Add Leaf Bones 는 끄세요.")
