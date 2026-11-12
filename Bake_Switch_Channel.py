# Bake_Switch_Channel.py
# Blender 4.2 ~ 4.5
#
# 용도
#  하이폴리의 PBR 텍스처(Base Color, Roughness, Metallic, Normal)를 로우폴리로 베이크할 때,
#  하이폴리 머티리얼 연결을 굽고 싶은 맵에 맞게 한 번에 바꿔 주는 스크립트입니다.
#  MODE = "ALL" 이면 네 장을 순서대로 자동으로 다 굽습니다.
#
# 하는 일
#  1) 선택한 하이폴리 오브젝트(활성 오브젝트를 뺀 나머지)의 모든 머티리얼에 BakeEmission 노드를 하나씩 넣고,
#     MODE 에 맞는 값을 Emission 에 연결한 뒤 Emission 을 Material Output 에 연결합니다.
#       BASECOLOR : Principled BSDF 의 Base Color 에 들어가던 것 (Brightness/Contrast 같은 보정 노드 포함)
#       ROUGHNESS : Principled BSDF 의 Roughness 에 들어가던 것
#       METALLIC  : Principled BSDF 의 Metallic 에 들어가던 것
#       NORMAL    : Emission 을 쓰지 않고 Principled BSDF 를 Material Output 에 다시 연결
#       RESTORE   : 원래대로 Principled BSDF 를 Output 에 연결하고 BakeEmission 노드를 지움
#       ALL       : BASECOLOR → ROUGHNESS → METALLIC → NORMAL 을 차례로 연결하고 직접 구운 뒤,
#                   마지막에 RESTORE 까지 하고, 구운 이미지를 .blend 파일 안에 보관(pack)합니다
#     값이 이미지가 아니라 숫자로만 들어 있는 머티리얼은 그 숫자를 Emission 색으로 넣습니다.
#  2) 로우폴리(활성 오브젝트) 머티리얼에서 이름에 BaseColor / Roughness / Metallic / Normal 이 들어간
#     이미지 노드를 찾아 선택해 둡니다. (블렌더는 선택된 이미지 노드에 굽습니다)
#  3) Bake Type 을 맞춰 둡니다. (BASECOLOR, ROUGHNESS, METALLIC = Emit / NORMAL = Normal, Tangent)
#     Selected to Active 도 켜 둡니다. Extrusion, Margin, 샘플 수는 건드리지 않습니다.
#
# 주의
#  - 하이폴리를 먼저 선택하고, 로우폴리를 마지막에 추가로 선택해서 로우폴리가 활성이어야 합니다.
#    활성 오브젝트는 테두리가 밝은 주황(노란빛 주황), 나머지는 진한 주황으로 보입니다.
#  - 머티리얼에 Principled BSDF 가 없으면 그 머티리얼은 건너뜁니다.
#  - 원래 있던 노드와 연결(Principled 쪽)은 지우지 않으므로, RESTORE 로 언제든 원래대로 돌아갑니다.
#  - 로우폴리 머티리얼에 구울 빈 이미지 노드가 미리 있어야 합니다. 이름에 BaseColor / Roughness /
#    Metallic / Normal 이 들어가게 만드세요. (BaseColor 는 sRGB, 나머지는 Non-Color)
#  - ALL 은 굽는 동안 블렌더가 멈춘 것처럼 보입니다. 끝날 때까지 기다리세요.
#  - 구운 이미지는 블렌더 안에만 있습니다. ALL 은 pack 까지 해 두므로 .blend 를 저장하면 남지만,
#    PNG 파일이 필요하면 Image Editor 에서 Image > Save As 로 따로 저장하세요.
#  - 굽기 전에 Render Properties > Sampling > Render 의 Max Samples 를 16 정도로 낮춰 두면 빠릅니다.
#
# 사용법
#  1) 하이폴리와 로우폴리 선택 (로우폴리가 마지막 = 활성)
#       3D 뷰포트에서 : 하이폴리 클릭 → 로우폴리 Shift+클릭
#       아웃라이너에서 : 하이폴리 이름 클릭 → 로우폴리 이름 Ctrl+클릭
#                       (아웃라이너에서 Shift+클릭은 사이에 있는 오브젝트까지 범위 선택되니 주의)
#     둘이 겹쳐 있어서 뷰포트에서 클릭하기 어려우면 아웃라이너가 편합니다.
#  2) Scripting 탭 > 새 텍스트 > 붙여넣기 > 아래 MODE 를 고르고 Run Script
#  3) 한꺼번에 굽기 : MODE = "ALL" 로 실행하면 끝 (Bake 버튼 안 눌러도 됨)
#     한 장씩 굽기   : MODE 를 BASECOLOR 로 실행 → Render Properties > Bake 패널의 Bake 버튼 클릭
#                      → ROUGHNESS → METALLIC → NORMAL 순서로 반복 → 마지막에 RESTORE 로 실행

import bpy

# 설정
MODE = "ALL"        # ALL / BASECOLOR / ROUGHNESS / METALLIC / NORMAL / RESTORE

SOCKET = {"BASECOLOR": "Base Color", "ROUGHNESS": "Roughness", "METALLIC": "Metallic"}
TARGET_KEY = {"BASECOLOR": "basecolor", "ROUGHNESS": "roughness", "METALLIC": "metallic", "NORMAL": "normal"}
ORDER = ("BASECOLOR", "ROUGHNESS", "METALLIC", "NORMAL")
EMIT_NAME = "BakeEmission"

if MODE not in ("ALL", "BASECOLOR", "ROUGHNESS", "METALLIC", "NORMAL", "RESTORE"):
    raise RuntimeError(f"MODE 값이 잘못됐습니다: {MODE}")

low = bpy.context.view_layer.objects.active
highs = [o for o in bpy.context.selected_objects if o != low and o.type == 'MESH']
if low is None or low.type != 'MESH' or not highs:
    raise RuntimeError("하이폴리를 먼저 선택하고, 로우폴리를 마지막에 추가로 선택하세요 "
                       "(뷰포트는 Shift+클릭, 아웃라이너는 Ctrl+클릭).")

mats = []
for o in highs:
    for s in o.material_slots:
        if s.material and s.material.use_nodes and s.material not in mats:
            mats.append(s.material)


def set_links(mode):
    # 하이폴리 머티리얼 연결 바꾸기. 바꾼 머티리얼 이름과 건너뛴 머티리얼 이름을 돌려줌
    done, skipped = [], []
    for m in mats:
        nt = m.node_tree
        nodes, links = nt.nodes, nt.links
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

        if mode in ("NORMAL", "RESTORE"):
            links.new(bsdf.outputs['BSDF'], surf)
            if mode == "RESTORE" and emit is not None:
                nodes.remove(emit)
            done.append(m.name)
            continue

        if emit is None:
            emit = nodes.new('ShaderNodeEmission')
            emit.name = emit.label = EMIT_NAME
            emit.location = (out.location.x, out.location.y - 200)
        emit.inputs['Strength'].default_value = 1.0
        col = emit.inputs['Color']
        for l in list(col.links):
            links.remove(l)

        src = bsdf.inputs[SOCKET[mode]]
        if src.links:
            links.new(src.links[0].from_socket, col)
        else:
            v = src.default_value
            col.default_value = tuple(v) if mode == "BASECOLOR" else (v, v, v, 1.0)
        links.new(emit.outputs['Emission'], surf)
        done.append(m.name)
    return done, skipped


def select_target(mode):
    # 로우폴리 머티리얼에서 구울 이미지 노드를 선택. 찾은 이미지를 돌려줌 (없으면 None)
    key = TARGET_KEY[mode]
    found = None
    for s in low.material_slots:
        if not (s.material and s.material.use_nodes):
            continue
        tn = s.material.node_tree.nodes
        cand = [n for n in tn if n.type == 'TEX_IMAGE' and n.image and key in n.image.name.lower()]
        for n in tn:
            n.select = False
        if cand:
            cand[0].select = True
            tn.active = cand[0]
            found = cand[0].image
    return found


def set_bake(mode):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.render.bake.use_selected_to_active = True
    if mode == "NORMAL":
        sc.cycles.bake_type = 'NORMAL'
        sc.render.bake.normal_space = 'TANGENT'
    else:
        sc.cycles.bake_type = 'EMIT'
    return sc.cycles.bake_type


print("=" * 60)
print(f"MODE = {MODE}")

if MODE == "ALL":
    import time
    baked, missing = [], []
    try:
        for mode in ORDER:
            img = select_target(mode)
            if img is None:
                missing.append(mode)
                print(f"[건너뜀] {mode}: 로우폴리에 이름에 '{TARGET_KEY[mode]}' 가 들어간 이미지 노드가 없습니다.")
                continue
            done, skipped = set_links(mode)
            btype = set_bake(mode)
            t0 = time.time()
            print(f"[굽는 중] {mode} → {img.name} ({btype}) ...")
            bpy.ops.object.bake(type=btype)
            try:
                img.pack()
            except Exception as e:
                print(f"  pack 실패 (Image > Save As 로 저장하세요): {e}")
            baked.append(img.name)
            print(f"[완료] {mode} → {img.name}  {time.time() - t0:.0f}초")
    finally:
        done, skipped = set_links("RESTORE")
        print("하이폴리 머티리얼을 원래대로 돌렸습니다.")
    if skipped:
        print(f"Principled BSDF 가 없어 건너뛴 머티리얼: {', '.join(skipped)}")
    print(f"구운 이미지 {len(baked)}장: {', '.join(baked)}")
    if missing:
        print(f"이미지 노드가 없어 굽지 못한 맵: {', '.join(missing)}")
    print(".blend 파일 안에 보관(pack)했습니다. 파일을 저장하세요. PNG 가 필요하면 Image > Save As.")

else:
    done, skipped = set_links(MODE)
    print(f"바꾼 머티리얼 {len(done)}개: {', '.join(done)}")
    if skipped:
        print(f"Principled BSDF 가 없어 건너뛴 머티리얼: {', '.join(skipped)}")
    if MODE == "RESTORE":
        print("하이폴리 머티리얼을 원래대로 돌렸습니다. 구운 이미지는 Image > Save As 로 저장하세요.")
    else:
        img = select_target(MODE)
        print(f"굽는 이미지: {img.name}" if img else
              f"로우폴리 머티리얼에 이름에 '{TARGET_KEY[MODE]}' 가 들어간 이미지 노드가 없습니다. 직접 만들고 선택하세요.")
        print(f"Bake Type: {set_bake(MODE)}  →  이제 Bake 버튼을 누르세요.")

print("=" * 60)
