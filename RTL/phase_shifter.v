`timescale 1ns / 1ps
// =============================================================================
// 모듈명: mmcm_phase_shifter
// 수정일: 2026-09-04
// =============================================================================
//
//  [★ 2026-09-04 전면 재설계 — "280스텝 자동 스윕" -> "목표 위상으로 이동"]
//
//  무엇이 바뀌었나
//    기존 : start_shift 에지 한 번에, 280스텝을 스텝당 10 ms 씩 머물며 자동으로
//           끝까지 훑고 IDLE 로 돌아옴. (2.8초 걸리는 통짜 동작)
//    변경 : phase_tgt 가 가리키는 위치까지 이동하고 멈춤. 스텝 사이 대기 없음.
//
//  왜 바꾸나
//    (1) 스윕은 이제 PS 의 for 문이다. AXI-Lite 로 phase_tgt 를 쓰고 busy 가 내려가길
//        기다리는 일을 반복하면 그게 스윕이므로, 하드웨어가 스윕을 품을 이유가 없다.
//        덤으로 스텝당 체류 시간을 PS 가 정한다 (기존엔 10 ms 로 박혀 있었다).
//    (2) 지터 평가(mode 1)는 "한 위상에 세워두고 반복 측정" 이라, 애초에 필요한 것이
//        '훑기' 가 아니라 '그 자리로 가기' 다.
//    ※ Zybo 보드 2대는 2026-09-04 부로 사용 중단. 옛 스윕 동작을 보존할 이유가 없어졌다.
//
//  [핵심 변경은 사실상 한 줄이다]
//    기존 IDLE 에 있던  loop_cnt <= 0;  을 지운 것.
//    이 줄이 있으면 카운터는 "이번에 몇 걸음 걸었나"(상대 걸음수) 이고,
//    지우면 "지금 어느 자리에 서 있나"(절대 위치) 가 된다.
//    MMCM 의 실제 위상은 시작할 때 0 으로 돌아가지 않으므로, 절대 위치로 추적해야만
//    "목표 위치로 이동" 이 성립한다. (예전 방식으로 137번에서 다시 시작해 200걸음을
//     걸으면 실제 도착지는 200 이 아니라 337 mod 280 = 57 이다.)
//
//  [방향은 증가만 쓴다 — psincdec 고정 1]
//    목표가 현재보다 뒤에 있으면 279 -> 0 으로 넘어가며 계속 증가해서 도달한다.
//    감소 방향은 이 프로젝트의 모든 교정 측정에서 한 번도 쓰인 적이 없어 특성이
//    검증되지 않았다. 최악의 경우 279스텝이지만 스텝 사이 대기가 없어 부담이 작다.
//    ※ psen -> psdone 한 스텝의 실제 지연은 아직 실측된 적이 없다 (예전 코드가 스텝마다
//      10 ms 를 강제로 기다려서 가려져 있었다). 첫 빌드에서 확인할 것.
//
//  [위상 스텝 번호는 0 ~ 279]
//    280스텝 x 17.857 ps = 5000 ps 로 한 주기를 정확히 덮는다 (VCO 1000 MHz 의 1/56).
//    기존 loop_cnt 는 1~280 으로 세는 걸음수였는데, 이제는 0~279 위치 인덱스다.
//    코드베이스 다른 곳(ILA 주석 "기준 위상 스텝 (0~279)")과도 이제 맞는다.
// =============================================================================

module mmcm_phase_shifter #(
    // 한 주기를 덮는 위상 스텝 수. VCO 1000 MHz / 56 = 17.857 ps 스텝 기준 280.
    // clk_wiz_0 의 VCO 를 바꾸면 이 값도 반드시 같이 바꿔야 한다.
    parameter integer STEPS_PER_PERIOD = 280
)(
    input  wire       clk,
    input  wire       rst_n,

    input  wire [8:0] phase_tgt,           // 목표 위상 스텝 (0 ~ STEPS_PER_PERIOD-1)

    output reg        psen,                // MMCM 위상시프트 요청 (1클럭 펄스)
    output wire       psincdec,            // 방향 : 항상 증가
    input  wire       psdone,              // MMCM 이 한 스텝 반영 완료

    output reg        busy,                // phase_cur != phase_tgt 인 동안 1
    output reg [8:0]  phase_cur,           // 현재 위상 스텝 (0 ~ STEPS_PER_PERIOD-1)
    output reg        loop_updated_toggle  // 스텝이 하나 진행될 때마다 토글 (CDC 용)
);

    assign psincdec = 1'b1;   // 증가 방향 고정 — 위 주석 [방향은 증가만 쓴다] 참조

    // 범위 밖 목표가 들어오면 영원히 도달 못 해 busy 가 안 내려간다(행). 0 으로 묶어
    // 최소한 멈추게 한다. 정상 범위 검사는 AXI 레지스터 쪽에서 하는 것이 맞다.
    wire [8:0] tgt_safe = (phase_tgt >= STEPS_PER_PERIOD) ? 9'd0 : phase_tgt;

    localparam IDLE = 1'b0, WAIT_DONE = 1'b1;
    reg state;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            psen                <= 1'b0;
            busy                <= 1'b0;
            phase_cur           <= 9'd0;   // MMCM 리셋 시 실제 위상도 0 이므로 일치한다
            loop_updated_toggle <= 1'b0;
            state               <= IDLE;
        end else begin
            case (state)
                // 목표와 다르면 한 스텝 요청하고, 같으면 그냥 쉰다.
                IDLE: begin
                    if (phase_cur != tgt_safe) begin
                        busy  <= 1'b1;
                        psen  <= 1'b1;          // 다음 1클럭 동안만 High
                        state <= WAIT_DONE;
                    end else begin
                        busy  <= 1'b0;
                        psen  <= 1'b0;
                    end
                end

                // psdone 을 기다렸다가 위치를 하나 진행시키고 IDLE 로 돌아가
                // 목표에 닿았는지 다시 판단한다.
                WAIT_DONE: begin
                    psen <= 1'b0;
                    if (psdone) begin
                        phase_cur <= (phase_cur == STEPS_PER_PERIOD - 1)
                                     ? 9'd0 : (phase_cur + 1'b1);
                        loop_updated_toggle <= ~loop_updated_toggle;
                        state <= IDLE;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end
endmodule
