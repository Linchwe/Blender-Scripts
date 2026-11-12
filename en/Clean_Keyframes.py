"""Clean Keyframes - remove meaningless keyframes from baked animation
(Mixamo, motion capture, AI-generated animation, etc.)

Baked animation has a key on every frame. There are two modes.

  POSES (default): removes all in-between keys while a motion keeps going in one direction, and keeps only these keys.
      - Where the direction changes (a bone's rotation/location is treated as one movement: the moment the
        movement slows sharply to change direction. For single values: the peaks and valleys where it goes up then down)
      - The start and end of fully still sections
      - The very first and last frames
    What remains is close to the key poses an animator would set by hand, so keys drop a lot and editing is easy. In exchange,
    the keys are reconnected with Bezier curves (ease in, ease out), so the result can differ slightly from the original.
    One extra key is kept only where the curve between keys strays far (more than SAFETY_ROTATION_DEG) from the original.
    A bone's rotation components (4 quaternion values) or location components (3) always keep keys on the same frames.

  ACCURATE: keeps every key needed for the difference from the original to stay within the tolerances (TOLERANCE values below).
    Almost identical to the original, but fewer keys are removed.

All remaining keys use Bezier (Auto Clamped) interpolation.

※ Don't run Blender's Decimate first. Run this directly on the original that has a key on every frame.

Usage (Blender 4.2 or later, 5.x also works)
  1. In Object Mode, select the armature (or object) with the animation.
  2. Scripting tab > Text > Open > this file > Run Script (Alt+P in the Text Editor).
  3. The result is shown in the status bar below and in the System Console (Window > Toggle System Console).
     To undo, press Ctrl+Z.

The settings are right below.
"""
import math

import bpy

# ----------------------------------------------------------------------------- Settings
MODE = "POSES"                 # "POSES": keep only direction changes and holds.  "ACCURATE": almost identical to the original

# POSES mode settings
TURN_ROTATION_DEG = 4.0        # Merge keys if the pose between them changes less than this (degrees). Larger = fewer keys
TURN_LOCATION_M = 0.02         # Direction-change threshold for location (world meters, 0.02 = 2cm)
TURN_OTHER = 0.01              # Direction-change threshold for other values such as scale
SMOOTH_FRAMES = 5              # Only when finding direction changes, view the curve smoothed over this many frames (ignores jitter). 1 = off
HOLD_FRAMES = 4                # Barely moving for this many frames or more counts as a 'hold'; keys are kept at its start and end
SAFETY_ROTATION_DEG = 3.0      # Keep one extra key only where the curve between keys strays more than this (degrees) from the original. 0 = off
SAFETY_LOCATION_M = 0.03       # Location threshold (meters) when SAFETY_ROTATION_DEG is on

# ACCURATE mode settings
ROTATION_TOLERANCE_DEG = 0.2   # Allowed rotation error (degrees). Larger = fewer keys
LOCATION_TOLERANCE_M = 0.002   # Allowed location error (world meters, 0.002 = 2mm)
SCALE_TOLERANCE = 0.001        # Allowed scale error (0.001 = 0.1%)
OTHER_TOLERANCE = 0.001        # Allowed error for other values (custom properties, shape keys, etc.)
ALL_ACTIONS = False            # False: only the current action of the selected objects. True: every action in the file
SELECTED_ONLY = True           # False: every object in the scene regardless of selection
# -----------------------------------------------------------------------------


def action_fcurves(action):
    """F-curves of an action (legacy style, or the layered/slotted actions of Blender 4.4+ / 5.x)."""
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
        # If a quaternion component changes by d, the rotation changes by about 2*d radians
        return math.radians(ROTATION_TOLERANCE_DEG) / 2.0
    if p.endswith("rotation_euler") or p.endswith("rotation_axis_angle"):
        return math.radians(ROTATION_TOLERANCE_DEG)
    if p.endswith("location"):
        return LOCATION_TOLERANCE_M / loc_scale
    if p.endswith("scale"):
        return SCALE_TOLERANCE
    return OTHER_TOLERANCE


def rdp(xs, ys, tol):
    """Indices of keys to keep using Ramer-Douglas-Peucker (judged by value difference from the frame-value line)."""
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
    """POSES mode: the smallest reversal on this curve that counts as 'the direction changed'."""
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
    """Key indices at direction-change peaks/valleys and at the start/end of holds.
    Reversals smaller than turn (jitter) don't count as direction changes."""
    n = len(ys)
    keep = {0, n - 1}
    raw = ys
    ys = _smoothed(raw, SMOOTH_FRAMES)                # find direction changes on the curve with jitter filtered out
    # 1) Direction changes: zigzag method. When it reverses by more than turn from a peak (or valley), that peak becomes a key
    trend, ext = 0, 0                                # trend: 1 going up, -1 going down, 0 unknown yet
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
    # Move each found peak to the frame near it (within SMOOTH_FRAMES) where the original actually sticks out most
    h = max(1, SMOOTH_FRAMES // 2)
    moved = {0, n - 1}
    for e in keep - {0, n - 1}:
        lo, hi = max(0, e - h), min(n, e + h + 1)
        up = ys[e] >= (ys[max(0, e - 1)] + ys[min(n - 1, e + 1)]) / 2
        moved.add(max(range(lo, hi), key=lambda m: raw[m] if up else -raw[m]))
    keep = moved
    ys = raw
    # 2) Holds: start and end of sections where the value stays almost the same for HOLD_FRAMES or more
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
    """Treat a group of components (4 rotation, 3 location) as one movement and pick key frame indices.
    When a bone changes direction or stops, its movement slows sharply at that moment, so frames where speed drops well below
    its surroundings, and the start/end of holds, are kept as keys. Keys whose pose differs by less than turn are merged (ignores jitter)."""
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
    still = turn * 0.25 / max(1, HOLD_FRAMES)       # moving less than this per frame counts as stopped
    start = None
    for i in range(1, n + 1):
        if i < n and sp[i] <= still:
            start = i - 1 if start is None else start
        else:
            if start is not None and i - 1 - start >= HOLD_FRAMES:
                cand.update((start, i - 1))
            start = None
    keep = [0]
    for i in sorted(cand - {0}):                     # merge if the pose didn't change by even turn
        d = math.sqrt(sum((Y[k][i] - Y[k][keep[-1]]) ** 2 for k in range(c)))
        if d > turn or i == n - 1:
            keep.append(i)
    return keep


def rebuild(fc, xs, ys, idx):
    """Remove all keys from the curve and re-insert only the original keys at the idx positions (Bezier, Auto Clamped handles)."""
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
    """Clean up one curve. Returns (key count before, key count after)."""
    kps = fc.keyframe_points
    n = len(kps)
    if n < 3:
        return n, n
    co = [0.0] * (2 * n)
    kps.foreach_get("co", co)
    xs, ys = co[0::2], co[1::2]
    if max(ys) - min(ys) <= (turn if MODE == "POSES" else tol):   # a curve that barely changes: one key is enough
        rebuild(fc, xs, ys, [0])
        return n, 1
    if MODE == "POSES":
        idx = pose_keys(ys, turn)
        rebuild(fc, xs, ys, idx)
        return n, len(idx)
    keep = set(rdp(xs, ys, tol * 0.5))
    for _ in range(50):                              # re-insert original keys where it differs from the original
        idx = sorted(keep)
        rebuild(fc, xs, ys, idx)
        err = [abs(fc.evaluate(x) - y) for x, y in zip(xs, ys)]
        added = False
        for a, b in zip(idx, idx[1:]):               # in each section with a large error, the frame that strays the most
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
    """POSES mode: clean up components of the same property (e.g. a bone's 4 rotation or 3 location components) as one group.
    The peaks and hold frames found for each component are combined, and every component in the group keeps keys on the same frames.
    (Keeping keys on different frames per component mixes up the rotation)"""
    data = [_read(fc) for fc in fcs]
    n = len(data[0][0])
    same = all(len(xs) == n and xs == data[0][0] for xs, _ in data)
    if not same or n < 3:                            # if key frames differ per component, process them one by one
        tot = [clean_fcurve(fc, None, rev) for fc in fcs]
        return sum(t[0] for t in tot), sum(t[1] for t in tot)
    xs = data[0][0]
    ys = [list(d[1]) for d in data]
    if fcs[0].data_path.endswith("rotation_quaternion") and len(fcs) == 4:
        # Quaternions q and -q are the same rotation: if the sign flips midway the values jump, so make it continuous
        for i in range(1, n):
            if sum(ys[c][i] * ys[c][i - 1] for c in range(4)) < 0:
                for c in range(4):
                    ys[c][i] = -ys[c][i]
    if all(max(y) - min(y) <= rev for y in ys):      # barely moves: one key is enough
        idx = [0]
    else:
        idx = pose_keys_vec(ys, rev) if len(ys) > 1 else pose_keys(ys[0], rev)
    for fc, y in zip(fcs, ys):
        rebuild(fc, xs, y, idx)
    if SAFETY_ROTATION_DEG > 0 and len(idx) > 1:     # add keys only in sections that stray far from the original
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
    """The object's world scale (used to adjust the location error when it is 0.01x, like a Mixamo FBX)."""
    s = obj.matrix_world.to_scale()
    return max(abs(s.x), abs(s.y), abs(s.z)) or 1.0


def main():
    objs = bpy.context.selected_objects if SELECTED_ONLY else bpy.context.scene.objects
    jobs = {}                                        # action -> location scale
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
            groups = {}                              # groups per property (data_path)
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
    """Operator that shows the result in the status bar and allows undo with Ctrl+Z."""
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
    except RuntimeError:                             # no window (command line run): just run it
        main()
