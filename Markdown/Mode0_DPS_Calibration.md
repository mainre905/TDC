# Mode 0 (DPS, Dynamic Phase Shift) 캘리브레이션 — 검증 계획

TDC 딜레이라인을 **MMCM 위상 스윕(결정론적 자극)** 으로 특성화하고, 캘리브레이션 전/후를
검증한다. Mode 1(Ring Osc)과 **같은 딜레이라인**을 다른 자극으로 측정.

**Mode 0의 부가가치:** 참 시간 기준(`loop_cnt`)이 있어 **code density(SW)뿐 아니라
하드웨어 실시간 교정(timestamp)까지** 검증 가능. (Mode 1은 code density만)

---

## 0. 두 갈래 검증 개요

| Phase | 방법 | 데이터 | 무엇을 증명 | 빌드 |
|---|---|---|---|---|
| **1** | Code density (SW) | 히스토그램 | LUT가 code density를 선형화 | 1회 |
| **2** | Timestamp 전달함수 (HW) | timestamp vs loop_cnt | **하드웨어가 실시간 교정** | 2회(선형/교정 COE) |

**참 시간 기준:** `t_true = loop_cnt × PHASE_STEP`,  `PHASE_STEP = 1000/56 ≈ 17.857 ps`
(1GHz VCO 기준 MMCM 1스텝). 스윕 스텝 수·스텝당 대기는 `phase_shifter.v`의
`loop_cnt` 종료값·`DELAY_MAX` 참조.

---

## Phase 1 — Code Density (소프트웨어, Mode 1과 동일)

### 1-1. 하드웨어 수집

1. `OPERATION_MODE = 0` 빌드 (hit = test_hit_sync, clk = shifted 200MHz). ROM COE 무관.
2. **리셋**으로 히스토그램 초기화.
3. `btn_shift` 1회 → MMCM 위상 스윕 시작. 스윕 중에만 hit 누적(gated = `final_ts_valid && ps_busy_sync`).
4. 스윕 끝(`ps_busy` 하강) → `readout_active` 스캔 → ILA 캡처.
5. CSV export (**Radix UNSIGNED**).
6. 리셋 → 재스윕 → 두 번째 캡처(측정 B, 독립).

### 1-2. ILA 설정 — 히스토그램 캡처

현재 top.v `universal_ila`(프로브 6개)에서 히스토그램 프로브:

| 프로브 | 신호 | 폭 | 용도 |
|---|---|---|---|
| `probe1` | `readout_active` | 1 | **트리거** (스캔 시작=1) |
| `probe4` | `probe_read_addr_d1` | 9 | **X축** = tap (0~319) |
| `probe5` | `histo_read_data` | 32 | **Y축** = 누적 카운트 |

**Hardware Manager 순서:**
1. **IP 확인:** `ila_0` = 6-프로브 `[1,1,9,48,9,32]`.
2. **Trigger Setup:** `probe1 (readout_active) == 1`.
3. **Capture:** Window depth **≥ 512**, Trigger position **맨 앞(0)**, Capture mode = **basic**
   (스캔이 320주소 연속이라 qualification 불필요).
4. **Run(Arm)** → `btn_shift` → 스윕·스캔 후 캡처.
5. **Export** `iladata.csv`, **Radix UNSIGNED**.

> X축은 반드시 `probe4`(=`probe_read_addr_d1`, BRAM latency 보정된 지연 주소)를 쓸 것.
> 지연 안 된 주소를 쓰면 히스토그램이 1-bin 밀림.

### 1-3. Python 파이프라인

| 순서 | 파일 | 입력 → 출력 |
|---|---|---|
| 1 | `Histogram.py` | `iladata.csv` → `tap_histogram_dps_A/B.csv` |
| 2 | `Making_COE_Mode_0.py` | 히스토그램 A → `tdc_calib_dps_rom.coe` (`SOURCE_TAG="dps"`) |
| 3 | `DNL_INL_codedensity.py` | CAL=A, VAL=B → before/after DNL·INL |

수식은 `Mode1_RingOsc_Calibration.md` 3절과 동일 (code density).

---

## Phase 2 — Timestamp 전달함수 (하드웨어 실시간 교정)

**핵심:** 하드웨어 ROM이 매 hit을 실시간으로 선형화하는지, **참 시간(loop_cnt)** 대비 측정.
COE만 다른 두 빌드(선형 vs 교정)를 **동일 ILA·동일 분석**으로 비교.

### 2-1. 빌드 절차 (2회, ROM COE만 차이)

```
[BEFORE 빌드]
  python Making_COE_linear.py       # canonical COE = 선형 램프 (미교정)
  → ROM IP에 로드 → Mode 0 빌드 → 프로그램
  → btn_shift 스윕 → ILA 캡처 → export → before_capture.csv

[AFTER 빌드]
  python Making_COE_Mode_0.py       # canonical COE = code-density (교정)
  → ROM 재로드 → 재빌드 → 프로그램
  → 동일 스윕/캡처 → after_capture.csv
```

> RTL·ILA는 두 빌드에서 **완전히 동일**. 오직 `tdc_calib_mode0_rom.coe`(canonical) 내용만 다름.

### 2-2. ILA 설정 — Timestamp 캡처 (★ Storage Qualification 필수)

`universal_ila`에서 timestamp 프로브:

| 프로브 | 신호 | 폭 | 용도 |
|---|---|---|---|
| `probe0` | `capture_trigger` | 1 | **트리거 + 자격저장** (스텝당 1펄스) |
| `probe2` | `current_loop_cnt` | 9 | **X축** = 위상 스텝 (참 시간 기준) |
| `probe3` | `final_timestamp_ps[47:0]` | 48 | **Y축** = 하드웨어 절대 시간 |

**왜 Storage Qualification이 필수인가:**
전체 스윕 = (스텝 수) × `DELAY_MAX`(2,000,000) ≈ 수억 클럭 ≈ 수 초.
ILA depth(수천)로는 실시간으로 못 따라감. 그러나 스텝당 대표 **1샘플**만 있으면 되므로
(`capture_trigger` = 스텝 바뀐 뒤 첫 유효 hit에서 1펄스), 자격저장으로 그 순간만 담으면
280~350 샘플이 depth 512에 충분히 들어감.

**Hardware Manager 순서:**
1. **IP 확인:** 6-프로브. (`probe3` = 48비트 timestamp 수용 필수)
2. **Capture Mode:** **BASIC → Capture Control 활성화**.
3. **Storage Qualification:** `probe0 (capture_trigger) == 1` 일 때만 저장.
   → 저장되는 모든 샘플이 "스텝당 1개 유효 hit".
4. **Trigger Setup:** `probe0 (capture_trigger) == 1` (또는 즉시 트리거).
5. **Capture:** Window depth **≥ 512** (스텝 수보다 크게), Trigger position 맨 앞.
6. **Run(Arm)** → `btn_shift`(스윕 시작) → 수 초 대기 → 스텝별 샘플 자격저장 완료.
7. **Export** `before_capture.csv` / `after_capture.csv`, **Radix UNSIGNED**.

> **주의(validate_timestamp.py 컬럼):** 스크립트는 `valid` 컬럼을 찾는데 프로브명이
> `capture_trigger`라 매칭되지 않음. 하지만 **자격저장으로 모든 행이 이미 유효**하므로
> 스크립트가 전체 행을 사용해 문제없음. (basic 캡처로 뽑으면 무효 행이 섞이니 반드시 자격저장 사용)

### 2-3. 수식

```
측정 fine = (-timestamp) mod 5000 = (5000 - timestamp % 5000) % 5000   [ps]
   (timestamp = coarse×5000 - calib_fine → coarse 성분 소거)

참 시간   t_true[s] = loop_cnt[s] × 17.857 ps

스텝별 평균: fine(s) = mean( 측정 fine | loop_cnt == s )
직선 피팅:   fine ≈ a·t_true + b
INL[s] = (fine(s) - (a·t_true[s]+b)) / (a·17.857)     [LSB]
DNL[s] = Δfine(s) / mean(Δfine) - 1                    [LSB]
```

- **BEFORE(선형 COE):** tap 폭 불균일 때문에 fine vs t_true가 구불구불 → INL 큼.
- **AFTER(교정 COE):** 직선에 근접 → INL 대폭 감소.

### 2-4. Python

```
python validate_timestamp.py     # before_capture.csv / after_capture.csv → 비교 그림
```

---

## 주의점 (검증됨)

| 항목 | 내용 |
|---|---|
| **INL vs DNL** | Timestamp 방식은 **INL 확실히 개선**. DNL은 tap 양자화(per-step) 한계라 개선 제한 → **INL을 헤드라인**으로. |
| **Storage Qualification** | Phase 2는 필수 (스윕이 ILA depth보다 훨씬 긺). Phase 1(히스토그램)은 불필요. |
| **순환성** | DPS로 교정·검증 = 부분적 self-consistency. 완전 독립 검증은 **Mode0↔Mode1 교차**(다음 단계). |
| **빌드 공정성** | Phase 2 두 빌드는 ROM COE만 다름 (RTL·ILA 동일). |

---

## 진행 순서

```
Phase 1 (SW, 빠름)       → DPS code density, Mode 1과 나란히 비교
Phase 2 (HW, 빌드 2회)   → 하드웨어 실시간 교정 실증 (INL 개선)
그 다음 → Mode0 ↔ Mode1 교차검증 (자극 무관 일반화, 논문 핵심)
```
