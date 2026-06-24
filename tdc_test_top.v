`timescale 1ns / 1ps

module tdc_test_top (
    input wire clk_125, 
    input wire rst_n, 
    input wire btn_shift, 
    output wire [3:0] led
);

    // ==========================================
    // 1. Clock & MMCM Phase Shifter
    // ==========================================
    parameter TEST_MODE_MMCM = 1; // 1: MMCM Sweep Mode, 0: RO Test Mode

    wire clk_200_fixed, clk_200_shifted, clk_locked;
    wire psen, psincdec, psdone, ps_busy; 
    wire [8:0] current_loop_cnt; 

    clk_wiz_0 u_clk (
        .clk_in1(clk_125), .reset(rst_n), 
        .clk_out1(clk_200_fixed), .clk_out2(clk_200_shifted), 
        .psclk(clk_200_fixed), .psen(psen), .psincdec(psincdec), .psdone(psdone), 
        .locked(clk_locked)
    );
    
    mmcm_phase_shifter u_ps_ctrl (
        .clk(clk_200_fixed), .rst_n(clk_locked), .start_shift(btn_shift), 
        .psen(psen), .psincdec(psincdec), .psdone(psdone), 
        .busy(ps_busy), .loop_cnt(current_loop_cnt)
    );

    // [MMCM Test Hit 생성] (약 250us 주기)
  reg [15:0] sync_cnt; 
    reg test_hit_sync;
    
    always @(posedge clk_200_fixed) begin 
        if (!clk_locked) begin 
            sync_cnt <= 0; 
            test_hit_sync <= 0; 
        end else begin 
            // 1. 카운터는 무조건 0 ~ 49999 반복
            if (sync_cnt == 16'd49999) begin 
                sync_cnt <= 0; 
            end else begin 
                sync_cnt <= sync_cnt + 1; 
            end 

            // 2. 카운트 값이 0, 1, 2, 3 인 4개의 클럭(20ns) 동안만 HIGH 유지
            // (49999에서 0으로 넘어간 직후부터 4클럭 동안 1이 유지됨)
            if (sync_cnt < 16'd4) begin
                test_hit_sync <= 1'b1;
            end else begin
                test_hit_sync <= 1'b0;
            end
        end 
    end

    // ==========================================
    // 2. Ring Oscillator (유지됨, 현재 미사용)
    // ==========================================
    (* ALLOW_COMBINATORIAL_LOOPS = "TRUE", KEEP = "TRUE", DONT_TOUCH = "TRUE" *) wire [30:0] ro_chain;
    genvar r; 
    generate 
        for(r=0; r<30; r=r+1) begin : RO_LOOP 
            (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *) LUT1 #(.INIT(2'h1)) u_lut_inv (.I0(ro_chain[r]), .O(ro_chain[r+1])); 
        end 
    endgenerate
    (* KEEP = "TRUE", DONT_TOUCH = "TRUE" *) LUT1 #(.INIT(2'h1)) u_lut_inv_fb (.I0(ro_chain[30]), .O(ro_chain[0]));

    wire ro_clk_buffered; 
    BUFG u_bufg_ro (.I(ro_chain[30]), .O(ro_clk_buffered));
    reg [15:0] ro_divider_cnt = 0; 
    always @(posedge ro_clk_buffered) ro_divider_cnt <= ro_divider_cnt + 1'b1;

    // 입력 소스 선택 (TEST_MODE_MMCM 파라미터에 따름)
    wire hit_random = ro_divider_cnt[5]; 
    wire test_hit  = (TEST_MODE_MMCM) ? test_hit_sync   : hit_random;
    wire tdc_clk   = (TEST_MODE_MMCM) ? clk_200_shifted : clk_200_fixed;

    // ==========================================
    // 3. TDC Core Instance
    // ==========================================
    wire [31:0] ts_coarse; 
    wire [8:0] ts_fine_idx; 
    wire ts_valid;
    
    tdc_fmcw_core u_tdc (
        .clk(tdc_clk), .rst_n(clk_locked), .hit(test_hit), 
        .ts_coarse(ts_coarse), .ts_fine_idx(ts_fine_idx), .ts_valid(ts_valid)
    );
    
    assign led[0] = clk_locked; 
    assign led[1] = ps_busy; 
    assign led[3:2] = 2'b00;

    // ==========================================
    // 4. Raw Data 파이프라인 및 ILA (ROM 계산 삭제)
    // ==========================================
    // ILA 배선 지연(Routing congestion)을 막기 위한 2-Stage DFF
    reg [31:0] ts_coarse_d1, ts_coarse_d2;
    reg [8:0]  ts_fine_idx_d1, ts_fine_idx_d2;
    reg        ts_valid_d1, ts_valid_d2;
    
    always @(posedge tdc_clk) begin
        if (!clk_locked) begin
            ts_coarse_d1 <= 0; ts_fine_idx_d1 <= 0; ts_valid_d1 <= 0;
            ts_coarse_d2 <= 0; ts_fine_idx_d2 <= 0; ts_valid_d2 <= 0;
        end else begin
            // Stage 1
            ts_coarse_d1 <= ts_coarse;
            ts_fine_idx_d1 <= ts_fine_idx;
            ts_valid_d1 <= ts_valid;
            
            // Stage 2 (To ILA)
            ts_coarse_d2 <= ts_coarse_d1;
            ts_fine_idx_d2 <= ts_fine_idx_d1;
            ts_valid_d2 <= ts_valid_d1;
        end
    end

    // ILA 프로브 수정: ROM 결과 대신 Raw 데이터와 MMCM Loop Count를 매칭하여 캡처
    ila_0 your_ila_instance (
        .clk(tdc_clk), 
        .probe0(ts_valid_d2),      // Trigger condition (== 1)
        .probe1(ts_coarse_d2),     // Coarse counter
        .probe2(ts_fine_idx_d2),   // Raw Fine Index (0 ~ 320)
        .probe3(psdone),           // Phase shift done status
        .probe4(current_loop_cnt)  // MMCM Sweep Step (0 ~ 280) -> 이것이 절대 시간의 기준이 됨
    );

endmodule