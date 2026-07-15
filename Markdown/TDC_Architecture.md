
# High-Resolution FPGA TDC System Architecture & Operation Flow

본 문서는 다중 모드(Multi-mode)를 지원하는 고해상도 FPGA TDC(Time-to-Digital Converter) 시스템의 전체 입출력 흐름과 하드웨어 동작 메커니즘을 상세히 기술한다. 본 시스템은 물리 버튼 조작 및 파라미터(`OPERATION_MODE`) 설정에 따라 동적 위상 천이(DPS), 링 오실레이터(RO), 그리고 외부 신호 측정(Real Measurement) 모드로 유연하게 동작할 수 있도록 설계되었다.

## 1. System Overview & TDC Architecture

본 TDC 시스템은 200MHz 시스템 클럭을 기반으로 넓은 측정 범위(Dynamic Range)를 확보하는 **Coarse 카운터**와, 클럭의 1주기(5000ps) 내부를 피코초(ps) 단위로 정밀하게 분할하는 **Fine 지연선(Delay Line)**이 결합된 하이브리드 아키텍처를 채택하였다.

<!-- 그림 삽입 위치: VS Code에서 제공해주신 이미지 파일을 같은 폴더에 넣고 링크를 연결합니다. -->
<p align="center">
  <img src="./block_diagram.png" alt="TDC Architecture Overview" width="100%">
  <br>
  <em>Figure 1. Overall Hardware Architecture and Dual-Path (Measurement vs. Calibration) Flow</em>
</p>

Figure 1은 본 시스템의 전체 하드웨어 블록도 및 데이터 흐름을 나타낸다. 시스템은 크게 입력 신호 선택부, 물리적 측정 코어, 그리고 용도에 따라 완벽히 분리된 두 개의 데이터 경로(Measurement Path 및 Calibration Path)로 구성된다.

### 1.1. Coarse-Fine 측정 원리 및 Metastability 회피 전략
TDC FMCW Core는 시스템의 심장부로서, Hit 신호가 입력된 절대 시간을 측정한다.

*   **Fine Scan (미세 시간 측정):** Hit 신호는 320 Taps로 구성된 CARRY4 Delay Chain을 통과한다. 클럭의 상승 에지가 도달하는 순간, Delay Chain의 상태가 캡처되어 클럭 주기 내의 정밀한 위상(Hit가 도착한 위치)을 9-bit `raw_fine_idx`로 출력한다.
*   **Coarse Scan (거친 시간 측정):** 200MHz 클럭(5000ps 주기)이 뛸 때마다 1씩 증가하는 32-bit 글로벌 카운터를 사용하여 Hit가 발생한 절대적인 클럭 사이클을 `raw_coarse`로 출력한다.
*   **Metastability Avoidance (0° / 180° 이중 카운터):** 
    Hit 신호가 클럭의 상승 에지와 거의 동시에 도착할 경우, Coarse 카운터의 값이 갱신되는 찰나이므로 셋업/홀드 타임 위반(Setup/Hold Violation)에 의한 메타스테빌리티(Metastability)가 발생하여 심각한 측정 오류(예: 5000ps 오차)가 발생한다. 
    이를 원천 차단하기 위해 본 설계는 **0°(상승 에지)에서 동작하는 기본 카운터와 180°(하강 에지)에서 동작하는 섀도우 카운터를 이중으로 배치**하였다. Fine Scan 결과(탭 번호)를 바탕으로 Hit가 클럭 에지 근처의 위험 구역(Danger Zone)에 도달했다고 판단되면, 안정된 상태인 180° 위상의 카운터 값을 선택하여 출력하는 기법을 적용해 측정의 무결성을 보장한다.

### 1.2. MUX 기반 입력 생성 및 다중 모드 (Mode 0, 1, 2)
TDC 코어로 진입하는 클럭(`tdc_clk`)과 Hit 신호(`tdc_hit_in`)는 3채널 MUX에 의해 결정되며, 이를 통해 하나의 하드웨어로 세 가지 연구 목적을 모두 수행할 수 있다.
1.  **Clock & MMCM (Mode 0):** 동기화된 Hit를 사용하며, MMCM의 Dynamic Phase Shifter를 통해 클럭 위상을 17.85ps 스텝으로 인위적으로 스윕하여 결정론적(Deterministic) 캘리브레이션을 수행한다.
2.  **Ring Oscillator (Mode 1):** 메인 클럭과 비동기(Asynchronous)로 자유 발진하는 RO의 랜덤 Hit를 사용하여 통계적(Statistical) 캘리브레이션을 수행한다.
3.  **External Signal (Mode 2):** LiDAR 등 외부 물리적 환경에서 입력되는 실제 Hit 신호를 수신하여 ToF(Time-of-Flight)를 측정한다.

### 1.3. Dual-Path Architecture: 측정 경로와 캘리브레이션 경로의 분리
TDC 코어에서 출력된 원시 데이터(`raw_coarse`, `raw_fine_idx`)는 시스템 목적에 따라 두 개의 경로로 나뉘어 처리된다.

*   **Measurement Path (적색 영역):** Timestamp Calculator 모듈 내부의 파이프라인 DSP 연산기를 거친다. 사전에 캘리브레이션 된 절대 시간 보정 테이블(LUT)을 참조하여, 비선형성이 완벽히 제거된 64-bit 절대 시간(`final_timestamp_ps`)을 산출한다.
*   **Calibration Path (녹색 영역):** Histogram Controller는 타임스탬프 계산이 완료되어 유효성(Valid)이 검증된 데이터에 한해서만 Gating을 수행한다. 검증된 Fine Index는 하드웨어 누적기(Dual-Port BRAM)에 실시간으로 압축·저장되며, 스윕이 완료되면 Readout Serializer를 통해 병목 없이 Vivado ILA(PC)로 추출된다.

이러한 Dual-Path 구조는 막대한 양의 캘리브레이션 데이터를 PC로 전송하는 병목을 FPGA 내부에서 하드웨어적으로 해결함과 동시에, 실시간 측정의 지연 시간(Latency)을 최소화하는 최적의 아키텍처이다.

---

## 2. Global Clock & Reset Control (도미노 리셋 구조)

시스템의 가장 뼈대가 되는 클럭과 리셋 제어는 FPGA 보드의 물리적 버튼 특성과 하드웨어 로직의 극성(Polarity) 충돌을 방지함과 동시에, **불안정한 클럭에 의한 시스템 오동작을 원천 차단**하기 위해 **도미노 리셋(Domino Reset)** 구조로 설계되었다.

*   **외부 입력 핀:** `clk_125` (125MHz 보드 클럭), `btn_rst` (Active-High 물리 푸시 버튼)
*   **클럭 위저드 (`clk_wiz_0`):** 
    보드의 푸시 버튼인 `btn_rst` 신호(누를 때 1)를 직접 입력받아, TDC 구동용 고정 클럭(`clk_200_fixed`)과 가변 위상 클럭(`clk_200_shifted`)을 생성한다.
*   **Active-Low 변환 및 `clk_locked`를 활용한 하위 모듈 리셋:** 
    버튼을 눌러 클럭 위저드가 리셋되면 정상 출력 상태를 나타내는 `clk_locked` 신호가 `0`으로 떨어진다. 본 설계에서는 외부 물리 버튼 신호를 하위 모듈(TDC Core, Timestamp Calc, Histogram 등)의 리셋 핀(`rst_n`)에 직접 연결하지 않고, **클럭 위저드의 `clk_locked` 신호를 하위 모듈의 글로벌 리셋(Global Reset)으로 사용하였다.**

**[`clk_locked`를 리셋 신호로 채택한 물리적/논리적 이유]**
1.  **클럭 안정성 보장 (Clock Stability Guarantee):** 
    하위 모듈(TDC 코어 및 BRAM)은 200MHz의 고속 클럭 기반으로 동작한다. 전원 인가 직후나 리셋 직후에는 클럭 위저드 내부의 PLL/MMCM이 안정화(Lock)되지 않아 글리치(Glitch)가 섞인 불안정한 클럭이 출력된다. 이때 로직이 동작하면 심각한 메타스테빌리티(Metastability)나 데이터 오염이 발생할 수 있다. `clk_locked` 신호를 리셋으로 사용하면, **클럭이 100% 안정화되기 전까지는 모든 하위 로직을 강제로 리셋(정지) 상태로 묶어두어 시스템의 오동작을 물리적으로 차단**할 수 있다.
2.  **물리적 극성(Polarity) 충돌 해결:** 
    외부 보드의 물리 버튼은 누를 때 1이 되는 Active-High 특성을 가지는 반면, 하위 하드웨어 모듈들은 모두 `if (!rst_n)` 구문을 사용하는 범용적인 Active-Low 리셋 구조로 설계되었다. 이 둘을 직접 연결하면 극성이 뒤집혀 시스템이 먹통이 된다. 하지만 `clk_locked` 신호를 매개로 사용하면, **"버튼 누름(1) $\rightarrow$ MMCM 리셋 $\rightarrow$ clk_locked 떨어짐(0) $\rightarrow$ 하위 모듈 Active-Low 조건 충족(Reset)"**이라는 도미노 현상이 자연스럽게 성립되어 별도의 인버터(Inverter) 게이트 없이 논리적 충돌을 완벽하게 해결할 수 있다.

---
## 3. Multi-Mode Architecture: 개념 및 설계 목적 (Motivation)

FPGA 기반 TDC는 내부 CARRY4 라우팅 배선의 비대칭성으로 인해 탭(Tap) 간의 지연 시간이 균일하지 않은 심각한 미분 비선형성(DNL, Differential Non-Linearity)을 가진다. 이를 보상하기 위해서는 모든 탭의 실제 지연 시간을 측정하여 절대 시간 보정 테이블(LUT)을 생성하는 **코드 밀도 테스트(Code Density Test) 기반의 캘리브레이션**이 필수적이다.

본 연구에서는 단순히 하나의 캘리브레이션 방식을 적용하는 데 그치지 않고, **결정론적(Deterministic) 방식과 통계적(Statistical) 방식의 캘리브레이션을 단일 FPGA 플랫폼 내에서 비교 분석**하고, 최종적으로 **실제 측정**까지 수행할 수 있도록 하드웨어 멀티플렉싱(MUX) 기반의 **3중 모드(Multi-Mode) 아키텍처**를 고안하였다. 각 모드의 설계 목적과 학술적 의의는 다음과 같다.

### 3.1. MODE 0: Dynamic Phase Shift (DPS) 기반 정적 캘리브레이션
*   **개념:** MMCM의 동적 위상 천이(DPS) 기능을 이용하여 측정 클럭의 위상을 인위적이고 정밀하게 스윕(Sweep)하며 Hit를 인가하는 **결정론적(Deterministic)** 방식이다.
*   **설계 목적 (Why):** 전통적인 링 오실레이터(RO) 기반 캘리브레이션은 FPGA 내부의 강력한 메인 클럭 노이즈로 인해 주파수가 동기화되어 버리는 **인젝션 락킹(Injection Locking)** 현상에 취약하다. MODE 0는 클럭과 Hit를 완벽히 동기화한 상태에서 위상만 밀어내므로 이러한 노이즈 간섭에서 100% 자유로우며, 단 **2.8초**의 극히 짧은 시간 안에 오차 없는 무결점 기준 데이터(Golden Reference)를 확보하기 위해 고안되었다.

### 3.2. MODE 1: Ring Oscillator (RO) 기반 동적 캘리브레이션
*   **개념:** 메인 클럭과 완전히 비동기(Asynchronous)로 동작하는 링 오실레이터를 자유 발진(Free-running)시켜, 확률적으로 자연스러운 Hit 분포를 수집하는 **통계적(Statistical)** 방식이다.
*   **설계 목적 (Why):** 시스템 운용 중 온도가 변화하면 지연 시간이 틀어지므로 실시간 보정이 필요하다. MODE 1은 별도의 MMCM 제어 자원을 소모하지 않고 백그라운드에서 상시 동작할 수 있어 **온도 변화에 대응하는 온라인/동적 캘리브레이션(Online Calibration)**에 매우 적합하다. 본 연구에서는 MODE 0와 MODE 1을 직접 교차 검증함으로써 두 방식의 DNL/INL 보상 성능 및 리소스 효율(Trade-off)을 학술적으로 비교하고자 이 모드를 탑재하였다.

### 3.3. MODE 2: External Real Measurement (실제 외부 측정)
*   **개념:** MODE 0 또는 MODE 1을 통해 도출된 보정 테이블(`.coe` 파일)을 하드웨어 Timestamp Calculator 모듈에 적재한 후, 외부 환경(LiDAR, PET 등)에서 들어오는 실제 물리적 Hit 신호를 수신하는 운용 모드이다.
*   **설계 목적 (Why):** 본 TDC 시스템이 단순한 캘리브레이션 테스트 벤치에 머물지 않고, 비선형성이 완벽하게 제거된 **64-bit 절대 시간(Absolute Time)을 실시간으로 출력**하여 상용 수준의 ToF(Time-of-Flight) 센서 시스템으로 즉각 활용될 수 있음을 증명하기 위해 구성되었다.

---

## 4. MODE 0: Dynamic Phase Shift (DPS) 기반 정적 캘리브레이션 아키텍처

MODE 0는 Xilinx FPGA 내장 MMCM(Mixed-Mode Clock Manager)의 동적 위상 천이(Dynamic Phase Shift) 기능을 이용하여, 클럭의 위상을 결정론적(Deterministic)으로 이동시키며 TDC 탭의 물리적 지연 시간(Bin Width)을 추출하는 정적 캘리브레이션 모드이다. 

이 모드는 하드웨어 내부에서 데이터가 생성되고 추출되기까지 **① 모수 설정(Math) $\rightarrow$ ② 구동 엔진(FSM) $\rightarrow$ ③ 물리적 측정(Core) $\rightarrow$ ④ 동기화(Calculator) $\rightarrow$ ⑤ 누적 및 게이팅(Histogram) $\rightarrow$ ⑥ 추출(Scanner)**의 6단계 파이프라인을 거친다.

### 4.1. Hit 발생 주기 및 총 누적 데이터(모수) 설정 원리

고해상도의 신뢰성 있는 Code Density 분포를 얻기 위해서는 각 탭(Tap)에 충분한 모수의 Hit가 누적되어야 한다. 본 설계에서는 200MHz 클럭(주기 $T_{clk} = 5000\text{ ps}$)의 1주기를 물리적인 오차 없이 완벽히 스윕(Sweep)하기 위해, MMCM의 아날로그 제원 스펙을 역산하여 파라미터를 다음과 같이 최적화하였다.

*   **위상 스텝 크기(Resolution) 및 횟수:** 
    Xilinx 7-Series MMCM의 동적 위상 천이 분해능(Dynamic Phase Shift Resolution, $T_{step}$)은 내부 VCO 주파수($F_{vco}$)에 의해 물리적으로 결정되며, 그 공식은 다음과 같다.
    
    $$T_{step} = \frac{1}{56 \times F_{vco}}$$
    
    본 설계의 MMCM은 $1\text{ GHz}$의 내부 VCO 주파수($F_{vco}$)를 사용하도록 설정되었다. 따라서 1 스텝당 물리적 위상 천이량은 다음과 같이 도출된다.
    
    $$T_{step} = \frac{1}{56 \times 1\text{ GHz}} = \frac{1000\text{ ps}}{56} \approx 17.857\text{ ps}$$
    
    200MHz 측정 클럭의 1주기($5000\text{ ps}$) 전체를 빈틈없이 스윕하기 위한 총 스텝 수($N_{step}$)는 다음과 같이 정확히 280회로 계산된다.
    
    $$N_{step} = \frac{T_{clk}}{T_{step}} = \frac{5000\text{ ps}}{17.857\text{ ps}} = 280\text{ Steps}$$
*   **Hit 발생 주기:** 동기화된 Hit 신호(`test_hit_sync`)는 **10 클럭(50ns)** 마다 1번씩 규칙적으로 발생하도록 설계되었다.
*   **1스텝 당 대기 시간:** 특정 위상에 도달한 후, 해당 위상에서 데이터를 수집하기 위해 머무르는 시간(`DELAY_MAX`)을 **2,000,000 클럭(10ms)**으로 설정하였다.
*   **총 누적 모수:** 1스텝 당 200,000개의 Hit가 발생하며, 280 스텝을 곱하여 **총 56,000,000개 (56M)**의 방대한 통계 데이터를 단 **2.8초** 만에 BRAM에 누적한다.

```verilog
// [코드 1] 10클럭(50ns) 주기 초고속 Hit 발생기 및 대기 시간 파라미터
reg [3:0] sync_cnt; 
always @(posedge clk_200_fixed) begin 
    if (sync_cnt == 4'd9) sync_cnt <= 0;      // 10클럭 주기로 반복
    else sync_cnt <= sync_cnt + 1; 

    // 카운터가 0, 1일 때만 High를 출력하여 일정한 펄스(Hit) 생성
    if (sync_cnt < 4'd2) test_hit_sync <= 1'b1; 
    else test_hit_sync <= 1'b0;
end 

localparam DELAY_MAX = 21'd2_000_000; // 1스텝당 2,000,000 클럭 대기
```

### 4.2. 구동 엔진: MMCM 제어용 FSM 및 핵심 신호(Control Logic) 해석

하드웨어 논블로킹(`<=`) 회로의 특성상, 모든 제어 신호는 클럭의 에지(Edge)에 동시 다발적으로 평가되고 다음 클럭에 상태가 반영된다. 본 설계의 `mmcm_phase_shifter` 모듈은 복잡한 MMCM Primitive를 안전하게 제어하기 위해 4단계의 FSM을 사용한다.

**[핵심 제어 신호 정의]**
*   `psen` (Phase Shift Enable): 위상 이동을 명령하는 1클럭짜리 트리거 (출력)
*   `psincdec`: 1이면 위상 증가(+), 0이면 감소(-)를 지시 (출력)
*   `psdone` (Phase Shift Done): 위상 천이 완료를 알리는 하드웨어 응답 (입력)
*   `ps_busy` (Phase Shifter Busy): 캘리브레이션이 진행 중임을 나타내는 글로벌 상태 깃발 (출력)

```verilog
// [코드 2] MMCM 제어 FSM 핵심 로직
case (state)
    IDLE: begin 
        psen <= 0; delay_cnt <= 0; 
        if (start_shift_edge) begin   // 스윕 버튼 클릭 감지
            busy <= 1'b1;             // 스윕 진행 깃발(ps_busy) ON
            loop_cnt <= 0; 
            state <= SHIFT; 
        end else busy <= 1'b0; 
    end
    SHIFT: begin 
        psen <= 1'b1;                 // MMCM 위상 이동 명령 발사
        psincdec <= 1'b1;             // 증가(+) 방향 설정
        state <= WAIT_DONE;           // 명령 직후 다음 클럭에서 바로 대기 상태로 진입
    end
    WAIT_DONE: begin 
        psen <= 1'b0;                 // 트리거 종료
        if (psdone) begin             // MMCM 하드웨어가 "이동 완료" 응답을 보내면
            loop_cnt <= loop_cnt + 1; // 스텝 횟수를 +1 증가시키고
            state <= DELAY;           // 데이터 누적을 위한 딜레이 상태로 진입
        end 
    end
    DELAY: begin 
        if (delay_cnt == DELAY_MAX) begin // 2,000,000 클럭(1스텝 체류 시간) 충족 시
            delay_cnt <= 0; 
            if (loop_cnt == 9'd280) begin // 목표치인 280 스텝을 모두 채웠다면?
                busy <= 1'b0;         // 스윕 완료 깃발(ps_busy) OFF
                state <= IDLE;        // FSM 종료 및 대기 상태 복귀
            end else begin
                state <= SHIFT;       // 아직 280 스텝이 안 남았다면 다음 위상으로 다시 SHIFT
            end
        end else delay_cnt <= delay_cnt + 1; 
    end
endcase
```

#이전에 작성된 **논리적 동작(CARRY4 및 인코더)**에 대한 설명과 방금 추가된 **물리적 배치(ASIC급 수동 XDC 제약)**에 대한 설명을 물 흐르듯 자연스럽게 하나로 융합했습니다. 

단순히 기능을 나열하는 것을 넘어, **"논리적으로 어떻게 측정하는가?" $\rightarrow$ "하지만 자동 배치에 맡기면 무슨 문제가 생기는가?" $\rightarrow$ "그래서 물리적으로 어떻게 완벽히 통제했는가?"** 라는 논문 특유의 '문제 제기 및 해결(Problem & Solution)' 구조를 갖추도록 다듬었습니다.

아래 텍스트를 기존 마크다운의 **2.3절** 자리에 그대로 덮어씌우시면 됩니다!

---

### 4.3. 물리적 측정 및 ASIC급 수동 배치 제어: TDC FMCW Core (`tdc_fmcw_core.v`)

Phase Shifter가 클럭 위상을 밀어내고 Hit를 쏘면, 실제 물리적인 시간 측정은 `tdc_fmcw_core` 모듈에서 수행된다. 고해상도 TDC의 선형성(DNL/INL)을 결정짓는 가장 중요한 요소는 논리적 설계뿐만 아니라, **CARRY4 셀의 출력 핀(O)에서 샘플링 플립플롭(D-FF)의 입력 핀(D)까지 도달하는 물리적 라우팅 지연(Routing Delay)의 절대적 균일성**이다.

본 설계는 완벽한 선형성 확보를 위해 논리적 지연선 구성과 물리적 수동 배치(Manual Placement) 기법을 동시에 적용하였다.

**[논리적 측정 구조: CARRY4 체인과 인코더]**
*   **Delay Chain 및 샘플링:** FPGA 내부의 전용 고속 라우팅 자원인 CARRY4 셀 80개를 직렬 연결하여 총 320 Taps의 미세 지연선(Delay Line)을 구성한다. Hit 신호가 지연선을 통과하는 순간, 클럭의 상승 에지에 맞춰 320개의 D-FlipFlop(`FDC`)이 일제히 현재 탭의 논리 상태를 샘플링한다.
*   **데이터 변환:** 샘플링된 Thermometer 코드는 내부 인코더를 거쳐 9-bit의 원시 탭 번호인 **`raw_ts_fine_idx`**와 32-bit의 **`raw_ts_coarse`**로 변환되어 출력된다.

```verilog
// [코드 3-1] TDC Core의 CARRY4 체인 및 1차 샘플링 레지스터 논리 선언
CARRY4 u_carry4 (.CO(carry_co), .O(carry_o), .CI(carry_ci), .CYINIT(hit), ...);

// Hit 통과 순간 클럭 에지에 맞춰 각 탭의 상태를 고속 캡처
(* DONT_TOUCH = "TRUE" *) FDC u_ff_0 ( .Q(taps_sampled[0]), .C(clk), .D(carry_o[0]) );
```

**[물리적 레이아웃 통제: Full Custom XDC Constraints]**
위와 같이 완벽한 논리 코드를 작성하더라도 Vivado의 자동 배치 라우터(Auto Placer & Router)에 레이아웃을 맡길 경우, 플립플롭들이 임의의 슬라이스(Slice)로 흩어지며 라우팅 지연이 불규칙해져 심각한 DNL 왜곡이 발생한다. 이를 원천 차단하기 위해 **ASIC 수준의 엄격한 수동 물리적 배치(BEL/LOC Mapping) 제약 조건**을 적용하였다.

1.  **자동 동기화 배치(`ASYNC_REG`) 속성 해제:** 일반적으로 비동기 신호 처리 시 툴이 플립플롭들을 모아주도록 유도하는 `ASYNC_REG` 속성을 사용한다. 하지만 설계자가 완벽한 핀투핀(Pin-to-pin) 좌표를 직접 지정하였으므로, 툴의 자동 배치 알고리즘이 수동 제약 조건과 충돌하여 배선을 틀어버리는 것을 막기 위해 `ASYNC_REG` 속성을 명시적으로 `false`로 해제하였다.
2.  **CARRY4와 1차 샘플링 FF의 강제 밀착 (Intra-Slice Routing):** 80개의 CARRY4 셀을 `SLICE_X42` 열(Column)을 따라 수직으로 배치하고, 1차 샘플링 플립플롭(`u_ff_0` ~ `u_ff_3`)들을 **CARRY4와 완벽하게 동일한 슬라이스 내부의 `AFF, BFF, CFF, DFF` (BEL)**에 강제로 욱여넣었다. 이를 통해 신호가 슬라이스 외부로 나가지 않는 초단거리 내부 배선(Intra-Slice Routing)을 강제하여 탭 간 지연 시간의 불균일성을 제거했다.
3.  **2차 파이프라인 레지스터의 인접 열(Column) 강제 할당:** 메타스테빌리티 완화를 위한 2차 파이프라인 레지스터(`taps_sampled_d1`) 역시 자동 배치를 불허하였다. 1차 FF가 위치한 `X42` 열과 정확히 맞닿아 있는 **바로 옆 열(`SLICE_X43`)에 1:1로 평행하게 강제 배치**함으로써, 320가닥의 거대한 데이터 버스가 단 하나의 꼬임(Congestion) 없이 직진하는 완벽한 데이터패스(Data-path)를 구현하였다.

```tcl
# [코드 3-2] DNL 왜곡 방지를 위한 ASIC급 수동 물리적 레이아웃 XDC 제약 조건

# 1. Vivado 자동 배치(ASYNC_REG) 간섭 원천 차단
set_property ASYNC_REG false [get_cells -hierarchical -filter {NAME =~ *u_ff_*}]
set_property ASYNC_REG false [get_cells -hierarchical -filter {NAME =~ *taps_sampled_d1_reg*}]

# 2. Stage 0 (최하단) CARRY4 및 1차 샘플링 FF를 동일 슬라이스(X42Y0)에 완벽 밀착
set_property LOC SLICE_X42Y0 [get_cells -hierarchical -filter {NAME =~ *CARRY_CHAIN[0].STAGE*u_carry4*}]
set_property LOC SLICE_X42Y0 [get_cells -hierarchical -filter {NAME =~ *CARRY_CHAIN[0]*u_ff_0*}]
set_property BEL AFF [get_cells -hierarchical -filter {NAME =~ *CARRY_CHAIN[0]*u_ff_0*}]
set_property LOC SLICE_X42Y0 [get_cells -hierarchical -filter {NAME =~ *CARRY_CHAIN[0]*u_ff_1*}]
set_property BEL BFF [get_cells -hierarchical -filter {NAME =~ *CARRY_CHAIN[0]*u_ff_1*}]
# (CFF, DFF 생략: 동일 구조 적용)

# 3. 2차 파이프라인 FF를 인접 슬라이스(X43Y0)에 평행 전송되도록 강제 배치
set_property LOC SLICE_X43Y0 [get_cells -hierarchical {*taps_sampled_d1_reg[0]}]
set_property BEL AFF [get_cells -hierarchical {*taps_sampled_d1_reg[0]}]
set_property LOC SLICE_X43Y0 [get_cells -hierarchical {*taps_sampled_d1_reg[1]}]
set_property BEL BFF [get_cells -hierarchical {*taps_sampled_d1_reg[1]}]
# (이하 Stage 1 (Y1), Stage 2 (Y2) ... 총 80 Stage 수직 반복 적용)
```
### 💡 (참고) 논문 작성 팁
이 XDC 코드를 논문에 넣으실 때는, 선생님께서 첨부해 주신 **"Vivado Implemented Design에서 CARRY4와 FF들이 나란히 빨간색/파란색으로 예쁘게 빽빽하게 배치된 Device 화면 캡처(Floorplan)"**를 같이 그림으로 삽입하시면 시각적인 파급력이 엄청납니다. 심사위원들이 논문을 보자마자 "이 사람은 하드웨어의 끝판왕이다"라고 인정할 것입니다!


---

### 4.4. 절대 시간 연산 및 파이프라인 동기화: Timestamp Calculator (`tdc_timestamp_calc.v`)

TDC Core에서 출력된 원시 데이터(`raw_ts_coarse`, `raw_ts_fine_idx`)는 Timestamp Calculator로 진입하여, 캘리브레이션 롬(LUT) 데이터와 결합된 최종 **64-bit 절대 시간(Absolute Time, ps 단위)**으로 변환된다.

이 모듈은 고속(200MHz) 동작 환경에서 타이밍 위반(Timing Violation) 없이 64-bit의 거대한 산술 연산을 수행하기 위해 **5단계(5-Stage)의 깊은 파이프라인 구조**로 설계되었으며, 단계별 연산 과정은 다음과 같다.

**[절대 시간 연산 파이프라인 흐름]**
1.  **Stage 1 (입력 버퍼링):** 입력된 32-bit Coarse 값을 DSP 곱셈기에 넣기 위해 상위 16-bit와 하위 16-bit로 분할(Split)하여 레지스터에 버퍼링한다.
2.  **Stage 2 (DSP 병렬 곱셈):** 클럭 1주기가 5000ps이므로, Coarse 카운터 값에 5000을 곱하여 ps 단위의 거친 시간을 도출해야 한다. 병목을 막기 위해 2개의 하드웨어 DSP48 블록(`mul_H`, `mul_L`)을 병렬로 구동하여 스케일링 연산을 수행한다.
3.  **Stage 3 (ROM 데이터 병합):** Stage 1에서 시작된 `.coe` 파일(Calibration ROM) 읽기 작업의 결과값(Latency=2)인 `calibrated_fine_ps`가 이 시점에 도착한다. 동시에 Stage 2의 상/하위 곱셈 결과를 더해 64-bit의 `coarse_total_ps`를 완성한다.
4.  **Stage 4 & 5 (Borrow-Lookahead 뺄셈 및 최종 출력):** 최종 절대 시간은 \[T_{coarse}-T_{fine}\] 수식으로 계산된다. 200MHz(5ns) 클럭 도메인에서 64-bit의 거대한 뺄셈을 단일 클럭 사이클에 수행할 경우, 긴 자리올림수 체인(Long Carry-chain)과 라우팅 지연에 의해 타이밍 위반(Setup Time Violation)이 발생할 위험이 크다.이를 방지하기 위해 본 설계는 **분할 파이프라인(Split-pipeline)** 구조를 채택하였다. Stage 4에서 하위 32-bit 뺄셈을 선행하여 빌림수(Borrow)를 레지스터에 저장하고, 다음 클럭인 Stage 5에서 상위 32-bit에 빌림수를 적용하여 최종 64-bit 타임스탬프를 완성함으로써 Critical Path를 절반 수준으로 단축하였다.

```verilog
// [코드 4] Timestamp Calculator 내부의 64-bit 절대 시간 계산 파이프라인 일부
// Stage 2: DSP를 활용한 Coarse 카운터 스케일링 (x 5000ps)
(* use_dsp = "yes" *) reg [31:0] mul_L_d2;
(* use_dsp = "yes" *) reg [47:0] mul_H_d2; 
always @(posedge clk) begin
    mul_L_d2 <= ts_coarse_L_d1 * 16'd5000; 
    mul_H_d2 <= ts_coarse_H_d1 * 16'd5000;
end

// Stage 4~5: 파이프라인 분할 뺄셈 (Absolute Time = Coarse - Fine)
always @(posedge clk) begin
    sub_lower_d4  <= {1'b0, coarse_total_ps_d3[31:0]} - {20'd0, calibrated_fine_ps_d3};
    final_absolute_time_ps_reg <= { (upper_half_d4 - {31'd0, sub_lower_d4[32]}), sub_lower_d4[31:0] };
end
```

**[동작 이해를 위한 직관적 수치 예시]**
위 복잡한 연산과 파이프라인 동기화(Time Alignment)가 왜 필요한지 직관적으로 이해하기 위해, 다음과 같은 상황을 가정해 본다.
*   **상황:** 클럭이 3번 뛴 후(Coarse = 3), 10번째 탭(Fine Index = 10)에서 Hit 신호가 측정되었다. 캘리브레이션 롬(ROM)에 기록된 10번째 탭의 실제 지연 시간은 150ps이다.
*   **절대 시간 연산:** 모듈 내부에서는 `(3 × 5000ps) - 150ps = 14,850ps` 라는 최종 절대 시간을 도출해 낸다. 하지만 이 곱셈, 롬 읽기, 뺄셈을 거치느라 하드웨어적인 시간(클럭)이 소요되어, 결과값과 **"계산 완료 허가증(`final_ts_valid = 1`)"은 원시 데이터가 입력된 시점으로부터 정확히 5클럭 뒤쳐져서(Latent) 출력**된다.
*   **파이프라인 동기화 (Time Alignment)의 필요성:** 
    만약 캘리브레이션 모드(MODE 0)에서, 코어에서 갓 튀어나온 탭 주소 `10`을 히스토그램 BRAM에 곧바로 꽂아버리면 어떻게 될까? 주소 `10`은 '클럭 0' 시점에 도착했지만, BRAM 쓰기 허가증(`final_ts_valid`)은 5클럭 뒤인 '클럭 5' 시점에 도착한다. 두 신호의 타이밍이 엇갈려(Mismatch) BRAM은 엉뚱한 주소에 카운트를 누적하게 된다.
*   **해결책:** 이를 완벽히 방지하기 위해 Calculator 내부에서 연산과 무관한 탭 주소 `10`을 고의로 **5-Stage Delay Line (D-FF 5개)**에 태운다. 결과적으로 연산이 끝나는 '클럭 5' 시점에 완벽하게 발걸음이 정렬(Time-aligned)된 상태인 `aligned_fine_idx`가 추출되며, 이것이 히스토그램 누적기(BRAM)의 입력 주소로 안전하게 인가된다.

**[히스토그램을 위한 파이프라인 동기화 (Time Alignment)]**
MODE 0(캘리브레이션) 동작 시에는 절대 시간 출력을 사용하지 않고 히스토그램 BRAM에 데이터를 누적해야 한다. 하지만 위에서 설명한 64-bit 연산을 거치느라 최종 유효 검증 신호(`final_ts_valid`)는 원시 데이터 입력 시점보다 **정확히 5클럭 뒤쳐져서(Latent)** 출력된다.

만약 코어에서 갓 튀어나온 탭 주소(`raw_ts_fine_idx`)를 히스토그램 BRAM에 바로 직결하면, 주소와 쓰기 허가증(`final_ts_valid`) 사이의 타이밍 엇갈림(Mismatch)이 발생하여 엉뚱한 위치에 데이터가 누적된다. 이를 완벽히 방지하기 위해 Calculator 내부에서 연산과 무관한 탭 주소를 고의로 **5-Stage Delay Line**에 태운다.

그 결과, 절대 시간 연산이 끝나는 시점에 완벽하게 발걸음이 정렬(Time-aligned)된 상태인 `aligned_fine_idx`가 추출되며, 이것이 히스토그램 누적기(BRAM)의 입력 주소로 안전하게 인가된다.

```verilog
// [코드 4] Timestamp Calculator 내부의 Time Alignment (Retiming) 로직
always @(posedge clk) begin
    ts_fine_idx_d1 <= ts_fine_idx;       // 1클럭 대기
    ts_fine_idx_d2 <= ts_fine_idx_d1;    // 2클럭 대기
    // ... (중간 파이프라인 단계 생략) ...
    ts_fine_idx_d5 <= ts_fine_idx_d4;    // 5클럭 대기 완료
end

// 최종 유효 신호(final_ts_valid)와 발걸음이 완벽히 맞춰진(Aligned) 주소 출력
assign fine_idx_out = ts_fine_idx_d5;    // Top 모듈의 aligned_fine_idx 로 연결됨
```
---
### 4.5. 데이터 누적 및 무결성 제어: Histogram BRAM & Gating (`tdc_histogram.v`)

동기화되어 도착한 `aligned_fine_idx`는 외부 PC로 전송되는 병목을 제거하기 위해 FPGA 내부에 구현된 **Hardware Histogram Accumulator(BRAM)**에 실시간으로 누적된다.

*   **Histo Gating Control:** 
    앞서 설명한 FSM의 `ps_busy` 신호는 단순히 상태를 나타내는 것을 넘어, **쓰레기 데이터 누적을 막는 하드웨어 밸브(Valve) 역할**을 수행한다. 위상 스윕이 멈춰있는 `IDLE` 상태(`ps_busy = 0`)에서는 특정 탭에 카운트가 몰빵되는 현상(Garbage Pile-up)을 원천 차단하며, 스윕 버튼이 눌려 약 2.8초(`ps_busy = 1`) 동안에만 게이트가 열려 5,600만 개의 데이터가 각 탭에 공정하게 분배된다.
*   **Read-Modify-Write (RMW):** Dual-Port BRAM을 활용하여, Hit가 들어온 탭 주소의 기존 값을 읽어온 뒤 +1을 더하여 다시 쓰는 RMW FSM이 파이프라인으로 동작한다.

```verilog
// [코드 5] Top 모듈의 Gating Logic 및 Histogram 내부의 Read-Modify-Write FSM
// 1. 대기 중 몰빵 방지를 위한 하드웨어 밸브(Gating) 적용
assign gated_ts_valid = final_ts_valid && ps_busy;

// 2. Histogram 내부 BRAM 누적 FSM (Read-Modify-Write)
STATE_RMW_W: begin
    count_reg <= ram_dout_a + 1'b1;  // 해당 탭(주소)의 기존 누적 값에 +1 증가
    state <= STATE_IDLE;
end
```
---
### 4.6. 직렬화 및 추출: Readout Scanner & ILA

2.8초 후 320개 탭에 거대한 데이터 누적이 완료되면 이를 ILA로 추출해야 한다. 32-bit $\times$ 320개의 데이터를 병렬로 추출하는 것은 하드웨어적으로 불가능하므로 **Readout Scanner**를 통한 직렬화(Serialization) 기법이 적용된다.

*   **Trigger 감지 및 스캔:** 하드웨어가 스스로 위상 스윕 완료 시점(`loop_cnt == 280`)을 감지하면, 즉시 `readout_active` 신호를 High로 켠다. 이후 320 클럭 사이클 동안 BRAM의 읽기 주소(`probe_read_addr`)를 0부터 319까지 1씩 증가시키며 내부 카운트 값을 차례대로 직렬 출력한다.
*   **ILA 연동:** Vivado ILA는 `readout_active == 1`을 캡처 조건으로 설정하여, 병목 없이 깔끔하게 압축된 Code Density 분포를 CSV 포맷으로 추출함으로써 한 사이클의 정적 캘리브레이션이 무결점(Zero-defect)으로 완료된다.

```verilog
// [코드 6] Readout Scanner의 하드웨어 자동 트리거 및 직렬화 스캔 로직
// 목표 스윕 횟수(280)에 도달하는 찰나를 감지
wire sweep_finished = (current_loop_cnt == 9'd280) && (loop_cnt_d1 == 9'd279);

always @(posedge tdc_clk) begin
    if (sweep_finished && !readout_active) begin
        readout_active <= 1'b1;     // ILA 캡처 시작 깃발 ON
        sweep_addr     <= 9'd0;     // 0번 주소부터 스캔 시작
    end else if (readout_active) begin
        if (sweep_addr == 9'd319) 
            readout_active <= 1'b0; // 319번까지 스캔 완료 후 깃발 OFF (종료)
        else 
            sweep_addr <= sweep_addr + 1'b1; // 주소를 +1씩 차례대로 증가
    end
end
```
```