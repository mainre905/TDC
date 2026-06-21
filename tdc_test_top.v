`timescale 1ns / 1ps

module tdc_test_top (
    input wire clk_125,
    input wire rst_n,
    output wire [3:0] led
);

// =====================================================
// 1. Clock Generation (125MHz -> 200MHz)
// =====================================================
wire clk_200;
wire clk_locked;
wire clk_wiz_rst;

// Active-Low 리셋 신호(rst_n)를 Clock Wizard의 Active-High 리셋에 맞게 반전
assign clk_wiz_rst = rst_n;

clk_wiz_0 u_clk (
    .clk_in1 (clk_125),
    .reset   (clk_wiz_rst),
    .clk_out1(clk_200),
    .locked  (clk_locked)
);

// =====================================================
// 2. 테스트 1단계: 1ms 정밀 펄스 생성기 (Coarse 테스트용)
// =====================================================
reg [17:0] cnt_1ms;
reg hit_1ms;

always @(posedge clk_200) begin
    if (!clk_locked) begin
        cnt_1ms <= 18'd0;
        hit_1ms <= 1'b0;
    end
    else begin
        // 200MHz 클럭 기준으로 200,000번 세면 정확히 1ms (1,000,000ns)
        if (cnt_1ms == 18'd199_999) begin
            cnt_1ms <= 18'd0;
            hit_1ms <= 1'b1;
        end else begin
            cnt_1ms <= cnt_1ms + 1'b1;
            hit_1ms <= 1'b0;
        end
    end
end

// =====================================================
// 3. 테스트 2단계: 31-Stage Ring Oscillator 기반 비동기 Hit 생성기
// =====================================================

// 1. Ring Oscillator 체인 선언
(* ALLOW_COMBINATORIAL_LOOPS = "TRUE", KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
wire [30:0] ro_chain;

// 2. 링 오실레이터 인버터 체인 생성 (LUT1 Primitive 인스턴스화로 물리적 맵핑 강제)
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

// 마지막 피드백 루프 (30번 핀에서 0번 핀으로 꼬리물기)
(* KEEP = "TRUE", DONT_TOUCH = "TRUE" *)
LUT1 #(.INIT(2'h1)) u_lut_inv_fb (
    .I0(ro_chain[30]),
    .O (ro_chain[0])
);

// -----------------------------------------------------
// [수정 사항] 링 오실레이터 출력 클럭을 글로벌 버퍼(BUFG)로 구동
// -----------------------------------------------------
wire ro_clk_buffered;

// 조합 루프의 출력을 전용 글로벌 클럭 라인에 연결
BUFG u_bufg_ro (
    .I(ro_chain[30]),
    .O(ro_clk_buffered)
);

reg [15:0] ro_divider_cnt = 0;

// 일반 라우팅 자원이 아닌 BUFG를 거친 신호(ro_clk_buffered)를 클럭으로 사용
always @(posedge ro_clk_buffered) begin
    ro_divider_cnt <= ro_divider_cnt + 1'b1;
end

// 1: 캘리브레이션 모드 (약 500ns 주기, 고속 데이터 수집)
// 0: 일반 테스트 모드 (약 1ms 주기)
parameter CALIBRATION_MODE = 1; 

wire hit_random = (CALIBRATION_MODE) ? ro_divider_cnt[5] : ro_divider_cnt[15];

// =====================================================
// 4. MUX (테스트 모드 선택기)
// =====================================================
wire test_hit = hit_random;

// =====================================================
// 5. TDC 코어 연결
// =====================================================
wire [31:0] ts_coarse;
wire [8:0] ts_fine_idx;
wire ts_valid;

tdc_fmcw_core u_tdc (
    .clk         (clk_200),
    .rst_n       (clk_locked),
    .hit         (test_hit),
    .ts_coarse   (ts_coarse),
    .ts_fine_idx (ts_fine_idx),
    .ts_valid    (ts_valid)
);

// 생존 확인용 LED
assign led[0] = clk_locked;
assign led[3:1] = 3'b000;

// =====================================================
// 6. ILA 모듈 인스턴스화
// =====================================================
ila_0 your_ila_instance (
    .clk    (clk_200),
    .probe0 (ts_valid),
    .probe1 (ts_coarse),
    .probe2 (ts_fine_idx),
    .probe3 (test_hit)
);

endmodule