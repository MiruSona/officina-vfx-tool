# 스냅 파티클 셰이더

파티클 **중심만** 텍셀 격자에 반올림(`round(xy × _PPU) / _PPU`)하고 네 정점을 같은 양만큼 민다. 쿼드 모양은 그대로라 도트가 격자에 맞는다.
설계 : `VFXTool/Docs/Design/2026-10-14-VFX툴설계.md` 5-2 · 5-3 절. 근거 : `VFXTool/Docs/Research/2026-10-14-VFX툴실측.md` A 절.

## 파일

| 파일 | 뜻 |
| --- | --- |
| `SnapParticleUnlit.shader` | `Officina/Vfx/SnapParticleUnlit` — 빛 없음. 블렌드를 머티리얼 속성으로 고른다. LightMode 태그 없는 패스 하나(실측 판과 같은 꼴) |
| `SnapParticleLit.shader` | `Officina/Vfx/SnapParticleLit` — URP 2D 빛 합성(`CombinedShapeLightShared`). 패스 `Universal2D` · `NormalsRendering` · `UniversalForward`(대비). 알파 블렌드 고정 |
| `VfxSnap.hlsl` | 두 셰이더가 같이 쓰는 스냅 함수 `VfxSnapPositionWS` |

## 파티클 렌더러 Custom Vertex Streams

순서가 어긋나면 중심을 엉뚱한 값으로 읽는다. `VfxBuilder` 가 코드로 넣는다.

| 순서 | 스트림 | 셰이더 입력 |
| --- | --- | --- |
| 1 | Position | `POSITION` |
| 2 | Color | `COLOR` (파티클 색 · 수명 색) |
| 3 | UV | `TEXCOORD0.xy` |
| 4 | Center | `TEXCOORD0.zw` = 중심 xy · `TEXCOORD1.x` = 중심 z |

## 속성

| 속성 | 뜻 | Unlit | Lit |
| --- | --- | --- | --- |
| `_MainTex` | 입자 텍스처(Point · 압축 없음). 기본 `Textures/px1.png` | ○ | ○ |
| `_Color` | 곱할 색. 파티클 정점 색과 곱한다 | ○ | ○ |
| `_PPU` | 텍셀/유닛. 프로필 `ppu`(기본 32) | ○ | ○ |
| `_Snap` | 1 이면 스냅, 0 이면 안 함 | ○ | ○ |
| `_SrcBlend` · `_DstBlend` · `_SrcBlendAlpha` · `_DstBlendAlpha` | 색 · 알파 블렌드 계수(숫자는 아래 표) | ○ | — (고정) |
| `_MaskTex` · `_NormalMap` | 2D 빛 마스크 · 노멀 맵. 비우면 흰색 · 평평 | — | ○ |

## 머티리얼

| 이름표 | 파일 | 셰이더 | 블렌드 (색 , 알파) | 숫자 `Src Dst SrcA DstA` |
| --- | --- | --- | --- | --- |
| `unlit/alpha` | `Materials/VfxUnlitAlpha.mat` | Unlit | SrcAlpha OneMinusSrcAlpha , One OneMinusSrcAlpha | 5 10 1 10 |
| `unlit/additive` | `Materials/VfxUnlitAdditive.mat` | Unlit | One One , One One | 1 1 1 1 |
| `lit/alpha` | `Materials/VfxLitAlpha.mat` | Lit | SrcAlpha OneMinusSrcAlpha , One OneMinusSrcAlpha | 셰이더에 고정 |

셋 다 `_Snap 1` · `_PPU 32` · `_MainTex = px1`.

- 알파 채널을 `One OneMinusSrcAlpha` 로 두는 까닭 : 투명 배경 (0,0,0,0) 에 그릴 때 결과 알파가 입자 알파 그대로 남는다(`SrcAlpha` 면 a² 로 준다).
- additive 알파를 `One One` 으로 두는 까닭 : `Zero One` 이면 알파가 0 이 되어 투명 PNG 에서 안 보인다(실측 ③).

## 블렌드 숫자 (`UnityEngine.Rendering.BlendMode`)

| 숫자 | 뜻 | 숫자 | 뜻 |
| --- | --- | --- | --- |
| 0 | Zero | 6 | OneMinusSrcColor |
| 1 | One | 7 | DstAlpha |
| 2 | DstColor | 8 | OneMinusDstAlpha |
| 3 | SrcColor | 9 | SrcAlphaSaturate |
| 4 | OneMinusDstColor | 10 | OneMinusSrcAlpha |
| 5 | SrcAlpha | | |
