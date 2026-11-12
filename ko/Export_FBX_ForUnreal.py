# Export_FBX_ForUnreal.py
# Blender 4.2 ~ 4.5
#
# 용도
#  리깅이 끝난 캐릭터(아마추어 + 메쉬)를 언리얼 엔진 5 용 FBX 로 한 번에 내보냅니다.
#  오브젝트를 선택하지 않아도 되고, Export 창에서 옵션을 하나하나 맞출 필요가 없습니다.
#
# 하는 일
#  1) .blend 파일이 있는 폴더에 Export 폴더를 만들고 "파일이름_Unreal.fbx" 로 저장합니다. (같은 이름이면 덮어씀)
#  2) 씬에 있는 아마추어와 메쉬를 전부 내보냅니다. 카메라, 라이트, 엠프티는 넣지 않습니다.
#  3) 내보내는 동안만 아마추어의 액션과 포즈를 떼어서 원래 포즈(에디트 모드 포즈)로 내보내고,
#     끝나면 액션과 포즈를 실행 전 상태로 되돌립니다. 애니메이션은 넣지 않습니다.
#  4) 내보내기 옵션 (유니티용과 다른 곳에 ※)
#       Apply Scalings = FBX All, Forward = -Z, Up = Y, Apply Unit 켬, Use Space Transform 켬, Apply Transform 끔
#       Smoothing = Face, Apply Modifiers 켬, ※ Triangulate 켬 (블렌더와 언리얼의 삼각형 분할을 같게 해서 노멀맵 이음새 방지)
#       Tangent Space 끔, Primary/Secondary Bone Axis = Y/X, Armature Node Type = Null
#       Only Deform Bones 끔, Add Leaf Bones 끔, Bake Animation 끔, Path Mode = Copy
#
# 주의
#  - .blend 파일을 먼저 저장해 두어야 합니다.
#  - 씬에 숨겨 둔 메쉬(하이폴리 등)도 같이 나갑니다. 넣기 싫은 메쉬는 다른 씬으로 옮기거나 지우고 실행하세요.
#  - 아마추어 오브젝트 이름은 "Armature" 그대로 두세요. 언리얼은 이 이름의 노드를 빼고 그 아래 첫 본
#    (AccuRIG 리그는 RL_BoneRoot) 을 루트 본으로 씁니다. 이름을 바꾸면 루트 본이 하나 더 생깁니다.
#  - 언리얼에서 가져온 뒤 꼭 확인하세요.
#      캐릭터 키가 맞는지 (UE 마네킹이 약 180cm). 다르면 임포트 옵션의 Uniform Scale 로 맞춤
#      노멀은 Import Normals 로 (자동 계산하면 블렌더에서 만든 노멀이 사라짐)
#  - 언리얼 머티리얼은 Roughness, Metallic, AO 를 따로 꽂아도 되고, ORM 한 장으로 합쳐 써도 됩니다.
#
# 사용법
#  1) Scripting 탭 > 새 텍스트 > 붙여넣기 > Run Script
#  2) 진행 상황은 Window > Toggle System Console 에서 볼 수 있습니다.

import bpy

# 설정
OUT_FOLDER = "Export"   # .blend 옆에 만들 폴더 이름
SUFFIX = "Unreal"
EXT = ".fbx"
OPERATOR = bpy.ops.export_scene.fbx


def make_settings(path):
    return dict(
        filepath=path, check_existing=False,
        use_selection=False, use_visible=False, use_active_collection=False,
        object_types={'ARMATURE', 'MESH'}, use_custom_props=False,
        global_scale=1.0, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
        apply_unit_scale=True, use_space_transform=True, bake_space_transform=False,
        mesh_smooth_type='FACE', use_mesh_modifiers=True, use_triangles=True, use_tspace=False,
        primary_bone_axis='Y', secondary_bone_axis='X', armature_nodetype='NULL',
        use_armature_deform_only=False, add_leaf_bones=False,
        bake_anim=False, path_mode='COPY', embed_textures=False, batch_mode='OFF',
    )

import os

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
print("=" * 60)
