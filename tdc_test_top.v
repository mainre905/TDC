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
    wire [8:0]  aligned_fine_idx;
    wire [31:0] aligned_coarse;

    tdc_timestamp_calc u_ts_calc (
        .clk             (tdc_clk),
        .rst_n           (clk_locked),
        .ts_coarse       (raw_ts_coarse),
        .ts_fine_idx     (raw_ts_fine_idx),
        .ts_valid        (raw_ts_valid),
        .timestamp_ps    (final_timestamp_ps),
        .timestamp_valid (final_ts_valid),
        .fine_idx_out    (aligned_fine_idx),
        .coarse_out      (aligned_coarse)         
    );

    // ==========================================================
    // 5. 온칩 ILA 리드아웃 스캐너 (350 도달 시 자동 출력)
    // ==========================================================
    reg        readout_active;
    reg [8:0]  sweep_addr;
    reg [8:0]  probe_read_addr;

    // ★ ILA 리드아웃 정렬 수정: BRAM read latency 보상용 주소 지연 레지스터
    // 히스토그램 BRAM의 Port B는 출력이 레지스터드(dout_b <= mem[addr_b])라 read latency가 1클럭입니다.
    //   → 사이클 N의 histo_read_data = 사이클 N-1의 read_addr가 가리킨 값
    // ILA는 probe1(주소)과 probe2(데이터)를 같은 엣지에서 캡처하므로, 주소를 그대로 연결하면
    // "주소 N" 옆에 "bin N-1의 카운트"가 찍혀 히스토그램 전체가 1-bin 밀립니다.
    // 주소도 데이터와 똑같이 1클럭 지연시켜 동일 사이클에서 짝이 맞도록 정렬합니다.
    reg [8:0]  probe_read_addr_d1;

    // ★ CDC 및 조기 트리거 수정 1: 이종 클럭(fixed -> shifted) 간 안전한 ps_busy 동기화를 위한 3단 FF 구현
    reg ps_busy_sync_d1;
    reg ps_busy_sync_d2;
    reg ps_busy_sync_d3; // 하강 에지 검출용 지연 레지스터

    always @(posedge tdc_clk or negedge clk_locked) begin
        if (!clk_locked) begin
            ps_busy_sync_d1 <= 1'b0;
            ps_busy_sync_d2 <= 1'b0;
            ps_busy_sync_d3 <= 1'b0;
        end else begin
            ps_busy_sync_d1 <= ps_busy;
            ps_busy_sync_d2 <= ps_busy_sync_d1; // 메타스테빌리티 방지 보장
            ps_busy_sync_d3 <= ps_busy_sync_d2; // 하강 에지 구분을 위해 1클럭 더 지연
        end
    end

    // ★ CDC 및 조기 트리거 수정 2: 
    // 다중 비트 loop_cnt 비교 대신, 280단계 대기가 끝나고 ps_busy가 1에서 0으로 떨어지는 순간(하강 에지)을 
    // 검출하여 대기 시간이 완전히 충족된 최종 시점에 정확히 readout을 가동시킵니다.
    wire sweep_finished = (!ps_busy_sync_d2 && ps_busy_sync_d3);

    always @(posedge tdc_clk or negedge clk_locked) begin
        if (!clk_locked) begin
            readout_active     <= 1'b0;
            sweep_addr         <= 9'd0;
            probe_read_addr    <= 9'd0;
            probe_read_addr_d1 <= 9'd0;
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
            probe_read_addr    <= sweep_addr;      // BRAM Port B로 나가는 실제 읽기 주소
            probe_read_addr_d1 <= probe_read_addr; // ★ BRAM 1클럭 지연분 보상 → ILA에서 histo_read_data와 동일 사이클
        end
    end

    // ==========================================================
    // 6. 히스토그램 데이터 게이팅 및 모듈 인스턴스 (핵심 수정)
    // ==========================================================
    wire gated_ts_valid;

    generate
        if (OPERATION_MODE == 0) begin : MODE_0_HISTO_CTRL
            // Mode 0: 스윕(Phase Shift) 중일 때만 Hit 누적! (대기 중 쌓이는 쓰레기 값 차단)
            // ★ CDC 수정 3: tdc_clk 도메인으로 동기화가 완료된 ps_busy_sync_d2를 적용하여 글리치 및 타이밍 불일치 차단
            assign gated_ts_valid = final_ts_valid && ps_busy_sync_d2;
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
    // ★ Entry transient 수정: 과거 led[2]에 tdc_hit_in을 연결했으나 제거함.
    //   hit 네트가 딜레이라인 CYINIT과 LED 패드(G14)를 동시에 구동하면서
    //   배선 부하로 에지 slew가 저하되고, 그 결과 CARRY4 초입에 entry transient 발생.
    //   (실측: net delay 4227ps / CARRY4#0 소비시간 129.71ps = 이상값 68.5ps의 1.89배,
    //    #1 1.51배, #2 1.16배로 감쇠하다 #3부터 정상 회복 → DNL 최댓값 +3.234의 주범)
    //   hit은 CYINIT 외에 어떤 부하도 걸어서는 안 되므로 연결하지 않는다.
    assign led[2] = 1'b0;
    assign led[3] = final_ts_valid; 

    // ==========================================================
    // 7. ILA (Integrated Logic Analyzer)
    // ==========================================================
    // [현재 모드] 캘리브레이션 검증용 timestamp 캡처
    //   목적: COE 적용 전(선형 COE)/후(code-density COE)를 '동일한 ILA·동일한 분석'으로 비교.
    //         측정값 = final_timestamp_ps, 참 시간 기준 = current_loop_cnt(위상 스텝).
    //   분석: fine = (-timestamp) mod 5000  →  fine vs loop_cnt 선형성(DNL/INL).
    //   ★ ila_0 IP를 재구성할 것: probe2 폭 32 → 48비트 (final_timestamp_ps[47:0] 수용).
    //     나머지 probe 폭(1/9/9/9)은 그대로.
    ila_0 your_ila_instance (
        .clk    (tdc_clk),
        .probe0 (final_ts_valid),            // [0:0]  Trigger: '1' (유효 히트마다)
        .probe1 (aligned_fine_idx),          // [8:0]  raw tap (참고)
        .probe2 (final_timestamp_ps[47:0]),  // [47:0] 측정 출력 (상위 비트는 항상 0이라 생략)
        .probe3 (current_loop_cnt),          // [8:0]  위상 스텝 = 참 시간 기준
        .probe4 (aligned_fine_idx)           // [8:0]  (여분)
    );

    // [보존] 히스토그램(code density) 캡처용 — COE 생성 시 이 설정으로 되돌릴 것.
    //        되돌릴 때 ila_0 IP의 probe2 폭도 48 → 32로 다시 바꿔야 함.
    // ila_0 your_ila_instance (
    //     .clk    (tdc_clk),
    //     .probe0 (readout_active),       // [0:0]
    //     .probe1 (probe_read_addr_d1),   // [8:0] X축: Tap 번호 (histo_read_data와 정렬됨)
    //     .probe2 (histo_read_data),      // [31:0] Y축: 카운트 값
    //     .probe3 (current_loop_cnt),     // [8:0]
    //     .probe4 (aligned_fine_idx)      // [8:0]
    // );
endmodule