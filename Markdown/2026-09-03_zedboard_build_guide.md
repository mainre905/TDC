# ZedBoard 빌드·측정 작업 지시서

> **작성일** 2026-09-02
> **작성** Claude Opus 5 (Claude Code)
> **대상** 2026-09-03 회사 작업 (ZedBoard, Claude 사용 불가 환경)
> **주의** AI가 생성한 문서입니다. 수치·절차는 사용 전 실제 코드/측정과 대조하십시오.

---

## 0. 이 문서의 목적

회사에는 ZedBoard 가 있고 Claude 를 쓸 수 없다. **혼자서 끝까지 진행할 수 있도록** 필요한 것을 전부 적었다. 막히면 §7 문제 해결을 먼저 볼 것.

**오늘 준비된 것**

| 파일 | 상태 |
|---|---|
| `RTL/tdc_zedboard_top.v` | 신규 — ZedBoard 최상위 래퍼 (LVDS 수신 + 코어 인스턴스) |
| `RTL/tdc_zedboard.xdc` | 신규 — ZedBoard 핀 + 기존 LOC 720개 |
| `python/Making_COE_Mode_0.py` | 수정 — `VALID_TAP_HI` 매크로 추가 |
| `RTL/tdc_test_top.v`, `RTL/tdc.xdc` | **안 건드림** (Zybo 용 그대로) |

---

## 1. 시작 전 하드웨어 — 이것부터 안 하면 아무것도 안 된다

### ★ 점퍼 J18 을 2.5V 로 옮길 것

ZedBoard 기본값은 **1.8V** 다. FMC 뱅크 34/35 의 VCCO 가 2.5V 여야:
- LA27 의 **LVDS_25** 수신이 규격 안에서 동작하고
- 내부 100옴 종단(**DIFF_TERM**)이 켜지며
- 버튼(뱅크 34)의 **LVCMOS25** 가 맞는다

**1.8V 로 두면 XDC 의 IOSTANDARD 가 전부 어긋나 빌드가 실패하거나, 통과해도 LVDS 가 안 잡힌다.**

### TLV3605 연결 확인

| 신호 | FMC 핀 | FPGA 핀 |
|---|---|---|
| LVDS+ | LA27_P | **E21** |
| LVDS− | LA27_N | **D21** |

---

## 2. Vivado 프로젝트 생성

1. **New Project** → RTL Project → part **`xc7z020clg484-1`**
2. **소스 파일 7개 추가** (`RTL/` 에서)

```
tdc_zedboard_top.v      ← 최상위로 지정할 것 (Set as Top)
tdc_test_top.v
tdc_fmcw_core_co.v
tdc_timestamp_calc.v
tdc_histogram.v          (안에 tdc_bram_512x32 도 들어있음)
phase_shifter.v          (안에 mmcm_phase_shifter)
dna_reader.v
```

3. **제약 파일 추가**: `RTL/tdc_zedboard.xdc`
   → **`tdc.xdc` 는 절대 같이 넣지 말 것** (Zybo 핀이라 충돌한다)

### IP 4개 생성

CLAUDE.md 에는 3개로 적혀 있으나 **실제로는 4개**다 (`xadc_wiz_0` 누락).

| IP | 설정 | 비고 |
|---|---|---|
| **`clk_wiz_0`** | 입력 **100 MHz**, VCO **1000 MHz**(M=10, D=1), CLKOUT0/CLKOUT1 = **200 MHz**, CLKOUT1 에 **Dynamic Phase Shift** 활성화 | ★ 아래 경고 참조 |
| `ila_0` | probe **10개**, depth **8192** | 폭은 §3 표 |
| `tdc_calib_rom` | 320 × 13bit, **latency 2**, `.coe` 로드 | latency 2 아니면 파이프라인 어긋남 |
| `xadc_wiz_0` | DRP 인터페이스, on-chip temperature | 다이 온도용 |

> ### ★ clk_wiz_0 의 VCO 를 반드시 1000 MHz 로
> `phase_shifter.v` 의 위상 스텝은 **VCO 주기의 1/56 = 17.857 ps** 다.
> 이 값이 **Mode 0 의 참 시간축**이라, VCO 가 1000 MHz 가 아니면 교정 계산이
> 전부 틀어진다. 100 MHz × 10 = 1000 MHz, ÷5 = 200 MHz 로 맞출 것.
> Vivado 가 다른 M/D 조합을 자동 제안하면 **직접 고쳐야 한다.**

### ILA probe 폭

| probe | 폭 | 신호 |
|---|---|---|
| 0 | 1 | `capture_trigger` |
| 1 | 1 | `readout_active` |
| 2 | 9 | `current_loop_cnt_stable` |
| 3 | **48** | `final_timestamp_ps` |
| 4 | 9 | `probe_read_addr_d1` |
| 5 | 32 | `histo_read_data` |
| 6 | 32 | `ro_meas_cnt` |
| 7 | 1 | `meas_strobe` |
| 8 | 16 | `die_temp_at_meas` |
| 9 | 32 | `device_dna` |

합계 181 비트. XC7Z020 은 BRAM 이 140개(XC7Z010 은 60개)라 depth 8192 는 여유 있다.

---

## 3. 빌드 순서 — 총 3회 빌드

`OPERATION_MODE` 는 **컴파일 타임 파라미터**라 모드마다 다시 합성해야 한다.
`tdc_zedboard_top.v` 39행의 `parameter integer OPERATION_MODE` 를 고친다.

| 빌드 | MODE | ROM(.coe) | 목적 |
|---|---|---|---|
| **A** | **1** | 아무거나 | 링오실레이터 히스토그램 → COE 재료 |
| **B** | **0** | `tdc_calib_linear_rom.coe` | BEFORE 전달함수 (기준선) |
| **C** | **0** | `tdc_calib_ringosc_rom.coe` | AFTER 전달함수 (교정 효과) |

---

## 4. 합성 직후 확인 (Tcl Console)

`open_run impl_1` 후:

```tcl
# ① LVDS 가 제대로 잡혔나
puts "hit 넷: [get_property NAME [get_nets -of_objects [get_pins -of_objects [get_cells -hier -filter {REF_NAME==CARRY4 && NAME =~ *CARRY_CHAIN\[0\]*}] -filter {REF_PIN_NAME==CYINIT}]]]"

# ② 히트 네트에 부하가 붙지 않았나 (반드시 1이어야 함)
set c0 [lindex [lsort [get_cells -hier -filter {REF_NAME==CARRY4 && NAME =~ *u_tdc/CARRY_CHAIN*}]] 0]
set cyi [get_pins -of_objects $c0 -filter {REF_PIN_NAME==CYINIT}]
puts "CYINIT 리프 부하: [llength [get_pins -of_objects [get_nets -of_objects $cyi] -leaf -filter {DIRECTION==IN}]] 개  (1 이어야 정상)"

# ③ 캐리체인 80단이 X42 열에 다 들어갔나
puts "CARRY4: [llength [get_cells -hier -filter {REF_NAME==CARRY4 && NAME =~ *u_tdc/CARRY_CHAIN*}]] 개  (80 이어야 정상)"

# ④ 샘플링 FF 320개가 fixed 클럭인가
set ffs [get_cells -hier -filter {NAME =~ *taps_sampled_d1_reg* && IS_PRIMITIVE}]
puts "샘플링 FF: [llength $ffs] 개, 클럭 [lsort -unique [get_property NAME [get_clocks -of_objects [get_pins -of_objects $ffs -filter {REF_PIN_NAME==C}]]]]"

# ⑤ 타이밍
puts "WNS = [get_property SLACK [lindex [get_timing_paths -max_paths 1 -delay_type max] 0]]"
puts "WHS = [get_property SLACK [lindex [get_timing_paths -max_paths 1 -delay_type min] 0]]"
```

**기대값**

| 항목 | 정상 |
|---|---|
| ① CYINIT 구동 넷 | `*hit_from_fmc*` 또는 `*ext_hit_in*` |
| ② CYINIT 리프 부하 | **1개** |
| ③ CARRY4 | **80개** |
| ④ 샘플링 FF | 320개, MODE 0/1/2 전부 **`clk_out1_clk_wiz_0`** |
| ⑤ WNS / WHS | 둘 다 **양수** |

②가 1이 아니면 히트 네트에 다른 부하가 붙은 것이다. 그대로 두면 진입 트랜지언트가
악화되므로(과거 `led[2]` 사례에서 CARRY4 초입 3단이 정상값의 1.16~1.89배로 늘어남)
원인을 찾아 제거할 것.

---

## 5. 측정 순서

**모든 캡처에서 `device_dna` 를 기록할 것.** ZedBoard 는 처음 쓰는 칩이라
집(`0x641A285C`)/회사 Zybo(`0x2E496854`)와 다른 새 값이 나온다. 그 값을 적어둘 것.

데이터 폴더: `data/Test_2026MMDD/`

### 5-1. 빌드 A (MODE 1) — 히스토그램 ×3

| ILA 설정 | 값 |
|---|---|
| Capture mode | BASIC |
| Storage qualification | `probe1` (`readout_active`) **== 1** |
| Trigger | `probe1` **== 1** (레벨. 에지 `R` 로 하면 1샘플만 잡히는 사례 있었음) |
| Trigger position | **0** |
| Depth | 1024 |
| Radix | `probe4`, `probe5` **UNSIGNED** |

리셋 → arm → 히트 1억 발 이상 누적 → 자동 스캔 → **Stop 눌러 부분 버퍼 업로드** → export.
**리셋으로 히스토그램 비우고 3회 반복.**

→ `ro_cal.csv`, `ro_val1.csv`, `ro_val2.csv`

> BASIC 이 말을 안 들으면 **Capture mode = ALWAYS**, Trigger `probe1 == R`, depth 1024
> 로 뽑아도 된다. 뒤쪽 잉여 행은 `Histogram.py` 가 주소별 최댓값을 취하므로 무해하다.

**즉시 확인**: 유효탭 수(320 중 몇 개에 히트가 있나), 다이 온도, DNA

### 5-2. 파이썬 — COE 2종 생성

```
cd python
python Histogram.py            # INPUT_CSV 를 ro_cal.csv 로 → 3회 반복(val1, val2 도)
python Making_COE_Mode_0.py    # CAL_CSV="tap_histogram_ro_cal.csv", SOURCE_TAG="ringosc"
python Making_COE_linear.py    # 같은 CAL_CSV, SOURCE_TAG="linear"
```

`Histogram.py` 상단 `DATA_SUBDIR` 을 오늘 폴더로 고칠 것.

> **이 단계에서는 `VALID_TAP_HI = None`(자동) 그대로 둔다.** 절단값은 §6 에서 정한다.

### 5-3. 빌드 B (MODE 0 + `tdc_calib_linear_rom.coe`) — BEFORE

**전달함수 ×3**

| ILA 설정 | 값 |
|---|---|
| Storage qualification | `probe0` (`capture_trigger`) **== 1** |
| Trigger | `probe0` **== 1** |
| Trigger position | **0** ← 중앙이면 절반만 참 |
| Depth | 8192 |
| Radix | `probe2`, `probe3` **UNSIGNED** |

리셋 → arm → `btn_shift`(BTNU, **T18**) → **2.8초 대기** → **4,480행**에서 멈춤 → Stop → export
→ `before_tf_1.csv` ~ `_3.csv`

**Mode 0 히스토그램 ×3** — §5-1 과 같은 설정 → `mode0_hist_1~3.csv`
(Mode 0 은 스윕 중에만 누적된다. `btn_shift` 를 눌러야 쌓인다)

**지터 ×5** — Storage qualification **없음**, Trigger `probe2` **== N**, position 0, depth 8192
N = 50, 100, 150, 200, 250 → `before_jitter_<N>.csv`

### 5-4. 빌드 C (MODE 0 + `tdc_calib_ringosc_rom.coe`) — AFTER

빌드 B 와 같은 캡처 → `after_tf_1~3.csv`, `after_jitter_<N>.csv`

---

## 6. ★ 유효탭 상한 정하기 — 이번 작업의 핵심

집 보드에서 **자동 검출한 유효탭을 그대로 쓰면 교정이 오히려 나빠졌다.**
링오실레이터(Mode 1)는 위상 스윕(Mode 0)이 한 주기 안에 도달하지 못하는
끝단 칸에도 히트를 쌓기 때문이다. 쓰이지 않는 칸에 5000 ps 의 몫을 떼주면
나머지 칸이 전부 좁아지고, 그 편향이 누적되어 INL 을 망친다.

**집 보드 실측 (XC7Z010)**

| 유효탭 | Mode 0 INL rms | 클럭 경계 점프 |
|---|---|---|
| 자동 298칸 | 19.93 ps | **−26.5 ps** |
| **수동 293칸** | **10.00 ps** | **+0.6 ps** |
| (참고) 무교정 등간격 | 15.68 ps | −10.7 ps |

**ZedBoard 는 다른 칩이므로 293 을 그대로 쓰면 안 된다. 다시 구해야 한다.**

### 정하는 방법 — 클럭 경계 점프가 0 이 되는 값

경계 점프는 INL 을 몰라도 잴 수 있는 독립적인 양이다. 집 보드에서 **INL 최소점과
경계 점프 0 이 같은 곳에서 만나는 것을 확인**했으므로 순환논법이 아니다.

**클럭 경계 점프란**: 스윕이 클럭 한 주기를 넘어갈 때 보고 시각이 매끄럽게 이어지지
않고 툭 튀는 양. LUT 의 총합이 정확히 5000 ps 가 아니면 생긴다.

**절차**

1. `python/Making_COE_Mode_0.py` 59~60행

```python
VALID_TAP_LO = None    # 그대로
VALID_TAP_HI = 290     # ← 이 숫자를 바꿔가며 반복
```

2. 스크립트 실행 → COE 생성 → **빌드 C 다시** → 전달함수 캡처
3. 경계 점프를 계산 (§6-1) → 0 에 가장 가까운 `VALID_TAP_HI` 채택

빌드가 여러 번 필요하므로, **먼저 `before_tf_*.csv`(빌드 B) 하나로 소프트웨어에서
여러 절단값을 시험해 후보를 좁힌 뒤** 빌드 C 를 한 번만 돌리는 것이 효율적이다.
(집 보드에서는 소프트웨어 예측과 하드웨어 실측이 19.93 vs 19.96 ps 로 일치했다)

### 6-1. 경계 점프 계산법 (엑셀/파이썬 공용)

`Markdown/calcaulation_method.md` 에 엑셀 수식으로 상세히 적혀 있다. 요약:

```
① fine        = MOD(5000 - MOD(timestamp, 5000), 5000)
② 스텝별 평균  = 같은 loop_cnt 끼리 16샘플 평균
                 (16샘플이 0과 5000 양쪽에 갈라진 스텝은 작은 값에 +5000 후 평균)
③ 참 시간     = loop_cnt × 17.857 ps
④ 언랩        = 5000 넘어가면 +5000 해서 단조 직선으로 폄
⑤ 랩 스텝 ±5  = 제외 (16샘플이 경계에 걸쳐 평균이 무의미)
⑥ 직선 적합   = y = a·t + b, 잔차 r = y − (a·t+b)
⑦ 경계 점프   = (경계 넘은 뒤 잔차 평균) − (넘기 전 잔차 평균)
   INL rms    = SQRT(SUMSQ(r)/COUNT(r))
```

**참고용 실측값(집 보드)**: 기울기 ±1.00 근처, 랩 스텝 74 또는 178,
사용 점수 270/280, 스텝당 산포 평균 9.2 ps

---

## 7. 문제 해결

| 증상 | 원인 / 조치 |
|---|---|
| IOSTANDARD 관련 에러 (LVDS_25, LVCMOS25) | **점퍼 J18 이 1.8V 다.** 2.5V 로 옮길 것 |
| `tdc.xdc` 핀 충돌 에러 | Zybo XDC 를 같이 넣었다. 제거하고 `tdc_zedboard.xdc` 만 남길 것 |
| LOC 제약 에러 (SLICE 없음) | XC7Z020 에 X42/X43 Y0~Y79 는 존재함을 확인했다(2026-09-02). 그래도 나면 pblock `SLICE_X42Y0:SLICE_X47Y100` 범위부터 의심 |
| 위상 스윕이 안 돌아감 | `btn_shift` = **T18(BTNU)**. `rst_n` = P16(BTNC). 두 버튼을 헷갈리기 쉽다 |
| ILA 가 8192 를 못 채우고 멈춤 | **정상이다.** 자격 샘플이 4,480개(280×16)뿐. Stop 눌러 업로드 |
| ILA BASIC 에서 1샘플만 잡힘 | Trigger 를 에지(`R`)가 아니라 레벨(`1`)로. 안 되면 ALWAYS 모드 사용 |
| 히스토그램이 전부 0 | Mode 0 은 스윕 중에만 누적된다. `btn_shift` 를 눌렀는지 확인 |
| 전달함수 기울기가 이상 | ZedBoard 는 기울기 **+1** 이 정상 (집 보드 8/23 실험의 −1 은 되돌린 RTL 변경 때문이었음) |
| `device_dna_valid` 가 0 | DNA 읽기 실패. 그 캡처의 보드 식별값은 믿지 말 것 |

---

## 8. 돌아와서 할 일 (집)

가져올 것: `data/Test_2026MMDD/` 전체 + 아래 메모

- ZedBoard **DNA 값**
- 각 빌드의 **다이 온도**
- Mode 1 유효탭 수 / Mode 0 도달 최대 탭
- 채택한 **`VALID_TAP_HI`** 와 그때의 경계 점프·INL rms
- 합성 결과 **WNS / WHS**
- **J18 점퍼를 실제로 2.5V 로 했는지 여부**

---

## 부록 — 파일 위치 요약

```
RTL/
 ├ tdc_zedboard_top.v      ★ ZedBoard 최상위 (Set as Top)
 ├ tdc_zedboard.xdc        ★ ZedBoard 제약
 ├ tdc_test_top.v            코어 (건드리지 말 것)
 ├ tdc_fmcw_core_co.v
 ├ tdc_timestamp_calc.v
 ├ tdc_histogram.v
 ├ phase_shifter.v
 ├ dna_reader.v
 └ tdc.xdc                  Zybo 전용 (ZedBoard 프로젝트에 넣지 말 것)

python/
 ├ Histogram.py             DATA_SUBDIR / INPUT_CSV 수정 후 사용
 ├ Making_COE_Mode_0.py     ★ VALID_TAP_HI 매크로 (59~60행)
 ├ Making_COE_linear.py
 └ DNL_INL_codedensity.py

Markdown/
 ├ 2026-08-24_report.md         유효탭 문제의 원인 분석 (읽어볼 것)
 └ calcaulation_method.md       INL 계산 수식 상세
```
