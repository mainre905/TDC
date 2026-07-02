여기 지금까지의 치열했던 디버깅 과정과 성공적인 최적화 결과를 집대성한 **[FMCW TDC 개발 및 최적화 완료 보고서]**를 작성해 드립니다. 

이 문서는 향후 논문 작성, 기술 블로그 포스팅, 또는 프로젝트 결과 보고서에 그대로 활용하실 수 있도록 엔지니어링 관점에서 전문적으로 구성되었습니다.

---

# 🚀 [기술 보고서] 고정밀 FMCW 레이저 제어용 Dual-Phase TDC 개발 및 최적화

## 1. 프로젝트 개요
본 프로젝트는 FMCW 레이저의 Beat 주파수를 실시간으로 정밀 측정하여 피드백 제어 시스템(PLL 등)에 활용하기 위한 **FPGA 기반의 고정밀 TDC(Time-to-Digital Converter)** 설계 및 최적화 과정이다. 
초기 설계에서 발생한 고질적인 타이밍 점프($\pm 5\text{ns}$)와 신호 무결성 문제를 분석하고, **Dual-Phase Counter 아키텍처**와 **하드웨어 타이밍 최적화(Timing Closure)** 기법을 도입하여 소프트웨어의 사후 보정 없이 **하드웨어 단독으로 100% 무결점(Flawless) 실시간 타임스탬프를 출력**하는 데 성공하였다.

---

## 2. 트러블슈팅 및 아키텍처 개선 히스토리 (History)

### 🛑 Phase 1: 파이프라인 불일치 버그 (ROM Latency Mismatch)
* **현상:** 특정 구간에서 5ns, 10ns 단위의 거대한 오차가 간헐적으로 발생함.
* **원인:** Vivado BRAM 기반의 캘리브레이션 ROM은 출력까지 2 Clock(Latency)이 소요되나, 연산 파이프라인에서는 1 Clock 만에 이전 펄스의 과거 데이터(Stale Data)를 래치하여 뺄셈을 수행함.
* **해결:** Coarse 누적 합산과 ROM 데이터 샘플링 시점을 `Stage 3`로 완벽히 정렬하여 동기화 달성.

### 🛑 Phase 2: 신호 무결성 저하 및 가짜 엣지 트리거 (Ringing & Glitch)
* **현상:** ILA 캡처 결과, 펄스 주기 내에서 `tdc_hit_in` 신호가 0으로 떨어지는 현상 발견 및 해당 시점에서 에러 폭증.
* **원인:** PMOD 케이블을 통해 유입된 STM32 펄스의 상승 엣지에 **링깅(Ringing) 노이즈**가 존재. TDC의 예민한 딜레이 라인이 이 찰나의 노이즈를 엣지로 착각하여 다수의 가짜 타임스탬프를 생성함.
* **해결:** 코어 내부 로직에 **데드타임(Hold-off) 마스킹 로직** 적용. 진짜 상승 엣지를 감지한 직후 `2 Cycles (10ns)` 동안 딜레이 라인의 변화를 무시하여 글리치를 완벽히 차단함.

### 🛑 Phase 3: 물리적 한계 돌파 - 메타스테빌리티 (Metastability) 극복
* **현상:** 노이즈가 제거된 깨끗한 데이터에서도 탭(Tap) 번호가 극단적인 초반(0~10) 또는 후반(260~280)일 때 필연적으로 $\pm 5\text{ns}$ 에러 발생.
* **원인:** 단일 클럭(Single-clock) 구조의 한계. 펄스가 클럭 엣지와 피코초 단위로 완벽히 충돌할 경우, 배선 지연(Routing Skew) 차이로 인해 `Fine 딜레이`와 `Coarse 카운터`가 서로 다른 클럭 주기(N과 N-1)를 캡처하는 **Setup/Hold Violation** 발생.
* **해결 (핵심 도약):** 0도(상승 엣지) 카운터와 180도(하강 엣지) 카운터를 동시에 가동하는 **Dual-Phase Coarse Counter** 구조 도입. 데이터 기반으로 탐지된 위험 구역(Danger Zone: Tap < 40 or Tap > 220)에서는, 0도 카운터 대신 가장 안전한 과거 시점에 래치된 180도 카운터에 위상 보정값(`+1`)을 더해 MUX로 스위칭하는 우주 방어 로직 구현.

### 🛑 Phase 4: 타이밍 클로저 (Timing Closure) 달성
* **현상:** Dual Counter 적용 후 Vivado 합성 시 `Setup Violation (-0.066ns)` 및 `Hold Violation (-0.134ns)` 발생.
* **원인 및 해결:**
    1. **Setup 에러:** 32비트 덧셈(`+1`)과 비교, MUX 로직이 1클럭 내에 집중되어 Logic Level이 6까지 증가함. 이를 해결하기 위해 무거운 덧셈 연산을 이전 클럭(Stage 3)에서 **미리 계산(Pre-calculation)**해두고 다음 클럭에서는 MUX만 수행하도록 파이프라인 최적화.
    2. **Hold 에러:** 파이프라인 레지스터들이 Shift Register(SRL)로 압축되면서 클럭 스큐에 의한 데이터 덮어쓰기 발생. `(* srl_style = "register" *)` 속성을 부여하여 라우터가 배선 지연을 확보할 수 있도록 강제 분리.

---

## 3. 최종 검증 결과
16,838개의 10MHz 연속 펄스를 측정하여 Python 기반 분석 스크립트로 검증한 결과, **$\pm 5\text{ns}$ 바운더리 에러 발생률 0%**를 달성. 모든 펄스 간격이 오차 없이 완벽한 일직선(100ns)을 그리는 무결점 하드웨어임을 입증함.

---

## 4. 최종 하드웨어 소스 코드 (Final Verilog)

### [모듈 1] `tdc_fmcw_core.v` (코어 및 Dual Counter MUX 로직)
```verilog
`timescale 1ns / 1ps

module tdc_fmcw_core #(
    parameter CARRY4_STAGES = 80 // 80 * 4 = 320 Taps (5ns 커버)
)(
    input wire clk,
    input wire rst_n,
    input wire hit,

    output reg [31:0]  ts_coarse,
    output reg [8:0]   ts_fine_idx,
    output reg         ts_valid
);

localparam NUM_TAPS = CARRY4_STAGES * 4;

(* keep = "true" *) wire [NUM_TAPS-1:0] carry_co;
(* keep = "true", dont_touch = "true" *) wire [NUM_TAPS-1:0] carry_o; 
(* ASYNC_REG = "TRUE", DONT_TOUCH = "TRUE" *) wire [NUM_TAPS-1:0] taps_sampled;

// -------------------------------------------------------------------------
// 1. Dual Phase Coarse Counters (0도 & 180도)
// -------------------------------------------------------------------------
reg [31:0] coarse_0;
reg [31:0] coarse_180;
reg [31:0] coarse_180_sync;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) coarse_0 <= 0;
    else coarse_0 <= coarse_0 + 1'b1;
end

always @(negedge clk or negedge rst_n) begin
    if (!rst_n) coarse_180 <= 0;
    else coarse_180 <= coarse_0; 
end

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) coarse_180_sync <= 0;
    else coarse_180_sync <= coarse_180; 
end

// -------------------------------------------------------------------------
// 2. 파이프라인 레지스터 (Hold 에러 방지 속성 적용)
// -------------------------------------------------------------------------
(* DONT_TOUCH = "TRUE" *) reg [NUM_TAPS-1:0] taps_sampled_d1;
reg taps_sampled_0_history;

reg snapshot_valid_stg2, snapshot_valid_stg3, snapshot_valid_stg4;

(* srl_style = "register" *) reg [31:0] captured_c0_stg2, captured_c180_stg2;
(* srl_style = "register" *) reg [31:0] captured_c0_stg3, captured_c180_stg3_plus1; 
(* srl_style = "register" *) reg [31:0] captured_c0_stg4, captured_c180_stg4_plus1;

reg [8:0]  fine_idx_stg4;
reg        danger_zone_stg4;

reg [3:0] stg1_halfA [0:19];
reg [3:0] stg1_halfB [0:19];
reg [7:0] stg3_group0, stg3_group1, stg3_group2, stg3_group3;

integer i;

function [3:0] popcount8;
    input [7:0] din;
    begin
        popcount8 = din[0] + din[1] + din[2] + din[3] + din[4] + din[5] + din[6] + din[7];
    end
endfunction

// -------------------------------------------------------------------------
// 3. CARRY4 CHAIN
// -------------------------------------------------------------------------
(* keep = "true" *) wire rst_high = ~rst_n;
genvar k;
generate
    for (k = 0; k < CARRY4_STAGES; k = k + 1) begin : CARRY_CHAIN
        if (k == 0) CARRY4 u_carry4 (.CO(carry_co[(k*4)+3:(k*4)]), .O(carry_o[(k*4)+3:(k*4)]), .CI(1'b0), .CYINIT(hit), .DI(4'b0000), .S(4'b1111));
        else        CARRY4 u_carry4 (.CO(carry_co[(k*4)+3:(k*4)]), .O(carry_o[(k*4)+3:(k*4)]), .CI(carry_co[(k*4)-1]), .CYINIT(1'b0), .DI(4'b0000), .S(4'b1111));
        
        (* DONT_TOUCH = "TRUE" *) FDC u_ff_0 (.Q(taps_sampled[(k*4)+0]), .C(clk), .CLR(rst_high), .D(carry_o[(k*4)+0]));								   
        (* DONT_TOUCH = "TRUE" *) FDC u_ff_1 (.Q(taps_sampled[(k*4)+1]), .C(clk), .CLR(rst_high), .D(carry_o[(k*4)+1]));									   
        (* DONT_TOUCH = "TRUE" *) FDC u_ff_2 (.Q(taps_sampled[(k*4)+2]), .C(clk), .CLR(rst_high), .D(carry_o[(k*4)+2]));		
        (* DONT_TOUCH = "TRUE" *) FDC u_ff_3 (.Q(taps_sampled[(k*4)+3]), .C(clk), .CLR(rst_high), .D(carry_o[(k*4)+3]));
    end
endgenerate

// -------------------------------------------------------------------------
// 4. MAIN LOGIC (Setup 에러 해결을 위한 Pre-calculation 파이프라인)
// -------------------------------------------------------------------------
localparam DEAD_TIME_CYCLES = 2; // 10ns 글리치 마스킹
reg [3:0] dead_time_cnt;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        taps_sampled_d1 <= 0; taps_sampled_0_history <= 0; dead_time_cnt <= 0;
        snapshot_valid_stg2 <= 0; snapshot_valid_stg3 <= 0; snapshot_valid_stg4 <= 0;
        captured_c0_stg2 <= 0; captured_c180_stg2 <= 0;
        captured_c0_stg3 <= 0; captured_c180_stg3_plus1 <= 0;
        captured_c0_stg4 <= 0; captured_c180_stg4_plus1 <= 0;
        fine_idx_stg4 <= 0; danger_zone_stg4 <= 0;
        ts_coarse <= 0; ts_valid <= 0; ts_fine_idx <= 0;
        stg3_group0 <= 0; stg3_group1 <= 0; stg3_group2 <= 0; stg3_group3 <= 0;
        for (i = 0; i < 20; i = i + 1) begin stg1_halfA[i] <= 0; stg1_halfB[i] <= 0; end
    end 
    else begin
        // [Stage 1] 
        taps_sampled_d1 <= taps_sampled;
        taps_sampled_0_history <= taps_sampled_d1[0]; 

        // [Stage 2] 데드타임 마스킹 및 Dual Counter 캡처
        if (dead_time_cnt > 0) begin
            dead_time_cnt <= dead_time_cnt - 1'b1; 
            snapshot_valid_stg2 <= 1'b0;
        end
        else if (taps_sampled_d1[0] && !taps_sampled_0_history) begin
            dead_time_cnt <= DEAD_TIME_CYCLES; 
            captured_c0_stg2   <= coarse_0;
            captured_c180_stg2 <= coarse_180_sync;
            
            for (i = 0; i < 20; i = i + 1) begin
                stg1_halfA[i] <= popcount8(taps_sampled_d1[i*16 +: 8]);
                stg1_halfB[i] <= popcount8(taps_sampled_d1[i*16+8 +: 8]);
            end
            snapshot_valid_stg2 <= 1'b1;
        end else begin
            snapshot_valid_stg2 <= 1'b0;
        end

        // [Stage 3] 부분 합산 및 180도 카운터 위상보상(+1) 선행 계산
        if (snapshot_valid_stg2) begin
            stg3_group0 <= stg1_halfA[0]+stg1_halfB[0] + stg1_halfA[1]+stg1_halfB[1] + stg1_halfA[2]+stg1_halfB[2] + stg1_halfA[3]+stg1_halfB[3] + stg1_halfA[4]+stg1_halfB[4];
            stg3_group1 <= stg1_halfA[5]+stg1_halfB[5] + stg1_halfA[6]+stg1_halfB[6] + stg1_halfA[7]+stg1_halfB[7] + stg1_halfA[8]+stg1_halfB[8] + stg1_halfA[9]+stg1_halfB[9];
            stg3_group2 <= stg1_halfA[10]+stg1_halfB[10] + stg1_halfA[11]+stg1_halfB[11] + stg1_halfA[12]+stg1_halfB[12] + stg1_halfA[13]+stg1_halfB[13] + stg1_halfA[14]+stg1_halfB[14];
            stg3_group3 <= stg1_halfA[15]+stg1_halfB[15] + stg1_halfA[16]+stg1_halfB[16] + stg1_halfA[17]+stg1_halfB[17] + stg1_halfA[18]+stg1_halfB[18] + stg1_halfA[19]+stg1_halfB[19];
            
            captured_c0_stg3 <= captured_c0_stg2;
            captured_c180_stg3_plus1 <= captured_c180_stg2 + 1'b1; // Setup 여유 확보
            
            snapshot_valid_stg3 <= 1'b1;
        end else begin
            snapshot_valid_stg3 <= 1'b0;
        end

        // [Stage 4] Fine 합산 및 Danger Zone 판별 (1-bit 저장으로 Fanout 최소화)
        if (snapshot_valid_stg3) begin
            begin : CALC_FINE
                reg [8:0] sum_fine;
                sum_fine = stg3_group0 + stg3_group1 + stg3_group2 + stg3_group3;
                fine_idx_stg4 <= sum_fine;
                danger_zone_stg4 <= (sum_fine < 9'd40 || sum_fine > 9'd220); // 넉넉한 Threshold
            end
            captured_c0_stg4 <= captured_c0_stg3;
            captured_c180_stg4_plus1 <= captured_c180_stg3_plus1;
            snapshot_valid_stg4 <= 1'b1;
        end else begin
            snapshot_valid_stg4 <= 1'b0;
        end

        // [Stage 5] 1-Bit 플래그 기반 초고속 MUX 스위칭
        if (snapshot_valid_stg4) begin
            ts_fine_idx <= fine_idx_stg4;
            if (danger_zone_stg4) ts_coarse <= captured_c180_stg4_plus1; 
            else                  ts_coarse <= captured_c0_stg4;          
            ts_valid <= 1'b1;
        end else begin
            ts_valid <= 1'b0;
        end
    end
end
endmodule
```

### [모듈 2] `tdc_timestamp_calc.v` (절대 시간 산출 순수 파이프라인)
```verilog
`timescale 1ns / 1ps

module tdc_timestamp_calc (
    input  wire         clk,
    input  wire         rst_n,
    
    input  wire [31:0]  ts_coarse,
    input  wire [8:0]   ts_fine_idx,
    input  wire         ts_valid,
    input  wire         hit,         
    
    output wire [63:0]  timestamp_ps,
    output wire         timestamp_valid,
    
    output wire         hit_out,
    output wire [8:0]   fine_idx_out,
    output wire [31:0]  coarse_out
);

    wire [12:0] calibrated_fine_ps;

    // Vivado ROM IP (Latency 반드시 2로 설정)
    tdc_calib_rom u_lut_rom (
        .clka  (clk), .ena   (1'b1), .addra (ts_fine_idx), .douta (calibrated_fine_ps)  
    );

    // 파이프라인 레지스터
    reg [15:0] ts_coarse_L_d1, ts_coarse_H_d1;
    reg        ts_valid_d1, hit_d1;
    reg [8:0]  ts_fine_idx_d1;

    (* use_dsp = "yes" *) reg [31:0] mul_L_d2;
    (* use_dsp = "yes" *) reg [47:0] mul_H_d2; 
    reg        ts_valid_d2, hit_d2;
    reg [8:0]  ts_fine_idx_d2;
    reg [31:0] ts_coarse_d2;

    reg [63:0] coarse_total_ps_d3;
    reg [12:0] calibrated_fine_ps_d3; 
    reg        ts_valid_d3, hit_d3;
    reg [8:0]  ts_fine_idx_d3;
    reg [31:0] ts_coarse_d3;

    reg [32:0] sub_lower_d4;  
    reg [31:0] upper_half_d4; 
    reg        ts_valid_d4, hit_d4;
    reg [8:0]  ts_fine_idx_d4;
    reg [31:0] ts_coarse_d4;

    reg [63:0] final_absolute_time_ps_reg;
    reg        ts_valid_d5, hit_d5;
    reg [8:0]  ts_fine_idx_d5;
    reg [31:0] ts_coarse_d5;

    always @(posedge clk) begin
        if (!rst_n) begin
            ts_coarse_L_d1 <= 0; ts_coarse_H_d1 <= 0; ts_valid_d1 <= 0; hit_d1 <= 0; ts_fine_idx_d1 <= 0;
            mul_L_d2 <= 0; mul_H_d2 <= 0; ts_coarse_d2 <= 0; ts_valid_d2 <= 0; hit_d2 <= 0; ts_fine_idx_d2 <= 0;
            coarse_total_ps_d3 <= 0; calibrated_fine_ps_d3 <= 0; ts_coarse_d3 <= 0; ts_valid_d3 <= 0; hit_d3 <= 0; ts_fine_idx_d3 <= 0;
            sub_lower_d4 <= 0; upper_half_d4 <= 0; ts_coarse_d4 <= 0; ts_valid_d4 <= 0; hit_d4 <= 0; ts_fine_idx_d4 <= 0; 
            final_absolute_time_ps_reg <= 0; ts_coarse_d5 <= 0; ts_valid_d5 <= 0; hit_d5 <= 0; ts_fine_idx_d5 <= 0; 
        end else begin
            // Stage 1
            ts_coarse_L_d1 <= ts_coarse[15:0]; ts_coarse_H_d1 <= ts_coarse[31:16];
            ts_valid_d1 <= ts_valid; hit_d1 <= hit; ts_fine_idx_d1 <= ts_fine_idx;

            // Stage 2 (곱셈)
            mul_L_d2 <= ts_coarse_L_d1 * 16'd5000; mul_H_d2 <= ts_coarse_H_d1 * 16'd5000;
            ts_coarse_d2 <= {ts_coarse_H_d1, ts_coarse_L_d1};
            ts_valid_d2  <= ts_valid_d1; hit_d2 <= hit_d1; ts_fine_idx_d2 <= ts_fine_idx_d1;

            // Stage 3 (ROM Latency 정렬 및 샘플링)
            coarse_total_ps_d3 <= {mul_H_d2[47:0], 16'd0} + mul_L_d2;
            calibrated_fine_ps_d3 <= calibrated_fine_ps; 
            ts_coarse_d3 <= ts_coarse_d2; ts_valid_d3 <= ts_valid_d2; hit_d3 <= hit_d2; ts_fine_idx_d3 <= ts_fine_idx_d2;

            // Stage 4 (Borrow-Lookahead 연산)
            sub_lower_d4  <= {1'b0, coarse_total_ps_d3[31:0]} - {20'd0, calibrated_fine_ps_d3};
            upper_half_d4 <= coarse_total_ps_d3[63:32]; 
            ts_coarse_d4 <= ts_coarse_d3; ts_valid_d4 <= ts_valid_d3; hit_d4 <= hit_d3; ts_fine_idx_d4 <= ts_fine_idx_d3;

            // Stage 5 (최종 출력)
            final_absolute_time_ps_reg <= { (upper_half_d4 - {31'd0, sub_lower_d4[32]}), sub_lower_d4[31:0] };
            ts_coarse_d5 <= ts_coarse_d4; ts_valid_d5 <= ts_valid_d4; hit_d5 <= hit_d4; ts_fine_idx_d5 <= ts_fine_idx_d4;
        end
    end

    assign timestamp_ps    = final_absolute_time_ps_reg;
    assign timestamp_valid = ts_valid_d5;
    assign hit_out      = hit_d5;
    assign fine_idx_out = ts_fine_idx_d5;
    assign coarse_out   = ts_coarse_d5;

endmodule
```