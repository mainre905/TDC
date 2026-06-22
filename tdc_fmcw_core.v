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

// -------------------------------------------------------------------------
// 1. 딜레이 라인용 Wire 선언
// -------------------------------------------------------------------------
(* keep = "true" *) wire [NUM_TAPS-1:0] carry_co;
(* keep = "true", dont_touch = "true" *) wire [NUM_TAPS-1:0] carry_o; 

// taps_sampled는 Primitive로 직접 박으므로 wire로 선언
(* ASYNC_REG = "TRUE", DONT_TOUCH = "TRUE" *) wire [NUM_TAPS-1:0] taps_sampled;

// -------------------------------------------------------------------------
// 2. 파이프라인용 내부 레지스터 (최적화 완료)
// -------------------------------------------------------------------------
reg [31:0] global_timer;
reg [31:0] global_timer_d1;

(* DONT_TOUCH = "TRUE" *) reg [NUM_TAPS-1:0] taps_sampled_d1; // 원본 격리용 (Fanout = 1)
reg taps_sampled_0_history; // 엣지 감지용 단 1비트 과거 저장소

reg snapshot_valid_stg2, snapshot_valid_stg3, snapshot_valid_stg4;

reg [3:0] stg1_halfA [0:19];
reg [3:0] stg1_halfB [0:19];
reg [4:0] stg2_sum [0:19];
reg [6:0] stg3_group0, stg3_group1, stg3_group2, stg3_group3;

integer i;
reg [31:0] coarse_d2, coarse_d3, coarse_d4;

function [3:0] popcount8;
    input [7:0] din;
    begin
        popcount8 = din[0] + din[1] + din[2] + din[3] +
                    din[4] + din[5] + din[6] + din[7];
    end
endfunction

// -------------------------------------------------------------------------
// 3. CARRY4 CHAIN & DIRECT DFF 연결
// -------------------------------------------------------------------------
genvar k;
generate
    for (k = 0; k < CARRY4_STAGES; k = k + 1) begin : CARRY_CHAIN
        if (k == 0) begin : STAGE_0
            CARRY4 u_carry4 (
                .CO (carry_co[(k*4)+3 : (k*4)]),
                .O  (carry_o[(k*4)+3 : (k*4)]),
                .CI (1'b0),
                .CYINIT(hit),
                .DI (4'b0000), 
                .S  (4'b1111)
            );
        end else begin : STAGE_N
            CARRY4 u_carry4 (
                .CO (carry_co[(k*4)+3 : (k*4)]),
                .O  (carry_o[(k*4)+3 : (k*4)]),
                .CI (carry_co[(k*4)-1]),
                .CYINIT(1'b0),
                .DI (4'b0000),
                .S  (4'b1111)
            );
        end
        // BEL 속성을 사용하여 CARRY4와 같은 슬라이스 내의 FF로 강제 매핑			   
        (* BEL = "AFF" *) FDCE u_ff_0 ( .Q(taps_sampled[(k*4)+0]), .C(clk), .CE(1'b1), .CLR(~rst_n), .D(carry_o[(k*4)+0]) );								   
        (* BEL = "BFF" *) FDCE u_ff_1 ( .Q(taps_sampled[(k*4)+1]), .C(clk), .CE(1'b1), .CLR(~rst_n), .D(carry_o[(k*4)+1]) );									   
        (* BEL = "CFF" *) FDCE u_ff_2 ( .Q(taps_sampled[(k*4)+2]), .C(clk), .CE(1'b1), .CLR(~rst_n), .D(carry_o[(k*4)+2]) );		
        (* BEL = "DFF" *) FDCE u_ff_3 ( .Q(taps_sampled[(k*4)+3]), .C(clk), .CE(1'b1), .CLR(~rst_n), .D(carry_o[(k*4)+3]) );
    end
endgenerate

// -------------------------------------------------------------------------
// 4. MAIN LOGIC (파이프라인 연산)
// -------------------------------------------------------------------------
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        global_timer <= 0;
        global_timer_d1 <= 0;
        taps_sampled_d1 <= 0;
        taps_sampled_0_history <= 0;
        
        snapshot_valid_stg2 <= 0;
        snapshot_valid_stg3 <= 0; 
        snapshot_valid_stg4 <= 0;
        coarse_d2 <= 0; coarse_d3 <= 0; coarse_d4 <= 0;
        ts_coarse <= 0; ts_valid <= 0; ts_fine_idx <= 0;
        stg3_group0 <= 0; stg3_group1 <= 0; stg3_group2 <= 0; stg3_group3 <= 0;

        for (i = 0; i < 20; i = i + 1) begin
            stg1_halfA[i] <= 0; stg1_halfB[i] <= 0; stg2_sum[i] <= 0;
        end
    end 
    else begin
        // [Stage 1] 원본 보호용 이송 및 타이머 동기화 (배선 지연 해결)
        global_timer <= global_timer + 1'b1;
        global_timer_d1 <= global_timer;
        
        taps_sampled_d1 <= taps_sampled;
        taps_sampled_0_history <= taps_sampled_d1[0]; // 엣지 판별용 1비트 

        // [Stage 2] 엣지 감지 및 즉시 Popcount 연산
        if (taps_sampled_d1[0] && !taps_sampled_0_history) begin
            for (i = 0; i < 20; i = i + 1) begin
                stg1_halfA[i] <= popcount8(taps_sampled_d1[i*16 +: 8]);
                stg1_halfB[i] <= popcount8(taps_sampled_d1[i*16+8 +: 8]);
            end
            coarse_d2 <= global_timer_d1 - 1'b1;
            snapshot_valid_stg2 <= 1'b1;
        end else begin
            snapshot_valid_stg2 <= 1'b0;
        end

        // [Stage 3] 구간별 합 완성
        if (snapshot_valid_stg2) begin
            for (i = 0; i < 20; i = i + 1) stg2_sum[i] <= stg1_halfA[i] + stg1_halfB[i];
            coarse_d3 <= coarse_d2; 
            snapshot_valid_stg3 <= 1'b1;
        end else begin
            snapshot_valid_stg3 <= 1'b0;
        end

        // [Stage 4] 최종 4그룹 병합 및 출력
        if (snapshot_valid_stg3) begin
            stg3_group0 <= stg2_sum[0]  + stg2_sum[1]  + stg2_sum[2]  + stg2_sum[3]  + stg2_sum[4];
            stg3_group1 <= stg2_sum[5]  + stg2_sum[6]  + stg2_sum[7]  + stg2_sum[8]  + stg2_sum[9];
            stg3_group2 <= stg2_sum[10] + stg2_sum[11] + stg2_sum[12] + stg2_sum[13] + stg2_sum[14];
            stg3_group3 <= stg2_sum[15] + stg2_sum[16] + stg2_sum[17] + stg2_sum[18] + stg2_sum[19];
            
            ts_fine_idx <= stg3_group0 + stg3_group1 + stg3_group2 + stg3_group3;
            ts_coarse   <= coarse_d3;
            ts_valid    <= 1'b1;
        end else begin
            ts_valid <= 1'b0;
        end
    end
end
endmodule