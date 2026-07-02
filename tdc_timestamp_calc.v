`timescale 1ns / 1ps

module tdc_timestamp_calc (
    input  wire         clk,
    input  wire         rst_n,
    
    // TDC Core에서 나오는 Raw 데이터
    input  wire [31:0]  ts_coarse,
    input  wire [8:0]   ts_fine_idx,
    input  wire         ts_valid,
    input  wire         hit,         
    
    // 최종 산출된 64비트 절대 시간 (단위: ps)
    output wire [63:0]  timestamp_ps,
    output wire         timestamp_valid,
    
    // ILA 디버깅용 (유지)
    output wire         hit_out,
    output wire [8:0]   fine_idx_out,
    output wire [31:0]  coarse_out
);

    wire [12:0] calibrated_fine_ps;

    // Vivado ROM IP (Latency 반드시 2)
    tdc_calib_rom u_lut_rom (
        .clka  (clk),            
        .ena   (1'b1),               
        .addra (ts_fine_idx),        
        .douta (calibrated_fine_ps)  
    );

    // [Stage 1] 데이터 버퍼링
    reg [15:0] ts_coarse_L_d1, ts_coarse_H_d1;
    reg        ts_valid_d1, hit_d1;
    reg [8:0]  ts_fine_idx_d1;

    // [Stage 2] DSP를 이용한 Coarse * 5000 곱셈
    (* use_dsp = "yes" *) reg [31:0] mul_L_d2;
    (* use_dsp = "yes" *) reg [47:0] mul_H_d2; 
    reg        ts_valid_d2, hit_d2;
    reg [8:0]  ts_fine_idx_d2;
    reg [31:0] ts_coarse_d2;

    // [Stage 3] ★ ROM 데이터 캡처 (파이프라인 동기화의 핵심) 및 Coarse 합산
    reg [63:0] coarse_total_ps_d3;
    reg [12:0] calibrated_fine_ps_d3; 
    reg        ts_valid_d3, hit_d3;
    reg [8:0]  ts_fine_idx_d3;
    reg [31:0] ts_coarse_d3;

    // [Stage 4] Borrow-Lookahead 뺄셈
    reg [32:0] sub_lower_d4;  
    reg [31:0] upper_half_d4; 
    reg        ts_valid_d4, hit_d4;
    reg [8:0]  ts_fine_idx_d4;
    reg [31:0] ts_coarse_d4;

    // [Stage 5] 최종 병합
    reg [63:0] final_absolute_time_ps_reg;
    reg        ts_valid_d5, hit_d5;
    reg [8:0]  ts_fine_idx_d5;
    reg [31:0] ts_coarse_d5;

    always @(posedge clk) begin
        if (!rst_n) begin
            ts_coarse_L_d1 <= 0; ts_coarse_H_d1 <= 0; ts_valid_d1 <= 0; hit_d1 <= 0; ts_fine_idx_d1 <= 0;
            mul_L_d2 <= 0; mul_H_d2 <= 0; ts_coarse_d2 <= 0; ts_valid_d2 <= 0; hit_d2 <= 0; ts_fine_idx_d2 <= 0;
            coarse_total_ps_d3 <= 0; calibrated_fine_ps_d3 <= 0; ts_coarse_d3 <= 0; ts_valid_d3 <= 0; hit_d3 <= 0; ts_fine_idx_d3 <= 0;
            sub_lower_d4 <= 0; upper_half_d4 <= 0; ts_valid_d4 <= 0; hit_d4 <= 0; ts_fine_idx_d4 <= 0; ts_coarse_d4 <= 0; 
            final_absolute_time_ps_reg <= 0; ts_valid_d5 <= 0; hit_d5 <= 0; ts_fine_idx_d5 <= 0; ts_coarse_d5 <= 0; 
        end else begin
            // [Stage 1] 
            ts_coarse_L_d1 <= ts_coarse[15:0]; 
            ts_coarse_H_d1 <= ts_coarse[31:16];
            ts_valid_d1    <= ts_valid; 
            hit_d1         <= hit; 
            ts_fine_idx_d1 <= ts_fine_idx;

            // [Stage 2] 곱셈은 1주기만에 끝남 (ROM은 아직 출력 안 나옴)
            mul_L_d2 <= ts_coarse_L_d1 * 16'd5000; 
            mul_H_d2 <= ts_coarse_H_d1 * 16'd5000;
            ts_coarse_d2   <= {ts_coarse_H_d1, ts_coarse_L_d1};
            ts_valid_d2    <= ts_valid_d1; 
            hit_d2         <= hit_d1; 
            ts_fine_idx_d2 <= ts_fine_idx_d1;

            // [Stage 3] ROM 데이터 도달(Latency 2). 여기서 샘플링!
            coarse_total_ps_d3 <= {mul_H_d2[47:0], 16'd0} + mul_L_d2;
            calibrated_fine_ps_d3 <= calibrated_fine_ps; // ★ 가장 순수한 원본 딜레이 데이터
            ts_coarse_d3          <= ts_coarse_d2;
            ts_valid_d3           <= ts_valid_d2; 
            hit_d3                <= hit_d2; 
            ts_fine_idx_d3        <= ts_fine_idx_d2;

            // [Stage 4] 뺄셈
            sub_lower_d4  <= {1'b0, coarse_total_ps_d3[31:0]} - {20'd0, calibrated_fine_ps_d3};
            upper_half_d4 <= coarse_total_ps_d3[63:32]; 
            ts_coarse_d4   <= ts_coarse_d3;
            ts_valid_d4    <= ts_valid_d3; 
            hit_d4         <= hit_d3; 
            ts_fine_idx_d4 <= ts_fine_idx_d3;

            // [Stage 5]
            final_absolute_time_ps_reg <= { (upper_half_d4 - {31'd0, sub_lower_d4[32]}), sub_lower_d4[31:0] };
            ts_coarse_d5   <= ts_coarse_d4; 
            ts_valid_d5    <= ts_valid_d4; 
            hit_d5         <= hit_d4; 
            ts_fine_idx_d5 <= ts_fine_idx_d4;
        end
    end

    assign timestamp_ps    = final_absolute_time_ps_reg;
    assign timestamp_valid = ts_valid_d5;
    assign hit_out      = hit_d5;
    assign fine_idx_out = ts_fine_idx_d5;
    assign coarse_out   = ts_coarse_d5;

endmodule