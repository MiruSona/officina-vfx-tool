# 남의 것 쓰는 목록 (THIRD-PARTY)

VFXTool 이 같이 쓰는 남의 소프트웨어. 툴 저장소 안에 복사본을 두지 않고 설치 때 받는다.

| 항목 | 어디서 쓰나 | 라이선스 | 받는 곳 |
| --- | --- | --- | --- |
| **Pillow** | Python — PNG 읽기 · 접촉판 · GIF | MIT-CMU (HPND) | pip (`pyproject.toml`) |
| **NumPy** | Python — 프레임 측정 | BSD-3-Clause | pip (`pyproject.toml`) |
| **Newtonsoft.Json** (`com.unity.nuget.newtonsoft-json` 3.2.2) | Unity — resolved.json 읽기 | MIT | Unity 패키지 관리자 (manifest 의존성) |

## 그림 소재

`src/vfxtool/lib/` 의 플립북 3장은 아래 CC0 원본을 잘라 만들었다. 원본은 저장소에 안 넣고 `lib/sources.json` 에 출처 · 자르기 창 · sha256 을 적는다.
CC0 는 표기 의무가 없지만 출처 관리용으로 적는다. **CC-BY · CC-BY-SA 소재는 넣지 않는다.** 기하 소재 7장(dot · cross · star4 · disc · ring · shard · streak)은 `lib_draw.py` 가 그린 것이라 VFXTool 라이선스(MIT)를 따른다.

| 소재 | 원본 | 저자 | 라이선스 | 받는 곳 | 우리가 바꾼 것 |
| --- | --- | --- | --- | --- | --- |
| `puff8` | Fire & Smoke Animations — `SmokeThickPuff.png` | Reactorcore | CC0 1.0 | https://opengameart.org/content/fire-smoke-animations | 흰 실루엣(알파 0/1) |
| `puff16` | Particles Pack 2 — puff | Polar_34 | CC0 1.0 | https://polar-34.itch.io/particles-pack-2 | 32칸 → 16칸 창 (8, 7) 자르기 · 흰 실루엣 |
| `burst16` | 16x16 Explosion — `explosion_sheet.png` | BitingChaos (Nicholas Caito) | CC0 1.0 | https://opengameart.org/node/156434 | 흰 실루엣(3~4단 명도 → 1단) |
