`timescale 1ns / 1ps

module mmcm_phase_shifter (
    input  wire       clk, 
    input  wire       rst_n, 
    input  wire       start_shift,  
    output reg        psen, 
    output reg        psincdec, 
    input  wire       psdone, 
    output reg        busy,
    output reg [8:0]  loop_cnt     // 스텝 번호 출력 (0 ~ 280)
);

localparam IDLE       = 3'd0;
localparam SHIFT      = 3'd1;
localparam WAIT_DONE  = 3'd2;
localparam DELAY      = 3'd3;

reg [2:0]  state;
reg        start_shift_d1, start_shift_edge;
reg [17:0] delay_cnt;   
  
localparam DELAY_MAX = 18'd200_000; // 200MHz 기준 1ms 대기 (17.85ps씩 천천히 스윕)

always @(posedge clk) begin 
    start_shift_d1 <= start_shift; 
    start_shift_edge <= (start_shift && !start_shift_d1); 
end

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin 
        psen <= 0; 
        psincdec <= 0; 
        busy <= 0; 
        loop_cnt <= 0; 
        delay_cnt <= 0; 
        state <= IDLE; 
    end else begin
        case (state)
            IDLE: begin 
                psen <= 0; 
                delay_cnt <= 0;
                if (start_shift_edge) begin 
                    busy <= 1; 
                    loop_cnt <= 0; 
                    state <= SHIFT; 
                end else begin
                    busy <= 0; 
                end
            end
            
            SHIFT: begin 
                psen <= 1; 
                psincdec <= 1; // 1: 위상 지연 방향
                state <= WAIT_DONE; 
            end
            
            WAIT_DONE: begin 
                psen <= 0; 
                if (psdone) begin 
                    loop_cnt <= loop_cnt + 1'b1; 
                    state <= DELAY; 
                end 
            end
            
            DELAY: begin
                if (delay_cnt == DELAY_MAX) begin
                    delay_cnt <= 0;
                    if (loop_cnt == 9'd280) begin 
                        busy <= 0; 
                        state <= IDLE; // 280번 완료 시 종료
                    end else begin
                        state <= SHIFT; // 다음 스텝 진행
                    end 
                end else begin
                    delay_cnt <= delay_cnt + 1'b1;
                end
            end
            
            default: state <= IDLE;
        endcase
    end
end
endmodule