`timescale 1ns / 1ps

module tdc_test_top (
    input  wire       clk_125, 
    input  wire       rst_n, 
    input  wire       btn_shift, 
    input  wire       ext_hit_in,  // ZYBO PMOD 외부 입력
    input  wire [1:0] sw_mode,     // [추가] 2-Bit 스위치 모드 선택 (SW1, SW0)
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

    // [Mode 1용] Calibration Test Hit Sync (약 250us 주기)
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

    // ==========================================
    // 3. ★ 핵심: 3-Way Mode MUXing 로직 ★
    // ==========================================
    // 0 (2'b00) : Hit = hit_random     | Clock = Fixed 200MHz
    // 1 (2'b01) : Hit = test_hit_sync  | Clock = Shift 200MHz
    // 2 (2'b10) : Hit = ext_hit_in     | Clock = Fixed 200MHz
    
    reg tdc_hit_in;
    always @(*) begin
        case (sw_mode)
            2'b00:   tdc_hit_in = hit_random;     // 모드 0: 순수 RO 테스트
            2'b01:   tdc_hit_in = test_hit_sync;  // 모드 1: MMCM LUT 추출용 스윕
            2'b10:   tdc_hit_in = ext_hit_in;     // 모드 2: STM32 외부 측정 모드
            default: tdc_hit_in = hit_random;     // Fallback
        endcase
    end

    // Xilinx Glitch-Free Clock MUX 사용 (sw_mode가 2'b01일 때만 1, 나머진 0)
    wire tdc_clk;
    wire clk_sel = (sw_mode == 2'b01) ? 1'b1 : 1'b0; 

    BUFGMUX u_tdc_clk_mux (
        .O  (tdc_clk),
        .I0 (clk_200_fixed),    // clk_sel = 0 일 때
        .I1 (clk_200_shifted),  // clk_sel = 1 일 때
        .S  (clk_sel)
    );

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

    // ==========================================
    // 5. 펄스 간 시간 간격(Interval) 계산
    // ==========================================
    reg [63:0] prev_timestamp_ps;
    reg [63:0] pulse_interval_ps;
    reg        interval_valid;

    always @(posedge tdc_clk) begin
        if (!clk_locked) begin
            prev_timestamp_ps <= 0;
            pulse_interval_ps <= 0;
            interval_valid    <= 0;
        end else begin
            if (final_ts_valid) begin
                prev_timestamp_ps <= final_timestamp_ps;
                pulse_interval_ps <= final_timestamp_ps - prev_timestamp_ps;
                interval_valid    <= 1'b1;
            end else begin
                interval_valid    <= 1'b0;
            end
        end
    end

    // LED 모니터링: [0]=락, [1]=Sweep상태, [3:2]=현재 스위치 모드
    assign led[0] = clk_locked; 
    assign led[1] = ps_busy; 
    assign led[3:2] = sw_mode; 

    // ==========================================
    // 6. ILA (Integrated Logic Analyzer)
    // ==========================================
    // ★ 주의: ILA IP 설정 시 probe5의 Width를 2로 수정해야 합니다!
    ila_0 your_ila_instance (
        .clk    (tdc_clk), 
        .probe0 (final_ts_valid),               // [0:0]  트리거 조건
        .probe1 (tdc_hit_in),                   // [0:0]  현재 MUX된 Hit 신호
        .probe2 (final_timestamp_ps[47:0]),     // [47:0] 절대 시간 (ps)
        .probe3 (pulse_interval_ps[47:0]),      // [47:0] ★펄스 간 간격(Interval, ps)
        .probe4 (aligned_fine_idx),             // [8:0]  보정 전 Raw 탭 번호 
        .probe5 (sw_mode)                       // [1:0]  ★현재 선택된 모드
    );

endmodule