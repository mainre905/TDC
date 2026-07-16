`timescale 1ns / 1ps

module tdc_test_top #(
    // ==========================================================
    // 0 : Hit = Test Sync(내부)  | Clock = Shifted 200MHz (MMCM 캘리브레이션용)
    // 1 : Hit = Ring Osc(랜덤)   | Clock = Fixed 200MHz  (기본 동작 및 탭 누적 테스트용)
    // 2 : Hit = 외부 STM32 신호  | Clock = Fixed 200MHz  (실제 측정용)
    // ==========================================================
    parameter integer OPERATION_MODE = 0
)(
    input  wire       clk_125, 
    input  wire       rst_n, 
    input  wire       btn_shift,   
    input  wire       ext_hit_in,  
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
            if (sync_cnt == 16'd9) sync_cnt <= 0; 
            else sync_cnt <= sync_cnt + 1; 

            if (sync_cnt < 16'd2) test_hit_sync <= 1'b1; 
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
        else if (OPERATION_MODE == 1) begin : MODE_1_RO_TEST
            assign tdc_hit_in = hit_random;
            assign tdc_clk    = clk_200_fixed;
        end
        else begin : MODE_2_EXT_STM32
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
    // 5. 온칩 ILA 리드아웃 스캐너 (350 도달 시 자동 출력)
    // ==========================================================
    reg        readout_active;
    reg [8:0]  sweep_addr;
    reg [8:0]  probe_read_addr; 

    reg [8:0] loop_cnt_d1;
    always @(posedge tdc_clk) begin
        loop_cnt_d1 <= current_loop_cnt;
    end

    // 위상 스윕이 350번까지 딱 끝나는 순간 감지
    wire sweep_finished = (current_loop_cnt == 9'd280) && (loop_cnt_d1 == 9'd279);

    always @(posedge tdc_clk or negedge clk_locked) begin
        if (!clk_locked) begin
            readout_active  <= 1'b0;
            sweep_addr      <= 9'd0;
            probe_read_addr <= 9'd0;
        end else begin
            if (sweep_finished && !readout_active) begin
                readout_active <= 1'b1;
                sweep_addr     <= 9'd0;
            end else if (readout_active) begin
                if (sweep_addr == 9'd319) begin
                    readout_active <= 1'b0;
                end else begin
                    sweep_addr <= sweep_addr + 1'b1;
                end
            end
            probe_read_addr <= sweep_addr;
        end
    end

    // ==========================================================
    // 6. 히스토그램 데이터 게이팅 및 모듈 인스턴스 (핵심 수정)
    // ==========================================================
    wire gated_ts_valid;

    generate
        if (OPERATION_MODE == 0) begin : MODE_0_HISTO_CTRL
            // Mode 0: 스윕(Phase Shift) 중일 때만 Hit 누적! (대기 중 쌓이는 쓰레기 값 차단)
            assign gated_ts_valid = final_ts_valid && ps_busy;
        end else begin : MODE_1_HISTO_CTRL
            // Mode 1: 대기 중에도 백그라운드에서 자연스럽게 수백만 개가 누적되도록 항상 켬
            assign gated_ts_valid = final_ts_valid;
        end
    endgenerate

    wire [31:0] histo_read_data;

    tdc_histogram #(
        .ADDR_WIDTH(9),
        .DATA_WIDTH(32)
    ) u_histo (
        .clk         (tdc_clk),
        .rst_n       (clk_locked),
        .ts_fine_idx (aligned_fine_idx),
        .ts_valid    (gated_ts_valid),   
        .read_addr   (probe_read_addr),
        .read_data   (histo_read_data)
    );

    assign led[0] = clk_locked; 
    assign led[1] = readout_active; 
    assign led[2] = tdc_hit_in;    
    assign led[3] = final_ts_valid; 

    // ==========================================================
    // 7. ILA (Integrated Logic Analyzer) 갱신
    // ==========================================================
    ila_0 your_ila_instance (
        .clk    (tdc_clk), 
        .probe0 (readout_active),       // [0:0] Trigger Setup에 넣고 '1'로 설정
        .probe1 (probe_read_addr),      // [8:0] X축: Tap 번호
        .probe2 (histo_read_data),      // [31:0] Y축: 카운트 값
        .probe3 (current_loop_cnt),     // [8:0]
        .probe4 (aligned_fine_idx)      // [8:0]
    );
endmodule