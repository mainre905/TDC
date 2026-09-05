`timescale 1ns / 1ps

module tdc_test_top #(
    // ==========================================================
    // 0 : Hit = Test Sync(내부)  | Clock = Shifted 200MHz (MMCM 캘리브레이션용)
    // 1 : Hit = Ring Osc(랜덤)   | Clock = Fixed 200MHz  (기본 동작 및 탭 누적 테스트용)
    // 2 : Hit = 외부 STM32 신호  | Clock = Fixed 200MHz  (실제 측정용)
    // ==========================================================
    parameter integer OPERATION_MODE = 1,

    // ★ [2026-09-03 추가] 캐리체인 단수 (탭 수 = CARRY4_STAGES x 4)
    //   ZedBoard 는 tdc_zedboard_top.v 에서 96단(384탭)으로 넘긴다. 이유는
    //   tdc_fmcw_core_co.v 상단의 ★ 2026-09-03 주석 참조.
    //   기본값 80단(320탭)은 옛 Zybo 빌드용이었다. Zybo 는 2026-09-04 부로 사용
    //   중단했으므로 지금 실제로 쓰이는 값은 96단뿐이다.
    //   ※ 16의 배수여야 popcount 트리가 4x(N/16)x16 으로 떨어진다 (80, 96, 112 ...).
    //   ※ 448 초과 금지 — sum_fine/ts_fine_idx 가 [8:0](<=511) 이고 히스토그램이 512칸이다.
    parameter integer CARRY4_STAGES  = 80
)(
    input  wire       clk_125, 
    input  wire       rst_n, 
    input  wire       btn_shift,   
    input  wire       ext_hit_in,  
    output wire [3:0] led,

    // ★ [2026-09-04 추가] AXI 레지스터 블록이 볼 TDC 도메인 신호들.
    //   tdc_axi_regs 가 이 신호들을 AXI 도메인으로 동기화해 PS 에 보여준다.
    //   2단계에서 시퀀서가 붙으면 busy/done 도 여기로 나온다.
    output wire       o_tdc_clk,      // clk_200_fixed — AXI 레지스터의 TDC 도메인 클럭
    output wire       o_locked,       // MMCM lock
    output wire [30:0] o_dna,         // 보드 식별자 (ILA probe9 와 같은 31비트)
    output wire       o_dna_valid,
    output wire       o_phase_busy    // 위상 이동 중
);


    // ★ [2026-09-03 추가] 탭 수 — 히스토그램 리드아웃 스캔 범위에 쓴다.
    //   히스토그램 BRAM 은 512칸(tdc_bram_512x32)이므로 448탭까지 그대로 담긴다.
    localparam integer NUM_TAPS = CARRY4_STAGES * 4;

    // ==========================================
    // 1. Clock Generation & MMCM Phase Shifter
    // ==========================================
    wire clk_200_fixed, clk_200_shifted, clk_locked;
    wire psen, psincdec, psdone, ps_busy; 
    wire [8:0] current_loop_cnt; 
    wire loop_updated_toggle; // ★ 2026-08-19 추가: 1단 CDC용 토글 와이어

    // ==========================================================
    // ★ 2026-08-20 추가 — Device DNA(칩 고유 ID) 보드 식별자
    //
    //  왜: Zybo 보드가 2대(회사/집)인데 캡처 CSV에 어느 보드인지 기록이 없었다.
    //      두 칩은 공정 편차로 지연선이 다르다 — 실측:
    //        집  보드  유효탭 299  LSB 16.722 ps  (8/04, 8/09, 8/12, 8/13)
    //        회사 보드  유효탭 284  LSB 17.606 ps  (8/06 온도셋, 8/20)
    //        같은 칩끼리 탭 폭 상관 r=0.999 (빌드가 달라도), 다른 칩끼리 r=0.54
    //      CARRY4 와 FF 이 tdc.xdc 로 같은 슬라이스에 고정돼 있어 탭 폭은 그
    //      슬라이스의 실리콘이 정한다. 보드가 바뀌면 지연선이 바뀐다.
    //      이 값을 ILA 에 찍어 모든 캡처에 보드 식별자를 영구히 남긴다.
    //      상세는 RTL/dna_reader.v 헤더 참조.
    // ==========================================================
    wire [56:0] device_dna;
    wire        device_dna_valid;

    dna_reader #(
        .CLK_DIV (16)                 // 200 MHz / 16 = 12.5 MHz (보수적)
    ) u_dna (
        .clk       (clk_200_fixed),
        .rst_n     (clk_locked),
        .dna       (device_dna),
        .dna_valid (device_dna_valid)
    );

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
    
    // ==========================================================
    // ★ [2026-09-04] phase_shifter 가 "목표 위상으로 이동" 방식으로 바뀌었다.
    //   (기존: start_shift 한 번에 280스텝 자동 스윕 -> 변경: phase_tgt 로 이동)
    //   이유와 상세는 RTL/phase_shifter.v 상단 주석 참조.
    //
    //   [아래 phase_tgt_reg 는 AXI 도입 전까지의 임시 구동부다]
    //   버튼(btn_shift)을 누를 때마다 목표 위상을 한 칸 올린다. 그러면
    //     목표 변경 -> ps_busy 상승 -> 이동 완료 -> ps_busy 하강
    //   이 되어, 기존의 sweep_finished(ps_busy 하강 에지) -> 히스토그램 리드아웃
    //   경로가 그대로 살아 있다. 예전엔 리드아웃 한 번 보려고 280스텝 2.8초를
    //   기다려야 했는데, 이제는 버튼 누르면 곧바로 뜬다.
    //
    //   ★ AXI 레지스터가 들어오면 이 블록을 통째로 지우고 phase_tgt 를
    //     CTRL/PHASE_TGT 레지스터에 직접 연결할 것.
    // ==========================================================
    reg [8:0] phase_tgt_reg  = 9'd0;
    reg       btn_shift_d1   = 1'b0;
    always @(posedge clk_200_fixed) begin
        btn_shift_d1 <= btn_shift;
        if (btn_shift && !btn_shift_d1)
            phase_tgt_reg <= (phase_tgt_reg == 9'd279) ? 9'd0 : (phase_tgt_reg + 1'b1);
    end

    mmcm_phase_shifter u_ps_ctrl (
        .clk                 (clk_200_fixed), 
        .rst_n               (clk_locked), 
        .phase_tgt           (phase_tgt_reg),   // ★ 2026-09-04 : start_shift 대체
        .psen                (psen), 
        .psincdec            (psincdec), 
        .psdone              (psdone), 
        .busy                (ps_busy), 
        .phase_cur           (current_loop_cnt),// ★ 2026-09-04 : 포트명 loop_cnt -> phase_cur
        .loop_updated_toggle (loop_updated_toggle) // ★ 2026-08-19 추가
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
    
    
    // ==========================================================
    // ★ RO 주파수 카운터 — 2026-07-24 수정 (원본: 1초 게이트, ÷64 탭)
    // ==========================================================
    //  [변경1] 게이트 1s -> 10ms.
    //     이유: injection lock 판정은 평균이 아니라 '변동'으로 해야 한다.
    //           잠긴 RO는 매번 정확히 같은 값이 나오고, 자유발진 RO는 흔들린다.
    //           1s 게이트는 ILA 한 캡처(=5us 창)에 값이 1개뿐이라 변동을
    //           볼 수 없었다. 10ms면 storage qualification으로 1024샘플
    //           = 10.24초 이력을 한 번에 확보한다.
    //     주의: code density에는 이 '흔들림'이 오히려 필수다. RO가 드리프트해야
    //           hit이 클럭 주기 전 위상을 고르게 훑는다.
    //  [변경2] 측정 탭 ro_divider_cnt[5](÷64) -> [1](÷4).
    //     이유: hit_random([5])은 TDC 데드타임(~15ns) 확보용이라 그대로 두고,
    //           주파수 카운터만 별도 탭을 쓴다. 같은 게이트에서 카운트 16배
    //           -> 분해능 16배. Nyquist: f_RO=40MHz 가정 시 탭 주파수 10MHz,
    //           200MHz 샘플링으로 주기당 20샘플이라 여유 충분.
    //  [변경3] gate_tick과 에지가 같은 사이클에 겹치면 그 에지가 유실되던 버그
    //           수정 (원본은 카운터를 무조건 0으로 리셋했음).
    //  [변경4] meas_strobe 추가 — ILA storage qualification용.
    //           gate_tick 시점에 캡처하면 '갱신 전' 값이 잡히므로 1클럭 지연.
    // ==========================================================
    localparam integer GATE_CYCLES = 2_000_000;  // 10 ms @ 200MHz
    localparam integer RO_MEAS_TAP = 1;          // ro_divider_cnt 탭 (÷4)

    reg [20:0] gate_cnt  = 0;
    reg        gate_tick = 0;
    always @(posedge clk_200_fixed) begin
        if (gate_cnt == GATE_CYCLES-1) begin
            gate_cnt  <= 0;
            gate_tick <= 1'b1;
        end else begin
            gate_cnt  <= gate_cnt + 1'b1;
            gate_tick <= 1'b0;
        end
    end

    // RO(비동기) -> 200MHz 도메인 동기화. ASYNC_REG로 배치 밀착 유도(MTBF 확보).
    wire ro_meas_tap = ro_divider_cnt[RO_MEAS_TAP];
    (* ASYNC_REG = "TRUE" *) reg ro_sync_d1 = 0;
    (* ASYNC_REG = "TRUE" *) reg ro_sync_d2 = 0;
    reg ro_sync_d3 = 0;
    always @(posedge clk_200_fixed) begin
        ro_sync_d1 <= ro_meas_tap;
        ro_sync_d2 <= ro_sync_d1;   // 메타스테빌리티 해소
        ro_sync_d3 <= ro_sync_d2;   // 에지 검출용 1클럭 추가 지연
    end
    wire ro_edge = (ro_sync_d2 && !ro_sync_d3);

    reg [31:0] ro_edge_cnt  = 0;
    (* mark_debug = "true" *) reg [31:0] ro_meas_cnt = 0;  // 게이트(10ms)당 에지 수
    reg        meas_strobe  = 0;

    always @(posedge clk_200_fixed) begin
        if (gate_tick) begin
            ro_meas_cnt <= ro_edge_cnt;
            ro_edge_cnt <= ro_edge ? 32'd1 : 32'd0;  // [변경3] 겹침 시 유실 방지
        end else if (ro_edge) begin
            ro_edge_cnt <= ro_edge_cnt + 1'b1;
        end
        meas_strobe <= gate_tick;                    // [변경4] 갱신 확정 사이클
    end

    // ==========================================================
    // ★ XADC 다이 온도 — 2026-07-24 신규
    // ==========================================================
    //  목적: RO 주파수와 온도의 상관을 '동시 캡처'로 확인하기 위함.
    //        (기존에는 Hardware Manager의 System Monitor를 눈으로 읽어
    //         ILA 값과 손으로 짝지어야 해서 동시성이 없었다.)
    //  동작: 변환 완료(eoc) -> DRP 주소 0x00(온도) 1회 읽기 -> drdy에 래치.
    //  환산: Temp[C] = (do_out[15:4] * 503.975 / 4096) - 273.15
    //        (12비트 결과가 16비트 레지스터의 상위에 정렬되어 있음)
    //  gate_tick에 함께 래치해 ro_meas_cnt와 시점을 명시적으로 맞춘다.
    // ==========================================================
    wire        xadc_eoc, xadc_drdy;
    wire [15:0] xadc_do;
    reg         xadc_den      = 1'b0;
    reg [15:0]  die_temp_raw  = 16'd0;
    (* mark_debug = "true" *) reg [15:0] die_temp_at_meas = 16'd0;

    always @(posedge clk_200_fixed) begin
        xadc_den <= 1'b0;                       // 기본 0, eoc에서만 1클럭 펄스
        if (xadc_eoc)  xadc_den     <= 1'b1;
        if (xadc_drdy) die_temp_raw <= xadc_do;
        if (gate_tick) die_temp_at_meas <= die_temp_raw;  // 주파수와 시점 정렬
    end

    xadc_wiz_0 u_xadc (
        .daddr_in    (7'h00),          // 0x00 = on-chip temperature
        .dclk_in     (clk_200_fixed),
        .den_in      (xadc_den),
        .di_in       (16'h0000),
        .dwe_in      (1'b0),
        .do_out      (xadc_do),
        .drdy_out    (xadc_drdy),
        .reset_in    (1'b0),
        .vp_in       (1'b0),
        .vn_in       (1'b0),
        .busy_out    (),
        .channel_out (),
        .eoc_out     (xadc_eoc),
        .eos_out     (),
        .alarm_out   ()
    );

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
    
    // 탭 소스 전환 : tdc_fmcw_core(O/XOR 출력) <-> tdc_fmcw_core_co(CO/캐리 출력)
    //   모듈명 한 단어만 바꾸면 된다. 포트와 내부 인스턴스 이름이 동일하므로
    //   tdc.xdc 의 LOC/BEL 제약이 양쪽 모두에 그대로 적용된다.
    //   실측(2026-08-04, 빌드 통제 완료) : INL p-p 155.8(O) -> 96.8(CO) ps,
    //   40->80 C 무보정 드리프트 69.7(O) -> 8.3(CO) ps. 상세는
    //   Markdown/2026-08-04_report.md §2-7 / §3-5 참조.
    // ★ 2026-08-22 : tdc_fmcw_core(O 탭) -> tdc_fmcw_core_co(CO 탭) 로 전환.
    //   집 보드 CO 단일 지연선 캠페인(Markdown/2026-08-22_home_board_campaign.md) 대상이다.
    // ★ 2026-09-03 : 단수를 상위에서 넘긴다 (Zybo 80단 / ZedBoard 112단)
    tdc_fmcw_core_co #(
        .CARRY4_STAGES (CARRY4_STAGES)
    ) u_tdc (
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
                // ★ [2026-09-03] 320탭 고정 -> NUM_TAPS 유도.
                //   80단이면 319, 112단이면 447 에서 스캔이 끝난다.
                //   이 값을 안 고치면 448탭 빌드에서 뒤쪽 128칸이 영영 안 읽혀,
                //   유효탭 상한을 히스토그램에서 읽어낸다는 이번 확장의 목적 자체가 무산된다.
                if (sweep_addr == (NUM_TAPS - 1)) begin
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
    // (1) MMCM 스텝(loop_cnt) 변경 감지 및 단발성 트리거 생성 로직
    //
    // ==========================================================
    // ★ [2026-08-19 CDC 1단 동기화 수정] 
    // 기존의 멀티비트 current_loop_cnt 직접 비교 조건(current_loop_cnt != prev_loop_cnt)은
    // 이종 클럭(clk_200_fixed -> tdc_clk) 간 비동기 샘플링 및 버스 스큐 문제로 인해 
    // 메타스테빌리티 및 유령 값 인식으로 loop_cnt 결손/중복 트리거를 유발했습니다.
    // 이에 mmcm_phase_shifter에서 생성된 1비트 loop_updated_toggle 신호를
    // FF로 동기화하여 스텝당 단 1회의 capture_trigger만 안전하게 생성합니다.
    //
    // ★ [2026-08-20 수정 ①] 동기화기를 1단 -> 2단으로.
    //   무엇이 문제였나 : toggle_sync_d1 이 비동기 신호를 직접 받는데, 그 값이 곧바로
    //     XOR 에 들어가고 있었다. d1 이 메타스테이블이면 그대로 펄스로 전파된다.
    //     d2 는 메타스테이빌리티 해소용이 아니라 에지 검출용 지연이었다.
    //   같은 파일의 다른 두 CDC 경로는 이미 제대로 돼 있다 —
    //     ps_busy : d1,d2 동기화 + d3 에지검출 (3단)
    //     RO      : ro_sync_d1, ro_sync_d2 둘 다 ASYNC_REG
    //   이 경로만 한 단 부족했다. d1·d2 를 동기화 2단으로 쓰고 d3 를 에지검출로 분리한다.
    //   d1,d2 둘 다 ASYNC_REG 여야 배치기가 두 FF 을 밀착시켜 해소 시간을 확보한다.
    //   비용 : FF 1개, 지연 1클럭(5 ns). 스텝 체류가 10 ms 이므로 무의미하다.
    //   주의 : 2026-08-20 실측(6캡처 x 280스텝)에서 결손·중복은 0 이었다. 관측된
    //          고장을 고치는 것이 아니라 여유를 확보하는 예방적 수정이다.
    // ==========================================================

    (* ASYNC_REG = "TRUE" *) reg toggle_sync_d1 = 1'b0; // 동기화 1단 (비동기 입력)
    (* ASYNC_REG = "TRUE" *) reg toggle_sync_d2 = 1'b0; // 동기화 2단 ★2026-08-20 추가
    reg                      toggle_sync_d3 = 1'b0;     // 에지 검출용 1클럭 지연

    always @(posedge tdc_clk or negedge clk_locked) begin
        if (!clk_locked) begin
            toggle_sync_d1 <= 1'b0;
            toggle_sync_d2 <= 1'b0;
            toggle_sync_d3 <= 1'b0;
        end else begin
            toggle_sync_d1 <= loop_updated_toggle; // CDC 1단
            toggle_sync_d2 <= toggle_sync_d1;      // CDC 2단 (메타스테빌리티 해소)
            toggle_sync_d3 <= toggle_sync_d2;      // 에지 검출용
        end
    end

    // 스텝 변경 에지 검출 펄스 — 해소가 끝난 d2/d3 로 만든다
    wire step_changed_pulse = (toggle_sync_d2 ^ toggle_sync_d3);

    // ==========================================================
    // ★ [2026-08-20 수정 ②] 스텝당 1샘플 -> CAP_PER_STEP 샘플
    //
    //   무엇이 문제였나 : 위상 스텝 하나에 히트가 20만 개(10 ms / 50 ns) 지나가는데
    //     capture_arm 이 첫 히트에서 바로 해제되어 ILA 에 1개만 저장됐다. 그 1개는
    //     양자화된 값이라 반드시 어느 탭 하나의 값으로만 나온다.
    //
    //   실측 근거 (2026-08-20, python/test_20260820/) :
    //     반복 3회 캡처로 잰 점당 측정 잡음  sigma_n = 7.79 ps (before) / 7.89 ps (after)
    //     이 값은 히스토그램에서 유도한 양자화 한계 8.20 ps 와 일치한다.
    //       8.20 = sqrt( sum(w[i]^2 * p[i]) / 12 ),  w=탭 폭, p=h[i]/H
    //     DNL 은 이웃 점의 차이라 잡음이 sqrt(2) 배 :
    //       0.62 LSB = sqrt(2) x 7.79 / 17.857     <- 측정된 DNL rms 1.10 LSB 의 절반
    //       실제 DNL rms = sqrt(1.10^2 - 0.62^2) = 0.91 LSB
    //     즉 DNL 측정값의 절반 가까이가 측정 잡음이었다.
    //
    //   왜 여러 번 재면 나아지나 : 한 번 재면 탭 값밖에 못 얻지만, 여러 번 재서 평균하면
    //     탭 사이를 읽어낸다. 실제로 jitter_100.csv 에서 820 히트의 평균이 277.81 ps 로
    //     나왔는데 이는 탭 272 와 282 사이의 값이다 (어느 탭에도 없는 값).
    //     K 개를 평균하면 잡음이 sqrt(K) 배 줄어든다.
    //
    //   K 선택 : ILA depth 8192 가 상한이다 (XC7Z010 BRAM 60개 x 36Kb = 2,211,840 비트,
    //     probe9 추가 후 프로브 폭 합계 181 비트 -> depth 16384 는 2,965,504 비트로 초과).
    //     280 스텝 x K <= 8192  ->  K <= 29.
    //       K=16 : 4,480 샘플 (55 %), 점당 1.95 ps, DNL 잡음 0.15 LSB
    //       K=24 : 6,720 샘플 (82 %), 점당 1.59 ps, DNL 잡음 0.13 LSB
    //     여유를 두어 16 을 기본으로 한다. 필요하면 이 값만 바꾸면 된다.
    //     ※ 실제 BRAM 사용량은 ILA IP GUI 또는 report_utilization 으로 확인할 것.
    //
    //   주의 : 이것은 TDC 성능을 올리는 수정이 아니라 TDC 를 더 정확히 재기 위한
    //          측정 방법 수정이다. 탭 폭도 지터도 바뀌지 않는다.
    //
    //   분석 : 파이썬에서 같은 current_loop_cnt_stable 끼리 묶어 평균낼 것.
    //          df.groupby('current_loop_cnt_stable')['fine'].mean()
    // ==========================================================
    localparam [4:0] CAP_PER_STEP = 5'd16;   // 스텝당 저장할 히트 수 (1~29)

    reg [8:0] current_loop_cnt_stable = 9'd0;
    reg [4:0] cap_cnt                 = 5'd0; // ★2026-08-20 : capture_arm(1비트) 대체

    always @(posedge tdc_clk or negedge clk_locked) begin
        if (!clk_locked) begin
            cap_cnt                 <= 5'd0;
            current_loop_cnt_stable <= 9'd0;
        end else begin
            // 스텝이 바뀌는 순간 CAP_PER_STEP 발 장전 + 스텝 안정값 래치
            if (step_changed_pulse) begin
                cap_cnt                 <= CAP_PER_STEP;
                current_loop_cnt_stable <= current_loop_cnt;
            end
            // 유효 데이터가 나올 때마다 1발씩 소모. 0 이 되면 그 스텝의 캡처 종료
            else if (cap_cnt != 5'd0 && final_ts_valid) begin
                cap_cnt <= cap_cnt - 1'b1;
            end
        end
    end

    wire capture_trigger = (cap_cnt != 5'd0) && final_ts_valid;

   //ila_0 your_ila_instance (
     //   .clk    (tdc_clk),
     //   .probe0 (capture_trigger),           // [0:0]  캡처 조건 플래그
     //   .probe1 (current_loop_cnt),          // [8:0]  X축: 기준 위상 스텝 (0 ~ 279)
     //   .probe2 (final_timestamp_ps[47:0]),  // [47:0] Y축: TDC가 계산한 절대 시간
     //   .probe3 (aligned_fine_idx)           // [8:0]  참고용: 캡처된 Raw Tap 번호
   // );
     
     // (2) 통합 ILA 인스턴스 (Depth는 1024 ~ 4096 정도로 넉넉히 설정)
    ila_0 universal_ila (
        .clk    (tdc_clk),
        
        // --- [INL 측정용 프로브 그룹] ---
        .probe0 (capture_trigger),           // [0:0]  INL 캡처 조건 (1일 때 캡처)
        .probe2 (current_loop_cnt_stable),   // [8:0]  ★ [2026-08-19 수정] 동기화된 안전 스텝 번호
        .probe3 (final_timestamp_ps[47:0]),  // [47:0] INL Y축: 절대 시간
        
        // --- [COE 추출을 위한 히스토그램 프로브 그룹 CODE DENSITY TEST] ---
        .probe1 (readout_active),            // [0:0]  히스토그램 캡처 조건 (1일 때 캡처)
        .probe4 (probe_read_addr_d1),        // [8:0]  히스토그램 X축: Tap 인덱스 (0~NUM_TAPS-1, 112단이면 0~447)
        .probe5 (histo_read_data),           // [31:0] 히스토그램 Y축: 누적 카운트 값

        // --- [RO 주파수/온도 특성화 그룹] 2026-07-24 추가 ---
        //   probe7을 storage qualification 조건으로 걸어야 게이트당 1샘플만
        //   저장되어 depth 1024 = 10.24초 이력이 된다. (basic 캡처로 뽑으면
        //   같은 값이 1024번 중복될 뿐 변동을 볼 수 없음)
        .probe6 (ro_meas_cnt),               // [31:0] 게이트(10ms)당 RO 에지 수
        .probe7 (meas_strobe),               // [0:0]  자격저장/트리거 조건
        .probe8 (die_temp_at_meas),          // [15:0] XADC 다이 온도 (raw)

        // --- [보드 식별] 2026-08-20 추가 ---
        //   ★ ila_0 IP 를 재구성할 것: probe 수 9 -> 10, probe9 폭 32비트.
        //     기존 probe0~8 의 폭은 그대로 두면 된다.
        //   구성 : {dna_valid, device_dna[30:0]}
        //     최상위 1비트가 0이면 아직 읽는 중이거나 실패한 것이니 그 캡처의
        //     보드 식별값은 믿지 말 것. 정상이면 리셋 후 수 us 안에 1이 된다.
        //     31비트만 뽑아도 보드 2대를 구분하기에는 충분하다.
        .probe9 ({device_dna_valid, device_dna[30:0]})   // [31:0] 보드 식별자
    );
  


    // [보존] 히스토그램(code density) 캡처용 - COE 생성 시 이 설정으로 되돌릴 것.
    //        되돌릴 때 ila_0 IP의 probe2 폭도 48 → 32로 다시 바꿔야 함.
    // ila_0 your_ila_instance (
    //     .clk    (tdc_clk),
    //     .probe0 (readout_active),       // [0:0]
    //     .probe1 (probe_read_addr_d1),   // [8:0] X축: Tap 번호 (histo_read_data와 정렬됨)
    //     .probe2 (histo_read_data),      // [31:0] Y축: 카운트 값
    //     .probe3 (current_loop_cnt),     // [8:0]
    //     .probe4 (aligned_fine_idx)      // [8:0]
    // );

    // ★ [2026-09-04] AXI 레지스터 블록으로 내보내는 TDC 도메인 신호
    assign o_tdc_clk    = clk_200_fixed;
    assign o_locked     = clk_locked;
    assign o_dna        = device_dna[30:0];
    assign o_dna_valid  = device_dna_valid;
    assign o_phase_busy = ps_busy;

endmodule
