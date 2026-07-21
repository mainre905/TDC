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

#### 용어 정리 — 비율(형상) vs 배율(스케일)

```
bin 폭 배열: [10, 31, 18, 8, 10, 31, 18, 8, ...] ps
              └ 서로 간의 관계 = 비율(형상, shape)
              └ 절대 크기      = 배율(스케일, scale)
```

가설이 **성립**하는 경우 (온도 상승 시 전부 같은 비율로 커짐):
```
25 C:  [10, 31, 18,  8]   평균 17.0 ps
85 C:  [11, 34, 20,  9]   평균 18.7 ps   <- 전부 x1.1
       비율 10:31:18:8 유지  ->  K=1.1 곱하기로 충분  OK
```

가설이 **깨지는** 경우 (제각각 다른 비율로 변함):
```
25 C:  [10, 31, 18,  8]
85 C:  [11, 32, 21, 10]   <- x1.10 / x1.03 / x1.17 / x1.25
       비율이 변함  ->  배율 하나로는 불가, 전체 재교정 필요  NG
```

**검증 방법:** 각 온도 히스토그램을 자기 평균으로 나누면 배율이 제거되고 형상만
남는다. 온도별 형상이 겹치면 가설 성립.

#### RO가 배율을 알려주는 원리

RO와 CARRY4는 **같은 FPGA fabric 소자**로 만들어져 온도에 함께 느려진다.
```
온도 상승 -> RO 인버터 지연 증가 -> RO 주파수 감소
          -> CARRY4 tap 지연 증가 -> bin 폭 증가
             (같은 원인, 같은 방향)
```
따라서 $K = f_{RO,ref} / f_{RO}(T)$ 로 배율을 추정한다.
열센서(XADC)는 "온도"를 재지만, RO는 "지연 그 자체"를 재므로 더 직접적이다.

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

### 3.4 IEEE 투고 준비도 — 냉정한 평가

목표가 IEEE 저널(TIM, TNS 등)이라면 **현재 상태로는 부족하다.**

| 보유 기여 | 예상 리뷰어 반응 |
|---|---|
| 구조 규명 (period-4, entry transient) | "흥미롭지만 **특정 디바이스 1개**의 특성화 보고. 새 기법 아님" |
| cal/val 분리 방법론 | "**당연히 해야 하는 것**. 기여로 보기 어려움" |
| 형상 불변 가설 | "가설은 좋으나 **아직 데이터가 없음**" |
| dual-phase, DPS/RO 교정 | "전부 선행연구" |

**결정적 약점 3가지**

1. **단일 디바이스·단일 칩** — Zynq-7000 하나. IEEE는 통상 다중 디바이스/칩 재현성을 요구.
2. **성능 수치 경쟁력 없음** — LSB 17 ps는 2013년 수준. 최신 논문은 wave-union·multi-chain으로 1.7~5 ps. **성능으로는 못 이긴다.**
3. **핵심 novelty 미측정** — 형상 불변성은 현재 **가설일 뿐**.

> 결론: "성능 경쟁"이 아니라 **"기존 기법의 이론적 근거를 최초로 실험 검증"** 으로 승부해야 한다.

### 3.5 IEEE급이 되기 위한 요건

**필수**

| # | 요건 | 상세 |
|---|---|---|
| R1 | **형상 불변성 정량 입증** | 넓은 온도 범위(25~85 C, 가능하면 0~85), 형상 잔차 ε(T) [LSB], 배율 드리프트 [ppm/C], **반증 조건 사전 정의**("형상이 X% 이상 변하면 기각"). **전압(V) 변동도 포함해야 PVT 완결** |
| R2 | **스칼라 보정 실효성 입증** | 아래 4-way 비교. **(c)가 (d)에 근접**함이 논문의 핵심 수치 |
| R3 | **다중 칩/보드 재현성** | 최소 2~3개 보드. 형상 패턴은 칩마다 달라도 **"불변성"이라는 성질은 공통**임을 보여야 일반화 성립 |

R2의 4-way 비교:
```
(a) 무보정              -> 오차 X ps
(b) 25C LUT 고정 사용   -> 오차 Y ps
(c) K(T) 스칼라 보정    -> 오차 Z ps   <- 제안 기법
(d) 각 온도 완전 재교정 -> 오차 W ps   <- 이상적 상한
        (c) ~= (d) 이면 "320개 대신 1개로 충분" 입증
```

**강력 권장**

| # | 요건 | 상세 |
|---|---|---|
| R4 | **물리적 설명** | 왜 형상이 불변인가 — CARRY4 내부 MUX 지연이 온도에 **비례적**으로 변하기 때문. Xilinx 속도등급 derating factor로 뒷받침 |
| R5 | **single-shot precision** | DNL/INL만으론 부족. RMS 해상도가 있어야 타 논문과 비교표 작성 가능 |

### 3.6 두 갈래 전략

| | 경로 A — IEEE 저널 직행 | 경로 B — 학회 선행 후 확장 |
|---|---|---|
| 필요 요건 | R1 + R2 + R3 전부 | R1 + R2 |
| 장비 | 온도챔버, 전압 조절, 보드 2~3개 | 온도 제어 수단 + 현 보드 |
| 기간 | 수개월 | 수주 |
| 리스크 | 리젝 시 시간 손실 큼 | 낮음, 중간 결과물 확보 |

> **권고: 경로 B.** 현 데이터로 저널 직행은 리젝 확률이 높다. 온도 실험(R1)만으로도
> 학회 발표는 충분하며, 피드백으로 R3의 범위를 구체화한 뒤 저널로 확장하는 편이 효율적이다.

### 3.7 형상 불변 실험 결과별 분기

**세 결과 모두 논문이 된다. 안 겹쳐도 실패가 아니다.**

| 실험 결과 | 해석 | 전략 |
|---|---|---|
| 잘 겹침 (ε < 0.1 LSB) | 가설 성립 | **강한 결과** → 다중 칩(R3) 추가해 저널 도전 |
| 애매하게 겹침 | 조건부 성립 | 학회 + "적용 한계" 를 정직하게 서술 |
| 안 겹침 | 가설 반증 | **"스칼라 보정은 불충분하다"** 는 비판적 검증 논문. 기존 기법에 대한 반증도 가치 있음 |

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

### 7.1 단기 (경로 B — 학회 목표)

```
1. T1 (DPS<->RO 교차검증)         <- 지금 즉시, 추가 측정 불필요
2. T2~T5 (그림·자원 export)       <- 초안 시각자료 완성
3. T6~T7 (온도 실험)  ★★★         <- 논문의 승부처. 여기서 전략이 갈림 (3.7 참조)
4. R2 4-way 비교 (3.5)            <- 스칼라 보정 실효성 입증
5. T15 (문헌 정밀 재조사)          <- novelty 확정 전 필수
6. T8 (single-shot precision)     <- 비교표 작성용
```

### 7.2 장기 (경로 A — 저널 확장 시 추가)

```
7.  R1 확장: 전압(V) 변동 포함, 온도 범위 확대(0~85 C)
8.  R3: 보드 2~3개 다중 칩 재현성
9.  R4: 물리적 설명 (Xilinx derating factor 근거)
10. T9~T11 (dual-phase 비교, 온라인 HW 구현, 온도 3-way)
11. T13~T14 (서지·선행연구 비교표)
```

### 7.3 판단 시점

**3단계(온도 실험) 결과가 나오면 즉시 §3.7 표로 전략을 확정할 것.**
그 전까지는 저널/학회 중 어디를 노릴지 확정하지 말 것 — 데이터가 결정한다.

**1~2단계만 끝나도 "특성화 + 교정 방법론" 초안은 성립**하지만,
3단계 없이는 IEEE 수준의 기여가 되지 않는다 (§3.4 참조).
