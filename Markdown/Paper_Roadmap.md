# 논문 로드맵 — 문헌조사 결과 · 방향성 · 수행 과제

> **작성일** 2026-07-21
> **작성** Claude Opus 4.8 (Claude Code) — 사용자와의 대화 및 검토를 거쳐 생성
> **근거** 2026-07-21 웹 문헌조사(아래 §1 출처 링크), 이 세션의 실측 데이터,
> `paper/main.tex` 초안
> **⚠️ 신규성 판정 한계** §1의 선행연구 조사는 **웹 검색 수준**입니다.
> 논문 신규성 확정 근거로는 불충분하므로, IEEE Xplore·Google Scholar
> 정밀 재조사(과제 T15)를 반드시 수행하십시오.
> **주의** AI가 생성한 문서입니다. 인용 서지 정보는 원문으로 검증하십시오.

---

## 1. 문헌조사 결과 (선행연구 판정)

당초 차별화 포인트로 생각했던 항목들을 검색한 결과, **대부분 이미 출판되어 있음**을 확인했다.

| # | 당초 주장 | 선행연구 | 출처 | 판정 |
|---|---|---|---|---|
| 1 | DPS로 cal 검증 | MMCM 동적위상시프트로 178.57 / 357.14 / 535.71 ps 기준 생성해 carry chain TDC 특성화 | [Sensors 26(3), 2026](https://doi.org/10.3390/s26031052) | ❌ 기존 |
| 2 | Ring Osc로 cal | 무상관 RO 기반 code density test — 표준 기법 | [Calibration Methods for TDC (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10007395/), [Appl. Sci. 12(7):3649, 2022](https://doi.org/10.3390/app12073649) | ❌ 기존 |
| 3 | DPS↔RO 교차검증 | 무상관 크리스털 2개로 code density 교차 수행 사례 존재 | 위 동일 | ⚠️ 약함 |
| 4 | Dual phase coarse | 상승/하강 에지 이중 카운터 + fine code로 선택 — ASIC에서 확립 | [arXiv:1708.03692 (ATLAS MDT TDC)](https://arxiv.org/abs/1708.03692) | ❌ 기존 |
| 5 | RO 기반 실시간 온도보정 | **"RO 주파수 불안정성을 측정해 delay line의 V/T 영향을 dead-time 없이 온라인 보정"** | [arXiv:1303.6840 (Bourdeauducq, 2013)](https://arxiv.org/abs/1303.6840) | ❌ 기존 |

### 추가 확인 사항

**average-bin-width 보정** ([Calibration Methods, 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC10007395/)):
> 동기식 TDC에서는 bin-by-bin 보정이 DNL을 개선하지 못하지만, **average-bin-width 보정은 DNL과 INL을 모두 크게 개선**한다.

단, 이 논문은 **온도 실시간 대응을 다루지 않으며**(post-processing), **형상 불변성을 실험 검증하지도 않았다.**

---

## 2. 남은 공백 (Novelty 후보)

선행연구를 종합하면 다음 지점이 비어 있다.

### 2.1 형상 불변성(shape invariance)의 실험적 미검증 ★핵심

- Bourdeauducq는 **RO로 스칼라 배율 보정**을 수행하지만, **"왜 배율 하나로 충분한가"** 를 입증하지 않았다.
- Calibration Methods는 average-bin-width가 효과적임을 보이지만 **온도 축에서 검증하지 않았다.**

> **가설:** CARRY4의 비선형 *형상*(period-4 패턴, 상대 bin 폭 비율)은 실리콘 레이아웃이 결정하므로 온도 불변이고, 변하는 것은 **전체 배율**뿐이다.

이를 여러 온도에서 code density로 정량 입증하면, **기존 스칼라 보정 기법에 이론적 정당성을 제공**하게 된다.

### 2.2 MMCM을 온도 안정 기준자로 사용한 RO 2차 보정

Bourdeauducq는 RO만 사용했고 **절대 기준자가 없었다.** 본 설계는 MMCM(크리스털 기준, 온도 안정)과 RO(fabric, 온도 민감)를 **둘 다** 갖는다.

```
K(T) = f_RO,ref / f_RO(T)      ← RO를 MMCM 클럭으로 카운팅
```
→ 외부 센서·XADC 없이 fabric 지연 드리프트를 절대 기준 대비로 측정.

### 2.3 측정 기반 구조 규명 (본 연구의 실측 자산)

- **intra-CARRY4 period-4 패턴 3.72×** 정량화
- **entry transient** (CYINIT general routing 주입) — 첫 3개 블록 1.89 / 1.51 / 1.16× 후 회복
- **clock region 경계는 무의미**하다는 반직관적 반증

---

## 3. 논문 방향성

### 3.1 포지셔닝 원칙

**기법 1~5는 신규성을 주장하지 않고 출처를 명시한다.** 대신 다음을 기여로 삼는다.

| 기여 | 내용 |
|---|---|
| C1 | Zynq-7000 캐리체인의 **정량적 구조 규명** (period-4 / entry transient 분리, clock region 무영향) |
| C2 | **자극 독립 교정 방법론** — cal/val 분리로 generalization error 보고 |
| C3 | **형상 불변 가설** 정식화 + 검증 실험 설계 |
| C4 | FMCW 레이더용 FPGA 구현 |

### 3.2 리뷰어 방어 논리

- "이거 이미 있는데?" → Related Work에서 **선제적으로 전부 인용**. 기여는 characterization + methodology임을 명확히.
- "DNL 0.11이 너무 좋은데?" → **cal/val 독립 분리**를 수식으로 제시. self-consistency가 아님을 명시.
- "왜 스칼라 하나로 충분한가?" → **형상 불변 가설의 실험적 검증**이 바로 그 답.

### 3.3 제목 변경

기존: *...Dual-Phase Timestamping and Multi-Level Calibration*
변경: *...Dual-Phase Coarse Timestamping and **Stimulus-Independent Code-Density Calibration***
→ 이미 나온 기법이 아니라 **방법론**을 앞세움.

---

## 4. 수행 과제 (TODO)

`paper/main.tex` 의 `\needdata{}` / `\needfig{}` 마커와 1:1 대응.

### 🔴 P0 — 즉시 가능 (기존 데이터로 지금 실행)

| # | 과제 | 방법 | 논문 위치 |
|---|---|---|---|
| T1 | **DPS ↔ RO 교차검증** | `DNL_INL_codedensity.py` 에 `CAL=DPS 히스토그램`, `VAL=RO 히스토그램` (그리고 반대) | Fig.\ref{fig:cross}, Sec. V |
| T2 | 그림 export: DNL/INL before-after | `DNL_INL_codedensity.py` 출력 PNG → PDF | Fig.\ref{fig:dnl}, \ref{fig:inl} |
| T3 | 그림 export: period-4 scatter | `Histogram.py` 의 CARRY4 position analysis | Fig.\ref{fig:period4} |
| T4 | 그림 export: 전체 블록도 | `diagram/tdc_system_block.drawio` → PDF | Fig.\ref{fig:overall} |
| T5 | 자원 사용량 | Vivado utilization report (LUT/FF/BRAM/DSP) | Sec. VII-A |

> T1이 가장 가치가 높다. **자극 독립성**은 C2의 핵심 근거이며, 추가 측정 없이 확보 가능.

### 🟠 P1 — 추가 측정 필요 (하드웨어 재빌드 불필요)

| # | 과제 | 방법 | 논문 위치 |
|---|---|---|---|
| T6 | **온도별 code density** ★ | 25 / 45 / 65 / 85 °C 에서 Mode 1 히스토그램 수집. 각 온도마다 cal/val 2회 권장 | Sec. VI-C, Fig.\ref{fig:shape} |
| T7 | 형상 잔차 분석 | 각 온도 히스토그램을 자기 평균으로 정규화 → 겹침 정도 ε(T) [LSB], 평균 bin 폭 드리프트 [ppm/°C] | Sec. VI-C |
| T8 | Single-shot precision | 고정 시간간격 N회 반복 측정 → 표준편차. cal 전/후 | Sec. VII-D |

> T6/T7이 **논문의 핵심 novelty**. 가열은 헤어드라이어/온도챔버 + XADC로 접합온도 모니터.

### 🟡 P2 — 하드웨어 작업 필요

| # | 과제 | 방법 | 논문 위치 |
|---|---|---|---|
| T9 | dual-phase vs single-phase 비교 | 180° 카운터 무효화 빌드 vs 정상 빌드. 고정 간격 반복 측정 → $T_{clk}$ 크기 이상치 발생률 | Sec. VII-C, Fig.\ref{fig:metares} |
| T10 | 온라인 보정 HW 구현 | RO 주파수 카운터 + 스케일 곱셈기. MMCM 클럭 기준 카운팅 | Sec. VI-D |
| T11 | 온도 안정성 3-way 비교 | (a) 무보정 (b) 정적보정 (c) 온라인 스케일보정 | Sec. VII-E, Fig.\ref{fig:temp} |
| T12 | Mode 0 timestamp 검증 (선택) | `validate_timestamp.py` — DPS의 loop_cnt 기준 INL. **ILA storage qualification 필수** | 보강 자료 |

### 🔵 P3 — 문헌/서지

| # | 과제 |
|---|---|
| T13 | `calibreview`, `sensors2026` 저자/권/호/페이지 확인 |
| T14 | 선행연구 비교표 작성 (device / LSB / DNL / INL / RMS / 온도보정 방식) |
| T15 | **IEEE Xplore·Google Scholar 정밀 재조사** — 특히 "shape invariance", "scale-only calibration" 키워드 |

> T15는 필수. 본 조사는 웹 검색 수준이므로 신규성 확정 근거로 부족하다.

---

## 5. 보유 자산 (현재 확보분)

### 측정 데이터
| 파일 | 모드 | 용도 | 히트 수 |
|---|---|---|---|
| `tap_histogram_20260719_160115.csv` | Mode 0 (DPS) | cal | 5.6e7 |
| `tap_histogram_20260719_155155.csv` | Mode 0 (DPS) | val | 5.6e7 |
| `tap_histogram_20260720_191308.csv` | Mode 1 (RO) | cal | 1.21e8 |
| `tap_histogram_20260720_195432.csv` | Mode 1 (RO) | val | 1.50e8 |

### 확정 실측값 (논문에 이미 반영)
```
유효 코드      : 1 ~ 294 (294 codes)
평균 bin 폭    : 17.0 ps
period-4       : O[0] 10.33 / O[1] 31.33 / O[2] 17.97 / O[3] 8.43 ps  → 3.72×
entry transient: CARRY4 #0/#1/#2 = 1.89 / 1.51 / 1.16 ×
DPS  DNL/INL   : 4.19 → 0.50 / 8.94 → 0.64 LSB
RO   DNL/INL   : 4.03 → 0.11 / 8.55 → 0.17 LSB
LED 부하 대조  : net 4227→2143 ps 인데 DNL 4.23→4.20 (배선지연 무관 입증)
```

### 스크립트
| 파일 | 역할 |
|---|---|
| `Histogram.py` | ILA CSV → tap_histogram, CARRY4 position 분석 |
| `Making_COE_Mode_0.py` | code density → 교정 LUT/COE (SOURCE_TAG로 DPS/RO 분리) |
| `Making_COE_linear.py` | 선형(미교정) COE — Method A의 BEFORE 빌드용 |
| `DNL_INL_codedensity.py` | cal/val 분리 DNL·INL (자극 무관) |
| `validate_timestamp.py` | timestamp vs loop_cnt 선형성 (Mode 0 전용) |

### 문서
- `Markdown/Mode1_RingOsc_Calibration.md` — Mode 1 절차·수식·실측
- `Markdown/Mode0_DPS_Calibration.md` — Mode 0 2단계 검증 계획·ILA 설정
- `diagram/tdc_system_block.drawio` — 전체 블록도
- `paper/main.tex` — IEEE 초안

---

## 6. 주의사항

| 항목 | 내용 |
|---|---|
| **LaTeX 인코딩** | `paper/main.tex` 는 **순수 ASCII 유지**. 한글 삽입 시 pdfLaTeX Unicode 에러 |
| **히스토그램은 COE 무관** | raw tap을 쓰므로 COE 교체해도 히스토그램 불변. 교정 효과는 SW 적용 또는 timestamp로만 확인 |
| **RMW 3-state 필수** | 예전 2-state 히스토그램은 데이터 해저드로 모든 bin이 평균화되어 **가짜 flat** 발생 |
| **Mode 1엔 참 시간 기준 없음** | 링오실 비동기 → code density만 가능. 절대시간 INL은 Mode 0에서만 |
| **DNL 0.11의 성격** | same-stimulus repeatability (가장 유리한 조건). 교차검증(T1)이 더 엄격한 근거 |

---

## 7. 권장 진행 순서

```
1. T1 (DPS↔RO 교차검증)          ← 지금 즉시, 추가 측정 불필요
2. T2~T5 (그림·자원 export)       ← 초안 시각자료 완성
3. T6~T7 (온도 실험)              ← ★ 논문 핵심 novelty
4. T15 (문헌 정밀 재조사)          ← novelty 확정 전 필수
5. T8~T11 (정밀도·HW 구현·온도 3-way)
6. T13~T14 (서지·비교표)
```

**1~2단계만 끝나도 "특성화 + 교정 방법론" 논문으로는 초안이 성립**한다.
3단계(온도)가 들어가야 5번 항목의 기여가 완성된다.
