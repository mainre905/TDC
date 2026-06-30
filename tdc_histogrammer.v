`timescale 1ns / 1ps

module tdc_histogrammer #(
    parameter NUM_BINS = 320
)(
    input  wire        clk,
    input  wire        rst_n,

    // Data collection interface (보정 완료된 피코초 단위 데이터)
    input  wire        hit_valid,
    input  wire [12:0] fine_time_ps, // 0 ~ 4999 ps

    // ILA Readout interface
    input  wire [8:0]  read_addr,    // 0 ~ 319 (ILA 스윕용)
    output reg  [31:0] read_data
);

    // 1. 피코초 -> Bin Index 고속 매핑 (파이프라인 1단)
    // 수식: bin_idx = (fine_time_ps * 320) / 5000
    // 최적화: bin_idx = (fine_time_ps * 67109) >> 20
    reg        hit_valid_d1;
    reg [8:0]  mapped_bin_idx;

    always @(posedge clk) begin
        if (!rst_n) begin
            hit_valid_d1   <= 1'b0;
            mapped_bin_idx <= 9'd0;
        end else begin
            hit_valid_d1   <= hit_valid;
            // DSP multiplier를 사용해 1 Clock만에 나눗셈 없이 매핑
            mapped_bin_idx <= (fine_time_ps * 20'd67109) >> 20; 
        end
    end

    // 2. 히스토그램 누적 RAM (320 x 32bit)
    reg [31:0] hist_mem [0:NUM_BINS-1];
    integer i;

    always @(posedge clk) begin
        if (!rst_n) begin
            for (i = 0; i < NUM_BINS; i = i + 1) begin
                hist_mem[i] <= 32'd0;
            end
            read_data <= 32'd0;
        end else begin
            // [Write] 매핑된 Bin 번호에 맞춰 히스토그램 +1 증가
            if (hit_valid_d1 && (mapped_bin_idx < NUM_BINS)) begin
                hist_mem[mapped_bin_idx] <= hist_mem[mapped_bin_idx] + 1'b1;
            end

            // [Read] ILA에서 파형을 볼 수 있도록 주소에 맞춰 출력
            read_data <= hist_mem[read_addr];
        end
    end
endmodule