`timescale 1ns / 1ps

module tdc_test_top (
    input  wire       clk_125, 
    input  wire       rst_n, 
    input  wire       btn_shift, 
    output wire [3:0] led
);

    // ==========================================
    // 1. Clock & MMCM Phase Shifter
    // ==========================================
    parameter TEST_MODE_MMCM = 0; // 0: RO Test Mode, 1: MMCM Sweep Mode

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

    // [MMCM Test Hit 생성] (약 250us 주기)
    reg [15:0] sync_cnt; 
    reg test_hit_sync;
    
    always @(posedge clk_200_fixed) begin 
        if (!clk_locked) begin 
            sync_cnt <= 0; 
            test_hit_sync <= 0; 
        end else begin 
            if (sync_cnt == 16'd49999) begin 
                sync_cnt <= 0; 
            end else begin 
                sync_cnt <= sync_cnt + 1; 
            end 

            if (sync_cnt < 16'd4) begin
                test_hit_sync <= 1'b1;
            end else begin
                test_hit_sync <= 1'b0;
            end
        end 
    end

    // ==========================================
    // 2. Ring Oscillator (안정성 보장 원본)
    // ==========================================
    (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *) reg ro_enable_reg = 1'b0;
    always @(posedge clk_125) begin
        ro_enable_reg <= clk_locked;
    end

    (* ALLOW_COMBINATORIAL_LOOPS = "TRUE", KEEP = "TRUE", DONT_TOUCH = "TRUE" *) wire [30:0] ro_chain;
    
    genvar r; 
    generate 
        for(r=0; r<30; r=r+1) begin : RO_LOOP 
            (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *) LUT1 #(.INIT(2'h1)) u_lut_inv (.I0(ro_chain[r]), .O(ro_chain[r+1])); 
        end 
    endgenerate
    
    (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *) LUT2 #(.INIT(4'h7)) u_lut_inv_fb (
        .I0(ro_chain[30]), 
        .I1(ro_enable_reg), 
        .O(ro_chain[0])
    );

    wire ro_clk_buffered; 
    BUFG u_bufg_ro (.I(ro_chain[30]), .O(ro_clk_buffered));
    
    (* DONT_TOUCH = "TRUE" *) reg [15:0] ro_divider_cnt = 0; 
    always @(posedge ro_clk_buffered) begin
        ro_divider_cnt <= ro_divider_cnt + 1'b1;
    end

    // 입력 소스 선택
    wire hit_random = ro_divider_cnt[5]; 
    wire test_hit   = (TEST_MODE_MMCM) ? test_hit_sync   : hit_random;
    wire tdc_clk    = (TEST_MODE_MMCM) ? clk_200_shifted : clk_200_fixed;

    // ==========================================
    // 3. TDC Core Instance (원시 데이터 추출)
    // ==========================================
    wire [31:0] raw_ts_coarse; 
    wire [8:0]  raw_ts_fine_idx; 
    wire        raw_ts_valid;
    
    tdc_fmcw_core u_tdc (
        .clk         (tdc_clk), 
        .rst_n       (clk_locked), 
        .hit         (test_hit), 
        .ts_coarse   (raw_ts_coarse), 
        .ts_fine_idx (raw_ts_fine_idx), 
        .ts_valid    (raw_ts_valid)
    );
    
    assign led[0] = clk_locked; 
    assign led[1] = ps_busy; 
    assign led[3:2] = 2'b00;

    // ==========================================
    // 4. 절대 시간 변환기 (5-Stage Pipeline) 
    // ==========================================
    wire [63:0] final_timestamp_ps;
    wire        final_ts_valid;

    wire [12:0] calibrated_ps_out; // ★ 추가됨
    
    wire        aligned_hit;
    wire [8:0]  aligned_fine_idx;
    wire [31:0] aligned_coarse;

    tdc_timestamp_calc u_ts_calc (
        .clk             (tdc_clk),
        .rst_n           (clk_locked),
        
        .ts_coarse       (raw_ts_coarse),
        .ts_fine_idx     (raw_ts_fine_idx),
        .ts_valid        (raw_ts_valid),
        .hit             (test_hit),
        
        .timestamp_ps    (final_timestamp_ps),    
        .timestamp_valid (final_ts_valid),

        .calibrated_sub_cycle_ps (calibrated_ps_out), // ★ 연결됨        
        
        .hit_out         (aligned_hit),           
        .fine_idx_out    (aligned_fine_idx),      
        .coarse_out      (aligned_coarse)         
    );


     // ==========================================
    // 5. 보정 후 히스토그램 수집기 (Post-Cal INL/DNL 평가)
    // ==========================================
    reg  [15:0] scan_div_cnt;
    reg  [8:0]  scan_addr;
    wire [31:0] hist_data_out;

    // ILA 파형 출력용 주소 스윕 카운터
    always @(posedge tdc_clk) begin
        if (!clk_locked) begin
            scan_div_cnt <= 0;
            scan_addr    <= 0;
        end else begin
            scan_div_cnt <= scan_div_cnt + 1'b1;
            if (scan_div_cnt == 16'hFFFF) begin
                if (scan_addr == 9'd319) scan_addr <= 0;
                else                     scan_addr <= scan_addr + 1'b1;
            end
        end
    end

    tdc_histogrammer u_histogrammer (
        .clk          (tdc_clk),
        .rst_n        (clk_locked),
        .hit_valid    (final_ts_valid),    
        .fine_time_ps (calibrated_ps_out), // ★ 보정된 피코초 데이터 입력
        .read_addr    (scan_addr),
        .read_data    (hist_data_out)
    );


    // ==========================================
    // 5. ILA (Integrated Logic Analyzer) - 원본 복구
    // ==========================================
    ila_0 your_ila_instance (
        .clk    (tdc_clk), 
        .probe0 (final_ts_valid),               // [0:0]  Trigger condition
        .probe1 (final_timestamp_ps[47:0]),     // [47:0] 절대 시간
        .probe2 (scan_addr),             // [8:0]  보정 전 Raw 탭 번호 
        .probe3 (hist_data_out),               // [31:0] 보정 전 Coarse 카운터 
        .probe4 (psdone),                       // [0:0]  MMCM 상태
        .probe5 (current_loop_cnt)              // [8:0]  MMCM Loop Count
    );

endmodule