# Blender-Scripts

Small Blender scripts for game-character work: baking, export presets for game engines, mesh cleanup, rig cleanup, and fixes for AI auto-rigging results (SkinTokens).
Each script has a usage guide in the comment block at the top of the file.

- `en/` : English comments and console messages
- `ko/` : Korean comments and console messages (한국어 주석)

The code is identical in both folders; only the comments and messages differ.

## Scripts

### Baking
| Script | What it does |
|---|---|
| `Bake_PBR_HighToLow.py` | Bakes Base Color, Roughness, Metallic, Normal, AO and Opacity from high-poly to low-poly in one run, saves PNGs and connects them to the low-poly material |
| `Bake_Switch_Channel.py` | Rewires the high-poly material to the map you want to bake next |
| `FaceSets_to_VertexColor.py` | Converts Face Sets to a vertex color attribute (for ID map baking) |

### Export
| Script | What it does |
|---|---|
| `Export_FBX_ForUnity.py` | FBX export preset for Unity |
| `Export_FBX_ForUnreal.py` | FBX export preset for Unreal Engine |
| `Export_GLB_ForGodot.py` | GLB export preset for Godot |
| `Export_Each_OBJ.py` | Exports every mesh object to its own OBJ file |

### Mesh cleanup
| Script | What it does |
|---|---|
| `Bisect_Half.py` | Cuts meshes exactly on the X=0 (or Y, Z) plane and deletes one half |
| `Center_Merge.py` | Merges crowded vertices on the center line of a symmetric mesh |
| `Tri_Cleanup.py` | Cleans up the face layout of a decimated triangle mesh |
| `Quad_Cleanup.py` | Cleans up auto-retopology results (Instant Meshes etc.): stray vertices, pointless edges, T-junctions |
| `FaceSets_to_Crease.py` | Adds edge crease on Face Set borders so they stay sharp under Subdivision Surface |
| `Rename_MaterialsAndTextures.py` | Renames mesh data, materials and textures after the object name |

### Rigging and animation
| Script | What it does |
|---|---|
| `Rig_To_Mixamo.py` | Renames and re-parents any rig to the Mixamo bone layout |
| `SkinTokens_Fix_Bones.py` | Cleans up SkinTokens auto-rig bones and matches them to the Mixamo rig layout (run first) |
| `SkinTokens_Fix_Weights.py` | Cleans up SkinTokens skin weights for humans and animals (run after Fix_Bones) |
| `Symmetry_Bones.py` | Mirrors left-side bone positions and roll to the right side (X axis) |
| `Symmetry_SkinWeight.py` | Mirrors left-side skin weights to the right side (X axis) |
| `Clean_Keyframes.py` | Removes redundant keyframes from baked animation (Mixamo, mocap, AI motion) |

## How to use

Blender > Scripting tab > New (or Open) > paste or choose the script > Run Script. Read the comment block at the top of each script first.
Tested with Blender 4.2 - 4.5 unless the script header says otherwise.

## License

MIT (see `LICENSE`).

---

게임 캐릭터 작업용 블렌더 스크립트 모음입니다. 한국어 주석 버전은 `ko/` 폴더, 영어 주석 버전은 `en/` 폴더에 있습니다. 두 폴더의 코드는 같고 주석과 콘솔 메시지만 다릅니다. 각 스크립트 맨 위 주석에 사용법이 있습니다.
