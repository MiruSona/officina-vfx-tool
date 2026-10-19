# com.officina.vfx

VFXTool 의 Unity 쪽 짝이다. Python `vfxtool check` 가 만든 `resolved.json` 을 Shuriken ParticleSystem 프리팹으로 조립하고, 판정용 프레임 PNG 를 뽑는다.
사람이 직접 부르는 패키지가 아니다. `vfxtool build` · `render` 가 `-batchmode -executeMethod Officina.Vfx.Editor.VfxEntry.Run` 으로 부른다.

## 부르는 꼴

```
Unity.exe -batchmode -projectPath <P> -logFile <work>/unity.log
          -executeMethod Officina.Vfx.Editor.VfxEntry.Run -vfxJob <work>/job.json
```

- `-nographics` 는 쓰지 않는다(GPU 렌더가 필요하다). `-quit` 도 필요 없다 — 진입점이 `EditorApplication.Exit` 로 끝낸다.
- `result.json` 은 job.json 옆에, 프레임 `f001.png …` 는 `job.outDir` 에 쓴다. 로그 줄 머리는 `[VFXTOOL]`.
- 종료 코드 : 0 ok · 1 issues(못 옮긴 칸 있음) · 2 error(인자 · 파일 · 저장 자리 거절 · 예외).
- 소재 묶음 `lib:` 는 Python 이 절대 PNG 경로 · tiles 로 풀어 넘긴다. 패키지가 새로 아는 건 `textureSheet.row`(정수 · `"random"` → SingleRow) 하나다.

## 설치

게임 프로젝트 `Packages/manifest.json` 에 두 줄을 사람이 넣는다.

```json
"com.officina.vfx": "file:<VFXTool 자리>/Unity/com.officina.vfx",
"com.unity.nuget.newtonsoft-json": "3.2.2"
```

EditMode 시험을 돌리려면 manifest 에 `"testables": ["com.officina.vfx"]` 도 넣는다.

## 폴더

| 자리 | 내용 |
| --- | --- |
| `Runtime/` | 레시피 모델(`VfxRecipe` · `VfxLayer` · 모듈 열 개) · 다형 값 `VfxValue` · 색 값 `VfxColor` · 시트 줄 `VfxRow` (Newtonsoft 로 읽음) · JSON 칸 이름 표 `VfxJsonKeys` |
| `Editor/` | 진입점 `VfxEntry` · 조립기 `VfxBuilder` · 모듈 넣기 `VfxModules` · `VfxLifetimeModules` · 에셋 `VfxAssets` · 이름표 `VfxMaterialTable` · 층 텍스처 · 머티리얼 만들기 `VfxMaterialFactory` · 렌더 `VfxRenderer` · 한 장 뽑기 `VfxCapture` · 프레임 셈 `VfxFrameTimes` · 출력 폴더 검사 `VfxOutDir` · job · result 모델 |
| `Shaders/` · `Materials/` · `Textures/` | 스냅 셰이더 · 이름표 머티리얼 셋 · 흰 텍스처 `px1` · `px2` |
| `Tests/Editor/` | EditMode 시험 — `VfxValueTests` · `VfxColorTests` · `VfxBuilderTests` · `VfxFrameTimesTests` · `VfxSafetyTests`(경로 · 이름 · 판 · 모르는 칸 거절) · `VfxPathJailTests`(조각 끝 공백 · 점, 정션 · 끊긴 정션 · 링크된 .mat 거절, 텍스처 원본 한 번 고르기) · `VfxTextureSheetRowTests`(row → SingleRow · 꼴 · 범위 오류 · startFrame 정규화) |

설계 원본 : `../../Docs/Design/2026-10-14-VFX툴설계.md` 5절.
