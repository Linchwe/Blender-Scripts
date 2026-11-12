"""Clean Keyframes - 구워진(베이크된) 애니메이션에서 의미 없는 키프레임 지우기
(믹사모, 모션캡처, AI로 만든 애니메이션 등)

구워진 애니메이션은 매 프레임마다 키가 있습니다. 모드는 두 가지입니다.

  POSES (기본): 한 방향으로 진행 중인 중간 키는 모두 지우고, 아래 키만 남깁니다.
      - 방향이 바뀌는 곳 (본의 회전/위치는 본 하나의 움직임으로 보고, 방향을 바꾸느라 움직임이 확
        느려지는 순간. 하나짜리 값은 올라가다 내려가는 꼭짓점과 바닥)
      - 완전히 멈추는 구간의 시작과 끝
      - 맨 처음과 맨 끝 프레임
    애니메이터가 손으로 잡는 키 포즈와 비슷하게 남아서 키가 크게 줄고 수정하기 쉽습니다. 대신 키 사이는
    베지어 곡선(천천히 출발해 천천히 멈춤)으로 다시 이어지므로, 원본과 조금 달라질 수 있습니다.
    키 사이가 원본과 크게(SAFETY_ROTATION_DEG 넘게) 어긋나는 곳에만 키를 하나씩 더 남깁니다.
    한 본의 회전 성분(쿼터니언 4개)이나 위치 성분(3개)은 항상 같은 프레임에 키가 남습니다.

  ACCURATE: 원본과의 차이가 허용 오차(아래 TOLERANCE 값들) 안에 들도록 필요한 키를 모두 남깁니다.
    원본과 거의 똑같지만 키가 덜 줄어듭니다.

남은 키는 모두 베지어(Auto Clamped) 보간입니다.

※ 블렌더의 Decimate 를 먼저 하지 말고, 매 프레임 키가 있는 원본에 바로 실행하세요.

사용법 (블렌더 4.2 이상, 5.x 도 됨)
  1. 오브젝트 모드에서 애니메이션이 있는 아마추어(또는 오브젝트)를 선택합니다.
  2. Scripting 탭 > Text > Open > 이 파일 > Run Script (텍스트 에디터에서 Alt+P).
  3. 결과는 아래 상태바와 시스템 콘솔(Window > Toggle System Console)에 표시됩니다.
     되돌리려면 Ctrl+Z.

설정은 바로 아래에 있습니다.
"""
import math

import bpy

# ----------------------------------------------------------------------------- 설정
MODE = "POSES"                 # "POSES": 방향 바뀌는 곳과 멈춤만 남김.  "ACCURATE": 원본과 거의 똑같이

# POSES 모드 설정
TURN_ROTATION_DEG = 4.0        # 키 사이 자세가 이만큼(도)도 안 바뀌면 합침. 크게 하면 키가 더 줄어듦
TURN_LOCATION_M = 0.02         # 위치의 방향 전환 기준(월드 기준 미터, 0.02 = 2cm)
TURN_OTHER = 0.01              # 스케일 등 그 밖의 값의 방향 전환 기준
SMOOTH_FRAMES = 5              # 방향 전환을 찾을 때만 이 프레임 수로 커브를 부드럽게 봄(잔떨림 무시). 1 이면 끔
HOLD_FRAMES = 4                # 이 프레임 수 이상 거의 안 움직이면 '멈춤'으로 보고 시작과 끝에 키를 남김
SAFETY_ROTATION_DEG = 3.0      # 키 사이 곡선이 원본과 이만큼(도) 넘게 어긋나는 곳에만 키를 하나 더 남김. 0 이면 꺼짐
SAFETY_LOCATION_M = 0.03       # SAFETY_ROTATION_DEG 를 켰을 때 위치 기준(미터)

# ACCURATE 모드 설정
ROTATION_TOLERANCE_DEG = 0.2   # 허용 회전 오차(도). 크게 하면 키가 더 줄어듦
LOCATION_TOLERANCE_M = 0.002   # 허용 위치 오차(월드 기준 미터, 0.002 = 2mm)
SCALE_TOLERANCE = 0.001        # 허용 스케일 오차(0.001 = 0.1%)
OTHER_TOLERANCE = 0.001        # 그 밖의 값(커스텀 프로퍼티, 셰이프 키 등) 허용 오차
ALL_ACTIONS = False            # False: 선택한 오브젝트의 현재 액션만. True: 파일 안의 모든 액션
SELECTED_ONLY = True           # False: 선택과 상관없이 씬의 모든 오브젝트
# -----------------------------------------------------------------------------


def action_fcurves(action):
    """액션의 F-커브 목록 (예전 방식, 또는 블렌더 4.4 이상 / 5.x 의 레이어·슬롯 방식 액션)."""
    try:
        return list(action.fcurves)
    except AttributeError:
        pass
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


def tolerance(fc, loc_scale):
    p = fc.data_path
    if p.endswith("rotation_quaternion"):
        # 쿼터니언 성분이 d 만큼 바뀌면 회전은 약 2*d 라디안 바뀜
        return math.radians(ROTATION_TOLERANCE_DEG) / 2.0
    if p.endswith("rotation_euler") or p.endswith("rotation_axis_angle"):
        return math.radians(ROTATION_TOLERANCE_DEG)
    if p.endswith("location"):
        return LOCATION_TOLERANCE_M / loc_scale
    if p.endswith("scale"):
        return SCALE_TOLERANCE
    return OTHER_TOLERANCE


def rdp(xs, ys, tol):
    """Ramer-Douglas-Peucker 방식으로 남길 키 번호 (프레임-값 직선에서 값 차이로 판단)."""
    keep = {0, len(xs) - 1}
    stack = [(0, len(xs) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        x0, y0, x1, y1 = xs[a], ys[a], xs[b], ys[b]
        worst, wi = -1.0, -1
        for i in range(a + 1, b):
            t = (xs[i] - x0) / (x1 - x0) if x1 != x0 else 0.0
            d = abs(ys[i] - (y0 + t * (y1 - y0)))
            if d > worst:
                worst, wi = d, i
        if worst > tol:
            keep.add(wi)
            stack += [(a, wi), (wi, b)]
    return sorted(keep)


def turn_size(fc, loc_scale):
    """POSES 모드: 이 커브에서 '방향이 바뀌었다'고 볼 최소 되돌림 크기."""
    p = fc.data_path
    if p.endswith("rotation_quaternion"):
        return math.radians(TURN_ROTATION_DEG) / 2.0
    if p.endswith("rotation_euler") or p.endswith("rotation_axis_angle"):
        return math.radians(TURN_ROTATION_DEG)
    if p.endswith("location"):
        return TURN_LOCATION_M / loc_scale
    return TURN_OTHER


def _smoothed(ys, k):
    if k <= 1:
        return ys
    h, n = k // 2, len(ys)
    return [sum(ys[max(0, i - h):min(n, i + h + 1)]) / (min(n, i + h + 1) - max(0, i - h)) for i in range(n)]


def pose_keys(ys, turn):
    """방향이 바뀌는 꼭짓점/바닥과 멈춤 구간의 시작·끝 키 번호.
    turn 보다 작은 되돌림(떨림)은 방향 전환으로 치지 않음."""
    n = len(ys)
    keep = {0, n - 1}
    raw = ys
    ys = _smoothed(raw, SMOOTH_FRAMES)                # 잔떨림을 걸러 낸 커브로 방향 전환을 찾음
    # 1) 방향 전환: 지그재그 방식. 꼭짓점(또는 바닥)에서 turn 넘게 되돌아가면 그 꼭짓점을 키로 확정
    trend, ext = 0, 0                                # trend: 1 올라가는 중, -1 내려가는 중, 0 아직 모름
    for i in range(1, n):
        if trend == 0:
            if ys[i] - ys[0] > turn:
                trend, ext = 1, i
            elif ys[0] - ys[i] > turn:
                trend, ext = -1, i
        elif trend == 1:
            if ys[i] >= ys[ext]:
                ext = i
            elif ys[ext] - ys[i] > turn:
                keep.add(ext)
                trend, ext = -1, i
        else:
            if ys[i] <= ys[ext]:
                ext = i
            elif ys[i] - ys[ext] > turn:
                keep.add(ext)
                trend, ext = 1, i
    # 찾은 꼭짓점 근처(앞뒤 SMOOTH_FRAMES)에서 원본이 실제로 가장 튀어나온 프레임으로 옮김
    h = max(1, SMOOTH_FRAMES // 2)
    moved = {0, n - 1}
    for e in keep - {0, n - 1}:
        lo, hi = max(0, e - h), min(n, e + h + 1)
        up = ys[e] >= (ys[max(0, e - 1)] + ys[min(n - 1, e + 1)]) / 2
        moved.add(max(range(lo, hi), key=lambda m: raw[m] if up else -raw[m]))
    keep = moved
    ys = raw
    # 2) 멈춤: HOLD_FRAMES 이상 값이 거의 그대로인 구간의 시작과 끝
    still = turn * 0.25
    start = 0
    for i in range(1, n + 1):
        if i == n or abs(ys[i] - ys[start]) > still:
            if i - 1 - start >= HOLD_FRAMES:
                keep.add(start)
                keep.add(i - 1)
            start = i
    return sorted(keep)


def pose_keys_vec(Y, turn):
    """여러 성분 묶음(회전 4개, 위치 3개)을 하나의 움직임으로 보고 키 프레임 번호를 고름.
    본이 방향을 바꾸거나 멈추면 그 순간 움직임이 확 느려지므로, 속도가 주변보다 크게 떨어지는 프레임과
    멈춘 구간의 시작·끝을 키로 남김. 키 사이 자세 차이가 turn 보다 작으면 합침(잔떨림 무시)."""
    n, c = len(Y[0]), len(Y)
    sp = [0.0] + [math.sqrt(sum((Y[k][i] - Y[k][i - 1]) ** 2 for k in range(c))) for i in range(1, n)]
    sp = _smoothed(sp, SMOOTH_FRAMES)
    win = 10
    cand = {0, n - 1}
    for i in range(1, n - 1):
        if sp[i] <= sp[i - 1] and sp[i] <= sp[i + 1]:
            peak = max(sp[max(0, i - win):min(n, i + win + 1)])
            if sp[i] < 0.5 * peak:
                cand.add(i)
    still = turn * 0.25 / max(1, HOLD_FRAMES)       # 프레임당 이보다 덜 움직이면 멈춘 것으로 봄
    start = None
    for i in range(1, n + 1):
        if i < n and sp[i] <= still:
            start = i - 1 if start is None else start
        else:
            if start is not None and i - 1 - start >= HOLD_FRAMES:
                cand.update((start, i - 1))
            start = None
    keep = [0]
    for i in sorted(cand - {0}):                     # 자세가 turn 만큼도 안 바뀌었으면 합침
        d = math.sqrt(sum((Y[k][i] - Y[k][keep[-1]]) ** 2 for k in range(c)))
        if d > turn or i == n - 1:
            keep.append(i)
    return keep


def rebuild(fc, xs, ys, idx):
    """커브의 키를 모두 지우고 idx 번째 원래 키들만 다시 넣음 (베지어, Auto Clamped 핸들)."""
    kps = fc.keyframe_points
    while len(kps):
        kps.remove(kps[0], fast=True)
    kps.add(len(idx))
    co = []
    for i in idx:
        co += [xs[i], ys[i]]
    kps.foreach_set("co", co)
    for kp in kps:
        kp.interpolation = "BEZIER"
        kp.handle_left_type = "AUTO_CLAMPED"
        kp.handle_right_type = "AUTO_CLAMPED"
    fc.update()


def clean_fcurve(fc, tol, turn):
    """커브 하나 정리. (정리 전 키 수, 정리 후 키 수) 를 돌려줌."""
    kps = fc.keyframe_points
    n = len(kps)
    if n < 3:
        return n, n
    co = [0.0] * (2 * n)
    kps.foreach_get("co", co)
    xs, ys = co[0::2], co[1::2]
    if max(ys) - min(ys) <= (turn if MODE == "POSES" else tol):   # 거의 안 바뀌는 커브: 키 하나면 충분
        rebuild(fc, xs, ys, [0])
        return n, 1
    if MODE == "POSES":
        idx = pose_keys(ys, turn)
        rebuild(fc, xs, ys, idx)
        return n, len(idx)
    keep = set(rdp(xs, ys, tol * 0.5))
    for _ in range(50):                              # 원본과 차이가 나는 곳에 원래 키를 다시 넣기
        idx = sorted(keep)
        rebuild(fc, xs, ys, idx)
        err = [abs(fc.evaluate(x) - y) for x, y in zip(xs, ys)]
        added = False
        for a, b in zip(idx, idx[1:]):               # 오차가 큰 구간마다 가장 많이 벗어난 프레임
            if b - a < 2:
                continue
            j = max(range(a + 1, b), key=lambda i: err[i])
            if err[j] > tol:
                keep.add(j)
                added = True
        if not added:
            break
    return n, len(keep)


def _read(fc):
    n = len(fc.keyframe_points)
    co = [0.0] * (2 * n)
    fc.keyframe_points.foreach_get("co", co)
    return co[0::2], co[1::2]


def clean_group(fcs, rev):
    """POSES 모드: 같은 속성(예: 한 본의 회전 4성분, 위치 3성분)을 한 묶음으로 정리.
    성분마다 찾은 꼭짓점과 멈춤 프레임을 합쳐서, 묶음의 모든 성분에 같은 프레임의 키를 남김.
    (성분마다 다른 프레임에 키를 남기면 회전이 엉뚱하게 섞임)"""
    data = [_read(fc) for fc in fcs]
    n = len(data[0][0])
    same = all(len(xs) == n and xs == data[0][0] for xs, _ in data)
    if not same or n < 3:                            # 키 프레임이 성분마다 다르면 하나씩 처리
        tot = [clean_fcurve(fc, None, rev) for fc in fcs]
        return sum(t[0] for t in tot), sum(t[1] for t in tot)
    xs = data[0][0]
    ys = [list(d[1]) for d in data]
    if fcs[0].data_path.endswith("rotation_quaternion") and len(fcs) == 4:
        # 쿼터니언 q 와 -q 는 같은 회전: 부호가 중간에 뒤집히면 값이 튀므로 연속되게 맞춤
        for i in range(1, n):
            if sum(ys[c][i] * ys[c][i - 1] for c in range(4)) < 0:
                for c in range(4):
                    ys[c][i] = -ys[c][i]
    if all(max(y) - min(y) <= rev for y in ys):      # 거의 안 움직임: 키 하나면 충분
        idx = [0]
    else:
        idx = pose_keys_vec(ys, rev) if len(ys) > 1 else pose_keys(ys[0], rev)
    for fc, y in zip(fcs, ys):
        rebuild(fc, xs, y, idx)
    if SAFETY_ROTATION_DEG > 0 and len(idx) > 1:     # 원본과 크게 어긋나는 구간에만 키 추가
        p = fcs[0].data_path
        if "rotation" in p:
            lim = math.radians(SAFETY_ROTATION_DEG) / (2.0 if p.endswith("quaternion") else 1.0)
        elif p.endswith("location"):
            lim = rev / TURN_LOCATION_M * SAFETY_LOCATION_M
        else:
            lim = rev * 3
        keep = set(idx)
        for _ in range(50):
            err = [max(abs(fc.evaluate(x) - y[i]) for fc, y in zip(fcs, ys)) for i, x in enumerate(xs)]
            cur = sorted(keep)
            added = False
            for a, b in zip(cur, cur[1:]):
                if b - a < 2:
                    continue
                k = max(range(a + 1, b), key=lambda m: err[m])
                if err[k] > lim:
                    keep.add(k)
                    added = True
            if not added:
                break
            for fc, y in zip(fcs, ys):
                rebuild(fc, xs, y, sorted(keep))
        idx = sorted(keep)
    return n * len(fcs), len(idx) * len(fcs)


def world_scale(obj):
    """오브젝트의 월드 스케일 (믹사모 FBX 처럼 0.01 배인 경우 위치 오차를 맞추는 데 씀)."""
    s = obj.matrix_world.to_scale()
    return max(abs(s.x), abs(s.y), abs(s.z)) or 1.0


def main():
    objs = bpy.context.selected_objects if SELECTED_ONLY else bpy.context.scene.objects
    jobs = {}                                        # 액션 -> 위치 스케일
    if ALL_ACTIONS:
        scale = max((world_scale(o) for o in objs), default=1.0)
        for act in bpy.data.actions:
            jobs[act] = scale
    else:
        for o in objs:
            ad = o.animation_data
            if ad and ad.action:
                jobs[ad.action] = world_scale(o)
    if not jobs:
        msg = "Clean Keyframes: no animation found (select the animated objects first)"
        print(msg)
        return msg
    total_before = total_after = 0
    for act, scale in jobs.items():
        before = after = 0
        curves = [fc for fc in action_fcurves(act) if not fc.lock and len(fc.keyframe_points)]
        if MODE == "POSES":
            groups = {}                              # 속성(data_path) 별 묶음
            for fc in curves:
                groups.setdefault(fc.data_path, []).append(fc)
            for fcs in groups.values():
                fcs.sort(key=lambda c: c.array_index)
                b, a = clean_group(fcs, turn_size(fcs[0], scale))
                before += b
                after += a
        else:
            for fc in curves:
                b, a = clean_fcurve(fc, tolerance(fc, scale), turn_size(fc, scale))
                before += b
                after += a
        total_before += before
        total_after += after
        pct = 100.0 * (1 - after / before) if before else 0.0
        print(f"[Clean Keyframes] {act.name}: {before} -> {after} keys ({pct:.0f}% removed)")
    pct = 100.0 * (1 - total_after / total_before) if total_before else 0.0
    msg = f"Clean Keyframes: {total_before} -> {total_after} keys ({pct:.0f}% removed)"
    print(msg)
    return msg


class _Report(bpy.types.Operator):
    """결과를 상태바에 보여 주고 Ctrl+Z 로 되돌릴 수 있게 하는 오퍼레이터."""
    bl_idname = "wm.clean_keyframes_report"
    bl_label = "Clean Keyframes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        self.report({"INFO"}, main())
        return {"FINISHED"}


if __name__ == "__main__":
    try:
        bpy.utils.register_class(_Report)
    except ValueError:
        pass
    try:
        bpy.ops.wm.clean_keyframes_report()
    except RuntimeError:                             # 창이 없는 경우(명령줄 실행): 그냥 실행
        main()
