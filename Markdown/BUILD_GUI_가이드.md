# ZedBoard TDC — GUI 만으로 처음부터 끝까지 빌드하기

> **작성일** 2026-09-06
> **작성** Claude Opus 5 (Claude Code)
> **용도** 회사 PC 에서 Claude 없이 혼자 빌드·테스트하기 위한 절차서.
> **검증** 2026-09-06, 이 절차대로 빌드해 **UART 키 입력까지 동작하는 것을 사용자가 확인**했다.
> **관련** 더 넓은 배경·문제해결은 `Markdown/HANDOVER_회사에서_혼자_하기.md` 참조.

---

## 0. 30초 요약

Vivado GUI 버튼과 Vitis GUI 버튼으로 전부 됩니다. **Tcl Console 을 쓰는 곳은 딱 두 군데**입니다.

| # | 단계 | 방식 | 대략 시간 |
|---|---|---|---|
| 1 | 프로젝트 생성 | **Tcl 3줄** | 2~3분 |
| 2 | 합성 | GUI 버튼 | 5~10분 |
| 3 | 합성 검증 | **Tcl 3줄** | 즉시 |
| 4 | 구현 전략 설정 ★ | GUI 메뉴 | 즉시 |
| 5 | 비트스트림 | GUI 버튼 | 15~25분 |
| 6 | 타이밍 확인 | GUI 표 | 즉시 |
| 7 | XSA 내보내기 | GUI 메뉴 | 1분 |
| 8 | **MIO 전압 확인 ★★** | cmd 한 줄 | 즉시 |
| 9 | Vitis 플랫폼+앱 | GUI | 10분 |
| 10 | 실행·확인 | GUI | — |

**절대 빼먹으면 안 되는 3개**: 4단계(구현 전략), 8단계(MIO 전압 확인), 10단계의 `d` 키(danger 임계값).

---

## 1. 준비물

| 항목 | 값 |
|---|---|
| Vivado | 2024.1 (`C:\Xilinx\Vivado\2024.1`) |
| Vitis | 2024.1 Unified IDE |
| 저장소 | `C:\Work\FPGA\Project\Source\TDC` |
| 보드 | ZedBoard (XC7Z020-CLG484-1), USB-JTAG + USB-UART 연결 |
| 신호원 | STM32 를 PMOD JA1(Y11) 에 점퍼로 연결 (Mode 2 용). **GND 도 반드시 연결** |

### 미리 확인해 둘 것

`python\tdc_calib_mode0_rom.coe` 가 있어야 빌드가 시작됩니다.

- 있어야 할 모습: **386줄** (헤더 2줄 + 데이터 384줄), 첫 데이터 `0,` 마지막 `4987;`
- 이건 **교정 안 된 선형 램프**입니다 (5000 ps ÷ 384탭 ≈ 13.02 ps 간격)
- 없으면: `cd python` → `python Making_COE_linear.py` (스크립트 안의 탭 수가 384 인지 확인)

> **알아 둘 것** — 지금까지 FPGA 에 들어간 교정 ROM 은 **한 번도 코드밀도 교정표였던 적이 없습니다.** 항상 이 선형 램프였습니다. 교정표를 실제로 넣는 것은 다음 과제(교정표 BRAM 화)입니다.

---

## 2. Vivado 프로젝트 생성 (Tcl 3줄)

1. Vivado 2024.1 실행 → **아무 프로젝트도 열지 않은 시작 화면** 상태로 둡니다
   (다른 프로젝트가 열려 있으면 `create_project` 가 꼬일 수 있습니다)
2. 창 **맨 아래 `Tcl Console` 탭** 클릭
3. 아래 3줄을 붙여넣고 Enter:

```tcl
cd C:/Work/FPGA/Project/Source/TDC
set argv {2 zed_uart 0 1}
source build_zedboard.tcl
```

> **경로는 반드시 슬래시(`/`)** 로 씁니다. Tcl 에서 역슬래시는 이스케이프 문자라
> `C:\Work\...` 로 쓰면 조용히 깨집니다.

### 인자 4개의 뜻

| 순서 | 값 | 뜻 |
|---|---|---|
| 1 | `2` | `OPERATION_MODE`. **0 만 아니면 결과가 같습니다** (§12-1 참조) |
| 2 | `zed_uart` | 프로젝트 폴더 = `vivado\zed_uart`. **이미 있으면 에러**가 나니 다른 이름을 주십시오 |
| 3 | `0` | **합성 안 함** (직접 GUI 로 하려고) |
| 4 | `1` | `HIT_INPUT` = **PMOD 단선 Y11**. `0` 이면 FMC LVDS(E21/D21) |

### 이 단계가 만드는 것

- Verilog 소스 10개 + XDC 1개를 **참조로** 추가 (복사 아님 → 저장소를 고치면 바로 반영)
- 블록디자인 `ps_sys` (PS7 + proc_sys_reset + AXI 인터커넥트)
- IP 3개: `clk_wiz_0` / `tdc_calib_rom` / `xadc_wiz_0` + 출력물 생성

끝나면 프로젝트가 GUI 에 열리고 왼쪽에 **Flow Navigator** 가 보입니다.

> **왜 이것만 GUI 로 안 하나**: IP 를 손으로 만들면 실수가 납니다. 특히 `clk_wiz_0` 의
> VCO 가 1000 MHz 가 아니면 Mode 0 의 참 시간축(1000/56 = 17.857 ps)이 통째로 틀어지고,
> `tdc_calib_rom` 의 latency 가 2 가 아니면 타임스탬프 파이프라인 정렬이 깨집니다.

---

## 3. 합성

**Flow Navigator → SYNTHESIS → Run Synthesis**
→ 대화상자에서 **Number of jobs: 8** → **OK**

끝나면 뜨는 대화상자에서 **"Open Synthesized Design"** 을 선택하고 **OK**.

---

## 4. 합성 결과 검증 (Tcl 3줄)

합성된 디자인이 열린 상태에서 **Tcl Console** 에:

```tcl
puts "CARRY4 = [llength [get_cells -hier -filter {NAME =~ *CARRY_CHAIN*u_carry4*}]]"
puts "taps   = [llength [get_cells -hier -filter {NAME =~ *taps_sampled_d1_reg*}]]"
puts "fanout = [get_property FLAT_PIN_COUNT [lindex [get_nets -hier -filter {NAME =~ *tdc_hit_in*}] 0]]"
```

| 출력 | 기대값 | 어긋나면 무슨 뜻인가 |
|---|---|---|
| `CARRY4` | **96** | XDC 의 LOC 제약이 안 먹어 지연선이 짧게 잡혔다 |
| `taps` | **384** | 탭 샘플링 레지스터가 일부 최적화로 날아갔다 |
| `fanout` | **1** | 히트 배선에 다른 부하가 붙었다 → 에지 slew 악화 → 진입 트랜지언트 커짐 |

`fanout` 이 중요한 이유: 예전에 `led[2]` 를 히트 네트에 물렸다가 `CYINIT` 에 부하가 붙어
**초입 3탭이 정상값의 1.16~1.89배**가 된 적이 있습니다. 히트는 `CYINIT` 하나만 구동해야 합니다.

> **필터 주의**: 첫 줄에서 `*CARRY_CHAIN*` 을 빼고 `*u_carry4*` 만 쓰면 안 됩니다.
> 예전에 ILA IP 내부의 `u_carry4_inst` 91개가 같이 잡혀 203 이 나온 적이 있습니다.
> (`build_zedboard.tcl:251-253` 주석. 지금은 ILA 를 뺐지만 안전한 쪽을 쓰십시오.)
>
> **`report_utilization` 의 Primitives 표로 판단하지 마십시오.** 거긴 다른 로직
> (`tdc_seq` 의 카운터, 타임스탬프 계산 등)의 CARRY4 까지 합산되어 96 이 안 나옵니다.

3개 중 하나라도 어긋나면 **여기서 멈추십시오.**

---

## 5. ★ 구현 전략 설정 — 구현 돌리기 **전에** 반드시

**Flow Navigator → Settings**
→ 왼쪽 트리에서 **Implementation**
→ **Strategy** 드롭다운 → **`Performance_ExplorePostRoutePhysOpt`** 선택
→ **Apply** → **OK**

**확인**: 왼쪽 아래 **Design Runs** 탭에서 `impl_1` 행의 **Strategy** 열을 눈으로 보십시오.

### 왜 반드시 해야 하나 (실측 근거)

2026-09-05, `zed_axi` 빌드 기준:

| 전략 | WNS | WHS | 결과 |
|---|---|---|---|
| 기본값 | — | **−0.045 ns** | **hold 위반** |
| `Performance_ExplorePostRoutePhysOpt` | +0.089 ns | +0.034 ns | 통과 |

- 위반 경로: `captured_c0_stg2 → stg3`, 같은 `clk_200_fixed` 도메인
- **원인은 지연이 아니라 스큐**입니다. 384탭 때문에 캐리체인 pblock 을 `Y140` 까지 넓히면서
  체인 양끝의 클럭 도착 시각 차이(**스큐 0.298 ns**)가 데이터 지연(**0.266 ns**)을 넘었습니다
- 이 전략은 라우팅 **후에** `post_route_phys_opt_design` 단계를 켜서, 실제 배선 지연을 보고
  레지스터를 재배치·복제해 스큐를 줄입니다. 배치 단계의 추정치만 보는 기본 전략은 못 잡습니다
- 대가: 구현 시간이 늘어납니다(단계가 하나 더 붙음)

근거는 `build_zedboard.tcl:266-275` 주석에 기록돼 있습니다.

> **★ setup 과 hold 는 처방이 정반대입니다.**
> WNS(setup) 음수 → 파이프라인 단 추가로 해결.
> WHS(hold) 음수 → **파이프라인을 넣으면 오히려 나빠집니다** (경로가 더 짧아지므로).
> hold 는 스큐 문제이니 위 전략이 실제로 걸렸는지부터 확인하십시오.

---

## 6. 비트스트림 생성

**Flow Navigator → PROGRAM AND DEBUG → Generate Bitstream**
→ "구현이 아직 안 됐다, 먼저 돌릴까?" 물으면 **Yes**
→ Number of jobs: 8 → **OK**

### 중간에 지나갈 메시지 — 무시하십시오

```
CRITICAL WARNING: [Vivado 12-2285] Cannot set LOC property ...
```

XDC 에 남아 있는 옛 Zybo용 절대경로 제약(`{u_tdc/...}`) 때문입니다.
**비트스트림 생성을 막지 않습니다** — 지난 빌드들에서도 이게 뜬 채 정상 완료됐습니다.

만들어지는 파일:
`vivado\zed_uart\zed_uart.runs\impl_1\tdc_zedboard_top.bit`

---

## 7. 타이밍 확인

왼쪽 아래 **Design Runs** 탭에서 `impl_1` 행의 **WNS** 와 **WHS** 열을 봅니다.

**둘 다 양수**여야 합니다. 이전 실적: **WNS +0.209 ns**.

| 결과 | 뜻 | 처방 |
|---|---|---|
| WNS < 0 | setup — 경로가 5 ns 안에 못 들어옴 | popcount 트리에 파이프라인 단 추가 |
| WHS < 0 | hold — 스큐 문제 | **5단계 전략이 실제로 걸렸는지부터 확인** |

열이 안 보이면 표 헤더를 우클릭해 표시할 열을 고를 수 있습니다.
자세히 보려면 **Open Implemented Design → Reports → Timing → Report Timing Summary**.

---

## 8. XSA 내보내기

1. **File → Export → Export Hardware...**
2. 마법사에서:
   - Output: **Include bitstream** 선택 ★ (빼면 Vitis 가 FPGA 를 못 굽습니다)
   - Files: 이름 `tdc_zedboard_top`, 위치는 기본값(프로젝트 폴더)
3. **Finish**

만들어지는 파일:
`C:\Work\FPGA\Project\Source\TDC\vivado\zed_uart\tdc_zedboard_top.xsa`

---

## 9. ★★ Vitis 로 가기 전 필수 확인 — MIO 전압

**이걸 확인하지 않고 Vitis 를 만들면, 아무리 잘 만들어도 UART 키 입력이 안 먹습니다.**

시작 → `cmd` 실행 → 붙여넣기:

```
findstr /S /C:"0XF80007C0" C:\Work\FPGA\Project\Source\TDC\vivado\zed_uart\*.tcl
```

### 판정

| 나온 값 | 판정 |
|---|---|
| **`0x000012E0`** | **정상.** 다음 단계로 |
| `0x000016E0` | **여기서 멈출 것.** 뱅크 전압 수정이 안 들어갔다 |

### 무슨 뜻인가

- `0xF80007C0` = Zynq 의 **MIO 48번 핀**(UART1 TX) 설정 레지스터 (`0x...7C4` 는 MIO 49 = RX)
- 그 값의 **비트[11:9] 가 IO_Type**
- `(0x12E0 >> 9) & 7 = 1` → **LVCMOS18**, 입력 문턱 약 **1.17 V** ✔
- `(0x16E0 >> 9) & 7 = 3` → LVCMOS33, 입력 문턱 약 **2.0 V** ✘

### 2026-09-06 에 겪은 증상과 원인 (반드시 읽을 것)

**증상**: 보드가 배너를 UART 로 잘 뿌린다(TX 정상). 그런데 터미널에서 **키를 눌러도 아무 반응이
없다**(RX 완전 불통). Vitis Serial Terminal 을 PuTTY 로 바꿔도 동일. JTAG 로 UART1 상태
레지스터(`0xE000102C`)를 20초간 직접 폴링해도 RX FIFO 에 **단 한 바이트도** 안 들어온다.
즉 소프트웨어가 아니라 **전기적 문제**다.

**원인**: ZedBoard 매뉴얼(`Parts/ZedBoard_HW_UG_v2_2.pdf`) **Table 21** —
`MIO Bank 0/500 = 3.3V`, **`MIO Bank 1/501 = 1.8V`**.
UART1 은 MIO[48:49] 로 **Bank 1/501(1.8V)** 에 있다. 그런데 PS7 IP 의 **기본값은 두 뱅크
모두 3.3V** 라, 이 설정을 안 하면 MIO48/49 가 LVCMOS33 으로 잡힌다.

**왜 TX 만 살아남았나**: 레벨 시프터(TXS0102)는 비대칭이다. **출력 스윙은 실제 VCCO(1.8V)가
정하고**, **입력 문턱은 IO_Type 설정(LVCMOS33 → 2.0V)이 정한다.** 그래서 보드가 내보내는
쪽(TX)은 멀쩡히 나가고, 받는 쪽(RX)만 1.8V 신호가 2.0V 문턱을 못 넘어 죽는다.

**수정**: `tcl/bd_ps_sys.tcl` 에 아래 두 줄 (커밋 `f3efb3c`).

```tcl
CONFIG.PCW_PRESET_BANK0_VOLTAGE  {LVCMOS 3.3V} \
CONFIG.PCW_PRESET_BANK1_VOLTAGE  {LVCMOS 1.8V} \
```

**정석 해법**: Digilent 보드 파일을 설치해 ZedBoard 프리셋을 적용하면 이런 수동 설정이
전부 필요 없어집니다. 나중에 하실 일입니다.

---

## 10. Vitis (전부 GUI)

### 10-1. 플랫폼 만들기

1. **Vitis Unified IDE** 실행 → 워크스페이스 폴더 지정 (예: `C:\Work\FPGA\vitis_ws`)
2. Welcome 화면 → **Create Platform Component**
3. 마법사:
   - Name: `tdc_plat`
   - **Hardware Design**: **Browse** → 8단계의 `tdc_zedboard_top.xsa`
   - Operating System: **standalone** / Processor: **ps7_cortexa9_0**
4. **Finish**

### 10-2. ★ stdin / stdout 을 `ps7_uart_1` 로

1. 왼쪽 **Vitis Components** 에서 `tdc_plat` 펼치기
2. **`vitis-comp.json`** 더블클릭 → **Board Support Package** 페이지
3. `standalone` 항목에서 **`stdin`** 과 **`stdout`** 을 **둘 다 `ps7_uart_1`** 로
4. 저장

> ZedBoard 의 USB-UART 는 MIO 48/49 = **UART1** 입니다. `ps7_uart_0` 이면 아무것도 안 나옵니다.
> **`stdout` 만 맞고 `stdin` 이 틀리면 "글자는 나오는데 키가 안 먹는" 증상**이 나는데,
> 9단계의 MIO 전압 문제와 증상이 똑같으니 둘 다 확인하십시오.

### 10-3. 플랫폼 빌드

`tdc_plat` 우클릭 → **Build**

### 10-4. 앱 만들기

1. **File → New Component → Application** (또는 Welcome 의 **Create Application Component**)
2. Name: `tdc_app`
3. Platform: **`tdc_plat`**
4. Domain: `standalone_ps7_cortexa9_0`
5. Template: **Empty Application (C)**
6. **Finish**

### 10-5. 소스 넣기

`tdc_app` → **`src`** 폴더 우클릭 → **Import → Files...**
→ `C:\Work\FPGA\Project\Source\TDC\vitis\tdc_app.c` 선택

### 10-6. ★ 링커 스크립트를 OCM 으로

1. `tdc_app` → `src` → **`lscript.ld`** 더블클릭 (Linker Script 편집기가 열립니다)
2. **모든 섹션**(`.text`, `.data`, `.bss`, `.heap`, `.stack` …)의 메모리 드롭다운을
   **`ps7_ram_0`** 으로 변경
3. 저장

**왜 DDR 이 아니라 OCM 인가**: 이 블록디자인에 ZedBoard 의 DDR3(MT41K128M16) 파라미터를
넣지 않았습니다. 보드 파일 없이 `DQS_TO_CLK_DELAY` / `BOARD_DELAY` 를 손으로 넣으면 틀리기
쉽고, **틀리면 조용히 동작하다 가끔 깨집니다.** OCM(`ps7_ram_0`)은 256 KB 이고 이 프로그램은
전역 배열이 40 KB 남짓(`g_histo` 384×4 + `g_cap_lo/hi` 4096×4×2 ≈ 34 KB)이라 충분합니다.

### 10-7. 앱 빌드

`tdc_app` 우클릭 → **Build**

### 10-8. 터미널 먼저 열기 ★ 순서 중요

**보드에 굽기 전에** 터미널을 붙여야 배너를 놓치지 않습니다.

1. 아래쪽 **Vitis Serial Terminal** 패널 → **`+`** 버튼
2. Port: ZedBoard 의 COM 포트
3. **Baud 115200 / Data 8 / Parity None / Stop 1**

### 10-9. 실행

`tdc_app` 우클릭 → **Run → Run on Hardware**

Run Configuration 에 **"Program FPGA"** 가 체크돼 있는지 확인하십시오
(8단계에서 bitstream 을 포함시켰으므로 XSA 안에 들어 있습니다).

---

## 11. 확인 — 무엇을 어떤 순서로

### (1) 먼저 이것부터

배너가 뜬 뒤 **`h` 를 눌러 메뉴가 다시 뜨는지** 봅니다.
배너(TX)는 문제가 있어도 나오므로, **키 입력(RX)이 먹는지가 유일한 판정 기준**입니다.

### (2) 키가 먹으면 바로 이어서

| 순서 | 키 | 하는 일 |
|---|---|---|
| 1 | **`i`** | 신원/상태. `ID = 0x54444302`, `MMCM=1` 확인 |
| 2 | **`1`** | Mode 1 코드밀도 측정 (200만 발, 약 2초) → 384탭 CSV |
| 3 | **`d`** | 히스토그램에서 danger 임계값 계산 → 설정 |

### (3) ★★ `d` 를 절대 빼먹지 마십시오

**빌드할 때마다 해야 합니다.**

히트가 찍히는 탭 범위(측정 창)는 히트 경로의 배선 지연에 따라 **통째로 미끄러집니다.**
2026-09-05 에 HIT_SRC 먹스(LUT 하나)가 들어가자 창이 **탭 2~321 에서 24~348 로** 옮겨갔고,
같은 RTL 을 재빌드해도 `349 → 348` 로 1탭 달라졌습니다.

`danger` 임계값은 그 창의 양 끝에 있어야 합니다. 안 맞으면 **coarse 가 5000 ps 틀리는 일이
생기는데, 히스토그램으로는 전혀 보이지 않습니다.**

`d` 가 하는 계산 (`vitis/tdc_app.c` 의 `cmd_set_danger`):
- 각 탭의 폭 `w[i] = h[i] / H × 5000 ps` (`H` = 히트 있는 구간의 총합)
- 창의 **아래 끝에서부터 누적 폭이 630 ps** 를 넘는 탭 → `lo`
- 창의 **위 끝에서부터 누적 폭이 630 ps** 를 넘는 탭 → `hi`

> **630 ps 의 출처**: 2026-09-05 에 쓰던 상수 `40` 이 만들던 아래쪽 가드 폭입니다.
> "예전과 같은 여유를 창이 어디로 가든 유지한다"는 뜻이지, **630 ps 가 옳다는 뜻은
> 아닙니다.** coarse 카운터의 실제 불안정 구간은 아직 측정된 적이 없습니다. (미해결 과제)

### (4) 그다음 — Mode 2

| 키 | 하는 일 |
|---|---|
| **`2`** | Mode 2 캡처, `timestamp_ps` 형식, 1024발 |
| **`r`** | Mode 2 캡처, raw `{coarse, fine}` 형식, **4096발** |

CSV 는 `----- 여기부터 CSV -----` 와 `----- CSV 끝 -----` 사이에 나옵니다.
그 부분만 복사해 파일로 저장하면 `python/` 스크립트에 그대로 들어갑니다.

---

## 12. 알아 두면 헷갈리지 않는 것

### 12-1. `OPERATION_MODE` 는 0 만 아니면 다 같습니다

RTL 전체에서 `OPERATION_MODE` 를 실제로 쓰는 곳은 **두 군데뿐**이고, **둘 다 `== 0` 인지만**
봅니다 (`RTL/tdc_test_top.v:340`, `:444`).

```verilog
if (OPERATION_MODE == 0) begin : MODE_0_MMCM_SWEEP
    assign tdc_hit_in = test_hit_sync;
    assign tdc_clk    = clk_200_shifted;     // ← 샘플링 클럭이 다르다
end
else begin : MODE_RUNTIME_MUX
    assign tdc_hit_in = (i_ctrl_hit_src == 2'b01) ? hit_random :   // Mode 1
                        (i_ctrl_hit_src == 2'b11) ? ext_hit_in :   // Mode 2
                                                    1'b0;
    assign tdc_clk    = clk_200_fixed;
end
```

즉 **`1` 로 빌드하든 `2` 로 빌드하든 하드웨어가 완전히 동일**합니다.
Mode 1 ↔ Mode 2 전환은 AXI 레지스터 `CTRL[1:0]`(주소 `0x43C0_0008`)로 **런타임에** 됩니다.
`tdc_app.c` 의 `1` / `2` 키가 그걸 합니다.

### 12-2. 무엇이 재빌드를 필요로 하는가

| 바꾸려는 것 | 재빌드? | 방법 |
|---|---|---|
| Mode 1 ↔ Mode 2 | **불필요** | `tdc_app.c` 의 `1` / `2` 키 |
| Mode 0 (DPS 위상 스윕) | **필요** | `OPERATION_MODE=0` 으로 빌드 |
| PMOD ↔ FMC LVDS | **필요** | `HIT_INPUT` 을 `1` ↔ `0` |
| danger 임계값 | 불필요 | `d` 키 |
| 교정 ROM 내용 | **필요** | COE 를 바꿔 재빌드 (BRAM 화하면 불필요해짐 — 다음 과제) |

**Mode 0 만 별도 빌드인 이유**: 지연선의 **샘플링 클럭 자체**가 `clk_200_shifted` 로 바뀝니다.
런타임에 고르려면 샘플링 클럭에 `BUFGMUX` 를 달아야 하는데 그러면 탭 폭이 흔들릴 위험이
있습니다 (`RTL/tdc_test_top.v:328-331` 주석).

### 12-3. 레지스터 맵 요약 (버전 6, 베이스 `0x43C0_0000`)

| 오프셋 | 이름 | R/W | 내용 |
|---|---|---|---|
| `0x00` | ID | R | `0x54444302` |
| `0x04` | BUILD | R | `{탭수16, 단수8, 맵버전8}` |
| `0x08` | **CTRL** | RW | `[1:0]` HIT_SRC (00=off 01=RO 10=DPS 11=EXT), `[2]` START, `[3]` STOP, `[4]` HISTO_CLR, `[5]` TDC_RST(**미연결**), `[6]` CAP_FMT |
| `0x0C` | STATUS | R | `[0]` MMCM lock, `[2]` DNA valid, `[3]` BUSY, `[4]` DONE, `[5]` PHASE_BUSY, `[10:8]` FSM 상태 |
| `0x14` | RO_CNT | R | 10 ms 게이트당 RO 에지 수 |
| `0x44` | DANGER | RW | `{hi[24:16], lo[8:0]}` |
| `0x1000+` | HISTO | R | 탭 `i` 의 카운트 (`i` = 0..383) |
| `0x8000+` | CAPTURE | R | 캡처 버퍼 (8바이트 stride, lo/hi) |

전체 맵은 `RTL/tdc_axi_regs.v` 상단 주석과 `vitis/tdc_app.c` 의 `#define` 를 보십시오.

**RO 주파수 환산**: `f_RO [kHz] = RO_CNT × 4 / 10`
(`ro_divider_cnt` 는 RO 상승엣지마다 +1, 측정 탭이 `[1]` 이라 4번 증가마다 한 주기 →
RO 4주기당 1카운트. 게이트 10 ms.) 실측 약 **55.5 MHz**.

> 이 식이 코드에 없어서 2026-09-04 문서가 **2배 틀린 값(111.0 MHz)** 을 실은 적이 있습니다.

---

## 13. 문제 해결 — 실제로 겪은 것만

| 증상 | 원인 / 조치 |
|---|---|
| `COE 가 없다` 로 2단계가 멈춘다 | `python/*.coe` 는 `.gitignore` 대상. §1 참조 |
| `이미 있다: .../vivado/zed_uart` | 폴더가 이미 있음. 지우거나 2번째 인자로 다른 이름을 |
| 합성 실패 | `vivado\zed_uart\zed_uart.runs\synth_1\runme.log` 확인 |
| `CRITICAL WARNING [Vivado 12-2285]` | **무시.** 옛 Zybo용 XDC 잔재. 빌드를 막지 않음 |
| WHS 음수 | 5단계 전략이 안 걸렸다. **파이프라인 추가는 역효과** |
| 배너는 나오는데 키가 안 먹는다 | ① §9 의 MIO 전압(`0x12E0`) ② §10-2 의 `stdin` |
| Vitis 앱이 뜨자마자 죽는다 | §10-6 의 링커 스크립트가 `ps7_ram_0` 인지 |
| 레지스터가 전부 `0xDEAD_0000` | AXI 주소 디코딩 밖을 읽고 있다. 베이스 주소 확인 |
| Mode 2 에서 히트가 한 발도 안 들어온다 | ① 신호원이 실제로 내보내는가(스코프) ② **GND 연결** ③ `HIT_INPUT` 이 1(PMOD)인가 |
| 히스토그램이 텅 비었다 | `1` 키 없이 `d` 를 눌렀다. `1` → `d` 순서 |

---

## 14. 지금 상태와 다음 할 일

### 되는 것 / 안 되는 것

| 항목 | 상태 |
|---|---|
| Mode 1 (링오실레이터 코드밀도) | **완성.** `HIT_CNT` = 384탭 합, 차이 0 확인 |
| Mode 2 (외부 입력) | **신호 수신까지 확인.** STM32 chirp 를 참값과 대조 통과 |
| Mode 0 (DPS 위상 스윕) | **미구현** |
| 교정표 | **선형 램프만 들어가 있음.** 코드밀도 LUT 은 한 번도 FPGA 에 안 들어감 |
| `CTRL[5]` TDC_RST | 맵에는 있으나 **하드웨어 미연결** |
| TDC 자체 정밀도 | **한 번도 측정된 적 없음** |

### 우선순위

1. **교정표를 쓰기 가능한 BRAM 으로** — 지금 ROM 은 선형 램프이고, 이것 때문에 정확도를
   25% 손해 보고 있습니다 (552 → 415 ps). PS 가 런타임에 교정표를 쓸 수 있게 되면
   재빌드 없이 교정 실험을 반복할 수 있습니다.
2. **TDC 자체 정밀도 측정** — Mode 0("클럭 대신 히트를 흔드는" 재설계) 필요.
   현재 415 ps 오차는 **TDC 가 아니라 신호원(STM32) 쪽**으로 좁혀졌습니다.
   근거: HSE 로 클럭 정확도를 5배 올려도 안 줄었고, 코드밀도 교정을 적용해도 안 줄었으며,
   10 kHz 에서 `dcoarse`(순수 클럭 카운트, 지연선 무관)가 **140 ns** 폭으로 퍼졌습니다
   (fine 이 보정할 수 있는 범위는 최대 5000 ps).
3. **Mode 2 핑퐁 더블버퍼** — 학습 알고리즘이 정해진 뒤.

---

## 15. 관련 파일

| 파일 | 내용 |
|---|---|
| `Markdown/HANDOVER_회사에서_혼자_하기.md` | 더 넓은 배경, 배치 파일 방식, XSCT 로 빠르게 확인하기 |
| `build_zedboard.tcl` | 프로젝트 생성 스크립트 (인자 처리는 파일 상단 주석) |
| `tcl/bd_ps_sys.tcl` | 블록디자인. **MIO 뱅크 전압 함정이 여기 기록돼 있음** |
| `vitis/tdc_app.c` | PS 제어 프로그램. 레지스터 맵 `#define` 전체 |
| `RTL/tdc_axi_regs.v` | AXI 슬레이브. 레지스터 맵 원본 |
| `Parts/ZedBoard_HW_UG_v2_2.pdf` | §2.3.2 (UART), **Table 21 (뱅크 전압)** |
| `run_build.bat` | 배치 파일 방식(GUI 없이). 이 문서의 대안 |
