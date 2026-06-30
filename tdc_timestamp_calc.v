`timescale 1ns / 1ps

module tdc_timestamp_calc (
    input  wire         clk,
    input  wire         rst_n,
    
    // TDC Core에서 나오는 Raw 데이터
    input  wire [31:0]  ts_coarse,
    input  wire [8:0]   ts_fine_idx,
    input  wire         ts_valid,
    input  wire         hit,         // 원본 코드의 test_hit 유지용
    
    // 최종 산출된 64비트 절대 시간 (단위: ps)
    output wire [63:0]  timestamp_ps,
    output wire         timestamp_valid,
    
    // 디버깅 및 하위 모듈 전달용 지연 신호
    output wire         hit_out,
    output wire [8:0]   fine_idx_out,
    output wire [31:0]  coarse_out
);

    // =====================================================
    // 0. ROM 인스턴시에이션 (Latency: 반드시 2 Clock 설정!)
    // =====================================================
    wire [12:0] calibrated_fine_ps;

    // Vivado Block Memory Generator IP 
    // - Memory Type: Single Port ROM
    // - Port A Options: Width 13, Depth 512
    // - ★ Primitives Output Register 체크 (Latency 2) ★
    tdc_calib_rom u_lut_rom (
        .clka  (clk),            
        .ena   (1'b1),               
        .addra (ts_fine_idx),        
        .douta (calibrated_fine_ps)  
    );

    // =====================================================
    // 1. 파이프라인 레지스터 선언
    // =====================================================
    // Stage 1
    reg [15:0] ts_coarse_L_d1, ts_coarse_H_d1;
    reg        ts_valid_d1, hit_d1;
    reg [8:0]  ts_fine_idx_d1;

    // Stage 2 (DSP 사용 명시)
    (* use_dsp = "yes" *) reg [31:0] mul_L_d2;
    (* use_dsp = "yes" *) reg [47:0] mul_H_d2; // 상위 비트 시프트 연산을 위한 여유 공간
    reg [12:0] calibrated_fine_ps_d2;
    reg        ts_valid_d2, hit_d2;
    reg [8:0]  ts_fine_idx_d2;
    reg [31:0] ts_coarse_d2;

    // Stage 3
    reg [63:0] coarse_total_ps_d3;
    reg [12:0] calibrated_fine_ps_d3; 
    reg        ts_valid_d3, hit_d3;
    reg [8:0]  ts_fine_idx_d3;
    reg [31:0] ts_coarse_d3;

    // Stage 4
    reg [32:0] sub_lower_d4;  // 최상위 비트(32번)는 Borrow(빌림) 비트
    reg [31:0] upper_half_d4; 
    reg        ts_valid_d4, hit_d4;
    reg [8:0]  ts_fine_idx_d4;
    reg [31:0] ts_coarse_d4;

    // Stage 5
    reg [63:0] final_absolute_time_ps_reg;
    reg        ts_valid_d5, hit_d5;
    reg [8:0]  ts_fine_idx_d5;
    reg [31:0] ts_coarse_d5;

    // =====================================================
    // 2. 5-Stage 파이프라인 메인 로직
    // =====================================================
    always @(posedge clk) begin
        if (!rst_n) begin
            ts_coarse_L_d1 <= 0; ts_coarse_H_d1 <= 0; ts_valid_d1 <= 0; hit_d1 <= 0; ts_fine_idx_d1 <= 0;
            mul_L_d2 <= 0; mul_H_d2 <= 0; calibrated_fine_ps_d2 <= 0; ts_coarse_d2 <= 0; ts_valid_d2 <= 0; hit_d2 <= 0; ts_fine_idx_d2 <= 0;
            coarse_total_ps_d3 <= 0; calibrated_fine_ps_d3 <= 0; ts_coarse_d3 <= 0; ts_valid_d3 <= 0; hit_d3 <= 0; ts_fine_idx_d3 <= 0;
            sub_lower_d4 <= 0; upper_half_d4 <= 0; ts_valid_d4 <= 0; hit_d4 <= 0; ts_fine_idx_d4 <= 0; ts_coarse_d4 <= 0; 
            final_absolute_time_ps_reg <= 0; ts_valid_d5 <= 0; hit_d5 <= 0; ts_fine_idx_d5 <= 0; ts_coarse_d5 <= 0; 
        end else begin
            // ---------------------------------------------------------
            // [Stage 1] Coarse 16비트 분할 및 제어 신호 버퍼링
            // ---------------------------------------------------------
            ts_coarse_L_d1 <= ts_coarse[15:0]; 
            ts_coarse_H_d1 <= ts_coarse[31:16];
            ts_valid_d1    <= ts_valid; 
            hit_d1         <= hit; 
            ts_fine_idx_d1 <= ts_fine_idx;

            // ---------------------------------------------------------
            // [Stage 2] DSP 곱셈 (x 5000) 및 ROM 데이터 샘플링
            // ---------------------------------------------------------
            // 1주기(5000ps) 곱셈 수행. DSP 블록(18x25)에 완벽히 매핑됨
            mul_L_d2 <= ts_coarse_L_d1 * 16'd5000; 
            mul_H_d2 <= ts_coarse_H_d1 * 16'd5000;
            
            // ROM Latency가 2클럭이므로, 여기서 출력되는 값을 캡처
            calibrated_fine_ps_d2 <= calibrated_fine_ps; 
            
            ts_coarse_d2   <= {ts_coarse_H_d1, ts_coarse_L_d1};
            ts_valid_d2    <= ts_valid_d1; 
            hit_d2         <= hit_d1; 
            ts_fine_idx_d2 <= ts_fine_idx_d1;

            // ---------------------------------------------------------
            // [Stage 3] 64비트 Coarse 누적 합 병합
            // ---------------------------------------------------------
            coarse_total_ps_d3 <= {mul_H_d2[47:0], 16'd0} + mul_L_d2;
            
            calibrated_fine_ps_d3 <= calibrated_fine_ps_d2; 
            ts_coarse_d3          <= ts_coarse_d2;
            ts_valid_d3           <= ts_valid_d2; 
            hit_d3                <= hit_d2; 
            ts_fine_idx_d3        <= ts_fine_idx_d2;

            // ---------------------------------------------------------
            // [Stage 4] Borrow-Lookahead 하위 32비트 뺄셈
            // ---------------------------------------------------------
            // {1'b0}을 추가하여 33비트로 확장 -> sub_lower_d4[32]가 Borrow Bit 역할
            sub_lower_d4  <= {1'b0, coarse_total_ps_d3[31:0]} - {20'd0, calibrated_fine_ps_d3};
            upper_half_d4 <= coarse_total_ps_d3[63:32]; 
            
            ts_coarse_d4   <= ts_coarse_d3;
            ts_valid_d4    <= ts_valid_d3; 
            hit_d4         <= hit_d3; 
            ts_fine_idx_d4 <= ts_fine_idx_d3;

            // ---------------------------------------------------------
            // [Stage 5] 상위 32비트 Borrow 보상 및 64비트 최종 병합
            // ---------------------------------------------------------
            final_absolute_time_ps_reg <= { (upper_half_d4 - {31'd0, sub_lower_d4[32]}), sub_lower_d4[31:0] };
            
            ts_coarse_d5   <= ts_coarse_d4; 
            ts_valid_d5    <= ts_valid_d4; 
            hit_d5         <= hit_d4; 
            ts_fine_idx_d5 <= ts_fine_idx_d4;
        end
    end

    // =====================================================
    // 3. 최종 출력 할당
    // =====================================================
    assign timestamp_ps    = final_absolute_time_ps_reg;
    assign timestamp_valid = ts_valid_d5;
    
    // 하위 모듈 전달 및 ILA 디버깅용 지연 신호
    assign hit_out      = hit_d5;
    assign fine_idx_out = ts_fine_idx_d5;
    assign coarse_out   = ts_coarse_d5;

endmodule