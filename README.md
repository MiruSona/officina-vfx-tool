# VFXTool

**AI 가 짧은 레시피 JSON 만 쓰면, 코드가 Unity Shuriken 파티클 이펙트(프리팹)를 조립하고 투명 배경 프레임 PNG 를 뽑아 검수하는 명령줄 툴이다.**
Python `vfxtool` 이 레시피를 검사 · 펼치고 프레임을 재며, C# UPM 패키지 `com.officina.vfx` 가 `-batchmode` 에서 조립 · 렌더한다.

**상태 : 1차 구현 끝 (2026-10-15).** pytest 572 통과(2 건너뜀) · Unity EditMode 47/47 · 실측 U1 ~ U3 통과(`Docs/Research/2026-10-15-VFX툴구현실측.md`).
남은 것은 사람 몫 U4(템플릿 접촉판 보기) · U5(게임 저장소에 붙여 보기)다.

## 한 줄 흐름

```
레시피(템플릿 + params) → check → render(Unity) → measure · sheet → AI 가 critic · patch → loop next … (최대 4바퀴) → loop best
묶음 JSON(속성 × 세기 × 시드) → variant expand → variant run(판마다 Unity) → overview.png 격자에서 고름 → 고른 판 recipe.json 을 loop 로 다듬기
```

variant run 은 뜻밖의 오류(VfxError 아닌 것)도 그 판만 `failed` 로 적고 계속 돈다. 다시 돌리려면 `expand --force`.

## 설치

**Python** — 받은 직후와 서브모듈을 갱신한 뒤마다 한 번 돌린다.

```powershell
powershell -NoProfile -File .\setup.ps1
```

Python 3.14(`py -3.14`)로 `.venv` 를 만들고 editable + test 로 깐 뒤 `python -m vfxtool --help` 로 연기 시험을 한다. 의존성은 `pillow` · `numpy` 뿐이다(`THIRD-PARTY.md`).

**Unity** — 게임 프로젝트 `Packages/manifest.json` 의 `dependencies` 에 두 줄을 사람이 넣는다(툴은 manifest 를 안 고치고 `vfxtool doctor` 가 있나만 본다).

```json
"com.officina.vfx": "file:<VFXTool 자리>/Unity/com.officina.vfx",
"com.unity.nuget.newtonsoft-json": "3.2.2"
```

EditMode 시험까지 돌리려면 최상위에 `"testables": ["com.officina.vfx"]` 도 넣는다. Unity 6000.3 · URP 17.3 2D 렌더러에서 실측했다.

## 시험

```powershell
.\.venv\Scripts\python.exe -m pytest .\Test -q
```

## 문서

| 자리 | 내용 |
| --- | --- |
| `Docs/Guide/명령안내.md` | **명령 열세 개** 인자 · 종료 코드 · 보고 꼴 · 고리 손 흐름 · `--input-root` 함정 |
| `Docs/Guide/게임저장소붙이기.md` | **게임 저장소에 붙이기(U5)** — 분리 전 · 뒤 manifest 줄 · 서브모듈 명령 · 첫 프리팹 build · 플레이 모드 체크리스트 · 막히는 자리 |
| `Docs/Guide/화풍조각대응표.md` | ArtTool 화풍 조각 키 ↔ VFX 프로필 칸 |
| `.claude/skills/vfxtool-usage/SKILL.md` | AI 가 고리를 돌릴 때 보는 스킬 — 레시피 요령 · critic · patch · 멈춤 |
| `Docs/Design/2026-10-14-VFX툴설계.md` | 설계(레시피 꼴 · 검수 규칙 · 고리). 13절이 구현 뒤 정정 |
| `Docs/Research/2026-10-14-VFX툴조사.md` | 남들이 한 것 · 도트풍 · 환경 조사 |
| `Docs/Research/2026-10-14-VFX툴실측.md` | 설계 전 실측(배치 렌더 · 알파 · 결정성 · 스냅 셰이더) |
| `Docs/Design/2026-10-15-변형묶음설계.md` | 7판 변형 묶음(속성 · 세기 · 시드). 끝 절이 구현 뒤 정정 |
| `Docs/Research/2026-10-15-VFX툴구현실측.md` | 1차 구현 실측(U1 ~ U3 · 잡은 버그 셋) · 판별 실측 절(7판 변형 묶음 포함) |
| `Unity/com.officina.vfx/README.md` | UPM 패키지 부르는 꼴 · 폴더 |
