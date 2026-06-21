module mmcm_phase_shifter (
    input wire clk,
    input wire rst_n,
    input wire start_shift,
    output reg        psen,
    output reg        psincdec,
    input  wire       psdone,
    output reg        busy
);

localparam IDLE  = 2'd0;
localparam START = 2'd1;
localparam WAIT  = 2'd2;

reg [1:0] state;
reg start_shift_d1, start_shift_edge;

// 입력 버튼 신호 에지 검출 (채터링 방지 및 1회 인가용)
always @(posedge clk) begin
    start_shift_d1 <= start_shift;
    start_shift_edge <= (start_shift && !start_shift_d1);
end

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        psen <= 1'b0;
        psincdec <= 1'b0;
        busy <= 1'b0;
        state <= IDLE;
    end else begin
        case (state)
            IDLE: begin
                psen <= 1'b0;
                if (start_shift_edge) begin
                    busy <= 1'b1;
                    state <= START;
                end else begin
                    busy <= 1'b0;
                end
            end
            
            START: begin
                psen <= 1'b1;
                psincdec <= 1'b1; // 1: 시간 지연 방향
                state <= WAIT;
            end
            
            WAIT: begin
                psen <= 1'b0;
                if (psdone) begin
                    busy <= 1'b0;
                    state <= IDLE;
                end
            end
            default: state <= IDLE;
        endcase
    end
end
endmodule