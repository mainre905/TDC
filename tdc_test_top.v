`timescale 1ns / 1ps

module tdc_test_top #(
    // ==========================================================
    // ★★★ 여기 숫자만 바꿔서 원하는 모드로 재합성하세요 ★★★
    // 0 : Hit = Ring Osc(랜덤)   | Clock = Fixed 200MHz  (기본 동작 테스트용)
    // 1 : Hit = Test Sync(내부)  | Clock = Shifted 200MHz (MMCM 캘리브레이션용)
    // 2 : Hit = 외부 STM32 신호  | Clock = Fixed 200MHz  (실제 측정용)
    // ==========================================================
    parameter integer OPERATION_MODE = 2
)(
    input  wire       clk_125, 
    input  wire       rst_n, 
    input  wire       btn_shift, 
    input  wire       ext_hit_in,  // ZYBO Hi-Speed PMOD (JB1 - V8)
    output wire [3:0] led
);

    // ==========================================
    // 1. Clock Generation & MMCM Phase Shifter
    // ==========================================
    wire clk_200_fixed, clk_200_shifted, clk_locked;
    wire psen, psincdec, psdone, ps_busy; 
    wire [8:0] current_loop_cnt; 

    clk_wiz_0 u_clk (
        .clk_in1  (clk_125), 
        .reset    (rst_n),  
        .clk_out1 (clk_200_fixed), 
        .clk_out2 (clk_200_shifted), 
        .psclk    (clk_200_fixed), 
        .psen     (psen), 
        .psincdec (psincdec), 
        .psdone   (psdone), 
        .locked   (clk_locked)
    );
    
    mmcm_phase_shifter u_ps_ctrl (
        .clk         (clk_200_fixed), 
        .rst_n       (clk_locked), 
        .start_shift (btn_shift), 
        .psen        (psen), 
        .psincdec    (psincdec), 
        .psdone      (psdone), 
        .busy        (ps_busy), 
        .loop_cnt    (current_loop_cnt)
    );

    // [Mode 1용] Calibration Test Hit Sync
    reg [15:0] sync_cnt; 
    reg test_hit_sync;
    always @(posedge clk_200_fixed) begin 
        if (!clk_locked) begin 
            sync_cnt <= 0; test_hit_sync <= 0; 
        end else begin 
            if (sync_cnt == 16'd49999) sync_cnt <= 0; 
            else sync_cnt <= sync_cnt + 1; 

            if (sync_cnt < 16'd4) test_hit_sync <= 1'b1; 
            else test_hit_sync <= 1'b0;
        end 
    end

    // ==========================================
    // 2. Ring Oscillator (Mode 0용)
    // ==========================================
    (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *) reg ro_enable_reg = 1'b0;
    always @(posedge clk_125) ro_enable_reg <= clk_locked;

    (* ALLOW_COMBINATORIAL_LOOPS = "TRUE", KEEP = "TRUE", DONT_TOUCH = "TRUE" *) wire [30:0] ro_chain;
    genvar r; generate 
        for(r=0; r<30; r=r+1) begin : RO_LOOP 
            (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *) LUT1 #(.INIT(2'h1)) u_lut_inv (.I0(ro_chain[r]), .O(ro_chain[r+1])); 
        end 
    endgenerate
    (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *) LUT2 #(.INIT(4'h7)) u_lut_inv_fb (.I0(ro_chain[30]), .I1(ro_enable_reg), .O(ro_chain[0]));

    wire ro_clk_buffered; 
    BUFG u_bufg_ro (.I(ro_chain[30]), .O(ro_clk_buffered));
    
    (* DONT_TOUCH = "TRUE" *) reg [15:0] ro_divider_cnt = 0; 
    always @(posedge ro_clk_buffered) ro_divider_cnt <= ro_divider_cnt + 1'b1;

    wire hit_random = ro_divider_cnt[5]; 

    // ==========================================================
    // 3. ★★★ 하드코딩된 모드 선택 로직 (Generate 문 사용) ★★★
    // ==========================================================
    // Verilog의 파라미터 값을 기준으로 컴파일 시점에 아예 회로를 다르게 생성합니다.
    // 스위치나 MUX가 존재하지 않으므로 클럭 글리치나 순간적인 오작동이 원천 차단됩니다.
    
    wire tdc_hit_in;
    wire tdc_clk;

    generate
        if (OPERATION_MODE == 0) begin : MODE_0_RO_TEST
            assign tdc_hit_in = hit_random;
            assign tdc_clk    = clk_200_fixed;
        end
        else if (OPERATION_MODE == 1) begin : MODE_1_MMCM_SWEEP
            assign tdc_hit_in = test_hit_sync;
            assign tdc_clk    = clk_200_shifted;
        end
        else begin : MODE_2_EXT_STM32 // OPERATION_MODE == 2
            assign tdc_hit_in = ext_hit_in;
            assign tdc_clk    = clk_200_fixed;
        end
    endgenerate


    // ==========================================
    // 4. TDC Core & 절대 시간 변환기
    // ==========================================
    wire [31:0] raw_ts_coarse; 
    wire [8:0]  raw_ts_fine_idx; 
    wire        raw_ts_valid;
    
    tdc_fmcw_core u_tdc (
        .clk         (tdc_clk), 
        .rst_n       (clk_locked), 
        .hit         (tdc_hit_in), 
        .ts_coarse   (raw_ts_coarse), 
        .ts_fine_idx (raw_ts_fine_idx), 
        .ts_valid    (raw_ts_valid)
    );
    
    wire [63:0] final_timestamp_ps;
    wire        final_ts_valid;
    wire        aligned_hit;
    wire [8:0]  aligned_fine_idx;
    wire [31:0] aligned_coarse;

    tdc_timestamp_calc u_ts_calc (
        .clk             (tdc_clk),
        .rst_n           (clk_locked),
        .ts_coarse       (raw_ts_coarse),
        .ts_fine_idx     (raw_ts_fine_idx),
        .ts_valid        (raw_ts_valid),
        .hit             (tdc_hit_in),
        .timestamp_ps    (final_timestamp_ps),    
        .timestamp_valid (final_ts_valid),        
        .hit_out         (aligned_hit),           
        .fine_idx_out    (aligned_fine_idx),      
        .coarse_out      (aligned_coarse)         
    );

    assign led[0] = clk_locked; 
    assign led[1] = ps_busy; 
    assign led[2] = tdc_hit_in;    // 현재 TDC로 들어가는 Hit 신호 상태를 실시간으로 보여줌 (매우 유용)
    assign led[3] = final_ts_valid; // Hit가 계산 완료될 때마다 깜빡임

    // ==========================================
    // 5. ILA (Integrated Logic Analyzer)
    // ==========================================
    ila_0 your_ila_instance (
        .clk    (tdc_clk), 
        .probe0 (final_ts_valid),               // [0:0]  트리거 조건 (Data Valid)
        .probe1 (tdc_hit_in),                   // [0:0]  현재 Hit 신호 (여기서 직접 STM32 파형 확인 가능)
        .probe2 (final_timestamp_ps[47:0]),     // [47:0] 절대 시간 (ps 단위)
        .probe3 (aligned_fine_idx),             // [8:0]  보정 전 Raw 탭 번호 
        .probe4 (raw_ts_coarse)                 // [31:0] Coarse 카운터 상태 확인용 (디버깅에 도움)
    );

endmodule