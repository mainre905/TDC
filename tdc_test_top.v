`timescale 1ns / 1ps

module tdc_test_top (
    input wire clk_125,
    input wire rst_n,
    input wire btn_shift, // 위상 시프트 트리거용 버튼 입력
    output wire [3:0] led
);

// =====================================================
// 0. 테스트 모드 선택 파라미터 (스위치 역할)
// =====================================================
// 1: MMCM Phase Shift 정밀 검증 모드 (동기식 Hit 사용)
// 0: 링 오실레이터 Calibration 모드 (비동기 Hit 사용)
parameter TEST_MODE_MMCM = 1; 

// =====================================================
// 1. Clock Generation (고정 클럭 및 시프트 클럭 출력)
// =====================================================
wire clk_200_fixed;   
wire clk_200_shifted; 
wire clk_locked;
wire clk_wiz_rst;

assign clk_wiz_rst = rst_n;

wire psen;
wire psincdec;
wire psdone;
wire ps_busy;

clk_wiz_0 u_clk (
    .clk_in1   (clk_125),
    .reset     (clk_wiz_rst),
    .clk_out1  (clk_200_fixed),   
    .clk_out2  (clk_200_shifted), 
    
    // Dynamic Phase Shift 인터페이스
    .psclk     (clk_200_fixed),
    .psen      (psen),
    .psincdec  (psincdec),
    .psdone    (psdone),
    .locked    (clk_locked)
);

// =====================================================
// 2. MMCM Phase Shift 제어 모듈 (FSM)
// =====================================================
mmcm_phase_shifter u_ps_ctrl (
    .clk         (clk_200_fixed),
    .rst_n       (clk_locked),
    .start_shift (btn_shift),
    .psen        (psen),
    .psincdec    (psincdec),
    .psdone      (psdone),
    .busy        (ps_busy)
);

// =====================================================
// 3. 동기식 Hit 생성기 (MMCM 검증용 기준 신호)
// =====================================================
reg [15:0] sync_cnt;
reg test_hit_sync;

always @(posedge clk_200_fixed) begin
    if (!clk_locked) begin
        sync_cnt <= 16'd0;
        test_hit_sync <= 1'b0;
    end else begin
        if (sync_cnt == 16'd49999) begin
            sync_cnt <= 16'd0;
            test_hit_sync <= 1'b1;
        end else begin
            sync_cnt <= sync_cnt + 1'b1;
            test_hit_sync <= 1'b0;
        end
    end
end

// =====================================================
// 4. 비동기 링 오실레이터 Hit 생성기 (Calibration 용)
// =====================================================
(* ALLOW_COMBINATORIAL_LOOPS = "TRUE", KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
wire [30:0] ro_chain;

genvar r;
generate
    for(r=0; r<30; r=r+1) begin : RO_LOOP
        (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
        LUT1 #(.INIT(2'h1)) u_lut_inv (
            .I0(ro_chain[r]),
            .O (ro_chain[r+1])
        );
    end
endgenerate

(* KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
LUT1 #(.INIT(2'h1)) u_lut_inv_fb (
    .I0(ro_chain[30]),
    .O (ro_chain[0])
);

wire ro_clk_buffered;
BUFG u_bufg_ro (
    .I(ro_chain[30]),
    .O(ro_clk_buffered)
);

reg [15:0] ro_divider_cnt = 0;
always @(posedge ro_clk_buffered) begin
    ro_divider_cnt <= ro_divider_cnt + 1'b1;
end

wire hit_random = ro_divider_cnt[5]; 

// =====================================================
// 5. MUX (테스트 모드 선택기)
// =====================================================
wire test_hit  = (TEST_MODE_MMCM) ? test_hit_sync : hit_random;
wire tdc_clk   = (TEST_MODE_MMCM) ? clk_200_shifted : clk_200_fixed;

// =====================================================
// 6. TDC 코어 연동
// =====================================================
wire [31:0] ts_coarse;
wire [8:0]  ts_fine_idx;
wire        ts_valid;

tdc_fmcw_core u_tdc (
    .clk         (tdc_clk), 
    .rst_n       (clk_locked),
    .hit         (test_hit),
    .ts_coarse   (ts_coarse),
    .ts_fine_idx (ts_fine_idx),
    .ts_valid    (ts_valid)
);

// 생존 확인용 LED
assign led[0] = clk_locked;
assign led[1] = ps_busy; 
assign led[3:2] = 2'b00;


// =====================================================
// ★ 7. ROM 기반 실시간 캘리브레이션 (4-Stage 최고속 파이프라인)
// =====================================================
wire [12:0] calibrated_fine_ps;

// [Stage 1] 입력 래치 및 16비트 분할
reg [15:0] ts_coarse_L_d1;
reg [15:0] ts_coarse_H_d1;
reg        ts_valid_d1;
reg        test_hit_d1;
reg [8:0]  ts_fine_idx_d1;

// [Stage 2] 병렬 곱셈 수행 및 ROM 출력 래치
(* use_dsp = "yes" *) reg [31:0] mul_L_d2;
(* use_dsp = "yes" *) reg [47:0] mul_H_d2;
reg [12:0] calibrated_fine_ps_d2;
reg        ts_valid_d2;
reg        test_hit_d2;
reg [8:0]  ts_fine_idx_d2;
reg [31:0] ts_coarse_d2;

// [Stage 3] 상위/하위 Coarse 시간 64비트 덧셈 (덧셈만 먼저 수행)
reg [63:0] coarse_total_ps_d3;
reg [12:0] calibrated_fine_ps_d3; // 뺄셈을 위해 데이터 유지
reg        ts_valid_d3;
reg        test_hit_d3;
reg [8:0]  ts_fine_idx_d3;
reg [31:0] ts_coarse_d3;

// [Stage 4] 최종 64비트 뺄셈 수행 (ROM 보정값 적용)
reg [63:0] final_absolute_time_ps_reg;
reg        ts_valid_d4;
reg        test_hit_d4;
reg [8:0]  ts_fine_idx_d4;
reg [31:0] ts_coarse_d4;


// ROM IP 인스턴스화
blk_mem_gen_0 u_lut_rom (
  .clka  (tdc_clk),            
  .ena   (1'b1),               
  .addra (ts_fine_idx),        // Stage 0: 주소 입력
  .douta (calibrated_fine_ps)  // Stage 1: 데이터 나옴
);

// 파이프라인 연산 처리 블록
always @(posedge tdc_clk) begin
    if (!clk_locked) begin
        // 리셋 초기화
        ts_coarse_L_d1 <= 0; ts_coarse_H_d1 <= 0; ts_valid_d1 <= 0; test_hit_d1 <= 0; ts_fine_idx_d1 <= 0;
        mul_L_d2 <= 0; mul_H_d2 <= 0; calibrated_fine_ps_d2 <= 0;
        ts_coarse_d2 <= 0; ts_valid_d2 <= 0; test_hit_d2 <= 0; ts_fine_idx_d2 <= 0;
        coarse_total_ps_d3 <= 0; calibrated_fine_ps_d3 <= 0;
        ts_coarse_d3 <= 0; ts_valid_d3 <= 0; test_hit_d3 <= 0; ts_fine_idx_d3 <= 0;
        final_absolute_time_ps_reg <= 0;
        ts_coarse_d4 <= 0; ts_valid_d4 <= 0; test_hit_d4 <= 0; ts_fine_idx_d4 <= 0;
    end else begin
        // ----------------------------------------------------
        // [Stage 1] 16비트씩 반으로 쪼개기
        // ----------------------------------------------------
        ts_coarse_L_d1 <= ts_coarse[15:0];
        ts_coarse_H_d1 <= ts_coarse[31:16];
        ts_valid_d1    <= ts_valid;
        test_hit_d1    <= test_hit;
        ts_fine_idx_d1 <= ts_fine_idx;

        // ----------------------------------------------------
        // [Stage 2] 병렬 DSP 곱셈
        // ----------------------------------------------------
        mul_L_d2              <= ts_coarse_L_d1 * 16'd5000;
        mul_H_d2              <= ts_coarse_H_d1 * 16'd5000;
        calibrated_fine_ps_d2 <= calibrated_fine_ps; // ROM에서 나온 보정값
        
        ts_coarse_d2   <= {ts_coarse_H_d1, ts_coarse_L_d1};
        ts_valid_d2    <= ts_valid_d1;
        test_hit_d2    <= test_hit_d1;
        ts_fine_idx_d2 <= ts_fine_idx_d1;

        // ----------------------------------------------------
        // [Stage 3] 64비트 덧셈 (Coarse 총 시간 병합) - "여기서 덧셈만 합니다"
        // ----------------------------------------------------
        coarse_total_ps_d3    <= {mul_H_d2[47:0], 16'd0} + mul_L_d2;
        calibrated_fine_ps_d3 <= calibrated_fine_ps_d2; // 다음 클럭으로 보정값 넘기기
        
        ts_coarse_d3   <= ts_coarse_d2;
        ts_valid_d3    <= ts_valid_d2;
        test_hit_d3    <= test_hit_d2;
        ts_fine_idx_d3 <= ts_fine_idx_d2;

        // ----------------------------------------------------
        // [Stage 4] 64비트 뺄셈 (최종 물리 시간 도출) - "여기서 뺄셈만 합니다"
        // ----------------------------------------------------
        final_absolute_time_ps_reg <= coarse_total_ps_d3 - calibrated_fine_ps_d3;
        
        ts_coarse_d4   <= ts_coarse_d3;
        ts_valid_d4    <= ts_valid_d3;
        test_hit_d4    <= test_hit_d3;
        ts_fine_idx_d4 <= ts_fine_idx_d3;
    end
end

// =====================================================
// ★ 8. ILA 모듈 연동 
// =====================================================
// Stage 4까지 밀려난 신호들을 모아서 관찰해야 짝이 맞습니다!
ila_0 your_ila_instance (
    .clk    (tdc_clk),                 
    .probe0 (ts_valid_d4),             // d4 로 변경
    .probe1 (ts_coarse_d4),            // d4 로 변경
    .probe2 (ts_fine_idx_d4),          // d4 로 변경
    .probe3 (test_hit_d4),             // d4 로 변경
    .probe4 (final_absolute_time_ps_reg) 
);
endmodule
