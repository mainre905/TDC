`timescale 1ns / 1ps

module tdc_histogram #(
    parameter ADDR_WIDTH = 9,   // 512 bins (320 taps 대응)
    parameter DATA_WIDTH = 32
)(
    input wire clk,
    input wire rst_n,
    
    // TDC 입력 인터페이스 (Port A 누적용)
    input wire [ADDR_WIDTH-1:0] ts_fine_idx,
    input wire                  ts_valid,
    
    // 스캐너 인터페이스 (Port B 일괄 읽기용)
    input wire [ADDR_WIDTH-1:0] read_addr,
    output wire [DATA_WIDTH-1:0] read_data
);

    // FSM 상태 정의 (타이밍 해결을 위해 3비트 5상태로 확장)
    localparam STATE_IDLE  = 3'b000;
    localparam STATE_CLEAR = 3'b001;
    localparam STATE_RMW_R = 3'b010;
    localparam STATE_RMW_A = 3'b011; // ★ 추가됨: +1 덧셈을 수행하는 파이프라인 단계
    localparam STATE_RMW_W = 3'b100;

    reg [2:0] state;
    reg [ADDR_WIDTH-1:0] clear_addr;
    reg [ADDR_WIDTH-1:0] active_addr;
    reg [DATA_WIDTH-1:0] count_reg;

    reg                  ram_we_a;
    reg  [ADDR_WIDTH-1:0] ram_addr_a;
    reg  [DATA_WIDTH-1:0] ram_din_a;
    wire [DATA_WIDTH-1:0] ram_dout_a;

    // -------------------------------------------------------------------------
    // 1. 순차 회로 FSM (Read-Modify-Write 루프 분할)
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= STATE_CLEAR;
            clear_addr <= 0;
            active_addr <= 0;
            count_reg <= 0;
        end else begin
            case (state)
                STATE_IDLE: begin
                    if (ts_valid) begin
                        active_addr <= ts_fine_idx;
                        state <= STATE_RMW_R;
                    end
                end
                
                STATE_CLEAR: begin
                    if (clear_addr == 9'd511) begin
                        state <= STATE_IDLE;
                    end else begin
                        clear_addr <= clear_addr + 1'b1;
                    end
                end
                
                STATE_RMW_R: begin
                    // BRAM에서 데이터가 나오길 기다림
                    state <= STATE_RMW_A;
                end
                
                STATE_RMW_A: begin
                    // ★ Setup 타이밍 해결 핵심: 
                    // BRAM에서 나온 값(ram_dout_a)에 +1을 한 뒤 FF(count_reg)에 안전하게 임시 저장
                    count_reg <= ram_dout_a + 1'b1; 
                    state <= STATE_RMW_W;
                end
                
                STATE_RMW_W: begin
                    // 쓰기 완료 후 대기 상태 복귀
                    state <= STATE_IDLE;
                end
                default: state <= STATE_IDLE;
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // 2. 조합 회로 제어 (Port A)
    // -------------------------------------------------------------------------
    always @(*) begin
        ram_we_a   = 1'b0;
        ram_addr_a = active_addr; // 기본적으로 현재 주소 유지 (안정성 확보)
        ram_din_a  = {DATA_WIDTH{1'b0}};
        
        case (state)
            STATE_CLEAR: begin
                ram_we_a   = 1'b1;
                ram_addr_a = clear_addr;
                ram_din_a  = {DATA_WIDTH{1'b0}};
            end
            STATE_IDLE: begin
                ram_we_a   = 1'b0;
                ram_addr_a = ts_fine_idx; // 입력이 들어오면 주소를 즉시 세팅
            end
            STATE_RMW_R, STATE_RMW_A: begin
                ram_we_a   = 1'b0;
                ram_addr_a = active_addr;
            end
            STATE_RMW_W: begin
                ram_we_a   = 1'b1;
                ram_addr_a = active_addr;
                ram_din_a  = count_reg; // ★ 레지스터(count_reg)의 안정된 값을 BRAM에 입력 (타이밍 충족)
            end
        endcase
    end

    // -------------------------------------------------------------------------
    // 3. Dual-Port BRAM 인스턴스
    // -------------------------------------------------------------------------
    tdc_bram_512x32 u_bram (
        .clk     (clk),
        .addr_a  (ram_addr_a),
        .we_a    (ram_we_a),
        .din_a   (ram_din_a),
        .dout_a  (ram_dout_a),
        
        .addr_b  (read_addr),
        .dout_b  (read_data)
    );

endmodule

// Vivado Block RAM 추론 템플릿
module tdc_bram_512x32 (
    input wire clk,
    input wire [8:0] addr_a,
    input wire we_a,
    input wire [31:0] din_a,
    output reg [31:0] dout_a,
    
    input wire [8:0] addr_b,
    output reg [31:0] dout_b
);
    (* ram_style = "block" *) reg [31:0] mem [0:511];

    always @(posedge clk) begin
        if (we_a) begin
            mem[addr_a] <= din_a;
        end
        dout_a <= mem[addr_a];
    end

    always @(posedge clk) begin
        dout_b <= mem[addr_b];
    end
endmodule