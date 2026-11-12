# Blender-Scripts

Small Blender scripts for game-character work: baking, export presets for game engines, rig cleanup, and fixes for AI auto-rigging results (SkinTokens).
Each script has a usage guide at the top of the file (in Korean).

| Script | What it does |
|---|---|
| `Bake_PBR_HighToLow.py` | Bakes Base Color, Roughness, Metallic, Normal, AO and Opacity from high-poly to low-poly in one run, saves PNGs and connects them to the low-poly material |
| `Bake_Switch_Channel.py` | Rewires the high-poly material to the map you want to bake next |
| `Clean_Keyframes.py` | Removes redundant keyframes from baked animation (Mixamo, mocap, AI motion) |
| `Export_FBX_ForUnity.py` | FBX export preset for Unity |
| `Export_FBX_ForUnreal.py` | FBX export preset for Unreal Engine |
| `Export_GLB_ForGodot.py` | GLB export preset for Godot |
| `Rig_To_Mixamo.py` | Renames and re-parents any rig to the Mixamo bone layout |
| `SkinTokens_Fix_Bones.py` | Cleans up SkinTokens auto-rig bones and matches them to the Mixamo rig layout (run first) |
| `SkinTokens_Fix_Weights.py` | Cleans up SkinTokens skin weights for humans and animals (run after Fix_Bones) |
| `Symmetry_Bones.py` | Mirrors left-side bone positions and roll to the right side (X axis) |
| `Symmetry_SkinWeight.py` | Mirrors left-side skin weights to the right side (X axis) |

## How to use

Blender > Scripting tab > Open > choose the script > Run Script. Read the comment block at the top of each script first.
Tested with Blender 4.2 - 4.5 unless the script header says otherwise.

## License

MIT (see `LICENSE`).

---

게임 캐릭터 작업용 블렌더 스크립트 모음입니다. 각 스크립트 맨 위 주석에 용도, 하는 일, 주의, 사용법이 있습니다.
