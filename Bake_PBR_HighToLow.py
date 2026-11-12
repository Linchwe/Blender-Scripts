# Bake_PBR_HighToLow.py
# Blender 4.2 ~ 4.5
#
# 용도
#  하이폴리의 PBR 텍스처(Base Color, Roughness, Metallic, Normal)와 AO, Opacity 를 로우폴리로 한 번에 베이크합니다.
#  선택하고 Run Script 한 번이면 굽기, PNG 저장, 로우폴리 머티리얼 연결까지 끝납니다.
#
# 하는 일
#  0) 베이크 설정을 자동으로 맞춥니다. (끝나면 렌더 엔진, 장치, 샘플 수, AO 거리는 원래대로 돌림)
#       Render Engine = Cycles, Device = GPU Compute, Max Samples = 16 (AO 만 128),
#       Selected to Active 켜기, Extrusion 0.02, Max Ray Distance 0, Margin 16, Clear Image 켜기
#     GPU 는 Edit > Preferences > System > Cycles Render Devices 가 None 이면 OptiX → CUDA → HIP → oneAPI
#     순서로 찾아 켭니다. (이미 골라 둔 게 있으면 그대로 씀) GPU 가 없으면 CPU 로 굽습니다.
#  1) 로우폴리 머티리얼에 4096 x 4096 빈 이미지 6장을 만듭니다. (Base Color 는 sRGB, 나머지는 Non-Color)
#  2) 하이폴리의 모든 머티리얼 연결을 맵마다 바꿔 가며 차례로 굽습니다.
#       Base Color / Roughness / Metallic : Principled BSDF 에 들어가던 값을 Emission 으로 연결해 Emit 으로 굽기
#                                           (Brightness/Contrast 같은 보정 노드를 거친 값도 그대로 구움)
#       Normal                            : Principled BSDF 그대로 Normal (Tangent, OpenGL) 로 굽기
#       AO                                : 하이폴리 형태에서 Cycles 로 직접 굽기 (Pixal3D ORM 의 AO 는 쓰지 않음)
#                                           굽는 동안만 선택하지 않은 오브젝트(바닥, 소품, 다른 캐릭터 등)를
#                                           렌더에서 잠깐 빼서 그 그림자가 묻지 않게 하고, 끝나면 다시 켬
#       Opacity                           : Principled BSDF 의 Alpha 를 Emit 으로 굽기. Margin 0 으로 굽습니다.
#                                           하이폴리에 구멍(찢어진 천, 벨트 구멍)이 있으면 그 자리는 광선이 빗나가서 검정,
#                                           나머지는 흰색. 구멍이 없으면 전부 흰색입니다.
#                                           구멍 뒤의 몸을 맞히지 않도록 이 맵만 광선 거리를 EXTRUSION x 2 로 제한합니다.
#                                           구운 뒤 UV 경계 바깥으로 MARGIN(16) 픽셀만큼 직접 패딩을 넣습니다.
#                                             경계 픽셀이 검정이면 검정으로, 흰색이면 흰색으로 번지고,
#                                             검정과 흰색이 함께 닿는 곳은 검정이 우선입니다.
#                                           구멍 안쪽(UV 안)은 패딩이 들어가지 않아 검정 그대로 남습니다.
#                                           UV 영역은 로우폴리만 흰색으로 한 번 더 구워서 알아냅니다.
#                                           이때 하이폴리 선택을 잠깐 풀었다가 원래대로 다시 선택합니다.
#  3) 다 구우면 하이폴리 머티리얼을 원래대로 돌립니다. (중간에 오류가 나도 돌립니다)
#  4) .blend 파일이 있는 폴더에 "Baked Textures" 폴더를 만들고 PNG 로 저장합니다.
#       파일 이름 : 로우폴리이름_BaseColor.png / _Roughness.png / _Metallic.png / _Normal.png / _AO.png / _Opacity.png
#       같은 이름 파일이 있으면 덮어씁니다.
#  5) 로우폴리 머티리얼의 Principled BSDF 에 연결합니다. (Normal 은 Normal Map 노드를 거쳐서, Opacity 는 Alpha 에)
#     AO 는 Principled BSDF 에 입력이 없어서 이미지 노드만 넣어 두고 연결하지 않습니다. 엔진에서 AO 슬롯에 넣으세요.
#
# 주의
#  - .blend 파일을 먼저 저장해 두어야 합니다. (저장 위치에 Baked Textures 폴더를 만들기 때문)
#  - 하이폴리와 로우폴리가 같은 자리에 겹쳐 있어야 하고, 로우폴리는 UV 가 펴져 있어야 합니다.
#  - 하이폴리 머티리얼에 Principled BSDF 가 없으면 그 머티리얼은 건너뜁니다.
#  - 굽는 동안 블렌더가 멈춘 것처럼 보입니다. 4096 여섯 장이고 AO 는 샘플이 많아 오래 걸리니 끝날 때까지 기다리세요.
#    진행 상황은 Window > Toggle System Console 에서 볼 수 있습니다.
#  - 구운 결과에 구멍이나 검은 얼룩이 있으면 아래 EXTRUSION 을 0.02 ~ 0.05 로 올리고,
#    다른 부위 색이 묻어나면 내려서 다시 실행하세요.
#  - AO 가 너무 넓게 어두우면 AO_DISTANCE 를 내리고, 주름이나 틈이 잘 안 보이면 올리세요. 얼룩지면 AO_SAMPLES 를 올리세요.
#  - Normal 은 OpenGL 방식입니다. 유니티, 고도는 그대로 쓰고, 언리얼은 가져올 때 Flip Green Channel 을 켜세요.
#
# 사용법
#  1) 하이폴리와 로우폴리를 선택합니다. 로우폴리를 마지막에 선택해서 활성으로 만드세요.
#       3D 뷰포트에서 : 하이폴리 클릭 → 로우폴리 Shift+클릭
#       아웃라이너에서 : 하이폴리 이름 클릭 → 로우폴리 이름 Ctrl+클릭
#                       (아웃라이너에서 Shift+클릭은 사이에 있는 오브젝트까지 범위 선택되니 주의)
#     활성(로우폴리)은 테두리가 밝은 주황, 하이폴리는 진한 주황으로 보입니다.
#     둘이 겹쳐 있어서 뷰포트에서 클릭하기 어려우면 아웃라이너가 편합니다.
#  2) Scripting 탭 > 새 텍스트 > 붙여넣기 > Run Script
#  3) 끝나면 .blend 를 저장(Ctrl+S)하세요. 텍스처는 Baked Textures 폴더에 있습니다.

import bpy
import os
import time
import numpy as np

# 설정
SIZE      = 4096    # 텍스처 크기 (픽셀)
EXTRUSION = 0.02    # 광선을 쏘는 거리 (m). 구멍이 생기면 올리고, 다른 부위 색이 묻으면 내림
MARGIN    = 16      # UV 경계 바깥으로 색을 번지게 하는 폭 (픽셀). 이음새 방지
SAMPLES   = 16      # 베이크 샘플 수. Base Color, Roughness, Metallic, Normal, Opacity 는 16 이면 충분
AO_SAMPLES  = 128   # AO 샘플 수. AO 는 노이즈가 생기므로 많이
AO_DISTANCE = 0.1   # AO 를 계산할 거리 (m). 이 거리 안에 다른 면이 있으면 어두워짐. 사람 크기 캐릭터 기준 0.05 ~ 0.3

MAPS = [  # (맵 이름, Principled 입력, 베이크 종류, sRGB 여부)
    ("BaseColor", "Base Color", 'EMIT',   True),
    ("Roughness", "Roughness",  'EMIT',   False),
    ("Metallic",  "Metallic",   'EMIT',   False),
    ("Normal",    "Normal",     'NORMAL', False),
    ("AO",        None,         'AO',     False),
    ("Opacity",   "Alpha",      'EMIT',   False),
]
EMIT_NAME = "BakeEmission"

# 선택 확인
if not bpy.data.filepath:
    raise RuntimeError(".blend 파일을 먼저 저장하세요. 저장 위치에 Baked Textures 폴더를 만듭니다.")
low = bpy.context.view_layer.objects.active
highs = [o for o in bpy.context.selected_objects if o != low and o.type == 'MESH']
if low is None or low.type != 'MESH' or not highs:
    raise RuntimeError("하이폴리를 먼저 선택하고, 로우폴리를 마지막에 추가로 선택하세요 "
                       "(뷰포트는 Shift+클릭, 아웃라이너는 Ctrl+클릭).")
if not low.data.uv_layers:
    raise RuntimeError(f"로우폴리 '{low.name}' 에 UV 가 없습니다. UV 를 먼저 펴세요.")

out_dir = os.path.join(os.path.dirname(bpy.data.filepath), "Baked Textures")
os.makedirs(out_dir, exist_ok=True)

# 하이폴리 머티리얼 목록
high_mats = []
for o in highs:
    for s in o.material_slots:
        if s.material and s.material.use_nodes and s.material not in high_mats:
            high_mats.append(s.material)

# 로우폴리 머티리얼 준비 (없으면 새로 만듦)
if not low.material_slots or low.material_slots[0].material is None:
    m = bpy.data.materials.new(f"{low.name}_Baked")
    m.use_nodes = True
    if low.material_slots:
        low.material_slots[0].material = m
    else:
        low.data.materials.append(m)
low_mats = []
for s in low.material_slots:
    if s.material and s.material not in low_mats:
        s.material.use_nodes = True
        low_mats.append(s.material)


def make_image(map_name, srgb):
    # 하이폴리가 쓰는 원본 텍스처와 이름이 겹치지 않게 이미지 이름 끝에 (Baked) 를 붙임
    name = f"{low.name}_{map_name} (Baked)"
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, SIZE, SIZE, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    return img


def target_nodes(img):
    # 로우폴리의 모든 머티리얼에 이미지 노드를 넣고(이미 있으면 재사용) 선택해 둠
    result = []
    for m in low_mats:
        nodes = m.node_tree.nodes
        tag = f"Baked_{img.name}"
        n = nodes.get(tag)
        if n is None:
            n = nodes.new('ShaderNodeTexImage')
            n.name = n.label = tag
        n.image = img
        for x in nodes:
            x.select = False
        n.select = True
        nodes.active = n
        result.append(n)
    return result


def set_high(mode_input):
    # mode_input 이 None 이면 원래대로(Principled → Output), 아니면 그 입력값을 Emission 으로 연결
    skipped = []
    for m in high_mats:
        nodes, links = m.node_tree.nodes, m.node_tree.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None) \
            or next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if bsdf is None or out is None:
            skipped.append(m.name)
            continue
        surf = out.inputs['Surface']
        for l in list(surf.links):
            links.remove(l)
        emit = nodes.get(EMIT_NAME)
        if mode_input is None:
            links.new(bsdf.outputs['BSDF'], surf)
            if emit is not None:
                nodes.remove(emit)
            continue
        if emit is None:
            emit = nodes.new('ShaderNodeEmission')
            emit.name = emit.label = EMIT_NAME
            emit.location = (out.location.x, out.location.y - 200)
        emit.inputs['Strength'].default_value = 1.0
        col = emit.inputs['Color']
        for l in list(col.links):
            links.remove(l)
        src = bsdf.inputs[mode_input]
        if src.links:
            links.new(src.links[0].from_socket, col)
        else:
            v = src.default_value
            col.default_value = tuple(v) if mode_input == "Base Color" else (v, v, v, 1.0)
        links.new(emit.outputs['Emission'], surf)
    return skipped


def connect_low(images):
    # 로우폴리 Principled BSDF 에 구운 텍스처 연결
    for m in low_mats:
        nodes, links = m.node_tree.nodes, m.node_tree.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        for i, (map_name, socket, btype, srgb) in enumerate(MAPS):
            img = images.get(map_name)
            if img is None:
                continue
            tex = nodes.get(f"Baked_{img.name}")
            tex.location = (bsdf.location.x - 700, bsdf.location.y - i * 300)
            if socket is None:
                continue
            if map_name == "Normal":
                nm = nodes.get("Baked_NormalMap") or nodes.new('ShaderNodeNormalMap')
                nm.name = nm.label = "Baked_NormalMap"
                nm.location = (bsdf.location.x - 300, bsdf.location.y - i * 300)
                links.new(tex.outputs['Color'], nm.inputs['Color'])
                links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
            else:
                links.new(tex.outputs['Color'], bsdf.inputs[socket])


GEOM_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES', 'POINTCLOUD', 'VOLUME'}


def isolate_render(on, hidden):
    # on=True: 선택하지 않은 형태 오브젝트를 렌더에서 빼고 목록에 기억 / on=False: 기억한 것만 다시 켬
    if on:
        keep = set(highs) | {low}
        for o in bpy.context.view_layer.objects:
            if o.type in GEOM_TYPES and o not in keep and not o.hide_render:
                o.hide_render = True
                hidden.append(o)
    else:
        for o in hidden:
            o.hide_render = False
        hidden.clear()
    bpy.context.view_layer.update()


def shift(a, dy, dx, fill):
    # 배열을 dy, dx 칸 밀기 (가장자리는 fill 로 채움, 반대편으로 넘어가지 않음)
    out = np.full_like(a, fill)
    h, w = a.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = \
        a[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def uv_mask():
    # 로우폴리 UV 가 덮는 픽셀은 True, 빈 곳은 False
    # 로우폴리만 선택해서 흰색 Emission 을 Margin 0 으로 구워 알아냄 (끝나면 선택, 노드 모두 원래대로)
    mimg = bpy.data.images.new("BakeTempMask", SIZE, SIZE, alpha=False, float_buffer=False)
    mimg.colorspace_settings.name = 'Non-Color'
    target_nodes(mimg)
    saved = []
    for m in low_mats:
        nodes, links = m.node_tree.nodes, m.node_tree.links
        out = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None) \
            or next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if out is None:
            out = nodes.new('ShaderNodeOutputMaterial')
        surf = out.inputs['Surface']
        old_from = surf.links[0].from_socket if surf.links else None
        e = nodes.new('ShaderNodeEmission')
        e.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        e.inputs['Strength'].default_value = 1.0
        links.new(e.outputs['Emission'], surf)
        saved.append((m, out, e, old_from))
    sel = list(bpy.context.selected_objects)
    for o in sel:
        if o != low:
            o.select_set(False)
    bk.use_selected_to_active = False
    bk.margin = 0
    try:
        bpy.ops.object.bake(type='EMIT')
    finally:
        bk.use_selected_to_active = True
        for o in sel:
            o.select_set(True)
        bpy.context.view_layer.objects.active = low
        for m, out, e, old_from in saved:
            m.node_tree.nodes.remove(e)
            if old_from is not None:
                m.node_tree.links.new(old_from, out.inputs['Surface'])
            tn = m.node_tree.nodes.get(f"Baked_{mimg.name}")
            if tn is not None:
                m.node_tree.nodes.remove(tn)
    px = np.empty(SIZE * SIZE * 4, np.float32)
    mimg.pixels.foreach_get(px)
    bpy.data.images.remove(mimg)
    return px.reshape(SIZE, SIZE, 4)[:, :, 0] > 0.5


def pad_black_first(img, covered, width):
    # UV 바깥으로 width 픽셀 패딩. 이웃한 UV 픽셀 중 가장 어두운 값을 가져옴 (검정 우선)
    px = np.empty(SIZE * SIZE * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(SIZE, SIZE, 4)
    v = np.where(covered, px[:, :, 0], 2.0).astype(np.float32)   # 2.0 = 아직 빈 픽셀
    for _ in range(width):
        best = np.full_like(v, 2.0)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    np.minimum(best, shift(v, dy, dx, 2.0), out=best)
        new = (v > 1.5) & (best < 1.5)
        if not new.any():
            break
        v[new] = best[new]
    v[v > 1.5] = 0.0     # 패딩 밖 빈 곳은 검정
    px[:, :, 0] = px[:, :, 1] = px[:, :, 2] = v
    px[:, :, 3] = 1.0
    img.pixels.foreach_set(px.ravel())
    img.update()


def use_gpu():
    # Preferences 의 Cycles Render Devices 에서 GPU 를 찾아 켬. 찾으면 장치 이름, 못 찾으면 None
    addon = bpy.context.preferences.addons.get('cycles')
    if addon is None:
        return None
    cp = addon.preferences
    if cp.compute_device_type == 'NONE':
        for t in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
            try:
                cp.compute_device_type = t
            except TypeError:
                continue
            cp.get_devices()
            if any(d.type == t for d in cp.devices):
                break
        else:
            cp.compute_device_type = 'NONE'
            return None
    cp.get_devices()
    gpus = [d for d in cp.devices if d.type == cp.compute_device_type]
    if not gpus:
        return None
    for d in gpus:
        d.use = True
    return f"{cp.compute_device_type} ({', '.join(d.name for d in gpus)})"


# 베이크 설정 (끝나면 원래 값으로 돌림)
sc = bpy.context.scene
old = (sc.render.engine, sc.cycles.samples, sc.cycles.bake_type, sc.cycles.device)
temp_world = sc.world is None
if temp_world:
    sc.world = bpy.data.worlds.new("BakeTempWorld")
old_ao_dist = sc.world.light_settings.distance
sc.render.engine = 'CYCLES'
gpu = use_gpu()
sc.cycles.device = 'GPU' if gpu else 'CPU'
sc.cycles.samples = SAMPLES
bk = sc.render.bake
bk.use_selected_to_active = True
bk.cage_extrusion = EXTRUSION
bk.max_ray_distance = 0.0
bk.margin = MARGIN
bk.use_clear = True
bk.normal_space = 'TANGENT'

print("=" * 60)
print(f"하이폴리: {', '.join(o.name for o in highs)}  →  로우폴리: {low.name}")
print(f"크기 {SIZE}, 저장 위치: {out_dir}")
print(f"장치: GPU {gpu}" if gpu else "GPU 를 찾지 못해 CPU 로 굽습니다. (오래 걸림)")

images, skipped, start = {}, [], time.time()
hidden = []
try:
    for map_name, socket, btype, srgb in MAPS:
        img = make_image(map_name, srgb)
        target_nodes(img)
        skipped = set_high(socket if btype == 'EMIT' else None)
        if map_name == "Opacity":
            bk.margin = 0                       # 구멍 자리에 흰색이 번지지 않게
            bk.max_ray_distance = EXTRUSION * 2  # 구멍 너머의 몸을 맞히지 않게
        else:
            bk.margin = MARGIN
            bk.max_ray_distance = 0.0
        if btype == 'AO':
            sc.cycles.samples = AO_SAMPLES
            sc.world.light_settings.distance = AO_DISTANCE
            isolate_render(True, hidden)
            if hidden:
                print(f"  AO 동안 렌더에서 잠깐 뺀 오브젝트 {len(hidden)}개: {', '.join(o.name for o in hidden)}")
        else:
            sc.cycles.samples = SAMPLES
        t0 = time.time()
        print(f"[굽는 중] {map_name} ...")
        bpy.ops.object.bake(type=btype)
        if hidden:
            isolate_render(False, hidden)
        if map_name == "Opacity":
            print("  UV 경계 패딩 넣는 중 ...")
            pad_black_first(img, uv_mask(), MARGIN)

        path = os.path.join(out_dir, f"{low.name}_{map_name}.png")
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        img.source = 'FILE'
        img.filepath = bpy.path.relpath(path)
        img.reload()
        img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
        images[map_name] = img
        print(f"[완료] {map_name} → {os.path.basename(path)}  ({time.time() - t0:.0f}초)")
finally:
    if hidden:
        isolate_render(False, hidden)
    set_high(None)
    sc.render.engine, sc.cycles.samples, sc.cycles.bake_type, sc.cycles.device = old
    sc.world.light_settings.distance = old_ao_dist
    bk.margin = MARGIN
    bk.max_ray_distance = 0.0
    if temp_world:
        w = sc.world
        sc.world = None
        bpy.data.worlds.remove(w)

connect_low(images)

print(f"하이폴리 머티리얼을 원래대로 돌렸습니다.")
if skipped:
    print(f"Principled BSDF 가 없어 건너뛴 머티리얼: {', '.join(skipped)}")
print(f"구운 텍스처 {len(images)}장을 저장하고 로우폴리 머티리얼에 연결했습니다. ({time.time() - start:.0f}초)")
print("이제 .blend 파일을 저장(Ctrl+S)하세요.")
print("=" * 60)
