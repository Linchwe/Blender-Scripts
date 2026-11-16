# Export_FBX_ForUnity_HDRP.py
# Blender 4.2 ~ 4.5
#
# 용도
#  리깅이 끝난 캐릭터(아마추어 + 메쉬)를 유니티 HDRP 용 FBX 와 텍스처로 한 번에 내보냅니다.
#  오브젝트를 선택하지 않아도 되고, Export 창에서 옵션을 하나하나 맞출 필요가 없습니다.
#  URP 프로젝트는 Export_FBX_ForUnity_URP.py 를 쓰세요.
#
# 하는 일
#  1) .blend 파일이 있는 폴더에 Export 폴더를 만들고 "파일이름_UnityHDRP.fbx" 로 저장합니다. (같은 이름이면 덮어씀)
#  2) 씬에 있는 아마추어와 메쉬를 전부 내보냅니다. 카메라, 라이트, 엠프티는 넣지 않습니다.
#  3) 내보내는 동안만 아마추어의 액션과 포즈를 떼어서 원래 포즈(에디트 모드 포즈)로 내보내고,
#     끝나면 액션과 포즈를 실행 전 상태로 되돌립니다. 애니메이션은 넣지 않습니다.
#  4) 내보내기 옵션
#       Apply Scalings = FBX All, Forward = -Z, Up = Y, Apply Unit 켬, Use Space Transform 켬
#       Apply Transform 끔 (실험 기능이라 아마추어가 깨질 수 있음. 유니티의 Bake Axis Conversion 으로 대신함)
#       Smoothing = Face, Apply Modifiers 켬, Triangulate 끔, Tangent Space 끔
#       Primary/Secondary Bone Axis = Y/X, Armature Node Type = Null, Only Deform Bones 끔, Add Leaf Bones 끔
#       Bake Animation 끔, Path Mode = Strip (텍스처는 FBX 에 넣거나 복사하지 않고 5번의 TGA 를 따로 씀)
#  5) 머티리얼마다 HDRP Lit 셰이더에 맞게 텍스처를 합쳐서 Export\파일이름_UnityHDRP_Textures 폴더에 TGA 로 저장합니다.
#       머티리얼이름_BaseColor.tga : RGB 색, A 투명도 (투명한 곳이 없으면 A 없이 저장)
#       머티리얼이름_MaskMap.tga   : R 금속성, G AO, B 디테일 마스크(흰색), A 스무스니스(1 - 러프니스)
#       머티리얼이름_Normal.tga    : 노멀 (OpenGL 방식 그대로. 유니티도 OpenGL 방식)
#     Principled BSDF 에 연결된 이미지(Normal Map, Separate Color 노드를 거친 것도 읽음)와, 연결 없이 넣어 둔
#     AO 이미지 노드(이름에 AO 가 들어간 것)를 읽습니다. Bake_PBR_HighToLow.py 로 구운 머티리얼을 그대로 읽습니다.
#     이미지가 없는 맵은 소켓 값으로, AO 가 없으면 흰색(가림 없음)으로 채웁니다. 크기가 다르면 가장 큰 크기에 맞춥니다.
#     블렌더 머티리얼과 원본 이미지는 바꾸지 않습니다.
#
# 주의
#  - .blend 파일을 먼저 저장해 두어야 합니다.
#  - 씬에 숨겨 둔 메쉬(하이폴리 등)도 같이 나갑니다. 넣기 싫은 메쉬는 다른 씬으로 옮기거나 지우고 실행하세요.
#  - Principled BSDF 앞에 Math, Brightness/Contrast 같은 보정 노드가 있으면 그 입력은 읽지 못하고 값으로 채웁니다.
#    (콘솔에 [주의] 로 나옴) 이럴 때는 Bake_PBR_HighToLow.py 로 구운 뒤 내보내세요.
#  - 유니티에서 가져온 뒤 꼭 확인하세요.
#      Model 탭 : Bake Axis Conversion 켜기, 캐릭터 키가 맞는지 확인 (다르면 Scale Factor 로 맞춤)
#                 Normals = Import, Tangents = Calculate Mikktspace
#      Rig 탭   : Animation Type = Humanoid, Configure 에서 T포즈 경고가 나오면 Pose > Enforce T-Pose
#      텍스처   : MaskMap 은 sRGB (Color Texture) 끄기, Normal 은 Texture Type = Normal map
#      머티리얼 : HDRP/Lit 셰이더에서
#                 Base Map = BaseColor, Mask Map = MaskMap, Normal Map = Normal (Normal Map Space = Tangent Space)
#                 투명한 곳이 있으면 Alpha Clipping 을 켜거나 Surface Type = Transparent
#
# 사용법
#  1) Scripting 탭 > 새 텍스트 > 붙여넣기 > Run Script
#  2) 진행 상황은 Window > Toggle System Console 에서 볼 수 있습니다.

import bpy
import os

# 설정
OUT_FOLDER = "Export"   # .blend 옆에 만들 폴더 이름
SUFFIX = "UnityHDRP"
EXT = ".fbx"
OPERATOR = bpy.ops.export_scene.fbx


def make_settings(path):
    return dict(
        filepath=path, check_existing=False,
        use_selection=False, use_visible=False, use_active_collection=False,
        object_types={'ARMATURE', 'MESH'}, use_custom_props=False,
        global_scale=1.0, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
        apply_unit_scale=True, use_space_transform=True, bake_space_transform=False,
        mesh_smooth_type='FACE', use_mesh_modifiers=True, use_triangles=False, use_tspace=False,
        primary_bone_axis='Y', secondary_bone_axis='X', armature_nodetype='NULL',
        use_armature_deform_only=False, add_leaf_bones=False,
        bake_anim=False, path_mode='STRIP', embed_textures=False, batch_mode='OFF',
    )

# 확인
if not bpy.data.filepath:
    raise RuntimeError(".blend 파일을 먼저 저장하세요. 저장 위치에 Export 폴더를 만듭니다.")
arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not meshes:
    raise RuntimeError("내보낼 메쉬가 없습니다.")

out_dir = os.path.join(os.path.dirname(bpy.data.filepath), OUT_FOLDER)
os.makedirs(out_dir, exist_ok=True)
base = bpy.path.display_name_from_filepath(bpy.data.filepath)
path = os.path.join(out_dir, f"{base}_{SUFFIX}{EXT}")

# 오브젝트 모드로
if bpy.context.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')

# ---------------------------------------------------------------------------------------------
# 텍스처 묶기 (엔진용 채널 합치기)
# ---------------------------------------------------------------------------------------------
import re
import numpy as np

TEX_DIR = f"{base}_{SUFFIX}_Textures"


def srgb(c):
    # 선형 값을 sRGB 로
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def find_tex(sock):
    # 소켓에 연결된 이미지와 채널을 찾음. 반환: (이미지, 채널) / None(연결 없음) / "complex"(읽을 수 없는 노드)
    if not sock.is_linked:
        return None
    link = sock.links[0]
    node, out = link.from_node, link.from_socket.name
    for _ in range(4):
        if node.type == 'TEX_IMAGE':
            if node.image is None:
                return None
            return (node.image, 'A' if out == 'Alpha' else 'RGB')
        if node.type == 'NORMAL_MAP':
            nxt = node.inputs['Color']
            ch = None
        elif node.type in ('SEPARATE_COLOR', 'SEPRGB') and getattr(node, "mode", 'RGB') == 'RGB':
            nxt = node.inputs[0]
            ch = {'Red': 'R', 'Green': 'G', 'Blue': 'B', 'R': 'R', 'G': 'G', 'B': 'B'}.get(out)
        else:
            return "complex"
        if not nxt.is_linked:
            return None
        link = nxt.links[0]
        node, out = link.from_node, link.from_socket.name
        if ch and node.type == 'TEX_IMAGE' and node.image is not None:
            return (node.image, ch)
    return "complex"


AO_NAME = re.compile(r'(^|[^A-Za-z])AO([^A-Za-z]|$)', re.IGNORECASE)


def find_ao(mat):
    # AO 이미지 노드: glTF Material Output 의 Occlusion 에 연결된 것, 없으면 이름에 AO 가 들어간 이미지 노드
    nodes = mat.node_tree.nodes
    for n in nodes:
        if n.type == 'GROUP' and n.node_tree and n.node_tree.name in ("glTF Material Output", "glTF Settings"):
            occ = n.inputs.get("Occlusion")
            if occ is not None:
                r = find_tex(occ)
                if isinstance(r, tuple):
                    return r
    for n in nodes:
        if n.type == 'TEX_IMAGE' and n.image is not None:
            if AO_NAME.search(n.image.name) or AO_NAME.search(n.label) or AO_NAME.search(n.name):
                return (n.image, 'RGB')
    return None


def read(img, size, channel, rgb=False, to_srgb=False):
    # 이미지를 size 크기로 읽어서 채널 하나(H,W) 또는 RGB(H,W,3) 로 돌려줌. 블렌더 순서(아래에서 위) 그대로
    w, h = size
    src = img
    tmp = None
    if tuple(img.size) != (w, h):
        tmp = img.copy()
        tmp.scale(w, h)
        src = tmp
    try:
        n = src.size[0] * src.size[1] * 4
        if n == 0:
            return None
        a = np.empty(n, np.float32)
        src.pixels.foreach_get(a)
        a = a.reshape(h, w, 4)
        if to_srgb and src.is_float:
            a[..., :3] = srgb(a[..., :3])
    except Exception:
        return None
    finally:
        if tmp is not None:
            bpy.data.images.remove(tmp)
    if channel == 'RGB':
        return a[..., :3].copy() if rgb else a[..., 0].copy()
    return a[..., 'RGBA'.index(channel)].copy()


def gather(mat):
    # 머티리얼에서 Base Color, Alpha, Roughness, Metallic, Normal, AO 를 모음
    if not mat or not mat.use_nodes:
        return None
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return None
    src = {}
    warn = []
    for key, sock in (("color", "Base Color"), ("alpha", "Alpha"), ("rough", "Roughness"),
                      ("metal", "Metallic"), ("normal", "Normal")):
        r = find_tex(bsdf.inputs[sock])
        if r == "complex":
            warn.append(sock)
            r = None
        src[key] = r
    src["ao"] = find_ao(mat)
    imgs = [v[0] for v in src.values() if isinstance(v, tuple)]
    sizes = [tuple(i.size) for i in imgs if i.size[0] > 0]
    size = max(sizes, key=lambda s: s[0] * s[1]) if sizes else (256, 256)
    w, h = size

    def plane(key, default):
        v = src.get(key)
        if isinstance(v, tuple):
            p = read(v[0], size, v[1])
            if p is not None:
                return p
            warn.append(v[0].name)
        return np.full((h, w), default, np.float32)

    col = None
    if isinstance(src["color"], tuple):
        col = read(src["color"][0], size, src["color"][1], rgb=True, to_srgb=True)
        if col is not None and col.ndim == 2:
            col = np.repeat(col[..., None], 3, axis=2)
    if col is None:
        c = np.array(bsdf.inputs["Base Color"].default_value[:3], np.float32)
        col = np.broadcast_to(srgb(c), (h, w, 3)).copy()
    nrm = None
    if isinstance(src["normal"], tuple):
        nrm = read(src["normal"][0], size, 'RGB', rgb=True) if src["normal"][1] == 'RGB' else None
    return {
        "size": size, "color": col,
        "alpha": plane("alpha", bsdf.inputs["Alpha"].default_value),
        "rough": plane("rough", bsdf.inputs["Roughness"].default_value),
        "metal": plane("metal", bsdf.inputs["Metallic"].default_value),
        "ao": plane("ao", 1.0),
        "normal": nrm, "warn": warn,
        "found": [k for k, v in src.items() if isinstance(v, tuple)],
    }


def save_tga(path, chans, alpha=None):
    # 채널(H,W) 3개 또는 4개를 TGA 로 저장. alpha 가 None 이면 24비트 RGB
    h, w = chans[0].shape
    rgba = np.ones((h, w, 4), np.float32)
    for i, c in enumerate(chans[:3]):
        rgba[..., i] = np.clip(c, 0, 1)
    if alpha is not None:
        rgba[..., 3] = np.clip(alpha, 0, 1)
    img = bpy.data.images.new("_PackTemp", w, h, alpha=alpha is not None)
    try:
        img.colorspace_settings.name = 'Non-Color'
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = path
        img.file_format = 'TARGA'
        img.save()
    finally:
        bpy.data.images.remove(img)


def safe(name):
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "Material"


def export_textures():
    folder = os.path.join(out_dir, TEX_DIR)
    os.makedirs(folder, exist_ok=True)
    mats = []
    for o in meshes:
        for slot in o.material_slots:
            if slot.material and slot.material not in mats:
                mats.append(slot.material)
    done = 0
    for m in mats:
        d = gather(m)
        if d is None:
            print(f"  [건너뜀] {m.name} : Principled BSDF 가 없습니다.")
            continue
        has_alpha = bool((d["alpha"] < 0.999).any())
        files = pack(os.path.join(folder, safe(m.name)), d, has_alpha)
        done += 1
        print(f"  {m.name} ({d['size'][0]}x{d['size'][1]}) : {', '.join(files)}")
        labels = {"color": "Base Color", "rough": "Roughness", "metal": "Metallic", "normal": "Normal", "ao": "AO"}
        missing = [labels[k] for k in labels if k not in d["found"]]
        if missing:
            print(f"    이미지가 없어 값으로 채운 맵: {', '.join(missing)}")
        if d["warn"]:
            print(f"    [주의] 노드가 복잡해서 읽지 못한 입력: {', '.join(d['warn'])} (값으로 채움)")
    print(f"텍스처 저장: {folder} (머티리얼 {done}개)")


def pack(stem, d, has_alpha):
    c = d["color"]
    save_tga(stem + "_BaseColor.tga", [c[..., 0], c[..., 1], c[..., 2]], d["alpha"] if has_alpha else None)
    save_tga(stem + "_MaskMap.tga", [d["metal"], d["ao"], np.ones_like(d["metal"])], 1.0 - d["rough"])
    out = ["BaseColor", "MaskMap"]
    if d["normal"] is not None:
        n = d["normal"]
        save_tga(stem + "_Normal.tga", [n[..., 0], n[..., 1], n[..., 2]])
        out.append("Normal")
    return out


def rest_pose_on():
    # 아마추어마다 액션, NLA, 포즈 값을 기억해 두고 원래 포즈(에디트 모드 포즈)로 돌림
    saved = []
    for a in arms:
        ad = a.animation_data
        rec = {"obj": a, "pose": {}}
        if ad:
            rec["action"] = ad.action
            rec["slot"] = getattr(ad, "action_slot", None)
            rec["use_nla"] = ad.use_nla
            ad.action = None
            ad.use_nla = False
        for pb in a.pose.bones:
            rec["pose"][pb.name] = (pb.location.copy(), pb.rotation_mode, pb.rotation_quaternion.copy(),
                                    pb.rotation_euler.copy(), pb.rotation_axis_angle[:], pb.scale.copy())
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.rotation_axis_angle = (0, 0, 1, 0)
            pb.scale = (1, 1, 1)
        saved.append(rec)
    bpy.context.view_layer.update()
    return saved


def rest_pose_off(saved):
    # 기억해 둔 액션, NLA, 포즈 값을 그대로 되돌림
    for rec in saved:
        a = rec["obj"]
        for pb in a.pose.bones:
            v = rec["pose"].get(pb.name)
            if v is None:
                continue
            pb.location, pb.rotation_mode, pb.rotation_quaternion, pb.rotation_euler, aa, pb.scale = v
            pb.rotation_axis_angle = aa
        ad = a.animation_data
        if ad and "action" in rec:
            ad.action = rec["action"]
            if rec.get("slot") is not None and hasattr(ad, "action_slot"):
                try:
                    ad.action_slot = rec["slot"]
                except Exception:
                    pass
            ad.use_nla = rec["use_nla"]
    bpy.context.view_layer.update()


def run(op, settings):
    # 블렌더 버전에 없는 옵션은 빼고 실행
    valid = {p.identifier for p in op.get_rna_type().properties}
    kw = {k: v for k, v in settings.items() if k in valid}
    skipped = [k for k in settings if k not in valid]
    if skipped:
        print(f"이 블렌더 버전에 없어서 건너뛴 옵션: {', '.join(skipped)}")
    return op(**kw)


print("=" * 60)
print(f"{SUFFIX} 용으로 내보내기")
print(f"아마추어: {', '.join(o.name for o in arms) or '없음'}")
print(f"메쉬: {', '.join(o.name for o in meshes)}")
saved = rest_pose_on()
try:
    run(OPERATOR, make_settings(path))
finally:
    rest_pose_off(saved)
print(f"저장: {path}")
print("액션과 포즈는 실행 전 상태로 되돌렸습니다.")
export_textures()
print("=" * 60)
