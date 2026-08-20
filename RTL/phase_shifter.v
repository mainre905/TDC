`timescale 1ns / 1ps
// =============================================================================
// 모듈명: mmcm_phase_shifter
// 수정일: 2026-08-19
// 변경점: 1단 CDC 동기용 loop_updated_toggle 1비트 출력 포트 추가
// =============================================================================

module mmcm_phase_shifter (
    input wire clk, 
    input wire rst_n, 
    input wire start_shift,  
    output reg psen, 
    output reg psincdec, 
    input wire psdone, 
    output reg busy, 
    output reg [8:0] loop_cnt,
    output reg loop_updated_toggle // ★ [2026-08-19 추가] 1단 CDC 동기용 토글 신호
);
    localparam IDLE=3'd0, SHIFT=3'd1, WAIT_DONE=3'd2, DELAY=3'd3;
    reg [2:0] state; 
    reg start_shift_d1, start_shift_edge;
    
    reg [20:0] delay_cnt; 
    localparam DELAY_MAX = 21'd2_000_000; // 10ms 대기 (200MHz 기준)

    always @(posedge clk) begin 
        start_shift_d1 <= start_shift; 
        start_shift_edge <= (start_shift && !start_shift_d1); 
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin 
            psen <= 0; psincdec <= 0; busy <= 0; loop_cnt <= 0; delay_cnt <= 0; state <= IDLE;
            loop_updated_toggle <= 1'b0; // ★ [2026-08-19] 리셋 초기화
        end else begin
            case (state)
                IDLE: begin 
                    psen <= 0; delay_cnt <= 0; 
                    if (start_shift_edge) begin busy <= 1; loop_cnt <= 0; state <= SHIFT; end 
                    else busy <= 0; 
                end
                SHIFT: begin 
                    psen <= 1; psincdec <= 1; state <= WAIT_DONE; 
                end
                WAIT_DONE: begin 
                    psen <= 0; 
                    if (psdone) begin 
                        loop_cnt <= loop_cnt + 1'b1; 
                        loop_updated_toggle <= ~loop_updated_toggle; // ★ [2026-08-19] 스텝 증가 시 토글
                        state <= DELAY; 
                    end 
                end
                DELAY: begin 
                    if (delay_cnt == DELAY_MAX) begin 
                        delay_cnt <= 0; 
                        if (loop_cnt == 9'd280) begin busy <= 0; state <= IDLE; end 
                        else state <= SHIFT; 
                    end else begin
                        delay_cnt <= delay_cnt + 1'b1; 
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule