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

localparam NUM_TAPS = CARRY4_STAGES * 4; // 320

(* keep = "true" *) wire [NUM_TAPS-1:0] carry_co;
(* keep = "true", dont_touch = "true" *) wire [NUM_TAPS-1:0] carry_o; 
(* ASYNC_REG = "TRUE", DONT_TOUCH = "TRUE" *) wire [NUM_TAPS-1:0] taps_sampled;

// -------------------------------------------------------------------------
// 1. Dual Phase Coarse Counters
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
// 2. 파이프라인 레지스터 (★ Hold 에러 방지 속성 추가 ★)
// -------------------------------------------------------------------------
(* DONT_TOUCH = "TRUE" *) reg [NUM_TAPS-1:0] taps_sampled_d1;
reg taps_sampled_0_history;

reg snapshot_valid_stg2, snapshot_valid_stg3, snapshot_valid_stg4;

// Vivado가 Shift Register로 압축하는 것을 막아 라우터가 배선 지연을 추가할 수 있게 돕습니다.
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
        popcount8 = din[0] + din[1] + din[2] + din[3] +
                    din[4] + din[5] + din[6] + din[7];
    end
endfunction

// -------------------------------------------------------------------------
// 3. CARRY4 CHAIN
// -------------------------------------------------------------------------
(* keep = "true" *) wire rst_high = ~rst_n;
genvar k;
generate
    for (k = 0; k < CARRY4_STAGES; k = k + 1) begin : CARRY_CHAIN
        if (k == 0) begin : STAGE_0
            CARRY4 u_carry4 (.CO(carry_co[(k*4)+3:(k*4)]), .O(carry_o[(k*4)+3:(k*4)]), .CI(1'b0), .CYINIT(hit), .DI(4'b0000), .S(4'b1111));
        end else begin : STAGE_N
            CARRY4 u_carry4 (.CO(carry_co[(k*4)+3:(k*4)]), .O(carry_o[(k*4)+3:(k*4)]), .CI(carry_co[(k*4)-1]), .CYINIT(1'b0), .DI(4'b0000), .S(4'b1111));
        end
        (* DONT_TOUCH = "TRUE" *) FDC u_ff_0 ( .Q(taps_sampled[(k*4)+0]), .C(clk), .CLR(rst_high), .D(carry_o[(k*4)+0]) );								   
        (* DONT_TOUCH = "TRUE" *) FDC u_ff_1 ( .Q(taps_sampled[(k*4)+1]), .C(clk), .CLR(rst_high), .D(carry_o[(k*4)+1]) );									   
        (* DONT_TOUCH = "TRUE" *) FDC u_ff_2 ( .Q(taps_sampled[(k*4)+2]), .C(clk), .CLR(rst_high), .D(carry_o[(k*4)+2]) );		
        (* DONT_TOUCH = "TRUE" *) FDC u_ff_3 ( .Q(taps_sampled[(k*4)+3]), .C(clk), .CLR(rst_high), .D(carry_o[(k*4)+3]) );
    end
endgenerate

// -------------------------------------------------------------------------
// 4. MAIN LOGIC 파이프라인
// -------------------------------------------------------------------------
localparam DEAD_TIME_CYCLES = 2; 
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
        for (i = 0; i < 20; i = i + 1) begin
            stg1_halfA[i] <= 0; stg1_halfB[i] <= 0;
        end
    end 
    else begin
        // [Stage 1] 
        taps_sampled_d1 <= taps_sampled;
        taps_sampled_0_history <= taps_sampled_d1[0]; 

        // [Stage 2] 
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

        // [Stage 3] 
        if (snapshot_valid_stg2) begin
            stg3_group0 <= stg1_halfA[0]+stg1_halfB[0] + stg1_halfA[1]+stg1_halfB[1] + stg1_halfA[2]+stg1_halfB[2] + stg1_halfA[3]+stg1_halfB[3] + stg1_halfA[4]+stg1_halfB[4];
            stg3_group1 <= stg1_halfA[5]+stg1_halfB[5] + stg1_halfA[6]+stg1_halfB[6] + stg1_halfA[7]+stg1_halfB[7] + stg1_halfA[8]+stg1_halfB[8] + stg1_halfA[9]+stg1_halfB[9];
            stg3_group2 <= stg1_halfA[10]+stg1_halfB[10] + stg1_halfA[11]+stg1_halfB[11] + stg1_halfA[12]+stg1_halfB[12] + stg1_halfA[13]+stg1_halfB[13] + stg1_halfA[14]+stg1_halfB[14];
            stg3_group3 <= stg1_halfA[15]+stg1_halfB[15] + stg1_halfA[16]+stg1_halfB[16] + stg1_halfA[17]+stg1_halfB[17] + stg1_halfA[18]+stg1_halfB[18] + stg1_halfA[19]+stg1_halfB[19];
            
            captured_c0_stg3 <= captured_c0_stg2;
            captured_c180_stg3_plus1 <= captured_c180_stg2 + 1'b1; 
            
            snapshot_valid_stg3 <= 1'b1;
        end else begin
            snapshot_valid_stg3 <= 1'b0;
        end

        // [Stage 4] 
        if (snapshot_valid_stg3) begin
            begin : CALC_FINE
                reg [8:0] sum_fine;
                sum_fine = stg3_group0 + stg3_group1 + stg3_group2 + stg3_group3;
                fine_idx_stg4 <= sum_fine;
                
                // ★ 데이터 기반 Threshold 적용 구역 (40, 220)
                danger_zone_stg4 <= (sum_fine < 9'd40 || sum_fine > 9'd220);
            end
            
            captured_c0_stg4 <= captured_c0_stg3;
            captured_c180_stg4_plus1 <= captured_c180_stg3_plus1;
            snapshot_valid_stg4 <= 1'b1;
        end else begin
            snapshot_valid_stg4 <= 1'b0;
        end

        // [Stage 5] 
        if (snapshot_valid_stg4) begin
            ts_fine_idx <= fine_idx_stg4;
            
            if (danger_zone_stg4) begin
                ts_coarse <= captured_c180_stg4_plus1; 
            end else begin
                ts_coarse <= captured_c0_stg4;          
            end
            
            ts_valid <= 1'b1;
        end else begin
            ts_valid <= 1'b0;
        end
    end
end
endmodule