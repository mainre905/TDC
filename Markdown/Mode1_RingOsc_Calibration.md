# Mode 1 (Ring Oscillator) 캘리브레이션 — 진행 정리

TDC 딜레이라인을 **링발진기(비동기 랜덤 hit)** 로 특성화하고, 캘리브레이션 전/후
DNL·INL을 code density로 비교한다. Mode 0(DPS)과 **같은 딜레이라인**을 다른 자극으로 측정.

---

## 0. 평가 원리 — 왜 code density인가

| | Mode 0 (DPS) | Mode 1 (Ring Osc) |
|---|---|---|
| 자극 | MMCM 위상 스윕(결정론) | 링발진기(비동기 랜덤) |
| 참 시간 기준 | `loop_cnt × 17.857 ps` **있음** | **없음** (hit이 async) |
| DNL/INL 평가 | 전달함수 또는 code density | **code density 전용** |

Mode 1은 개별 hit의 참 시간을 모르므로(비동기), **통계적 code density**로 평가한다.
링발진기 hit은 클럭 주기를 균일 샘플링 → 각 tap의 hit 수 ∝ tap 폭 → 이것이 DNL/INL 근거.

> **중요:** 히스토그램은 **raw tap(`aligned_fine_idx`)** 을 쓰며 **COE를 거치지 않는다.**
> 따라서 새 COE를 넣고 재측정해도 히스토그램은 그대로다. 캘리브레이션은
> **소프트웨어(LUT 적용)** 로 평가하며, 이는 하드웨어와 수학적으로 동일하다(ROM==COE 검증됨).

---

## 1. 전체 흐름

```
[측정 A] Ring Osc 누적 → 히스토그램 A → LUT(COE) 생성        (cal)
[측정 B] Ring Osc 누적 → 히스토그램 B                         (val, A와 독립)
        → A의 LUT를 B에 소프트웨어 적용 → before/after DNL·INL
```

**cal/val 분리(A≠B)로 순환논리 회피** — A로 만든 LUT가 독립 측정 B를 선형화하면 일반화 성공.

---

## 2. 하드웨어 데이터 수집

1. `OPERATION_MODE = 1` 빌드 (hit = ring osc, clk = 200MHz fixed). ROM COE는 무관.
2. **리셋**으로 히스토그램 초기화(BRAM clear).
3. 대기하며 자동 누적(btn 불필요). 링오실 ~1.5MHz → tap당 100만개까지 10~20분.
   - 더 원하면 그냥 더 기다림. rate를 올리려면 `ro_divider_cnt[5]→[3]` (hit 간격 ≥ 8클럭).
4. **readout 트리거:** `btn_shift` 1회 → 약 2.8초 후 `readout_active`가 0→319 스캔 → ILA 캡처.
5. CSV export (**Radix UNSIGNED**).
6. 리셋 후 **재누적 → 두 번째 캡처**(측정 B). → 독립 2회 확보.

### ILA 설정 (Vivado Hardware Manager)

현재 top.v는 `universal_ila`(프로브 6개) 사용. 히스토그램 캡처에 쓰는 프로브:

| 프로브 | 신호 | 폭 | 용도 |
|---|---|---|---|
| `probe1` | `readout_active` | 1 | **트리거** (스캔 시작 = 1) |
| `probe4` | `probe_read_addr_d1` | 9 | **X축** = tap 인덱스 (0~319) |
| `probe5` | `histo_read_data` | 32 | **Y축** = 누적 카운트 |

*(probe0/2/3은 timestamp(INL)용 — 히스토그램 캡처에선 무시)*

설정 순서:
1. **IP 확인:** `ila_0`가 6-프로브 `[1,1,9,48,9,32]` 로 구성돼 있어야 함
   (probe3=48비트 timestamp 때문). 안 맞으면 합성 실패.
2. **Trigger Setup:** `probe1 (readout_active) == 1`
3. **Capture:** Window depth **≥ 512** (스캔 320주소 + 여유), Trigger position **맨 앞(0)**.
   Capture mode = basic (매 사이클). readout이 320주소 연속이라 storage qualification 불필요.
4. **Run(Arm)** → `btn_shift` 누름 → 2.8초 후 스캔 캡처됨.
5. **Export:** File → `iladata.csv`, **Radix = UNSIGNED**.

> **X/Y 정렬:** `probe_read_addr_d1`은 BRAM read latency(1클럭)를 보정한 지연 주소라
> `histo_read_data`와 같은 사이클에 정렬돼 있음. 반드시 `probe4`(=_d1)를 X축으로 쓸 것
> (지연 안 된 주소를 쓰면 히스토그램이 1-bin 밀림).

> **주의:** 히스토그램 회로는 3-state RMW(`count_raw`) 버전이어야 함. 예전 2-state는
> RMW 데이터 해저드로 모든 bin이 평균화되어 **flat(가짜)** 히스토그램이 나온다.
> 정상 결과는 **spiky**(tap 1 최대, period-4).

---

## 3. 수식

기호: `h[i]` = tap i 히트 수, `H = Σh`, `T = 5000 ps`, `N` = 유효 tap 수, `LSB = T/N`.

### (a) tap 실측 폭 (측정 B)
$$w_B[i] = \frac{h_B[i]}{H_B}\,T$$

### (b) BEFORE — raw code density
$$\text{DNL}_\text{before}[i] = \frac{w_B[i]}{\text{LSB}} - 1,\qquad
  \text{INL}_\text{before}[i] = \sum_{k\le i}\text{DNL}_\text{before}[k]$$

### (c) LUT (측정 A, cumulative code density, bin 중심)
$$\text{LUT}[i] = \frac{T}{H_A}\Big(\sum_{k<i} h_A[k] + \tfrac{h_A[i]}{2}\Big)$$
tap 경계(edge): $\ \text{edge}_A[i] = \dfrac{T}{H_A}\sum_{k<i} h_A[k]$

### (d) AFTER — A의 LUT를 B에 적용 (fractional re-binning)
측정 B의 각 tap 히트를, A가 정한 시간 구간 $[\text{edge}_A[i],\ \text{edge}_A[i{+}1])$ 에
균일하게 펼쳐 균일 격자(폭 LSB)로 재분배:
$$\text{merged}[k] = \sum_i h_B[i]\cdot
  \frac{\text{overlap}\big([\text{edge}_A[i],\text{edge}_A[i{+}1]),\ \text{bin}_k\big)}
       {\text{edge}_A[i{+}1]-\text{edge}_A[i]}$$
$$\text{DNL}_\text{after}[k] = \frac{\text{merged}[k]}{\overline{\text{merged}}} - 1,\qquad
  \text{INL}_\text{after}[k] = \sum_{j\le k}\text{DNL}_\text{after}[j]$$

**직관:** LUT가 "이 tap은 실제로 이만큼 넓다"고 알려주면, 그 폭대로 히트를 시간축에
펼쳐 균일 격자에서 평평해진다 → 비선형성 상쇄.

### 실제 숫자로 이해하기 (2026-07-20 측정)

공통값: `H_A = 121,475,372`, `H_B = 149,709,691`, `N = 294`, `LSB = T/N = 17.007 ps`

측정 A·B의 실제 히트 수와 각 단계 계산:

| tap | h_A | h_B | w_B (b) | DNL_before (b) | edge_A (c) | LUT_A (c) |
|---|---|---|---|---|---|---|
| **1** | 1,683,039 | 2,073,511 | **69.25 ps** | **+3.072** | 0.0 ps | 34.6 ps |
| 2 | 171,321 | 219,043 | 7.32 ps | −0.570 | 69.3 ps | 72.8 ps |
| 3 | 1,125,928 | 1,390,787 | 46.45 ps | +1.731 | 76.3 ps | 99.5 ps |
| 34 | 189,582 | 237,405 | 7.93 ps | −0.534 | 679.7 ps | 683.6 ps |
| 100 | 763,040 | 935,457 | 31.24 ps | +0.837 | 1758.1 ps | 1773.8 ps |

**각 열이 어떻게 나오나 — tap 1 예시:**

- **(b) 폭** `w_B[1] = h_B[1]/H_B × T = 2,073,511 / 149,709,691 × 5000 = 69.25 ps`
  → tap 1이 전체 히트의 1.39%를 받음 = 클럭주기의 1.39% = 69.25ps 폭.

- **(b) BEFORE DNL** `= w_B[1]/LSB − 1 = 69.25/17.007 − 1 = +3.07 LSB`
  → 이상(17ps)보다 **4배나 넓다** = entry transient. DNL이 크게 튐(나쁨).

- **(c) LUT** `LUT[1] = (Σ_{k<1} h_A + h_A[1]/2)/H_A × T = (0 + 841,519)/121,475,372 × 5000 = 34.6 ps`
  → A가 "tap 1의 중심 시각 = 34.6ps"라고 기록. 경계는 `edge_A[1]=0 ~ edge_A[2]=69.3ps`.

**(d) AFTER 재분배 — tap 1이 평준화되는 과정:**

```
A의 LUT: tap 1은 시간 0 ~ 69.3ps 를 차지 (폭 69.3ps)
B의 히트: h_B[1] = 2,073,511 개

이 2,073,511 히트를 0~69.3ps 구간에 '균일하게' 펼침
균일격자 폭 LSB = 17ps → 이 구간은 격자 0,1,2,3 + 4의 일부 (약 4.1개)에 걸침
→ 2,073,511 ÷ 4.1 ≈ 509,041 개씩 각 격자로 분배
```

- **BEFORE**: tap 1 한 칸에 2,073,511개가 몰려 있음 (DNL +3.07, 스파이크)
- **AFTER**: 그 2,073,511개가 **4.1개 격자에 ~509,041씩** 나뉨
  → 격자당 값이 **평균(H_B/N ≈ 509,216)에 근접** → DNL ≈ 0 (평평)

즉 "넓은 tap을 그 폭만큼 여러 격자로 쪼개고, 좁은 tap은 이웃과 합쳐" 모든 격자를
비슷하게 만드는 것. 이것이 전체적으로 DNL 4.03 → 0.11로 줄어드는 메커니즘이다.

---

## 4. 사용 Python 파일 (실행 순서)

| 순서 | 파일 | 입력 → 출력 |
|---|---|---|
| 1 | `Histogram.py` | `iladata.csv` → `tap_histogram_*.csv` (측정 A, B 각각) |
| 2 | `Making_COE_Mode_0.py` | 히스토그램 A → `tdc_calib_mode0_rom.coe`(canonical) + `tdc_calib_ringosc_rom.coe`(태그) |
| 3 | `DNL_INL_codedensity.py` | CAL=A, VAL=B → `dnl_inl_dps_compare.png` + DNL/INL |

`DNL_INL_codedensity.py` 설정:
```python
CAL_CSV = "tap_histogram_A.csv"   # LUT 생성 (edge_A)
VAL_CSV = "tap_histogram_B.csv"   # 독립 평가 (h_B)
```

---

## 5. 실측 결과 (2026-07-20)

```
CAL: tap_histogram_20260720_191308.csv (측정 A)
VAL: tap_histogram_20260720_195432.csv (측정 B, 독립)
유효 구간: tap 1~294 (294 bins), raw LSB = 17.007 ps

           DNL P-P    INL P-P
BEFORE      4.029      8.553
AFTER       0.110      0.173      ← DNL 37×, INL 50× 개선
```
절대값: AFTER DNL ≈ 1.9 ps, INL ≈ 2.9 ps.

**해석:** A로 만든 LUT가 독립 측정 B를 DNL 0.11 / INL 0.17 LSB로 선형화 → 일반화 성공.
단, A·B 모두 Ring Osc·같은 칩·근접 시각이라 **same-stimulus repeatability**(가장 유리한 조건)임.

---

## 6. timestamp_ps 검증 가능 범위 (Mode 1)

| 검증 | 필요 | Mode 1 |
|---|---|---|
| 절대시간 선형성 (measured vs 참 시간) | 참 시간 기준 | ❌ 불가 (링오실 비동기) |
| COE 적용 무결성 (tap N → LUT[N]) | (tap, timestamp) 쌍 | ✅ 가능 (기준 불필요) |

절대시간 선형성 INL은 **Mode 0(DPS, loop_cnt 기준)** 에서 `validate_timestamp.py`로만 가능.

---

## 7. 남은 단계

1. **DPS ↔ Ring Osc 교차검증** (더 강력): DPS LUT를 Ring Osc 데이터에 적용 → 자극 무관 일반화 입증. `DNL_INL_codedensity.py` CAL=DPS, VAL=RingOsc.
2. **timestamp_ps 검증** (Mode 0 하드웨어 실시간 교정): `validate_timestamp.py`.
3. **DPS COE 보관**: Mode 0 데이터로 `SOURCE_TAG="dps"` → `tdc_calib_dps_rom.coe`.
