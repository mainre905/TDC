# FPGA 기반 초정밀 TDC 시스템 및 STM32 Chirp 신호 연동/분석 보고서

## 1. 프로젝트 개요 (Overview)
본 프로젝트는 Xilinx Zynq-7000(Zybo Z7-20) FPGA 내부의 CARRY4 체인을 활용하여 **17.8ps의 초정밀 해상도를 갖는 TDC(Time-to-Digital Converter)**를 설계하고, 외부 STM32 마이크로컨트롤러에서 생성된 **고속 Chirp 펄스 신호(100kHz ~ 1MHz 선형 주파수 변조)**의 시간 간격을 오차 없이 측정하여 분석하는 것을 목표로 합니다.

---

## 2. 주요 설계 변경 및 트러블슈팅 (Troubleshooting)

### 2.1. 타이밍 에러(Setup Violation) 해결
* **문제 발생:** 초기 설계에서는 FPGA 내부에서 64비트 절대 시간(`timestamp_ps`)의 이전 값과 현재 값을 빼서 펄스 간격(Interval)을 실시간으로 계산했습니다. 이로 인해 200MHz(5ns) 클럭 제약 내에서 64비트 Carry 체인 연산이 끝나지 못해 **-0.058ns의 Intra-Clock Setup Time Violation**이 발생했습니다.
* **해결 및 원인:** FPGA 실무의 원칙에 따라, FPGA는 **오직 절대 시간(Timestamp)의 정밀한 캡처**만 담당하도록 뺄셈 로직을 전면 삭제했습니다. 계산과 통계 분석은 Python 기반의 PC 소프트웨어로 위임하여 하드웨어 리소스를 절약하고 타이밍 에러를 100% 제거했습니다.

### 2.2. 귀신 트리거(Ghost Trigger) 및 클럭 MUX 글리치 해결
* **문제 발생:** `SW[1]`을 이용해 내부 테스트 신호와 외부 STM32 신호를 동적으로 스위칭(`BUFGMUX` 사용)하도록 설계했으나, 스위치 조작 없이 리셋만으로는 외부 신호가 트리거되지 않는 현상이 발생했습니다.
* **해결 및 원인:** 클럭이 동적으로 변환될 때 발생하는 **글리치(Glitch)**가 TDC의 엣지 감지 로직(과거 상태 기억 레지스터)을 오염시켰기 때문입니다. 이를 해결하기 위해 동적 스위칭 로직을 완전히 제거하고, **컴파일 시점에 회로를 고정하는 파라미터 기반 하드코딩(Hardcoding)** 방식으로 RTL을 재설계하여 안정성을 극대화했습니다.

---

## 3. 핵심 하드웨어 (RTL & XDC) 코드

### 3.1. 최상위 모듈 (`tdc_test_top.v`) - 하드코딩 적용
```verilog
`timescale 1ns / 1ps

module tdc_test_top #(
    // ★ 동작 모드 하드코딩 (MUX 글리치 방지)
    // 0: 내부 RO 테스트 | 1: MMCM Sweep | 2: 외부 STM32 신호 측정
    parameter integer OPERATION_MODE = 2 
)(
    input  wire       clk_125, 
    input  wire       rst_n, 
    input  wire       ext_hit_in,  // ZYBO Hi-Speed PMOD (JB1 - V8)
    output wire [3:0] led
);

    // [중략: Clock & MMCM, RO 체인 로직] ...

    wire tdc_hit_in;
    wire tdc_clk;

    // Generate 문을 통한 컴파일 타임 회로 고정 (오동작 원천 차단)
    generate
        if (OPERATION_MODE == 0) begin : MODE_0_RO_TEST
            assign tdc_hit_in = hit_random;
            assign tdc_clk    = clk_200_fixed;
        end
        else if (OPERATION_MODE == 1) begin : MODE_1_MMCM_SWEEP
            assign tdc_hit_in = test_hit_sync;
            assign tdc_clk    = clk_200_shifted;
        end
        else begin : MODE_2_EXT_STM32 
            assign tdc_hit_in = ext_hit_in;
            assign tdc_clk    = clk_200_fixed;
        end
    endgenerate

    // TDC Core 인스턴스
    tdc_fmcw_core u_tdc ( ... );
    tdc_timestamp_calc u_ts_calc ( ... );

    // LED 디버깅 매핑
    assign led[0] = clk_locked; 
    assign led[2] = tdc_hit_in;     // STM32 입력 신호 모니터링 (실시간 펄스 확인)
    assign led[3] = final_ts_valid; // 연산 완료 트리거 확인

    // ILA 프로브 (연산 간소화 적용, 뺄셈 제거됨)
    ila_0 your_ila_instance (
        .clk    (tdc_clk), 
        .probe0 (final_ts_valid),           // [0:0]  트리거 조건
        .probe1 (tdc_hit_in),               // [0:0]  원시 Hit 신호
        .probe2 (final_timestamp_ps[47:0]), // [47:0] 절대 시간 (ps)
        .probe3 (aligned_fine_idx)          // [8:0]  Raw 탭 번호 
    );
endmodule
```

### 3.2. 제약 조건 (`ZYBO.xdc`) - 고속 핀 및 비동기 타이밍 무시
```tcl
# STM32 Hit Input (Hi-Speed PMOD JB - Pin 1 / V8)
set_property PACKAGE_PIN V8 [get_ports ext_hit_in]
set_property IOSTANDARD LVCMOS33 [get_ports ext_hit_in]

# 외부 비동기 신호로 인한 Setup/Hold Violation 가짜 에러 무시
set_false_path -from [get_ports ext_hit_in]
```

---

## 4. 데이터 수집 및 Python 후처리 소프트웨어

### 4.1. ILA Capture Control 
200MHz 클럭으로 데이터를 무작정 수집하면 4096 버퍼 기준 단 20.48us의 데이터만 수집됩니다. 이를 극복하기 위해 ILA의 **Capture Control** 기능을 활성화하고, `final_ts_valid == 1`일 때만 버퍼에 기록하도록 설정하여, **정확히 4096개의 유효한 STM32 펄스 데이터를 연속으로 추출**했습니다.

### 4.2. Python 분석 스크립트 (`tdc_analyzer.py`)
디렉토리 경로 문제를 해결(`os.path`)하고, 절대 시간 누적(Absolute Time Domain)을 통해 완벽한 선형 주파수 그래프를 도출하는 최종 코드입니다.

```python
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def analyze_tdc_intervals(csv_file_path):
    df = pd.read_csv(csv_file_path)
    
    # 1. Vivado 헤더 필터링 및 Timestamp 추출
    if df.iloc[0].astype(str).str.contains('Radix|Unsigned|Hex', na=False, case=False).any():
        df = df.iloc[1:].reset_index(drop=True)
    
    time_col = [col for col in df.columns if 'timestamp' in col.lower() or 'probe2' in col.lower()][0]
    df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
    df = df.dropna(subset=[time_col]).copy()

    # 2. 펄스 간격(T) 및 주파수(f) 계산
    df['interval_ps'] = df[time_col].diff()
    df = df.dropna(subset=['interval_ps']).copy()
    
    # Wrap-around 보상
    wrap_condition = df['interval_ps'] < 0
    if wrap_condition.any():
        df.loc[wrap_condition, 'interval_ps'] += 2**48

    df['interval_us'] = df['interval_ps'] / 1_000_000.0
    df['frequency_kHz'] = (1.0 / df['interval_us']) * 1000.0

    # 3. 누적 절대 시간(Absolute Time) 계산 (착시 현상 제거)
    df['absolute_time_ms'] = df['interval_us'].cumsum() / 1000.0

    # 4. 시각화 (Subplots)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    
    ax1.plot(df['absolute_time_ms'].values, df['interval_us'].values, marker='.', color='b', markersize=3, alpha=0.7)
    ax1.set_title("STM32 Chirp Signal Analysis (Absolute Time Domain)", fontsize=16)
    ax1.set_ylabel(r"Time Interval ($\mu s$)", fontsize=12, fontweight='bold', color='b')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    ax2.plot(df['absolute_time_ms'].values, df['frequency_kHz'].values, marker='.', color='r', markersize=3, alpha=0.7)
    ax2.set_ylabel("Frequency (kHz)", fontsize=12, fontweight='bold', color='r')
    ax2.set_xlabel("Absolute Time (ms)", fontsize=12, fontweight='bold')
    ax2.grid(True, linestyle='--', alpha=0.6)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    absolute_file_path = os.path.join(script_dir, "iladata.csv")
    analyze_tdc_intervals(absolute_file_path)
```

---

## 5. 물리적 현상 및 STM32 펌웨어 고찰

### 5.1. STM32 펌웨어의 정밀도 (Quantization Sync)
측정된 그래프에서 완벽한 주파수 선형성(Linearity)이 나온 이유는 STM32 펌웨어의 아래 로직 때문입니다.
```c
// 단순 이론적 시간이 아닌, 실제 하드웨어 카운터(ARR) 기준 누적 시간 연산
t += (float)(arr_val + 1) / TIMER_CLK;
```
단순 이론 시간(`1/f`)을 더하지 않고, 실제 타이머 레지스터(`ARR`)에 양자화되어 들어간 하드웨어 주기를 역산하여 누적시켰으므로 부동소수점 누적 오차가 완벽히 통제되었습니다. 또한, **DMA Burst Multi-Write**를 사용하여 CPU 개입 없이 타이머 레지스터를 업데이트함으로써 펌웨어 지터(Jitter)를 0으로 만들었습니다.

### 5.2. 고주파 대역 그래프 잉크 뭉침(두꺼워짐) 현상의 원인
출력된 그래프에서 고주파(1MHz)로 갈수록 선이 두꺼워 보이는 현상은 회로의 노이즈가 아닌 **물리적/수학적 필연**입니다.
1. **STM32 분해능 한계 (Quantization Error):** 170MHz 타이머 클럭에서 100kHz를 만들 땐 ARR 값이 1700 부근이므로 미세 조절이 가능하지만, 1MHz 구간에서는 ARR 값이 170 부근이 되어 **ARR 1 변화당 주파수가 약 6kHz씩 계단형으로 점프**하게 됩니다.
2. **수학적 증폭 ($f = 1/T$):** FPGA는 17.8ps의 정밀한 시간(T)을 측정하지만, 파이썬에서 주파수(f)로 변환할 때 분모가 작아지는 고주파 영역일수록 미세한 오차가 제곱 비례($f^2$)하여 거대하게 나타납니다.

### 5.3. 물리적 연결(점퍼선)에 따른 고려사항
점퍼선 사용 시 발생하는 **고정된 시간 지연(Propagation Delay)**은 `현재 시간 - 이전 시간`의 뺄셈 연산을 통해 완벽하게 상쇄됩니다. 
다만, 쉴드(Shield) 처리되지 않은 듀폰 케이블은 안테나 역할을 하여 외부 노이즈에 의한 **랜덤 지터(Random Jitter) 및 링깅(Ringing)**을 유발할 수 있습니다. 이를 방지하기 위해 신호선과 GND선을 꼬아서 사용하는 **Twisted Pair** 방식을 권장합니다.

## 6. 결론
본 프로젝트를 통해 STM32 하드웨어 타이머의 극한을 활용한 FMCW Chirp 신호 발생기와, 이를 17.8ps 해상도로 포착해내는 FPGA-TDC 기반의 측정 파이프라인이 오차 없이 완벽하게 구축되었습니다. 하드웨어와 소프트웨어의 역할을 정확히 분리(RTL은 측정만, 파이썬은 계산)함으로써 타이밍 이슈를 근본적으로 해결한 성공적인 엔지니어링 사례입니다.