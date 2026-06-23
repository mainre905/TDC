`timescale 1ns / 1ps

module tdc_test_top (
    input wire clk_125,
    input wire rst_n,
    input wire btn_shift,
    output wire [3:0] led
);

// 1: MMCM Phase Shift 정밀 검증 모드 (동기식 Hit 사용)
// 0: 링 오실레이터 Calibration 모드 (비동기 Hit 사용)
parameter TEST_MODE_MMCM = 1; 

wire clk_200_fixed;   
wire clk_200_shifted; 
wire clk_locked;
wire clk_wiz_rst = rst_n;

wire psen, psincdec, psdone, ps_busy;

wire [8:0] current_loop_cnt; 

clk_wiz_0 u_clk (
    .clk_in1   (clk_125),
    .reset     (clk_wiz_rst),
    .clk_out1  (clk_200_fixed),   
    .clk_out2  (clk_200_shifted), 
    .psclk     (clk_200_fixed),
    .psen      (psen),
    .psincdec  (psincdec),
    .psdone    (psdone),
    .locked    (clk_locked)
);

mmcm_phase_shifter u_ps_ctrl (
    .clk         (clk_200_fixed),
    .rst_n       (clk_locked),
    .start_shift (btn_shift),
    .psen        (psen),
    .psincdec    (psincdec),
    .psdone      (psdone),
    .busy        (ps_busy),
    .loop_cnt    (current_loop_cnt) // ★ 새로 추가된 출력 연결
);


// 동기식 Hit 생성기
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

// 비동기 링 오실레이터 Hit 생성기
(* ALLOW_COMBINATORIAL_LOOPS = "TRUE", KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
wire [30:0] ro_chain;
genvar r;
generate
    for(r=0; r<30; r=r+1) begin : RO_LOOP
        (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
        LUT1 #(.INIT(2'h1)) u_lut_inv (.I0(ro_chain[r]), .O (ro_chain[r+1]));
    end
endgenerate
(* KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
LUT1 #(.INIT(2'h1)) u_lut_inv_fb (.I0(ro_chain[30]), .O (ro_chain[0]));

wire ro_clk_buffered;
BUFG u_bufg_ro (.I(ro_chain[30]), .O(ro_clk_buffered));

reg [15:0] ro_divider_cnt = 0;
always @(posedge ro_clk_buffered) ro_divider_cnt <= ro_divider_cnt + 1'b1;
wire hit_random = ro_divider_cnt[5]; 

// 모드 분기 MUX
wire test_hit  = (TEST_MODE_MMCM) ? test_hit_sync : hit_random;
wire tdc_clk   = (TEST_MODE_MMCM) ? clk_200_shifted : clk_200_fixed;

// TDC 코어 연동
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

assign led[0] = clk_locked;
assign led[1] = ps_busy; 
assign led[3:2] = 2'b00;

// =====================================================
// ★ 5-Stage ROM 기반 실시간 캘리브레이션 
// =====================================================
wire [12:0] calibrated_fine_ps;

reg [15:0] ts_coarse_L_d1, ts_coarse_H_d1;
reg        ts_valid_d1, test_hit_d1;
reg [8:0]  ts_fine_idx_d1;

(* use_dsp = "yes" *) reg [31:0] mul_L_d2;
(* use_dsp = "yes" *) reg [47:0] mul_H_d2;
reg [12:0] calibrated_fine_ps_d2;
reg        ts_valid_d2, test_hit_d2;
reg [8:0]  ts_fine_idx_d2;
reg [31:0] ts_coarse_d2;

reg [63:0] coarse_total_ps_d3;
reg [12:0] calibrated_fine_ps_d3; 
reg        ts_valid_d3, test_hit_d3;
reg [8:0]  ts_fine_idx_d3;
reg [31:0] ts_coarse_d3;

reg [32:0] sub_lower_d4;  
reg [31:0] upper_half_d4; 
reg        ts_valid_d4, test_hit_d4;
reg [8:0]  ts_fine_idx_d4;
reg [31:0] ts_coarse_d4;

reg [63:0] final_absolute_time_ps_reg;
reg        ts_valid_d5, test_hit_d5;
reg [8:0]  ts_fine_idx_d5;
reg [31:0] ts_coarse_d5;

blk_mem_gen_0 u_lut_rom (
  .clka  (tdc_clk),            
  .ena   (1'b1),               
  .addra (ts_fine_idx),        
  .douta (calibrated_fine_ps)  
);

always @(posedge tdc_clk) begin
    if (!clk_locked) begin
        ts_coarse_L_d1 <= 0; ts_coarse_H_d1 <= 0; ts_valid_d1 <= 0; test_hit_d1 <= 0; ts_fine_idx_d1 <= 0;
        mul_L_d2 <= 0; mul_H_d2 <= 0; calibrated_fine_ps_d2 <= 0; ts_coarse_d2 <= 0; ts_valid_d2 <= 0; test_hit_d2 <= 0; ts_fine_idx_d2 <= 0;
        coarse_total_ps_d3 <= 0; calibrated_fine_ps_d3 <= 0; ts_coarse_d3 <= 0; ts_valid_d3 <= 0; test_hit_d3 <= 0; ts_fine_idx_d3 <= 0;
        sub_lower_d4 <= 0; upper_half_d4 <= 0; ts_valid_d4 <= 0; test_hit_d4 <= 0; ts_fine_idx_d4 <= 0; ts_coarse_d4 <= 0; 
        final_absolute_time_ps_reg <= 0; ts_valid_d5 <= 0; test_hit_d5 <= 0; ts_fine_idx_d5 <= 0; ts_coarse_d5 <= 0; 
    end else begin
        // Stage 1
        ts_coarse_L_d1 <= ts_coarse[15:0]; ts_coarse_H_d1 <= ts_coarse[31:16];
        ts_valid_d1 <= ts_valid; test_hit_d1 <= test_hit; ts_fine_idx_d1 <= ts_fine_idx;

        // Stage 2
        mul_L_d2 <= ts_coarse_L_d1 * 16'd5000; mul_H_d2 <= ts_coarse_H_d1 * 16'd5000;
        calibrated_fine_ps_d2 <= calibrated_fine_ps; ts_coarse_d2 <= {ts_coarse_H_d1, ts_coarse_L_d1};
        ts_valid_d2 <= ts_valid_d1; test_hit_d2 <= test_hit_d1; ts_fine_idx_d2 <= ts_fine_idx_d1;

        // Stage 3
        coarse_total_ps_d3 <= {mul_H_d2[47:0], 16'd0} + mul_L_d2;
        calibrated_fine_ps_d3 <= calibrated_fine_ps_d2; ts_coarse_d3 <= ts_coarse_d2;
        ts_valid_d3 <= ts_valid_d2; test_hit_d3 <= test_hit_d2; ts_fine_idx_d3 <= ts_fine_idx_d2;

        // Stage 4
        sub_lower_d4 <= {1'b0, coarse_total_ps_d3[31:0]} - {20'd0, calibrated_fine_ps_d3};
        upper_half_d4 <= coarse_total_ps_d3[63:32]; ts_coarse_d4 <= ts_coarse_d3;
        ts_valid_d4 <= ts_valid_d3; test_hit_d4 <= test_hit_d3; ts_fine_idx_d4 <= ts_fine_idx_d3;

        // Stage 5
        final_absolute_time_ps_reg <= { (upper_half_d4 - {31'd0, sub_lower_d4[32]}), sub_lower_d4[31:0] };
        ts_coarse_d5 <= ts_coarse_d4; ts_valid_d5 <= ts_valid_d4; test_hit_d5 <= test_hit_d4; ts_fine_idx_d5 <= ts_fine_idx_d4;
    end
end

// =====================================================
// ★ ILA 연동
// =====================================================
ila_0 your_ila_instance (
    .clk    (tdc_clk),                 
    .probe0 (ts_valid_d5),               // Width: 1  (측정 완료 펄스)
    .probe1 (ts_coarse_d5),              // Width: 32 (파이썬 분석용)
    .probe2 (ts_fine_idx_d5),            // Width: 9  (파이썬 분석용 원시 데이터)
    .probe3 (final_absolute_time_ps_reg),// Width: 64 (최종 계산된 물리 시간)
    .probe4 (psdone),                    // Width: 1  (MMCM 자동 스윕 트리거용)
    .probe5 (current_loop_cnt)           // Width: 9  (현재 스텝: 0~280)
);


endmodule
