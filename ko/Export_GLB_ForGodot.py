# Export_GLB_ForGodot.py
# Blender 4.2 ~ 4.5
#
# 용도
#  리깅이 끝난 캐릭터(아마추어 + 메쉬)를 고도 4 용 GLB(glTF 2.0) 로 한 번에 내보냅니다.
#  고도는 FBX 보다 glTF 를 공식 추천 형식으로 씁니다. (FBX 는 4.3 부터 되지만 변환 단계가 하나 더 들어감)
#
# 하는 일
#  1) .blend 파일이 있는 폴더에 Export 폴더를 만들고 "파일이름_Godot.glb" 로 저장합니다. (같은 이름이면 덮어씀)
#     텍스처는 GLB 파일 안에 함께 들어갑니다.
#  2) 씬에 있는 아마추어와 메쉬를 전부 내보냅니다. 카메라, 라이트는 넣지 않습니다.
#  3) 내보내는 동안만 아마추어의 액션과 포즈를 떼어서 원래 포즈로 내보내고, 끝나면 실행 전 상태로 되돌립니다.
#     애니메이션은 넣지 않습니다.
#  4) 내보내기 옵션
#       Format = glTF Binary (.glb), +Y Up 켬, UV / Normals / Tangents 켬
#       Skinning 켬, 본 영향 4개 (고도 호환), Deformation Bones Only 끔, Use Rest Position Armature 켬
#       Shape Keys 켬, Materials = Export, Images = Automatic, Draco 압축 끔 (고도가 못 읽음)
#       Animations 끔
#  5) 머티리얼의 Roughness 와 Metallic 은 glTF 규격에 맞게 한 장으로 자동으로 합쳐지고,
#     Alpha 에 연결한 Opacity 도 그대로 들어갑니다. 고도는 이 머티리얼을 바로 씁니다.
#
# 주의
#  - .blend 파일을 먼저 저장해 두어야 합니다.
#  - 씬에 숨겨 둔 메쉬(하이폴리 등)도 같이 나갑니다. 넣기 싫은 메쉬는 다른 씬으로 옮기거나 지우고 실행하세요.
#  - 고도에서 가져온 뒤 Advanced Import Settings 에서 Skeleton3D 를 고르고 BoneMap 에
#    SkeletonProfileHumanoid 를 넣어야 다른 캐릭터의 애니메이션을 리타깃할 수 있습니다.
#    AccuRIG 의 CC_Base 이름은 자동 매핑이 일부만 맞으니 빈 칸은 직접 지정하세요.
#    A포즈 계열 리그는 Fix Silhouette 을 켜면 리타깃 결과가 좋아집니다.
#
# 사용법
#  1) Scripting 탭 > 새 텍스트 > 붙여넣기 > Run Script
#  2) 진행 상황은 Window > Toggle System Console 에서 볼 수 있습니다.

import bpy

# 설정
OUT_FOLDER = "Export"   # .blend 옆에 만들 폴더 이름
SUFFIX = "Godot"
EXT = ".glb"
OPERATOR = bpy.ops.export_scene.gltf


def make_settings(path):
    return dict(
        filepath=path, check_existing=False, export_format='GLB',
        use_selection=False, use_visible=False, use_renderable=False, use_active_collection=False,
        export_cameras=False, export_lights=False, export_extras=False,
        export_yup=True, export_apply=False,
        export_texcoords=True, export_normals=True, export_tangents=True,
        export_materials='EXPORT', export_image_format='AUTO',
        export_skins=True, export_all_influences=False, export_influence_nb=4,
        export_def_bones=False, export_leaf_bone=False, export_rest_position_armature=True,
        export_morph=True, export_animations=False,
        export_draco_mesh_compression_enable=False,
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
