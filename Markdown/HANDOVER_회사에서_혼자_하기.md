# 회사에서 혼자 빌드하고 테스트하기

> **작성일** 2026-09-06
> **작성** Claude Opus 5 (Claude Code)
> **주의** AI가 생성한 문서입니다. 수치는 사용 전 원본 로그·CSV와 대조하십시오.
>
> 이 문서만 보고 **Vivado 빌드 → Vitis 테스트**를 처음부터 끝까지 할 수 있도록 썼습니다.
> 막히는 곳은 §6 문제 해결을 먼저 보십시오. 오늘까지 실제로 겪은 함정만 모았습니다.

---

## 0. 30초 요약 — 배치 파일을 더블클릭하면 됩니다

저장소 폴더에 배치 파일 세 개가 있습니다. **탐색기에서 더블클릭**하거나,
그 폴더에서 **명령 프롬프트(cmd)** 를 열어 이름만 치면 됩니다.

| 파일 | 하는 일 | 걸리는 시간 |
|---|---|---|
| **`run_build.bat`** | 프로젝트 생성 + 합성 + 비트스트림 | 20~30분 |
| **`run_check.bat`** | 보드에 굽고 레지스터·Mode1 확인 + **danger 자동설정** | 1~2분 |
| **`run_capture.bat`** | Mode 2 raw 캡처 | 30초 |

```
run_build.bat
run_check.bat
```

인자를 주고 싶으면 뒤에 붙입니다:

```
run_build.bat 2 zed_fmc 1 0      FMC LVDS 로 빌드
run_check.bat 1                  Mode 2 까지 확인
run_capture.bat 4096             4096발 raw 캡처
```

> **명령 프롬프트(cmd)** 에서 여십시오. PowerShell 이면 앞에 `.\` 를 붙여야 합니다
> (`.\run_build.bat`).
>
> 배치 파일 안은 **전부 영어**입니다. `.bat` 에 한글을 넣으면 cmd 가 코드페이지 때문에
> 파싱을 깨뜨려 실행이 안 됩니다 (실제로 겪었습니다). 설명은 이 문서에 있습니다.

저장소를 처음 받는다면:

```
git clone https://github.com/mainre905/TDC.git
```

Vitis 로 하려면 §4 로 가십시오.

---

## 1. 준비물

| | |
|---|---|
| Vivado / Vitis | **2024.1** (다른 버전이면 IP 프로퍼티 이름이 달라 스크립트가 실패할 수 있음) |
| 보드 | ZedBoard, USB-JTAG + USB-UART 두 개 다 연결 |
| 저장소 | `github.com/mainre905/TDC` |
| COE 파일 | `python/tdc_calib_mode0_rom.coe` — **저장소에 없으면 빌드가 멈춥니다** (§6-1) |

**Vivado 프로젝트 파일(`.xpr`)은 저장소에 없습니다.** 소스만 있고 프로젝트는 스크립트가 매번 새로 만듭니다. 그게 집/회사 어디서 만들어도 같은 결과가 나오게 하는 방법입니다.

---

## 2. Vivado 빌드

### 2-1. 배치 파일로

```
run_build.bat <모드> <폴더이름> <빌드?> <히트입력>
```

인자는 전부 생략할 수 있고, 생략하면 `2 zed_pmod 1 1` 입니다.

<details><summary>배치 파일 없이 직접 치려면 — 반드시 한 줄로</summary>

명령 프롬프트에서 **줄바꿈 없이**:

```
"C:\Xilinx\Vivado\2024.1\bin\vivado.bat" -mode batch -source build_zedboard.tcl -tclargs 2 zed_pmod 1 1
```

이전 문서에 있던 줄 끝 `\` 이어쓰기는 Git Bash 문법이라 cmd/PowerShell 에서는 안 됩니다.
</details>

| 인자 | 뜻 | 값 |
|---|---|---|
| 1 | `OPERATION_MODE` | `0`=DPS(미구현) `1`=링오실레이터 `2`=외부입력 |
| 2 | 프로젝트 폴더 이름 | `vivado/<이름>` 에 만들어짐 |
| 3 | 빌드까지 할지 | `1`=합성~비트스트림, `0`=프로젝트만 |
| 4 | **히트 입력** | **`1`=PMOD 단선 Y11, `0`=FMC LVDS E21/D21** |

**모드 1과 2는 한 비트스트림에서 실행 중에 고를 수 있습니다.** `OPERATION_MODE`는 사실상 `0`이냐 아니냐만 의미가 있습니다. 지금은 `2`로 빌드하면 됩니다.

### 2-2. 자주 쓸 조합

```bash
# STM32 를 PMOD 에 물려 쓰는 지금 구성
... -tclargs 2 zed_pmod 1 1

# 고속 비교기가 돌아왔을 때 (FMC LVDS)
... -tclargs 2 zed_fmc  1 0
```

**되돌리는 데 RTL 수정이 필요 없습니다.** 마지막 인자만 바꾸면 됩니다.

### 2-3. GUI 로 하고 싶다면

```tcl
# Vivado GUI 의 Tcl Console 에서
cd C:/Work/FPGA/Project/Source/TDC
set argv [list 2 zed_pmod 0 1]     ;# 0 = 프로젝트만 만들고 멈춤
source build_zedboard.tcl
```

프로젝트가 열리면 평소처럼 Run Synthesis / Run Implementation 을 누르면 됩니다.
**단 §2-4 를 반드시 먼저 하십시오.**

### 2-4. ★ 구현 전략을 반드시 바꿀 것

**기본 전략으로는 타이밍이 깨집니다.** 배치 모드로 돌리면 스크립트가 알아서 넣지만,
GUI 에서 직접 돌릴 때는 손으로 지정해야 합니다.

```tcl
set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
```

또는 GUI 에서 **Implementation → Strategy → `Performance_ExplorePostRoutePhysOpt`**

> **왜** : PS7+AXI 가 들어온 뒤 기본 전략은 hold 가 깨진다 (WHS −0.045 ns).
> 원인은 지연이 아니라 스큐다 — 384탭 때문에 캐리체인 pblock 을 `SLICE_X42Y0`~`Y140`
> 까지 세로로 늘리면서 클럭 스큐(0.298 ns)가 데이터 지연(0.266 ns)을 넘어섰다.
> 이 전략은 route 뒤에 `post_route_phys_opt_design` 을 켜서 실제 배선 지연을 보고
> 레지스터를 재배치·복제해 스큐를 줄인다.

### 2-5. 빌드가 끝나면 확인할 것

```
WNS / WHS 가 둘 다 양수인가        (스크립트가 마지막에 찍는다)
비트스트림이 나왔는가              vivado/<이름>/<이름>.runs/impl_1/tdc_zedboard_top.bit
```

**참고값** (2026-09-06 기준): WNS +0.109 / WHS +0.035 ns, BRAM 7.5/140, LUT 약 1500.

---

## 3. XSCT 로 빠르게 확인하기 (Vitis 없이)

가장 빠른 검증입니다. **C 프로그램을 만들 필요가 없습니다** — XSCT 가 JTAG 로 ARM 코어에
붙어 메모리를 직접 읽고 씁니다.

```
run_check.bat              레지스터 + Mode 1 + danger 자동설정 (Mode 2 건너뜀)
run_check.bat 1            Mode 2 까지 (신호가 들어오고 있을 때)
run_capture.bat 4096       raw {coarse, fine} 캡처 4096 발
```

결과는 화면과 **파일 양쪽**에 남습니다:

| 파일 | 내용 |
|---|---|
| `vivado/mode2_check.log` | 검사 결과 전문 |
| `vivado/histo_mux.csv` | Mode 1 히스토그램 384탭 |
| `vivado/capture_raw.csv` | Mode 2 raw 캡처 |
| `vivado/capture.csv` | Mode 2 timestamp_ps 캡처 |

분석:

```
python python/analyze_chirp_capture.py
```

---

## 4. Vitis 로 하기

### 4-1. XSA 내보내기

빌드가 끝난 Vivado 프로젝트에서:

```tcl
open_project vivado/zed_pmod/zed_pmod.xpr
write_hw_platform -fixed -include_bit -force -file C:/Work/FPGA/tdc.xsa
```

또는 GUI 에서 **File → Export → Export Hardware → Include bitstream**.

### 4-2. Vitis 프로젝트 만들기

1. Vitis 실행 → **Create Platform Component** → 위에서 만든 `tdc.xsa` 선택
2. **Create Application Component** → 그 플랫폼 위에 → **Empty Application (C)**
3. 저장소의 **`vitis/tdc_app.c`** 를 `src/` 에 복사
4. 빌드 → Run

### 4-3. ★ 반드시 확인할 두 가지

**(1) 링커 메모리를 OCM 으로**

Application 의 `lscript.ld` 에서 모든 섹션의 메모리를 **`ps7_ram_0` (OCM, 256 KB)** 로
지정하십시오. Vitis GUI 에서 `lscript.ld` 를 열면 드롭다운으로 바꿀 수 있습니다.

> **왜** : 이 블록 디자인은 DDR 파라미터를 ZedBoard 에 맞춰 넣지 않았다.
> ZedBoard 의 DDR3(MT41K128M16)는 보드마다 배선 지연(`DQS_TO_CLK_DELAY`,
> `BOARD_DELAY`) 값이 다른데, 보드 파일 없이 손으로 넣으면 틀리기 쉽고 **틀리면
> 조용히 동작하다 가끔 깨진다.** OCM 은 그런 위험이 없고, 이 프로그램은 전역 배열이
> 40 KB 남짓이라 충분하다.
>
> DDR 을 제대로 쓰고 싶으면 **Digilent 보드 파일을 설치**해 ZedBoard 프리셋을
> 적용하는 것이 정석입니다. 그러면 `tcl/bd_ps_sys.tcl` 의 수동 설정도 필요 없어집니다.

**(2) stdout 이 `ps7_uart_1` 인지**

Platform 의 BSP 설정에서 `stdin`/`stdout` 이 `ps7_uart_1` 이어야 합니다.
ZedBoard 의 USB-UART 가 MIO 48/49 에 물려 있습니다.

터미널은 **115200-8-N-1**.

### 4-4. 프로그램 쓰는 법

띄우면 신원과 상태를 찍고 메뉴가 나옵니다. 터미널에서 키 하나를 누르면 됩니다.

| 키 | 하는 일 |
|---|---|
| `i` | 신원 / 상태 읽기 |
| `1` | **Mode 1 코드밀도 측정 (200만 발, 약 2초)** → 384탭 CSV |
| `d` | **히스토그램에서 danger 임계값 계산해 설정** ← `1` 뒤에 반드시 한 번 |
| `2` | Mode 2 캡처 (timestamp_ps) → CSV |
| `r` | Mode 2 캡처 (raw coarse/fine, 4096발) → CSV |
| `p` | 위상 이동 시험 |
| `h` | 도움말 |

CSV 는 `----- 여기부터 CSV -----` 와 `----- CSV 끝 -----` 사이에 나옵니다.
터미널에서 그 부분만 복사해 파일로 저장하면 `python/` 스크립트에 그대로 들어갑니다.

---

## 5. ★ 빌드할 때마다 해야 하는 것 — danger 임계값 다시 맞추기

**이걸 빼먹으면 타임스탬프의 coarse 가 5000 ps 틀리는 일이 생기는데, 히스토그램으로는
보이지 않습니다.**

### 왜 필요한가

TDC 는 시간을 **시침**(coarse, 클럭 개수)과 **분침**(fine, 탭 번호)으로 잽니다.
3시 정각에 시침을 읽으면 2시로도 3시로도 읽히듯, 히트가 클럭 에지 근처에 오면
coarse 가 전이 중이라 잘못 읽힙니다. 그래서 **반 주기 어긋난 보조 카운터**를 두고,
fine 이 위험 구간이면 그쪽을 씁니다. 그 경계가 `DANGER_LO` / `DANGER_HI` 입니다.

### 문제는 창이 움직인다는 것

히트가 찍히는 탭 범위(창)는 **히트 경로 지연에 따라 통째로 미끄러집니다.**

| 빌드 | 히트 경로 | 창 |
|---|---|---|
| 2026-09-04 | 로직 없음 | 2 ~ 322 |
| 2026-09-05 (AXI) | 로직 없음 | 2 ~ 321 |
| 2026-09-05 (먹스 추가) | LUT4 하나 | **24 ~ 349** |
| 2026-09-05 (같은 RTL 재빌드) | LUT4 하나 | **24 ~ 348** |

**같은 RTL 을 재빌드해도 1탭 달라집니다.** Vivado 가 LUT 위치를 매번 다시 정하기
때문입니다. 경계가 상수면 창이 밀릴 때마다 사람이 고쳐야 합니다.

그래서 `DANGER_LO/HI` 를 **AXI 레지스터(0x44)로 빼두었고**, 소프트웨어가 히스토그램에서
창을 읽어 스스로 정합니다.

### 하는 법

```
Vitis :  '1' 로 Mode 1 측정  →  'd' 로 danger 설정
XSCT  :  tcl/xsct_mode2_check.tcl 이 [A-2] 에서 자동으로 한다
```

> 목표 가드 폭 630 ps 는 2026-09-05 에 상수 40 이 만들던 아래 가드 폭입니다.
> **"예전과 같은 여유를 창이 어디로 가든 유지한다"** 는 뜻이지 630 ps 가 옳다는 뜻이
> 아닙니다. coarse 카운터가 실제로 흔들리는 시간은 **아직 측정된 적이 없습니다.**

---

## 6. 문제 해결 — 오늘까지 실제로 겪은 것만

### 6-1. `COE 가 없다` 로 빌드가 멈춘다

`python/*.coe` 는 `.gitignore` 로 제외돼 있어 저장소에 없을 수 있습니다.
384줄짜리 선형 램프를 만들어야 합니다:

```bash
cd python
python Making_COE_linear.py     # 스크립트 안의 탭 수가 384 인지 확인할 것
```

없으면 손으로 만들어도 됩니다 — 헤더 2줄 + 데이터 384줄, `0, 13, 26, ... 4987;`

### 6-2. XSCT 가 `targets` 에서 아무것도 못 찾는다

- `connect` 직후에는 `hw_server` 가 JTAG 체인을 아직 다 못 읽었습니다. **3초 기다려야
  합니다** (스크립트에 `after 3000` 이 들어 있습니다).
- 타깃 이름에 **"PS7" 은 없습니다.** 실제 이름은 `APU` / `ARM Cortex-A9 MPCore #0` /
  `xc7z020` 입니다.
- `ps7_init` 과 `mrd`/`mwr` 는 **ARM 타깃**, `fpga -file` 은 **`xc7z020` 타깃**에서
  해야 합니다.

### 6-3. 레지스터가 전부 `0xDEAD_0000` 으로 읽힌다

없는 주소를 읽었다는 뜻입니다. `BUILD`(0x04)의 하위 8비트로 맵 버전을 확인하십시오.
지금은 **6** 이어야 하고, `BUILD = 0x01806006` 입니다.

### 6-4. 아무것도 안 읽힌다 / MMCM 이 안 잠긴다

`ps7_init` 을 **비트스트림 굽기 전에** 했는지 확인하십시오. PS 의 PLL 이 설정돼야
FCLK_CLK0 이 나오고, 그게 있어야 AXI 도 MMCM 도 돕니다.

### 6-5. Mode 2 에서 히트가 한 발도 안 들어온다

순서대로 보십시오:

1. **GND 가 연결돼 있는가** — 점퍼로 이을 때 제일 흔히 빠뜨립니다
2. 신호원이 실제로 신호를 내보내는가 (스코프)
3. `HIT_INPUT` 이 맞는가 — `1`이면 **PMOD JA1 1번(Y11)**, `0`이면 FMC LA27_P/N
4. FMC 를 쓴다면 **J18 점퍼가 2.5V 인가**
   — ZedBoard 매뉴얼 Table 21 / 표 22 확인 : **J18 기본값은 1.8V** 이고 1.8 / 2.5 / 3.3V
   중 고를 수 있다. 뱅크 34/35(FMC)가 이 전압을 쓴다. 우리 XDC 는 `LVDS_25` + `DIFF_TERM`
   이므로 **2.5V 로 옮겨야** 한다. (3.3V 점퍼 자리는 FMC 카드 보호를 위해 의도적으로
   비워 두었다고 매뉴얼에 적혀 있다)
5. 신호 레벨이 3.3V 인가 (PMOD 뱅크 13 은 `LVCMOS33`)

> ★ **Y11 = PMOD JA1 1번** 이라는 대응은 ZedBoard 매뉴얼 기준이며 저장소에서 문서로
> 대조한 적이 없습니다. Vivado 로 확인한 것은 "Y11 은 뱅크 13 의 범용 IO" 까지입니다.
> **실크스크린으로 한 번 확인해 주십시오.**

### 6-6. Vitis 앱이 뜨자마자 죽는다

링커 메모리가 DDR 로 잡혀 있을 가능성이 큽니다. §4-3 (1) 을 보십시오.

### 6-6b. ★ UART 로 글자는 나오는데 키 입력이 안 먹는다 (2026-09-06 해결)

**증상** : 배너와 메뉴는 터미널에 잘 나오는데(TX 정상), 키를 눌러도 아무 반응이 없다.
Vitis Serial Terminal 을 PuTTY 로 바꿔도 똑같다.

**원인** : **MIO 뱅크 전압 설정 누락.** ZedBoard 매뉴얼 Table 21 에 따르면

```
MIO Bank 0/500 = 3.3V
MIO Bank 1/501 = 1.8V     ← UART1(MIO 48/49)이 여기 있다
```

인데, PS7 IP 의 기본값은 **두 뱅크 모두 3.3V** 다. 그래서 MIO48/49 가 `LVCMOS33` 으로
잡히고, 입력 판정 문턱이 약 2.0V 가 된다. 보드의 TXS0102 레벨 시프터가 1.8V 쪽으로
내보내는 최대치는 1.8V 이므로 **1.8V < 2.0V** 라 Zynq 가 HIGH 를 영영 인식하지 못한다.

출력은 실제 나가는 전압을 뱅크 전원(1.8V)이 정하므로 설정과 무관하게 잘 나간다.
**그래서 TX 만 되고 RX 만 죽는, 아주 헷갈리는 증상이 된다.**

**고침** : `tcl/bd_ps_sys.tcl` 에 아래 두 줄을 넣었다 (2026-09-06 반영 완료).

```tcl
CONFIG.PCW_PRESET_BANK0_VOLTAGE {LVCMOS 3.3V}
CONFIG.PCW_PRESET_BANK1_VOLTAGE {LVCMOS 1.8V}
```

`ps7_init.tcl` 의 MIO 설정값이 `0x16E0/0x16E1`(LVCMOS33) → `0x12E0/0x12E1`(LVCMOS18)
로 바뀌면 제대로 들어간 것이다. **이 수정 뒤에는 BD 부터 다시 만들어야 한다**
(빌드 → XSA 재출력 → Vitis 플랫폼 갱신).

**진단에 쓴 방법** — 같은 증상이 또 나오면 이 순서로 가르면 된다:
JTAG 로 UART1 상태 레지스터(`0xE000102C`)의 `RXEMPTY`(bit1)를 폴링하면서 키를 눌러 본다.
비트가 한 번도 안 내려가면 소프트웨어가 아니라 전기적 문제다. 실행 중인 프로그램,
BSP 설정, 터미널 프로그램과 전부 무관하게 확인할 수 있다.

### 6-7. 타이밍이 깨진다

§2-4 의 구현 전략을 확인하십시오. 그래도 안 되면 `vivado/<이름>/timing_summary.rpt`
에서 위반 경로를 보십시오. 지금까지 나온 두 종류:

- `u_seq` 안의 32비트 덧셈 → 감소 카운터로 바꿔 해결 (2026-09-05, 지금은 없음)
- CDC 2FF 동기화기의 hold → setup 을 고치면 같이 사라졌음

---

## 7. 지금 어디까지 됐나

| | 상태 |
|---|---|
| **Mode 1** (링오실레이터 코드밀도) | **완성.** FSM 6상태, 히스토그램 AXI 리드백, `HIT_CNT`==탭합 확인 |
| **Mode 2** (외부 신호 캡처) | **신호 수신까지.** 캡처 버퍼·FSM 동작 확인, chirp 재현 |
| Mode 0 (DPS 위상 스윕) | **안 됨.** 샘플링 클럭이 달라 클럭 구조 재설계 필요 |

### Mode 2 에서 아직 안 된 것

1. **FMC LVDS 경로를 실제 신호로 시험한 적이 없습니다** (고속 비교기가 없어서).
   검증된 건 PMOD 단선뿐입니다.
2. **핑퐁 이중 버퍼가 없습니다.** PS 가 읽는 동안(약 1.2 ms) 신호를 놓칩니다.
3. **chirp 시작 트리거가 없습니다.** 학습 알고리즘이 정해져야 설계할 수 있습니다.
4. **교정표가 이 빌드와 안 맞습니다.** ROM 이 선형 램프라 552 ps → 415 ps 만큼
   손해를 보고 있습니다 (§8 참조).

### 그 밖에 미연결

- **`CTRL[5] TDC_RST`** — 레지스터에는 있는데 하드웨어에 안 걸려 있습니다.
  쓰면 되읽히지만 아무 일도 일어나지 않습니다.

---

## 8. 다음에 할 일 (우선순위 순)

### (1) 교정표를 쓰기 가능한 BRAM 으로 — 4단계

지금 교정 ROM 은 **선형 램프**(384칸, 0~4987 ps, 한 칸 13 ps)인데, 이 빌드가 실제로
쓰는 창은 탭 24~348(325칸)이고 한 칸이 15.385 ps 입니다. **ROM 이 이 창에 대해
4212 ps 만 표현해 788 ps 가 모자랍니다.**

2026-09-06 실측으로 값어치가 확인됐습니다 — 같은 raw 데이터를 변환만 바꿔 계산:

| fine → ps 변환 | 간격 오차 RMS |
|---|---|
| 지금 FPGA 의 ROM (선형 13 ps) | 552.2 ps |
| 단순 선형 (창 균등 15.385 ps) | **414.7 ps** |

**25 % 개선됩니다.** ROM 을 BRAM 으로 바꾸면 재빌드 없이 표만 갈아끼울 수 있고,
"재빌드마다 place & route 가 달라진다" 는 비교의 최대 오차 요인도 사라집니다.

### (2) TDC 자체 정밀도 측정

**아직 한 번도 못 쟀습니다.** 지금까지 잰 415 ps / 17 ns 는 전부 **신호원의 흔들림**
이었습니다 — `dcoarse`(순수 클럭 개수)가 140 ns 폭으로 퍼진 것이 증거입니다.
지연선이 개입할 수 없는 값입니다.

방법은 **Mode 0** 입니다. 히트를 `clk_200_shifted` 로 만들고 샘플링은
`clk_200_fixed` 로 유지하면(= "클럭 대신 히트를 흔든다"), 클럭 구조를 안 건드리고도
됩니다. 위상을 고정하면 참 시간이 매번 완전히 같으므로, **그때 fine 이 흔들리는 정도가
곧 TDC 자신의 오차**입니다.

> 단, 위상 스텝 대 fine 의 **기울기 부호가 뒤집힙니다** (전에는 클럭을 밀었고 이제
> 히트를 미니까). `python/validate_timestamp.py` 도 함께 고쳐야 합니다.

### (3) Mode 2 핑퐁 버퍼 — 학습 알고리즘이 정해진 뒤

---

## 9. 참고 — 레지스터 맵 (버전 6, 베이스 `0x43C0_0000`)

| 오프셋 | 이름 | R/W | 내용 |
|---|---|---|---|
| `0x00` | ID | R | `0x5444_4302` |
| `0x04` | BUILD | R | `{탭수16, 단수8, 맵버전8}` = `0x0180_6006` |
| `0x08` | CTRL | RW | `[1:0]`HIT_SRC `[2]`START `[3]`STOP `[4]`HISTO_CLR `[5]`TDC_RST(미연결) `[6]`CAP_FMT |
| `0x0C` | STATUS | R | `[0]`MMCM `[2]`DNA_VALID `[3]`BUSY `[4]`DONE `[5]`PHASE_BUSY `[10:8]`상태 |
| `0x10` | DNA | R | `[31]`valid + DNA |
| `0x14` | RO_CNT | R | 10 ms 게이트당 RO 에지 수 |
| `0x18` | DIE_TEMP | R | XADC 온도 raw |
| `0x1C` | PHASE | RW | 쓰기=목표, 읽기 `[24:16]`=현재 |
| `0x20` | TARGET_HITS | RW | 목표 히트 수 (**0 = 무제한, STOP 으로만 종료**) |
| `0x24` | HIT_CNT | R | 실제 누적된 히트 수 — **384탭 합과 같아야 함** |
| `0x28` | SETTLE_N | RW | RO 안정화 대기 클럭 수 (기본 20000 = 100 µs) |
| `0x2C` / `0x30` | RO_AT_START / END | R | 측정 시작·끝의 RO 카운트 |
| `0x34` | TEMP_SE | R | `{끝 온도[31:16], 시작 온도[15:0]}` |
| `0x38` | DROP_CNT | R | 버려진 히트 수 |
| `0x3C` / `0x40` | CAP_N / CAP_CNT | RW / R | 캡처 목표 / 현재 |
| `0x44` | DANGER | RW | `{hi[24:16], lo[8:0]}` — **빌드마다 다시 맞출 것** |
| `0x1000 + i×4` | HISTO[i] | R | 탭 i 카운트, i = 0…383 |
| `0x8000 + i×8` | CAPBUF[i] | R | 캡처 버퍼, 2워드/히트 |

**HIT_SRC**: `00`=off `01`=RO(Mode 1) `10`=DPS(미구현) `11`=EXT(Mode 2)

### 환산식

```
탭 폭        w[i] = h[i] / H × 5000 ps        H = 유효구간 히트 총합
양자화 한계  σ = sqrt( Σw³ / (12·Σw) )        2026-09-05 실측 7.07 ps
RO 주파수    f_RO [Hz] = RO_CNT × 4 / 0.01 s   히트율 = f_RO / 64
다이 온도    T[°C] = raw/65536 × 503.975 − 273.15   (UG480 식 2-6)
위상 스텝    17.857 ps  (= VCO 1000 MHz 주기의 1/56)
```

---

## 10. 파일이 어디 있나

| 경로 | 내용 |
|---|---|
| **`run_build.bat`** | **빌드 (더블클릭)** |
| **`run_check.bat`** | **보드 확인 + danger 자동설정 (더블클릭)** |
| **`run_capture.bat`** | **raw 캡처 (더블클릭)** |
| `build_zedboard.tcl` | 위 배치가 부르는 실제 스크립트 |
| `tcl/bd_ps_sys.tcl` | PS7 블록 디자인 (UART1 포함) |
| `tcl/xsct_mode2_check.tcl` | 레지스터 + Mode 1 회귀 + danger 자동설정 + Mode 2 |
| `tcl/xsct_capture_raw.tcl` | raw `{coarse,fine}` 캡처 |
| `tcl/xsct_stage1_check.tcl` / `stage3_check.tcl` | 단계별 검증 (과거 기록용) |
| `vitis/tdc_app.c` | **Vitis 베어메탈 프로그램** |
| `python/analyze_chirp_capture.py` | 캡처를 STM32 참값과 대조 |
| `python/Histogram.py` 등 | 기존 교정 파이프라인 |
| `stm32/main_fixed_freq.c` | STM32 고정 주파수 신호원 |
| `RTL/` | Verilog + XDC |
| `Data/*.zip` | 측정 데이터 (각 README 에 조건과 계산법) |
| `Markdown/2026-09-05_report.md` | 어제 작업 상세 |
