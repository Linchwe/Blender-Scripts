# Blender-Scripts (한국어)

게임 캐릭터 작업용 블렌더 스크립트 모음입니다. 베이크, 게임 엔진별 내보내기, 메쉬 정리, 리그 정리, AI 오토리깅(SkinTokens) 결과 보정 스크립트가 들어 있습니다.
각 스크립트 맨 위 주석에 용도, 하는 일, 주의, 사용법이 있습니다.

이 폴더는 주석과 콘솔 메시지가 한국어인 버전입니다. 영어 버전은 `en` 폴더에 있고, 두 폴더의 코드는 같습니다.

## 스크립트 목록

### 베이크
| 스크립트 | 하는 일 |
|---|---|
| `Bake_PBR_HighToLow.py` | 하이폴리의 Base Color, Roughness, Metallic, Normal, AO, Opacity 를 로우폴리로 한 번에 굽고, PNG 로 저장한 뒤 로우폴리 머티리얼에 연결 |
| `Bake_Switch_Channel.py` | 다음에 구울 맵에 맞게 하이폴리 머티리얼 연결을 바꿈 |
| `FaceSets_to_VertexColor.py` | 페이스셋을 버텍스 컬러로 바꿈 (ID 맵 베이크용) |

### 내보내기
| 스크립트 | 하는 일 |
|---|---|
| `Export_FBX_ForUnity.py` | 유니티용 FBX 내보내기 |
| `Export_FBX_ForUnreal.py` | 언리얼 엔진용 FBX 내보내기 |
| `Export_GLB_ForGodot.py` | 고도용 GLB 내보내기 |
| `Export_Each_OBJ.py` | 메쉬 오브젝트마다 따로 OBJ 파일로 내보내기 |

### 메쉬 정리
| 스크립트 | 하는 일 |
|---|---|
| `Bisect_Half.py` | 메쉬를 X=0 (또는 Y, Z) 평면에서 정확히 잘라 한쪽 반을 지움 |
| `Center_Merge.py` | 좌우 대칭 메쉬의 중앙선 위에 몰린 버텍스를 합침 |
| `Tri_Cleanup.py` | 디시메이트한 삼각형 메쉬의 면 형태 정리 |
| `Quad_Cleanup.py` | 자동 리토폴로지(Instant Meshes 등) 결과 정리: 의미 없는 버텍스, 엣지, T자 교차 |
| `FaceSets_to_Crease.py` | 페이스셋 경계에 크리즈를 넣어 Subdivision Surface 를 걸어도 각이 살아 있게 함 |
| `Rename_MaterialsAndTextures.py` | 메쉬 데이터, 머티리얼, 텍스처 이름을 오브젝트 이름에 맞춤 |

### 리깅, 애니메이션
| 스크립트 | 하는 일 |
|---|---|
| `Rig_To_Mixamo.py` | 어떤 리그든 본 이름과 부모-자식 관계를 믹사모 리그 규격으로 바꿈 |
| `SkinTokens_Fix_Bones.py` | SkinTokens 오토리깅 결과의 본을 정리하고 믹사모 리그 규격으로 맞춤 (먼저 실행) |
| `SkinTokens_Fix_Weights.py` | SkinTokens 오토리깅 결과의 웨이트 정리, 사람과 동물 모두 (Fix_Bones 다음에 실행) |
| `Symmetry_Bones.py` | 왼쪽 본의 위치와 롤을 오른쪽에 X축 대칭으로 복사 |
| `Symmetry_SkinWeight.py` | 왼쪽 스킨 웨이트를 오른쪽에 X축 대칭으로 복사 |
| `Clean_Keyframes.py` | 구워진 애니메이션(믹사모, 모션캡처, AI 모션)에서 의미 없는 키프레임 지우기 |

## 사용법

블렌더 > Scripting 탭 > New(또는 Open) > 스크립트를 붙여넣거나 고르기 > Run Script.
실행 전에 스크립트 맨 위 주석을 먼저 읽어 주세요.
스크립트 머리말에 따로 적혀 있지 않으면 블렌더 4.2 ~ 4.5 에서 테스트했습니다.

## 라이선스

MIT (저장소 맨 위의 `LICENSE` 참고)
