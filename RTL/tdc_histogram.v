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

    // ★ Setup 타이밍 수정: BRAM 출력을 '로직 없이' 받아두는 중간 레지스터.
    // RAMB36E1은 출력 레지스터를 쓰지 않으면 clock-to-out이 ~3ns(Zynq-7000 -1, slow corner)에 달합니다.
    // 여기에 32비트 캐리 체인(+1)까지 같은 사이클에 붙이면 5ns 예산을 초과합니다.
    //   (실측: logic 3.991ns + route 0.916ns = 4.907ns > 예산 4.71ns → slack -0.180ns)
    // BRAM Tcko 경로와 가산기 경로를 서로 다른 사이클로 분리하기 위한 레지스터입니다.
    reg [DATA_WIDTH-1:0] count_raw;

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
            count_raw <= 0;
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
                    // IDLE에서 이미 주소를 걸어놨으므로 ram_dout_a는 이 사이클에 유효합니다.
                    // ★ 여기서는 +1을 하지 않고 '캡처만' 합니다.
                    //   경로: BRAM(Tcko ~3ns) -> route -> FF(D). 조합 로직이 없어 여유 있게 닫힘.
                    count_raw <= ram_dout_a;
                    state <= STATE_RMW_A;
                end

                STATE_RMW_A: begin
                    // ★ 이제 +1은 FF -> 32비트 가산기 -> FF 경로가 됩니다.
                    //   BRAM Tcko가 경로에서 빠지므로 캐리 체인 전파(~1ns)만 남아 크게 여유가 생깁니다.
                    count_reg <= count_raw + 1'b1;
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