# 집 보드 CO 단일 지연선 TDC — 정밀 측정·검증 캠페인

> **작성일** 2026-08-22
> **작성** Claude Opus 5 (Claude Code)
> **대상 보드** 집 Zybo — `device_dna[30:0] = 1679435868 = 0x641A285C`
> **상태** 계획 문서. 실측 전. 결과는 §9에 채울 것.
> **선행** `Markdown/2026-08-19_mode0_plan.md`(1차 계획), `Markdown/2026-08-20_report.md`(회사 보드 실행 결과)
> **주의** AI가 생성한 문서입니다. 수치·절차는 사용 전 실제 코드/측정과 대조하십시오.

---

## 0. 목적과 범위 — 먼저 구분할 것

CO(캐리 출력) 탭 기반 **단일 지연선** TDC를 집 보드에서 처음부터 다시 세우고, 진짜 시간
기준으로 특성을 확정한다.

### 0-1. 교정이 고치는 것과 못 고치는 것

| | 무엇 | 교정으로 개선되나 |
|---|---|---|
| **정확도** | 이득 오차, INL, **클럭 경계 불연속** | **된다** |
| **정밀도** (single-shot σ) | 한 번 재면 얼마나 흔들리나 | **안 된다** |

**σ는 양자화 한계다.** 2026-08-20 실측에서 5개 위상 전부 `σ = Δ·√(p(1−p))`와 **0.01 ps
이내로 일치**했다(Δ = 인접 두 탭 간격, p = 한쪽 비율). 아날로그 지터의 기여가 측정에
전혀 나타나지 않는다. 즉 σ를 줄이려면 탭을 더 촘촘히 만드는 수밖에 없고, LUT로는 안 된다.

> **이 캠페인의 목표는 σ를 줄이는 것이 아니라, 정확도를 한계까지 끌어올리고 σ가
> 양자화 한계에 도달해 있음을 진짜 시간 기준으로 확정하는 것이다.**

### 0-2. 이번에 반드시 잡아야 할 것 — 클럭 경계 불연속

2026-08-20 집 보드 측정(`python/final_test.csv`)에서 발견한 문제다.

```
로드된 ROM  tdc_calib_mode0_rom.coe = 15.625 ps/탭 (선형)
ROM 풀스케일 4,594 ps  vs  클럭 주기 5,000 ps
차이 406 ps  ->  히트가 클럭 경계를 넘을 때마다 타임스탬프가 406 ps 튄다
```

`ts_coarse`는 정확히 5,000 ps를 더하는데 fine은 4,594 ps만 덮으므로 생기는 실제 오차다.
**이것 하나가 INL p-p를 100 ps에서 424 ps로 4배 키웠다.** 코드밀도 LUT는 정의상
`w[i] = h[i]/H × 5000 ps`로 정규화되어 풀스케일이 정확히 5,000 ps이므로 이 항이 0이 된다.

---

## 1. 집 보드 기준값

`python/co_histo_back.csv` (2026-08-13, Mode 1 RO, 히트 187,096,643, 다이 40.7 °C) 실측·유도:

| 양 | 값 | 계산식 | 종류 |
|---|---|---|---|
| 유효탭 | **299** | `h[i] > 0` 인 탭 수 | 측정 |
| LSB (산술평균 탭 폭) | **16.722 ps** | 5000 / 299 | 유도 |
| 히트가중 평균 탭 폭 | 24.138 ps | Σ w[i]·p[i], p[i]=h[i]/H | 유도 |
| **σ 양자화 한계** | **7.87 ps** | √( Σ w[i]²·p[i] / 12 ) | 유도 |
| 탭이 균일했다면 | 4.83 ps | LSB / √12 | 유도 |
| 최대 탭 폭 | 86.6 ps | max w[i] | 측정 |
| DNL rms (코드밀도) | 0.666 LSB | w[i]/LSB − 1 | 유도 |
| INL p-p (코드밀도) | 99.0 ps | cumsum(DNL) × LSB | 유도 |
| `%4` 그룹 평균 폭 | 16.90 / 26.65 / 6.62 / 16.85 ps | `%4` = 탭 인덱스 mod 4 | 유도 |

**빌드 재현성**: 집 보드는 8/04 → 8/09 → 8/13 세 빌드가 탭 폭 상관 **r = 0.999**로 일치했다.
같은 칩이면 빌드가 달라도 지연선이 같다(CARRY4·FF이 `tdc.xdc`로 같은 슬라이스에 고정됨).

**보드 지문**

| 보드 | `device_dna[30:0]` | 16진 | 유효탭 | LSB |
|---|---|---|---|---|
| **집 (이번 대상)** | **1679435868** | **`0x641A285C`** | 299 | 16.722 ps |
| 회사 | 776562772 | `0x2E496854` | 284 | 17.606 ps |

**모든 캡처에서 `device_dna` 컬럼을 확인할 것.** `0x641A285C`가 아니면 집 보드가 아니다.

---

## 2. 전체 구조 — 빌드 3회, 매번 한 가지만 바꾼다

```
Build 1   Mode 1 (RO)   + 아무 COE     →  코드밀도 히스토그램 → LUT 2종 생성
   ↓  (OPERATION_MODE 만 바꿈)
Build 2   Mode 0 (DPS)  + 선형 COE     →  BEFORE 전달함수 + 지터 + Mode0 히스토그램
   ↓  (ROM 만 바꿈)
Build 3   Mode 0 (DPS)  + 코드밀도 LUT →  AFTER  전달함수 + 지터
```

| | `OPERATION_MODE` | 코어 | ROM COE |
|---|---|---|---|
| Build 1 | **1** (RO) | `tdc_fmcw_core_co` | 아무거나 (결과 무관) |
| Build 2 | **0** (DPS) | `tdc_fmcw_core_co` | **`tdc_calib_linear_rom.coe`** (풀스케일 정합) |
| Build 3 | 0 (DPS) | `tdc_fmcw_core_co` | **`tdc_calib_ringosc_rom.coe`** (코드밀도) |

Build 2 ↔ 3 이 **ROM만 다른 통제 비교**라 교정 효과가 깨끗하게 분리된다.

### 왜 선형 COE를 새로 만들어야 하나

레포에 있는 두 COE는 **집 보드에 안 맞는다**:

| 파일 | 탭당 | 집 보드 풀스케일 | 경계 튐 |
|---|---|---|---|
| `dummy_rom.coe` | 17.857 ps | 5,339 ps (299탭) | **오버플로** |
| `tdc_calib_mode0_rom.coe` | 15.625 ps | 4,672 ps | **328 ps** |
| **`Making_COE_linear.py` 출력** | **5000/299 = 16.722 ps** | **5,000 ps** | **0** |

`Making_COE_linear.py`는 `LSB_nominal = 5000 / N_valid`로 만들고 유효 구간도 코드밀도와
동일하게 잡으므로 **공정한 BEFORE**가 된다. 반드시 이걸 쓸 것.

---

## 3. Build 1 — Mode 1 (Ring Osc) 코드밀도

### 3-1. RTL

`RTL/tdc_test_top.v`

| 줄 | 현재 | 바꿀 값 |
|---|---|---|
| 9 | `OPERATION_MODE = 1` | **그대로 1** |
| **251** | `tdc_fmcw_core u_tdc (` | **`tdc_fmcw_core_co u_tdc (`** |

**`RTL/tdc.xdc` 변경 없음.** 이미 들어가 있는 것: `dna_reader`, `probe9`, `CAP_PER_STEP=16`,
동기화 2단.

합성 대상: `tdc_test_top.v`, `dna_reader.v`, **`tdc_fmcw_core_co.v`**,
`tdc_timestamp_calc.v`, `tdc_histogram.v`, `phase_shifter.v`, `tdc.xdc`
IP: `clk_wiz_0`, `ila_0`(probe 10개, probe9 32비트), `tdc_calib_rom`(latency 2)

### 3-2. ILA 설정 (히스토그램)

| 항목 | 값 |
|---|---|
| Capture mode | BASIC |
| Storage qualification | **`probe1` (`readout_active`) == 1** |
| Trigger | `probe1` rising edge |
| Trigger position | **0** |
| Depth | 1024 |
| Radix | `probe4`, `probe5` **UNSIGNED** |

### 3-3. 캡처 — 3회

리셋 → 히트 충분히 누적(**1억 개 이상 권장**) → `readout_active` 자동 스캔 → 캡처 → export.
**리셋으로 히스토그램을 비우고** 3회 반복.

| # | 파일명 | 용도 |
|---|---|---|
| 1 | `python/home/ro_cal.csv` | **LUT 생성용 (cal)** |
| 2 | `python/home/ro_val1.csv` | 평가용 (val) |
| 3 | `python/home/ro_val2.csv` | 평가용 예비 |

> **cal/val 분리는 필수.** LUT를 만든 데이터로 그 LUT를 평가하면 자기 일관성을 재는 것이지
> 교정 품질을 재는 게 아니다.

### 3-4. 즉시 확인

- `device_dna` = **1679435868** (`0x641A285C`)
- 유효탭 **299** 근처 — 8/13 `co_histo_back.csv`와 탭 폭 상관 **r > 0.99** 여야 정상
- 다이 온도 기록 (세 캡처 간 변화 < 0.3 °C)

### 3-5. 파이썬

| 순서 | 스크립트 | 고칠 상수 | 출력 |
|---|---|---|---|
| ① | `Histogram.py` | 12줄 `csv_filepath` (**3회 반복**) | `tap_histogram_*.csv` ×3 |
| ② | `Making_COE_Mode_0.py` | `CAL_CSV`=cal 것 **명시**, `SOURCE_TAG="ringosc"` | **`tdc_calib_ringosc_rom.coe`** + `tdc_calib_mode0_rom.coe`(덮어씀) |
| ③ | `Making_COE_linear.py` | `CAL_CSV`=cal 것 **명시**, `SOURCE_TAG="linear"` | **`tdc_calib_linear_rom.coe`** |
| ④ | `DNL_INL_codedensity.py` | `CAL_CSV`, `VAL_CSV` | DNL·INL (교정 전/후, 소프트웨어 예측) |

> **②를 돌리기 전에 백업**: `cp tdc_calib_mode0_rom.coe tdc_calib_mode0_rom.coe.bak`
> (②가 이 파일을 덮어쓴다)

②의 콘솔 검증값을 **전부 기록**할 것 — 유효 구간, 총 히트, LUT 범위(목표 0~5000),
단조 증가 OK 여부, 13비트 이내 여부, 최대/최소 step(**최소 0이면 missing code**), ROM 라인 수 320.

④는 `VAL_CSV`를 val1/val2로 바꿔 두 번 돌려 재현성을 볼 것.

---

## 4. Build 2 — Mode 0 (DPS) + 선형 COE → BEFORE

### 4-1. RTL / IP

- 9줄 `OPERATION_MODE = 0`
- **`tdc_calib_rom` IP를 `tdc_calib_linear_rom.coe`로 재생성**
- 코어·XDC 변경 없음

### 4-2. 스윕 사양 (RTL에서 읽은 값)

```
DELAY_MAX = 2,000,000 클럭 @200 MHz  →  스텝당 10 ms
loop_cnt 1 ~ 280 (280회 체류)        →  280 × 17.857 ps = 4,999.96 ps = 정확히 한 주기
총 스윕 2.80 초
hit 주기 10클럭 = 50 ns (20 MHz)     →  스텝당 200,000 히트
CAP_PER_STEP = 16                    →  캡처 4,480행
```

### 4-3. 캡처 A — 전달함수 ×3

| 항목 | 값 |
|---|---|
| Storage qualification | **`probe0` (`capture_trigger`) == 1** |
| Trigger | `probe0 == 1` |
| **Trigger position** | **0** ← 중앙이면 절반만 찬다 |
| Depth | 8192 |
| Radix | `probe2`, `probe3` **UNSIGNED** |

리셋 → arm → `btn_shift` → **2.8초 대기** → 4,480행 확인 → export.
파일명 `python/home/before_tf_1.csv` ~ `_3.csv`.

**버퍼가 8192를 못 채우고 4,480에서 멈추는 것이 정상이다** (자격 샘플이 그만큼뿐).
Stop을 눌러 업로드할 것.

### 4-4. 캡처 B — Mode 0 히스토그램 ×2

§3-2와 같은 설정. 파일명 `python/home/mode0_histo_1.csv`, `_2.csv`.

**목적**: Mode 1(`clk_200_fixed`)로 만든 LUT를 Mode 0(`clk_200_shifted`)에 쓰는 것이
타당한지 검증. `tdc_histogram`은 교정 전 raw `aligned_fine_idx`를 누적하므로 COE와 무관하고
`ro_cal.csv`와 직접 비교된다.

> **r > 0.99 면 클럭 차이가 무시할 수준이고 LUT 이식이 정당하다.
> 크게 어긋나면 Mode 0 히스토그램으로 LUT를 다시 만들어야 한다.** 이 확인은 2026-08-19
> 계획에 있었으나 아직 한 번도 수행되지 않았다.

### 4-5. 캡처 C — 지터 ×5

| 항목 | 값 |
|---|---|
| Storage qualification | **없음** |
| Trigger | **`probe2` (`current_loop_cnt_stable`) == N** |
| Trigger position | 0 |
| Depth | 8192 |

N = **50, 100, 150, 200, 250**. 파일명 `python/home/before_jit_<N>.csv`.
히트가 정확히 10클럭마다 나오므로 8,192행에서 유효 히트 **820개**를 뽑는다.

**Build 3에서 같은 N을 쓸 것** — LUT가 σ에 영향을 주는지 직접 비교하기 위함.

---

## 5. Build 3 — Mode 0 (DPS) + 코드밀도 LUT → AFTER

### 5-1. RTL / IP

- **`tdc_calib_rom` IP만 `tdc_calib_ringosc_rom.coe`로 재생성**
- 그 외 **전부 Build 2와 동일** → COE 효과만 분리됨

### 5-2. 캡처

§4-3 전달함수 ×3 → `python/home/after_tf_1.csv` ~ `_3.csv`
§4-5 지터 ×5 (**같은 N**) → `python/home/after_jit_<N>.csv`
§4-4 히스토그램 ×1 → `python/home/after_histo_1.csv` (재현성 확인용)

---

## 6. 분석 — 무엇을 어떻게 계산하나

### 6-1. 전달함수 (캡처 A)

```
참 시간   t_true[n] = n × PHASE_STEP,   PHASE_STEP = 1000/56 = 17.857 ps
측정 fine f[n]      = (5000 − timestamp mod 5000) mod 5000     ← coarse 성분 소거
```

**스텝당 16샘플을 평균낸다** — 이게 이번 빌드의 핵심이다.
```python
df.groupby('current_loop_cnt_stable')['fine'].mean()
```

> **★ 경계(wrap) 스텝은 반드시 제외할 것.** 스텝 안에서 fine이 0 근처와 5000 근처로 갈리는
> 스텝이 1~2개 생긴다(2026-08-20 집 보드에서는 step 74 하나). 이봉 분포라 평균이 무의미하다.
> 판정: 스텝 내 `max − min > 2500 ps` 이면 경계 스텝.

직선 피팅 `f = a·t_true + b` →
- `a` = 이득. `|1 − a|` = 이득 오차
- 잔차 `r[n] = f[n] − (a·t_true[n] + b)` → **INL**
- 차분 `d[n] = f[n+1] − f[n]`, `DNL[n] = d[n]/PHASE_STEP − 1` → **DNL [LSB]**

### 6-2. 측정 잡음 (같은 캡처에서 공짜로 나온다)

스텝 안 16샘플의 표준편차 = **1샘플 측정 잡음 σₙ**. 그 평균/4 = 16평균의 표준오차.

2026-08-20 실측: σₙ = 7.92 ps → 16평균 1.98 ps. **DNL 측정 잡음 0.62 → 0.16 LSB.**
집 보드 예측 σₙ ≈ **7.87 ps**(§1). 이 값이 나와야 정상이다.

### 6-3. 클럭 경계 불연속 ★ 이번의 핵심 지표

```
ROM 풀스케일 = (관측 최대 fine) − (관측 최소 fine) + 1 LSB
경계 불연속  = 5000 ps − ROM 풀스케일
```

| | 기대 |
|---|---|
| BEFORE (선형, 풀스케일 정합) | ≈ 0 ps |
| AFTER (코드밀도 LUT) | **정확히 0 ps** (정의상) |

**둘 다 0에 가까우면 §0-2의 문제가 해결된 것이다.** 8/20 집 보드의 406 ps와 대조할 것.

### 6-4. 지터 (캡처 C)

각 위상에서 상위 2탭의 간격 Δ와 비율 p로 `σ_예측 = Δ·√(p(1−p))`를 계산해 실측 σ와 비교.
**0.1 ps 이내로 맞으면 양자화 한계에 도달한 것이다.**

**BEFORE vs AFTER의 σ를 같은 N에서 비교** — LUT는 σ를 바꾸면 안 된다(§0-1).
바뀐다면 LUT가 뭔가 잘못됐다는 뜻이다.

### 6-5. 코드밀도 (캡처 B, `DNL_INL_codedensity.py`)

전달함수(하드웨어 실측)와 코드밀도(소프트웨어 예측)가 **같은 지연선을 다른 원리로** 재므로,
일치하면 양쪽 다 신뢰할 수 있다.

---

## 7. 기대값 요약

| 지표 | BEFORE (선형 정합) | AFTER (코드밀도) | 근거 |
|---|---|---|---|
| 이득 오차 | ≈ 0 % | ≈ 0 % | 둘 다 풀스케일 5000 정합 |
| **경계 불연속** | ≈ 0 ps | **0 ps** | §6-3 |
| INL p-p | **탭 불균일이 그대로** | **줄어야 한다** | 교정의 본체 |
| DNL rms | ~0.67 LSB (코드밀도 값) | 줄어야 한다 | |
| **σ (5 위상)** | **양자화 한계** | **BEFORE와 같아야** | §0-1 |
| 1샘플 측정 잡음 σₙ | 7.87 ps | 7.87 ps | §1 |

**AFTER의 INL이 안 줄면** → §4-4의 Mode1↔Mode0 히스토그램 대조부터 확인할 것.

**교정 후에도 INL이 남는 것은 정상이다.** 코드밀도 LUT는 각 히트를 bin 중심에 놓는 것이
최선이라 넓은 bin의 오차는 못 없앤다. 집 보드 최대 탭 폭 86.6 ps → 그 탭에서만 ±43 ps.
**"정적 LUT의 잔차는 bin 폭 분포가 결정한다"**가 정량적 결론이 된다.

---

## 8. 체크리스트

**Build 1 — Mode 1 (RO)**
- [ ] `tdc_test_top.v` 251줄 → `tdc_fmcw_core_co`
- [ ] `dna_reader.v` 프로젝트에 포함, `ila_0` probe 10개 확인
- [ ] Vivado 프로젝트 사본이 레포와 동일한지 (`grep -c dna_reader`, `grep -n CAP_PER_STEP`)
- [ ] 합성 후: `DNA_PORT`=1, `toggle_sync`=3, `cap_cnt`=5비트
- [ ] 구현 후: WNS ≥ 0, BRAM ≤ 60, CARRY4 80개 `SLICE_X42Y0~Y79`
- [ ] 다이 온도 안정화 대기 (변화 < 0.3 °C)
- [ ] 히스토그램 ×3 → `home/ro_cal.csv`, `ro_val1.csv`, `ro_val2.csv`
- [ ] **`device_dna` = 1679435868 확인**
- [ ] `cp tdc_calib_mode0_rom.coe tdc_calib_mode0_rom.coe.bak`
- [ ] `Histogram.py` ×3 → `Making_COE_Mode_0.py` → `Making_COE_linear.py` → `DNL_INL_codedensity.py`
- [ ] `ro_cal` ↔ 8/13 `co_histo_back.csv` 상관 r > 0.99 확인

**Build 2 — Mode 0 + 선형 정합 COE (BEFORE)**
- [ ] 9줄 `OPERATION_MODE = 0`, ROM을 `tdc_calib_linear_rom.coe`로 재생성
- [ ] 전달함수 ×3 (Trigger position **0**, 4,480행) → `home/before_tf_1~3.csv`
- [ ] Mode 0 히스토그램 ×2 → `home/mode0_histo_1~2.csv`
- [ ] 지터 ×5 (N=50/100/150/200/250) → `home/before_jit_*.csv`

**Build 3 — Mode 0 + 코드밀도 LUT (AFTER)**
- [ ] ROM만 `tdc_calib_ringosc_rom.coe`로 재생성 (그 외 전부 동일)
- [ ] 전달함수 ×3 → `home/after_tf_1~3.csv`
- [ ] 지터 ×5 (**같은 N**) → `home/after_jit_*.csv`
- [ ] 히스토그램 ×1 → `home/after_histo_1.csv`

**분석**
- [ ] 경계 스텝 검출·제외 후 INL/DNL
- [ ] 경계 불연속 (5000 − ROM 풀스케일) BEFORE/AFTER
- [ ] σ 5위상 BEFORE/AFTER 비교
- [ ] Mode1 ↔ Mode0 히스토그램 상관
- [ ] 결과를 §9에 기록

---

## 9. 결과 (측정 후 작성)

*(비어 있음)*

---

## 10. 이번 범위 밖

- **2채널 차분법** — 지연선을 하나 더 만들어야 한다. 단일 체인으로 간다.
- **외부 신호원 검증** — Zybo는 50 Ω 입력이 없어 PMOD 경유 시 반사·슬루 저하로 time walk가
  생긴다. STM32 출력 지터(일반 사양 20~50 ps, **미측정**)가 이 TDC의 σ(≈ 8 ps)보다 커서
  TDC가 아니라 STM32를 재게 된다.
- **절대 이득의 독립 검증** — 코드밀도 정규화가 지연선을 클럭 주기에 앵커시키므로 이득은
  **측정이 아니라 정의**다. 논문에 그렇게 명시할 것.
- **온도 실험** — 챔버가 회사에만 있다. 집 보드로는 불가.
- **회사 보드 데이터와 혼용** — 다른 칩이라 탭 폭 상관 r = 0.54. 절대 섞지 말 것.
