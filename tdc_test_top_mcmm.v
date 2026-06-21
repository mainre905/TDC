`timescale 1ns / 1ps

module tdc_test_top (
    input wire clk_125,
    input wire rst_n,
    input wire btn_shift, // 위상 시프트 트리거용 버튼 입력 (추가)
    output wire [3:0] led
);

// =====================================================
// 0. 테스트 모드 선택 파라미터 (스위치 역할)
// =====================================================
// 1: MMCM Phase Shift 정밀 검증 모드 (동기식 Hit 사용)
// 0: 링 오실레이터 Calibration 모드 (비동기 Hit 사용)
parameter TEST_MODE_MMCM = 1; 

// =====================================================
// 1. Clock Generation (고정 클럭 및 시프트 클럭 출력)
// =====================================================
wire clk_200_fixed;   // clk_out1 (고정 기준 클럭)
wire clk_200_shifted; // clk_out2 (위상 변동 시프트 클럭)
wire clk_locked;
wire clk_wiz_rst;

assign clk_wiz_rst = rst_n;

// MMCM 제어 신호 선언
wire psen;
wire psincdec;
wire psdone;
wire ps_busy;

clk_wiz_0 u_clk (
    .clk_in1   (clk_125),
    .reset     (clk_wiz_rst),
    .clk_out1  (clk_200_fixed),   // 200MHz Fixed
    .clk_out2  (clk_200_shifted), // 200MHz Shifted
    
    // Dynamic Phase Shift 인터페이스 연결
    .psclk     (clk_200_fixed),
    .psen      (psen),
    .psincdec  (psincdec),
    .psdone    (psdone),
    
    .locked    (clk_locked)
);

// =====================================================
// 2. MMCM Phase Shift 제어 모듈 (FSM)
// =====================================================
// 버튼을 누를 때마다 MMCM에 1스텝(약 17.8ps) 지연 트리거를 인가합니다.
mmcm_phase_shifter u_ps_ctrl (
    .clk         (clk_200_fixed),
    .rst_n       (clk_locked),
    .start_shift (btn_shift),
    .psen        (psen),
    .psincdec    (psincdec),
    .psdone      (psdone),
    .busy        (ps_busy)
);

// =====================================================
// 3. 동기식 Hit 생성기 (MMCM 검증용 기준 신호)
// =====================================================
reg [15:0] sync_cnt;
reg test_hit_sync;

always @(posedge clk_200_fixed) begin
    if (!clk_locked) begin
        sync_cnt <= 16'd0;
        test_hit_sync <= 1'b0;
    end else begin
        // 50,000 클럭 주기(250 us)마다 정확히 1클럭 크기의 정밀 동기 펄스 생성
        if (sync_cnt == 16'd49999) begin
            sync_cnt <= 16'd0;
            test_hit_sync <= 1'b1;
        end else begin
            sync_cnt <= sync_cnt + 1'b1;
            test_hit_sync <= 1'b0;
        end
    end
end

// =====================================================
// 4. 기존 링 오실레이터 기반 비동기 Hit 생성기 (Calibration 용)
// =====================================================
(* ALLOW_COMBINATORIAL_LOOPS = "TRUE", KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
wire [30:0] ro_chain;

genvar r;
generate
    for(r=0; r<30; r=r+1) begin : RO_LOOP
        (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
        LUT1 #(.INIT(2'h1)) u_lut_inv (
            .I0(ro_chain[r]),
            .O (ro_chain[r+1])
        );
    end
endgenerate

(* KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
LUT1 #(.INIT(2'h1)) u_lut_inv_fb (
    .I0(ro_chain[30]),
    .O (ro_chain[0])
);

wire ro_clk_buffered;
BUFG u_bufg_ro (
    .I(ro_chain[30]),
    .O(ro_clk_buffered)
);

reg [15:0] ro_divider_cnt = 0;
always @(posedge ro_clk_buffered) begin
    ro_divider_cnt <= ro_divider_cnt + 1'b1;
end

// 파라미터 세팅에 따라 64분주(Calibration) 또는 65536분주 선택
wire hit_random = ro_divider_cnt[5]; 

// =====================================================
// 5. MUX (테스트 모드 선택기)
// =====================================================
// TEST_MODE_MMCM가 1이면 동기식 펄스를 사용하고, TDC 클럭을 시프트 클럭에 연결합니다.
wire test_hit  = (TEST_MODE_MMCM) ? test_hit_sync : hit_random;
wire tdc_clk   = (TEST_MODE_MMCM) ? clk_200_shifted : clk_200_fixed;

// =====================================================
// 6. TDC 코어 연결
// =====================================================
wire [31:0] ts_coarse;
wire [8:0] ts_fine_idx;
wire ts_valid;

tdc_fmcw_core u_tdc (
    .clk         (tdc_clk), // 선택된 클럭 인가
    .rst_n       (clk_locked),
    .hit         (test_hit),
    .ts_coarse   (ts_coarse),
    .ts_fine_idx (ts_fine_idx),
    .ts_valid    (ts_valid)
);

// 생존 확인용 LED
assign led[0] = clk_locked;
assign led[1] = ps_busy; // 위상 이동 중일 때 LED 온
assign led[3:2] = 2'b00;

// =====================================================
// 7. ILA 모듈 인스턴스화
// =====================================================
ila_0 your_ila_instance (
    .clk    (clk_200_fixed), // ILA는 고정 기준으로 관찰
    .probe0 (ts_valid),
    .probe1 (ts_coarse),
    .probe2 (ts_fine_idx),
    .probe3 (test_hit)
);

endmodule


// =====================================================
// 8. MMCM 위상 제어 유닛 보조 모듈
// =====================================================
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