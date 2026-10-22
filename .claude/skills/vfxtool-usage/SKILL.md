---
name: vfxtool-usage
description: Use when making a Unity particle effect (Shuriken VFX) for a game — before writing a VFX recipe JSON, while running the vfxtool loop, or when reading its sheet / measure report — 파티클 이펙트 레시피를 쓰기 직전 · vfxtool 고리를 돌릴 때 · 접촉판 · measure 보고를 읽고 critic · patch 를 쓸 때.
---

# 파티클 이펙트는 레시피 JSON 으로 만든다

AI 는 **짧은 레시피 JSON 과 patch 만** 쓴다. ParticleSystem 조립 · 렌더 · 측정은 코드가 한다.
한 바퀴 = 레시피 → `loop run`(check → Unity 렌더 → measure → sheet) → 접촉판을 보고 critic · patch → `loop next`. 최대 4바퀴.

| 더 볼 것 | 언제 |
| --- | --- |
| `<VFXTool>/Docs/Guide/명령안내.md` | 명령 인자 · 보고 칸 · 고리 손 흐름 · `--input-root` 함정 |
| `<VFXTool>/Docs/Design/2026-10-14-VFX툴설계.md` 2 ~ 4절 · 13절 | 레시피 칸 · 다형 값 · 프로필 · 템플릿 꼴 (13절이 구현 뒤 바뀐 것) |
| `<VFXTool>/Docs/Design/2026-10-15-소재묶음설계.md` 끝 절 | 소재 묶음(`lib:`) · 템플릿 층 · 구현 뒤 바뀐 것 |
| `<VFXTool>/Docs/Design/2026-10-15-변형묶음설계.md` 끝 절 | 변형 묶음(`variant`) · 사전 · 세기 `tiers` · 구현 뒤 바뀐 것 |
| `<VFXTool>/src/vfxtool/symptoms.json` | 증상 낱말 · 먼저 볼 칸 |

`<VFXTool>` 은 VFXTool 폴더다(서브모듈이면 보통 `Tools/VFXTool`). 명령은 `<VFXTool>\.venv\Scripts\python.exe -m vfxtool …`.

## 레시피 쓰는 요령

1. **템플릿부터 고른다.** `vfxtool template list` → `template show <이름>`. 다섯 : `hit_sparks`(맞음 파편) · `land_dust`(착지 먼지) · `sparkle`(플립북 반짝임) · `ambient_motes`(분위기 입자) · `heal_rise`(회복 입자). 맞는 게 있으면 층에 `template` + `preset` + `params` 만 쓴다. 손으로 층을 짜는 건 맞는 템플릿이 없을 때만.
2. **값 단위** : 크기 · 거리 · 속도는 **텍셀**(속도는 텍셀/초), 시간은 초, 각도는 **도**. Unity 단위 · 라디안 바꾸기는 check 가 한다.
3. **색은 `p<n>`**(프로필 팔레트 번호)로 쓴다. hex 는 팔레트 밖이면 warn, 반투명 알파 hex 는 `binary` 프로필에서 error.
4. **색은 startColor 에, 그러데이션은 알파만.** Unity 는 startColor × colorOverLifetime 색을 곱한다. 그러데이션 색 키는 `[[0, "#FFFFFF"]]` 로 두고 `alpha` 키로 사라짐만 그린다. 둘 다 색이면 `recipe.color_multiply` warn.
5. **방향** : Cone 을 위로 쏘려면 `shape.rotation: [-90, 0, 0]`(회전 없으면 화면 안쪽 +Z 로 쏴서 안 보인다). Edge 는 회전 없이 가로선 · 위로 나간다. Box 는 startSpeed 가 +Z 라 안 보이니 `velocityOverLifetime` 으로 움직인다.
6. 크기 곡선은 기본 계단(`step: true`) — 중간 크기는 도트를 깬다. `startSize` × 곡선 키가 프로필 `pixel_size` 안이어야 한다.
7. 플립북 `textureSheet.startFrame` 은 칸 번호(칸 = floor(값)). 모든 칸에서 고르려면 `{"random": [0, 칸 수]}`.
8. 레시피 `profile` · `texture` 가 레시피 폴더 밖이면 `--input-root <위 폴더>` 를 준다(안 주면 `recipe.paths` error).
9. Unity 를 띄우기 전에 `vfxtool check` 로 거른다(1초). fail 이면 렌더하지 않는다.
10. **입자 그림은 소재 묶음에서 고른다.** `vfxtool lib list` · `lib show <이름>` → 층에 `"texture": "lib:<이름>"`(dot · cross · star4 · disc · ring · shard · streak · puff8 · puff16 · burst16). tiles · fps 는 check 가 채운다. 변형 줄 소재는 `textureSheet.row`(정수 · `"random"`)로 한 줄만 쓴다.
11. 소재 · 시트 층은 **startSize 상수 하나**(소재 칸의 정수 배). 크기 곡선 · random 크기는 `recipe.lib_size` error 다 — 크기 변화는 플립북 장으로 낸다.
12. lib 소재는 흰 실루엣이라 명도 단이 없다. 플립북(burst16 등)이 평평한 원판으로 보이면 `lib cut --ramp p0,p1,… --profile … --out <레시피 폴더>` 로 팔레트 램프 PNG 를 만들고(가까운 휘도로 골라 순서 무관, 같으면 앞 것), 층은 그 PNG + **startColor `#FFFFFF`** 로 쓴다(명령안내 11절).
13. **같은 이펙트의 여러 판(불 · 얼음 · 독 · 번개 × 약 · 중 · 강 × 시드)은 변형 묶음으로 만든다.** `variant expand <묶음.json> --work …` → `variant run --work <묶음 폴더> --project …` → (run 이 부름) `variant sheet`. `variant run` 은 기본이 묶음(Unity 한 번에 다 굽기)이고 `--each` 면 판마다 따로 띄운다. AI 는 짧은 **묶음 JSON 하나만** 쓴다(`template` · `profile` · `attrs` · `tiers` · `seeds`, 판 수 48 이하). 모든 판에 깔 손 덧칠은 묶음 `params` 에 쓴다 — 판 폴더 레시피를 하나씩 고치지 않는다. **`overview.png` 를 Read 로 보고** 속성 색이 안 갈리면(둘 다 흰빛) 사전 `params` 로 색 파라미터를 p1 · p2 로 옮긴다(게임 쪽 `--variants` 사전). 고른 판의 `recipe.json` 만 `patch` · `loop` 로 다듬는다. 세기 범위 밖은 자르지 않고 `variant.tier_range` 실패 — 즉석 세기로 고친다(명령안내 13절).

## critic.json · patch.json

```json
{ "score": 0.6, "symptoms": ["too_dense"], "notes": "파편이 화면을 덮는다. 앞 판보다 끝이 깔끔해짐" }
```

- `score` 0 ~ 1 은 「이 게임 도트풍 이펙트로 쓸 만한가」. 2바퀴부터는 **앞 판 sheet 와 견줘** 매긴다. `symptoms` 는 증상표 낱말만.

```json
{ "layers": { "hit": { "params": { "count": 10 } } }, "duration": 0.45 }
```

- patch 는 부분 덮기다. 객체는 합치고 배열 · 값은 통째로 바꾸고 `null` 은 지운다.
- `layers` 는 **층 이름 열쇠 객체**(배열 금지). 템플릿 층은 펼친 이름(`hit.sparks`)이 아니라 부른 층의 `params` · `preset` · `override` 를 고친다.
- `profile` · `name` · `version` 은 못 바꾼다. 템플릿 `fixed` 칸(material · blend · space)도 못 바꾼다.
- **한 바퀴에 원인 하나**만 고친다. 여럿을 한꺼번에 바꾸면 무엇이 통했는지 모른다.

## 보고 읽는 법

| 칸 | 읽는 법 |
| --- | --- |
| `status` | `fail`(종료 1)이면 레시피 · 결과물 문제 — 고친다. `error`(종료 2)면 인자 · 파일 · Unity 문제 — 레시피를 고치지 말고 detail 을 읽는다 |
| `issues[].rule` | `recipe.*` 는 레시피 칸, `frame.*` 은 렌더 결과, `unity.*` · `entry.*` 는 환경 · 버그 |
| `issues[].hint` | 먼저 고칠 칸. 여기부터 본다 |
| `metrics.symptoms` | measure 가 자동으로 찾은 증상 낱말. critic 의 `symptoms` 에 그대로 옮겨도 된다 |
| `metrics.grid_ratio` | 프레임마다 경계가 격자에 맞는 비율. 회전 · 크기 곡선 층이 있으면 1 아래가 정상(info) |

**sheet.png 를 꼭 Read 로 본다.** 지표가 ok 여도 모양이 틀릴 수 있다(방향 · 퍼짐 · 리듬). GIF 는 Read 로 못 돌리니 사람용이다.

## 멈춤 규칙

- 고리가 스스로 멈춘다 : error 0 · warn 0 · score ≥ 0.9 / 4바퀴 다 씀 / rollback 두 번 연속. `metrics.stopped` 가 true 면 더 돌리지 않는다.
- 최고점 판보다 못한 판은 버려지고(rollback) 다음 patch 는 최고점 판에 댄다. 버린 patch 를 다시 내지 않는다.
- 4바퀴로 안 되면 **템플릿 고르기가 틀린 것**이다. 다른 템플릿으로 새 고리를 열거나 사람에게 묻는다.
- 끝나면 `loop best` 의 sheet 를 사람에게 보인다. 「보기 좋은가」 와 PixelLab 우회 여부는 사람이 정한다.
- Unity 를 두 개 동시에 띄우지 않는다. 같은 프로젝트에 에디터가 열려 있으면 render 는 종료 2 다 — 사람에게 닫아 달라고 한다.
