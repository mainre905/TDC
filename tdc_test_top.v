`timescale 1ns / 1ps

module tdc_test_top #(
    // ==========================================================
    // ★★★ 동작 모드 정의 (사용자 피드백 반영) ★★★
    // 0 : Hit = Test Sync(내부)  | Clock = Shifted 200MHz (MMCM 캘리브레이션용)
    // 1 : Hit = Ring Osc(랜덤)   | Clock = Fixed 200MHz  (기본 동작 및 탭 누적 테스트용)
    // 2 : Hit = 외부 STM32 신호  | Clock = Fixed 200MHz  (실제 측정용)
    // ==========================================================
    parameter integer OPERATION_MODE = 1
)(
    input  wire       clk_125, 
    input  wire       rst_n, 
    input  wire       btn_shift,   // 물리 버튼 (ILA Sweep Trigger 및 MMCM Shift 공용)
    input  wire       ext_hit_in,  // ZYBO PMOD JB1 (V8 Pin)
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

    // [Mode 0용] Calibration Test Hit Sync
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
    // 2. Ring Oscillator (Mode 1용)
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

    // ==========================================
    // 3. 하드코딩된 모드 선택 제너레이터
    // ==========================================
    wire tdc_hit_in;
    wire tdc_clk;

    generate
        if (OPERATION_MODE == 0) begin : MODE_0_MMCM_SWEEP
            assign tdc_hit_in = test_hit_sync;
            assign tdc_clk    = clk_200_shifted;
        end
        else if (OPERATION_MODE == 1) begin : MODE_1_RO_TEST       // Mode 1 = Ring Osc 연결
            assign tdc_hit_in = hit_random;
            assign tdc_clk    = clk_200_fixed;
        end
        else begin : MODE_2_EXT_STM32                             // Mode 2 = 외부 STM32 연결
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

    // ==========================================================
    // 5. 버튼 디바운싱 및 온칩 ILA 리드아웃 스캐너
    // ==========================================================
    reg btn_shift_d1, btn_shift_d2;
    always @(posedge tdc_clk) begin
        btn_shift_d1 <= btn_shift;
        btn_shift_d2 <= btn_shift_d1;
    end
    wire btn_trigger_sweep = (btn_shift_d1 && !btn_shift_d2);

    reg        readout_active;
    reg [8:0]  sweep_addr;
    reg [8:0]  probe_read_addr; 

    always @(posedge tdc_clk or negedge clk_locked) begin
        if (!clk_locked) begin
            readout_active  <= 1'b0;
            sweep_addr      <= 9'd0;
            probe_read_addr <= 9'd0;
        end else begin
            if (btn_trigger_sweep && !readout_active) begin
                readout_active <= 1'b1;
                sweep_addr     <= 9'd0;
            end else if (readout_active) begin
                if (sweep_addr == 9'd319) begin
                    readout_active <= 1'b0;
                end else begin
                    sweep_addr <= sweep_addr + 1'b1;
                end
            end
            // BRAM Read Latency (1 clk) 보정
            probe_read_addr <= sweep_addr;
        end
    end

    // ==========================================================
    // 6. 히스토그램 모듈 인스턴스
    // ==========================================================
    wire [31:0] histo_read_data;

    tdc_histogram #(
        .ADDR_WIDTH(9),
        .DATA_WIDTH(32)
    ) u_histo (
        .clk         (tdc_clk),
        .rst_n       (clk_locked),
        .ts_fine_idx (aligned_fine_idx),
        .ts_valid    (final_ts_valid),
        .read_addr   (sweep_addr),
        .read_data   (histo_read_data)
    );

    // 외부 보드 상태 LED 맵핑
    assign led[0] = clk_locked; 
    assign led[1] = readout_active; // 리드아웃 스위핑 동작 시 점등
    assign led[2] = tdc_hit_in;    
    assign led[3] = final_ts_valid; 

    // ==========================================================
    // 7. ILA (Integrated Logic Analyzer) 갱신
    // ==========================================================
    // 트리거 신호와 리드아웃 정보를 수집하도록 변경
    ila_0 your_ila_instance (
        .clk    (tdc_clk), 
        .probe0 (readout_active),   // [0:0]  ILA 트리거 소스 (0 -> 1 상승에지 트리거)
        .probe1 (probe_read_addr),  // [8:0]  출력 중인 지연선 탭 번호 (0 ~ 319)
        .probe2 (histo_read_data),  // [31:0] 해당 탭의 누적 통계 카운트 데이터
        .probe3 (tdc_hit_in),       // [0:0]  Ring Oscillator 파형 유입 여부 모니터링
        .probe4 (final_ts_valid)    // [0:0]  TDC 모듈 출력 플래그
    );

endmodule