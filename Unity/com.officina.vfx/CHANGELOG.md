# Changelog

## [Unreleased] - 2026-10-15 (VFXTool 3판 소재 묶음)

- `textureSheet.row` 를 읽는다. 정수 → SingleRow · Custom · rowIndex, `"random"` → SingleRow · Random. 안 적으면 전처럼 Grid · WholeSheet.
- 새 `Runtime/VfxRow.cs` · `VfxRowConverter.cs`. 꼴이 틀리면(음수 · 글자 · long 넘는 정수) `build.bad_value`, 줄 수 밖이면 `build.texture_sheet_row` — 둘 다 시트 전체로 둔다.
- SingleRow 면 `FramesInAnimation` = numTilesX (startFrame 정규화도 이 값으로).
- 프레임 시각을 `t = start + (i − 0.5)/fps` 로 바꿈(`VfxFrameTimes`). 장 k 가 플립북 k번 칸 가운데를 찍는다. 전 `i/fps` 는 칸 경계에서 칸이 빠졌다.
- EditMode 56 → 75.

## [0.1.0] - 2026-10-15

- 첫 판. resolved.json 모델 · 다형 값 / 색 값 변환 · 모듈 열 개 조립 · 텍스처 / 머티리얼 / 프리팹 저장 · EditMode 시험.
