`timescale 1ns / 1ps

module mmcm_phase_shifter (
    input wire clk, 
    input wire rst_n, 
    input wire start_shift,  
    output reg psen, 
    output reg psincdec, 
    input wire psdone, 
    output reg busy, 
    output reg [8:0] loop_cnt
);
    localparam IDLE=3'd0, SHIFT=3'd1, WAIT_DONE=3'd2, DELAY=3'd3;
    reg [2:0] state; 
    reg start_shift_d1, start_shift_edge;
    
    // ★ 수정 1: 비트 수를 21비트로 확장 (2,000,000을 담기 위해)
    reg [20:0] delay_cnt; 
    
    // ★ 수정 2: 대기 시간을 10ms (2,000,000 클럭)으로 10배 증가 (1스텝당 40샘플 확보)
    localparam DELAY_MAX = 21'd2_000_000; 

    always @(posedge clk) begin 
        start_shift_d1 <= start_shift; 
        start_shift_edge <= (start_shift && !start_shift_d1); 
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin 
            psen<=0; psincdec<=0; busy<=0; loop_cnt<=0; delay_cnt<=0; state<=IDLE; 
        end else begin
            case (state)
                IDLE: begin 
                    psen<=0; delay_cnt<=0; 
                    if (start_shift_edge) begin busy<=1; loop_cnt<=0; state<=SHIFT; end 
                    else busy<=0; 
                end
                SHIFT: begin 
                    psen<=1; psincdec<=1; state<=WAIT_DONE; 
                end
                WAIT_DONE: begin 
                    psen<=0; 
                    if (psdone) begin loop_cnt<=loop_cnt+1; state<=DELAY; end 
                end
                DELAY: begin 
                    if (delay_cnt == DELAY_MAX) begin 
                        delay_cnt <= 0; 
                        // ★ 수정 3: 스윕 횟수를 350번으로 연장하여 5ns 한 주기를 여유 있게 덮음
                        if (loop_cnt == 9'd350) begin busy<=0; state<=IDLE; end 
                        else state<=SHIFT; 
                    end else begin
                        delay_cnt <= delay_cnt + 1; 
                    end
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule