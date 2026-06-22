`timescale 1ns / 1ps

module tdc_test_top (
    input wire clk_125,
    input wire rst_n,
    input wire btn_shift, // 위상 시프트 트리거용 버튼 입력
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
wire clk_200_fixed;   
wire clk_200_shifted; 
wire clk_locked;
wire clk_wiz_rst;

assign clk_wiz_rst = rst_n;

wire psen;
wire psincdec;
wire psdone;
wire ps_busy;

clk_wiz_0 u_clk (
    .clk_in1   (clk_125),
    .reset     (clk_wiz_rst),
    .clk_out1  (clk_200_fixed),   
    .clk_out2  (clk_200_shifted), 
    
    // Dynamic Phase Shift 인터페이스
    .psclk     (clk_200_fixed),
    .psen      (psen),
    .psincdec  (psincdec),
    .psdone    (psdone),
    .locked    (clk_locked)
);

// =====================================================
// 2. MMCM Phase Shift 제어 모듈 (FSM)
// =====================================================
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
// 4. 비동기 링 오실레이터 Hit 생성기 (Calibration 용)
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

wire hit_random = ro_divider_cnt[5]; 

// =====================================================
// 5. MUX (테스트 모드 선택기)
// =====================================================
wire test_hit  = (TEST_MODE_MMCM) ? test_hit_sync : hit_random;
wire tdc_clk   = (TEST_MODE_MMCM) ? clk_200_shifted : clk_200_fixed;

// =====================================================
// 6. TDC 코어 연동
// =====================================================
wire [31:0] ts_coarse;
wire [8:0]  ts_fine_idx;
wire        ts_valid;

tdc_fmcw_core u_tdc (
    .clk         (tdc_clk), 
    .rst_n       (clk_locked),
    .hit         (test_hit),
    .ts_coarse   (ts_coarse),
    .ts_fine_idx (ts_fine_idx),
    .ts_valid    (ts_valid)
);

// 생존 확인용 LED
assign led[0] = clk_locked;
assign led[1] = ps_busy; 
assign led[3:2] = 2'b00;


// =====================================================
// ★ 7. ROM 기반 실시간 캘리브레이션 (LUT 적용 파이프라인)
// =====================================================
wire [12:0] calibrated_fine_ps; // ROM 출력 (ps 단위의 딜레이값)

// ROM 읽기 지연(1 클럭)을 보상하기 위한 파이프라인 레지스터 선언
reg [31:0] ts_coarse_d1;
reg        ts_valid_d1;
reg        test_hit_d1;

// ROM IP 인스턴스화
blk_mem_gen_0 u_lut_rom (
  .clka  (tdc_clk),            // 동기화를 위해 반드시 tdc_clk 사용
  .ena   (1'b1),               // 항상 Enable
  .addra (ts_fine_idx),        // TDC에서 출력된 원시 탭 번호를 주소로 입력
  .douta (calibrated_fine_ps)  // 1클럭 뒤에 보정된 시간값(ps) 출력
);

// 타이밍 정렬 블록 (1 클럭 지연)
always @(posedge tdc_clk) begin
    if (!clk_locked) begin
        ts_coarse_d1 <= 32'd0;
        ts_valid_d1  <= 1'b0;
        test_hit_d1  <= 1'b0;
    end else begin
        ts_coarse_d1 <= ts_coarse;
        ts_valid_d1  <= ts_valid;
        test_hit_d1  <= test_hit;
    end
end

// 최종 물리적 정밀 시간 도출 (단위: ps)
wire [63:0] final_absolute_time_ps;

// 수식: (Coarse 시간 * 5000ps) - LUT에서 나온 Fine 시간(ps)
assign final_absolute_time_ps = (ts_coarse_d1 * 32'd5000) - calibrated_fine_ps;


// =====================================================
// ★ 8. ILA 모듈 연동 (포트 업데이트 필요)
// =====================================================
// ※ 주의: Vivado에서 ILA IP를 열고 probe4(64bit)를 추가로 생성해 주셔야 합니다!
// ※ CDC(Clock Domain Crossing) 방지를 위해 ILA 클럭도 tdc_clk로 연결했습니다.
ila_0 your_ila_instance (
    .clk    (tdc_clk),                 // 클럭 도메인 통일
    .probe0 (ts_valid_d1),             // 1클럭 밀린 valid 
    .probe1 (ts_coarse_d1),            // 1클럭 밀린 coarse
    .probe2 (ts_fine_idx),             // 원시 index 확인용 (밀리지 않음)
    .probe3 (test_hit_d1),             // 1클럭 밀린 hit
    .probe4 (final_absolute_time_ps)   // [추가됨] 64비트 정밀 물리 시간 (ps)
);

endmodule
