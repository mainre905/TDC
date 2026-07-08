제시해주신 Zybo 보드의 실제 Pmod 회로도를 바탕으로, **FPGA에서의 LVDS 수신 원리, 보드 레벨의 하드웨어 분석, 그리고 실제 구현 가이드**를 체계적으로 정리한 마크다운(Markdown) 보고서 형식의 가이드입니다. 

---

# 📑 Zybo FPGA 보드를 활용한 고속 LVDS 신호 수신 기술 가이드

본 문서는 고속 비교기 등에서 출력되는 표준 LVDS 신호를 Zybo 보드의 Pmod 포트를 통해 수신하기 위한 전기적 메커니즘, 회로 분석 및 실제 구현 방안을 정리한 기술 가이드입니다.

---

## 1. LVDS 전기적 규격 및 FPGA 호환성 정의

### 1.1 표준 LVDS (Standard LVDS) 사양
국제 전기 전자 표준(TIA/EIA-644 및 IEEE 1596.3)에 정의된 표준 LVDS의 핵심 전압 스펙은 다음과 같습니다.

*   **공통 모드 전압 ($V_{CM}$):** **Nominal $1.2\text{V}$** (허용 스펙 범위: $1.0\text{V} \sim 1.4\text{V}$)
*   **차동 신호 진폭 ($V_{OD}$ / Swing):** **$\approx \pm 350\text{mV}$**
*   **동작 원리:** 송신단에서 $3.5\text{mA}$의 정전류를 흘려보내면, 수신단에 병렬로 결합된 $100\,\Omega$ 종단 저항을 통과하며 옴의 법칙($V = I \times R$)에 의해 수신측 핀단에 $350\text{mV}$의 전압 스윙을 형성합니다.

### 1.2 I/O Bank 전원 전압($V_{CCO}$)과 공통 모드 전압($V_{CM}$)의 분리
*   **$V_{CCO}$ (FPGA 내부 뱅크 구동 전원):** FPGA I/O 버퍼 회로 자체를 켜기 위한 동력원입니다.
*   **$V_{CM}$ (신호 자체의 전압 축):** 수신받는 아날로그 차동 신호가 물리적으로 흔들리는 전압 중심축입니다.
*   **호환성:** Xilinx 7-Series FPGA의 LVDS 입력 버퍼 허용 범위($V_{ICM}$)는 **$0.3\text{V} \sim 1.425\text{V}$**입니다. 비교기의 공통 모드 전압($1.2\text{V}$)은 이 허용 범위의 한가운데 위치하므로, FPGA 전원이 안정적으로 구동되는 상태라면 전기적으로 완벽하게 호환됩니다.

---

## 2. Zybo Pmod 포트 회로도 분석

제공해주신 회로도를 기반으로 고속 차동 수신 가능 여부를 판별하면 다음과 같습니다.

![Pmod_Schematic](lvds.png) *(사용자 인가 회로도 참조)*

### 2.1 Pmod JE (하단 - 수신 불가)
*   **하드웨어 구성:** FPGA 핀과 외부 커넥터 사이에 **$200\,\Omega$ 직렬 보호 저항(`R17 ~ R24`)**이 장착되어 있습니다.
*   **수신 실패 원인:** 외부 커넥터에 $100\,\Omega$ 종단 저항을 부착하면, 직렬 보호 저항 $200\,\Omega$과 함께 **전압 분배기(Voltage Divider)** 회로가 형성됩니다.
    $$\text{수신 전압 스윙} \approx 350\text{mV} \times \left( \frac{100\,\Omega}{200\,\Omega + 200\,\Omega + 100\,\Omega} \right) \approx 70\text{mV}$$
    이로 인해 신호 크기가 $70\text{mV}$ 이하로 대폭 감쇠하여 FPGA 입력 버퍼가 신호를 감지하지 못하고 먹통이 됩니다.

### 2.2 Pmod JC (상단 - 수신 가능)
*   **하드웨어 구성:** 보호 저항 자리가 **$0\,\Omega$ 저항(`R1 ~ R8`)**으로 구성되어 신호 감쇠가 전혀 없습니다.
*   **차동 매칭 배선:** Net Name이 **`JC1_P` / `JC1_N`**과 같이 차동 구조(`_P` / `_N`)로 명시되어 있으며, PCB 패턴 또한 고속 차동 임피던스(Differential Impedance)를 타겟하여 대칭 구조로 평행 배선되어 있습니다.
*   **정전기 보호:** 회로도의 `D3`, `D4`는 고속 신호를 왜곡하지 않는 **초저용량(Low-Capacitance) ESD 클램프 다이오드**로 설계되어 신호 품질에 영향을 미치지 않습니다.

---

## 3. 3.3V I/O Bank와 외부 종단 저항(External Termination) 솔루션

### 3.1 3.3V 뱅크에서 내부 종단(`DIFF_TERM`)을 켜지 못하는 이유
Xilinx 7-Series High Range(HR) I/O Bank 내부의 내장 종단 저항 회로는 MOSFET 트랜지스터의 ON-임피던스를 이용해 구현됩니다. 이 회로는 물리적으로 **$V_{CCO} = 2.5\text{V}$가 공급될 때만 정교한 $100\,\Omega$ 임피던스를 유지**하도록 바이어스(Biasing)되어 있습니다.
*   뱅크 전원이 3.3V인 상태에서 `DIFF_TERM = TRUE` 설정을 가하면, 바이어스 파괴 및 오작동을 예방하기 위해 Vivado 컴파일러(DRC Check) 단계에서 합성을 차단합니다.

### 3.2 해결책: 외부 $100\,\Omega$ 종단 저항 결합
Xilinx SelectIO 가이드라인(UG471)에 의거하여, **수신 뱅크 전원이 3.3V이더라도 외부에 물리적인 $100\,\Omega$ 저항을 장착하면 차동 입력 표준인 `LVDS_25`로 신호를 완벽하게 수신**할 수 있습니다.

---

## 4. 실제 구현 가이드 (Step-by-Step)

### 4.1 하드웨어 결선 (외부 저항 납땜)
고속 차동 Pmod JC 포트의 차동 핀 쌍 사이에 물리적인 $100\,\Omega$ 금속 피막 저항(가급적 오차 1% 이내의 고정밀 저항)을 최대한 커넥터 핀에 밀착하여 병렬 결합합니다.

*   **JC 1번 핀(JC1_P) $\leftrightarrow$ JC 2번 핀(JC1_N)** 사이에 $100\,\Omega$ 저항 결합
*   **JC 3번 핀(JC2_P) $\leftrightarrow$ JC 4번 핀(JC2_N)** 사이에 $100\,\Omega$ 저항 결합

```
      [ 고속 비교기 ]                         [ High-Speed Pmod JC ]
  LVDS_P (Out) ---------------------------> JC1_P (Pin 1)
                                                 |
                                               [100 Ohm 물리 저항]
                                                 |
  LVDS_N (Out) ---------------------------> JC1_N (Pin 2)
```

### 4.2 Vivado 제약 파일 (XDC) 설정 규칙
XDC 파일 작성 시, 내부 종단 저항(`DIFF_TERM`) 옵션은 반드시 **`FALSE`**로 두고, 신호 규격은 **`LVDS_25`**로 강제합니다.

```tcl
# =========================================================================
# High-Speed Pmod JC를 통한 고속 비교기 LVDS 차동 신호 수신 제약 설정
# =========================================================================

# 1. 물리 핀 맵 매핑 (Zybo 보드 사양에 맞춘 예시 주소)
set_property PACKAGE_PIN V15 [get_ports ext_hit_in_p]; # JC1_P (1번 핀)
set_property PACKAGE_PIN W15 [get_ports ext_hit_in_n]; # JC1_N (2번 핀)

# 2. 입출력 전기 표준 설정 (3.3V Bank 내 외부 종단 구동 차동 입력)
set_property IOSTANDARD LVDS_25 [get_ports ext_hit_in_p]
set_property IOSTANDARD LVDS_25 [get_ports ext_hit_in_n]

# 3. 내부 종단 저항 비활성화 (BRAM 및 전원 규칙 위반 원천 방지)
set_property DIFF_TERM FALSE [get_ports ext_hit_in_p]
```