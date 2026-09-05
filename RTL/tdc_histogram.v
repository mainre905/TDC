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

    // ★ 2026-09-05 추가 : 히스토그램 지우기 (AXI CTRL.HISTO_CLR)
    //   레벨 신호다. 1 인 동안 CLEAR 상태에 머물며 주소를 순회하면서 0 을 쓴다.
    //   왜 펄스가 아니라 레벨인가 : 펄스를 쓰면 클럭 도메인이 다른 소프트웨어가
    //   그 한 사이클을 놓칠 수 있다. 레벨이면 "512 사이클(2.6 us) 넘게 들고
    //   있다가 내린다"는 것만 지키면 반드시 전부 지워진다.
    //   이 신호는 tdc_axi_regs 가 이미 tdc_clk 도메인으로 래치해서 준다.
    input wire                  histo_clr,

    // ★ 2026-09-05 변경 : Port B 는 이제 ILA 스캐너가 아니라 AXI 가 읽는다.
    //   clk_b 로 별도 클럭을 받는다 — 듀얼포트 BRAM 은 포트마다 클럭이 달라도
    //   되게 만들어진 물건이고, Port B 를 AXI 클럭으로 돌리면 AXI 쪽에서는
    //   전부 동기 논리가 되어 클럭 도메인 교차 처리가 아예 필요 없어진다.
    //   누적(Port A)이 도는 중에 읽어도 BRAM 포트 읽기는 워드 단위로 원자적이라
    //   32비트 값이 찢어지지 않는다. 옛값이냐 새값이냐만 갈릴 뿐이다.
    input wire                   clk_b,
    input wire [ADDR_WIDTH-1:0]  read_addr,
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
        end else if (histo_clr) begin
            // ★ 2026-09-05 : 지우기 요청이 걸려 있는 동안 CLEAR 에 머문다.
            //   진입할 때만 주소를 0 으로 놓고, 머무는 동안은 계속 증가시킨다
            //   (9비트라 511 다음은 저절로 0 으로 돌아간다).
            //   요청이 내려가면 아래 case 의 STATE_CLEAR 가 511 까지 마저 돌고
            //   IDLE 로 빠진다. CLEAR 중에는 ts_valid 를 보지 않으므로 그 사이
            //   들어온 히트는 버려진다 — 지우는 중이니 그게 맞다.
            state      <= STATE_CLEAR;
            clear_addr <= (state == STATE_CLEAR) ? (clear_addr + 1'b1)
                                                 : {ADDR_WIDTH{1'b0}};
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
        .clk_a   (clk),
        .addr_a  (ram_addr_a),
        .we_a    (ram_we_a),
        .din_a   (ram_din_a),
        .dout_a  (ram_dout_a),

        .clk_b   (clk_b),          // ★ 2026-09-05 : Port B 는 AXI 클럭
        .addr_b  (read_addr),
        .dout_b  (read_data)
    );

endmodule

// Vivado Block RAM 추론 템플릿
// ★ 2026-09-05 : 단일 클럭 -> 포트별 독립 클럭 (clk -> clk_a / clk_b).
//   무엇이 바뀌었나 : Port B 를 ILA 스캐너(tdc_clk, 200 MHz) 대신 AXI 슬레이브
//     (s_axi_aclk, 100 MHz)가 읽게 되었다.
//   왜 이렇게 해도 되나 : 7-series 의 RAMB36E1 은 원래 포트마다 클럭 입력이
//     따로 있는 진짜 듀얼포트다. 아래처럼 always 블록 두 개의 클럭을 다르게
//     써 주면 Vivado 가 그대로 추론한다.
//   무엇을 보장하나 / 보장하지 않나 : 한 포트의 읽기는 32비트 워드 단위로
//     원자적이라, 반대편에서 누적(RMW)이 도는 중에 읽어도 값이 찢어지지 않는다.
//     다만 그 순간 옛값이 나올지 새값이 나올지는 정해지지 않는다. 히스토그램
//     카운트를 읽는 용도에서는 1 차이가 문제되지 않으므로 이 정도면 충분하다.
//     (정확한 스냅샷이 필요하면 읽기 전에 누적을 멈추면 된다)
module tdc_bram_512x32 (
    input wire clk_a,
    input wire [8:0] addr_a,
    input wire we_a,
    input wire [31:0] din_a,
    output reg [31:0] dout_a,

    input wire clk_b,
    input wire [8:0] addr_b,
    output reg [31:0] dout_b
);
    (* ram_style = "block" *) reg [31:0] mem [0:511];

    always @(posedge clk_a) begin
        if (we_a) begin
            mem[addr_a] <= din_a;
        end
        dout_a <= mem[addr_a];
    end

    always @(posedge clk_b) begin
        dout_b <= mem[addr_b];
    end
endmodule