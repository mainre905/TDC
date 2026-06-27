# TDC Calibration 및 LUT 생성을 위한 데이터 처리 알고리즘 종합 분석 보고서

## 1. 개요 (Overview)
본 보고서는 FPGA 내부의 **TDC(Time-to-Digital Converter)** 회로 측정 데이터를 분석하여 하드웨어 캘리브레이션에 사용될 **LUT(Look-Up Table, .coe 파일)**를 신뢰성 있게 도출하는 5단계 알고리즘 프로세스를 기술합니다.

수집된 디지털 시간 정보(Raw Data)는 하드웨어 카운터의 구조적 한계와 랩어라운드(Wrap-around) 특성으로 인해 불연속적인 분절 형태로 기록됩니다. 이를 해결하기 위해 본 알고리즘은 **1) 시간대 통일(Modulo), 2) 우선순위 병합(Priority Stitching), 3) 위상 펼침(Unwrapping), 4) 선형 보간(Linear Interpolation), 5) 하드웨어 양자화(Quantization)**를 거쳐 왜곡 없는 절대 지연선을 설계하는 수학적 기초를 제공합니다.

---

## 2. 시스템 파라미터 및 원본 데이터 세그먼트 분석
### 2.1 주요 시스템 변수 정의
*   **TDC 샘플링 클럭 주기 ($T_{\text{clk}}$):** $5000.0 \text{ ps}$ (200 MHz)
*   **MMCM VCO 동작 주파수:** $1.0 \text{ GHz}$ (1주기 = $1000.0 \text{ ps}$)
*   **위상 이동 최소 해상도 ($\Delta t_{\text{step}}$):** 
    $$\Delta t_{\text{step}} = \frac{1000.0 \text{ ps}}{56} \approx 17.857142857 \text{ ps}$$

### 2.2 수집된 원본 데이터 세그먼트 분류
제공된 데이터를 정렬하여 분석하면, 연속되던 탭 번호가 급락하는 지점을 경계로 세 가지 고유한 데이터 군(Segment)이 식별됩니다.

1.  **Segment 1 (Loop 1 ~ 127):** 
    *   탭 분포: Tap 157 ~ Tap 292 (총 127개 행)
    *   시간 범위: $17.857 \text{ ps} \sim 2267.857 \text{ ps}$
2.  **Segment 2 (Loop 128):** 
    *   탭 분포: Tap 235 (총 1개 행, 불안정 천이 영역)
    *   시간 데이터: $2285.714 \text{ ps}$
3.  **Segment 3 (Loop 129 ~ 350):** 
    *   탭 분포: Tap 8 $\rightarrow$ Tap 1 $\rightarrow$ Tap 230 (총 222개 행)
    *   시간 범위: $2303.571 \text{ ps} \sim 6250.0 \text{ ps}$

**선정 결과:** 
알고리즘 규칙 1에 따라 유효 데이터 점수가 가장 조밀한 **Segment 3(길이 222)**이 캘리브레이션의 기초 축이 되는 **Main Segment**로 우선 설정됩니다.

---

## 3. 알고리즘 5단계 상세 프로세스 및 수식 검증

### [Step 1] Phase Modulo: 단일 주기 평면 통일
수집 시점의 지연 시간 차이를 배제하고 동일 선상에서 위상을 비교할 수 있도록, 모든 원본 시간 데이터 $t_{\text{raw}}$를 샘플링 클럭 주기 $T_{\text{clk}}\ (5000 \text{ ps})$로 제한하는 모듈러 연산을 가합니다.

*   **수학적 모델:**
$$\phi = t_{\text{raw}} \pmod{T_{\text{clk}}}$$

*   **실제 데이터 적용 사례:**
    *   **Loop 130 (Tap 1):** $\phi = 2321.42857 \pmod{5000} = \mathbf{2321.42857 \text{ ps}}$
    *   **Loop 280 (Tap 156):** $\phi = 5000.0 \pmod{5000} = \mathbf{0.0 \text{ ps}}$
    *   **Loop 281 (Tap 157):** $\phi = 5017.85714 \pmod{5000} = \mathbf{17.85714 \text{ ps}}$

---

### [Step 2] Priority Stitching: 중복 데이터 배제 및 유일성 확보
가장 정밀도가 높은 Main Segment(Segment 3)의 영역(Tap 1 ~ Tap 230)을 최우선적으로 확보합니다. 해당 세그먼트에서 소실된 나머지 외곽 영역(Tap 231 ~ Tap 292)에 한해서만 Segment 1의 데이터를 차용하는 분할 정의 기법을 적용합니다. 이 과정에서 중복 수집된 구간은 폐기됩니다.

*   **수학적 모델 (Piecewise Function):**
$$
\Phi_{\text{merged}}(\text{tap}) = \begin{cases} 
\bar{\phi}_{\text{Main}}(\text{tap}), & \text{if } \text{tap} \in \text{Main} \\ 
\bar{\phi}_{\text{Spare}}(\text{tap}), & \text{if } \text{tap} \notin \text{Main} \text{ and } \text{tap} \in \text{Spare} \\ 
\text{NaN}, & \text{otherwise} 
\end{cases}
$$

*   **실제 탭 평균화 ($\bar{\phi}$) 분석:**
    *   **Tap 1 (Main):** Loop 130, 131, 132 평균
        $$\bar{\phi}_{\text{Tap 1}} = \frac{2321.42857 + 2339.28571 + 2357.14286}{3} = \mathbf{2339.28571 \text{ ps}}$$
    *   **Tap 157 (Main):** Loop 281, 282 평균
        $$\bar{\phi}_{\text{Tap 157}} = \frac{17.85714 + 35.71429}{2} = \mathbf{26.78571 \text{ ps}}$$
    *   **Tap 292 (Patched):** Loop 127 실측값 매핑 (Tap 292는 Main에 없으므로 Segment 1에서 인입)
        $$\bar{\phi}_{\text{Tap 292}} = \mathbf{2267.85714 \text{ ps}}$$

---

### [Step 3] Phase Unwrapping: 연속 물리적 직선 복원
인접 탭 간의 1차 차분 위상차 $\Delta \phi_i$를 탐색하여, 하향 돌출 경계 조건($-2500 \text{ ps}$ 미만) 발생 시 기준 오프셋을 클럭 주기($5000 \text{ ps}$) 단위로 증가시킴으로써 누적선 형태로 평탄화합니다.

*   **수학적 모델:**
$$\Delta \phi_i = \phi_i - \phi_{i-1}$$

$$t_{\text{unwrap}}(i) = \phi_i + \text{offset}_i$$

$$
\text{offset}_i = \text{offset}_{i-1} + \begin{cases} 
5000, & \text{if } \Delta \phi_i < -2500 \text{ ps} \\ 
0, & \text{otherwise} 
\end{cases}
$$

*   **실제 연속 구간 추적:**
    *   **Tap 155:** $\phi_{155} = 4982.14286 \text{ ps}$ (오프셋 0) $\rightarrow t_{\text{unwrap}} = \mathbf{4982.14286 \text{ ps}}$
    *   **Tap 156:** $\phi_{156} = 0.0 \text{ ps}$
        $$\Delta \phi = 0.0 - 4982.14286 = -4982.14286 \text{ ps} < -2500 \text{ ps}$$
        급격한 전이가 발생하였으므로 가산 오프셋은 $5000 \text{ ps}$로 갱신됩니다.
        $$\rightarrow t_{\text{unwrap}} = 0.0 + 5000 = \mathbf{5000.0 \text{ ps}}$$
    *   **Tap 157:** $\phi_{157} = 26.78571 \text{ ps}$
        $$\rightarrow t_{\text{unwrap}} = 26.78571 + 5000 = \mathbf{5026.78571 \text{ ps}}$$

*   **영점 수렴 정규화 (Zero-Normalization):**
    실제 사용을 위해 기준 원점 $t_{\text{unwrap}}(1)$을 감산 연산하여 영점으로 통일합니다.
    $$t_{\text{norm}}(i) = t_{\text{unwrap}}(i) - t_{\text{unwrap}}(1) \quad (\text{단, } t_{\text{unwrap}}(1) = 2339.28571 \text{ ps})$$
    *   **Tap 1 정규화:** $2339.28571 - 2339.28571 = \mathbf{0.0 \text{ ps}}$
    *   **Tap 155 정규화:** $4982.14286 - 2339.28571 = \mathbf{2642.85715 \text{ ps}}$
    *   **Tap 156 정규화:** $5000.0 - 2339.28571 = \mathbf{2660.71429 \text{ ps}}$
    *   **Tap 292 정규화:** $7267.85714 - 2339.28571 = \mathbf{4928.57143 \text{ ps}}$

---

### [Step 4] Linear Interpolation: 선형 보간 및 경계 조건 예외 처리
정렬이 완료된 실측 데이터셋에서 발생한 중간 유실 탭(예: Tap 2 등)과 탐색 한계점 바깥의 영역(Tap 0 및 Tap 293 ~ 319)을 완성하기 위해 선형 보간법 및 경계 한계 Clamping을 실행합니다.

*   **수학적 모델:**
$$t_{\text{interp}}(x) = y_1 + (x - x_1) \frac{y_2 - y_1}{x_2 - x_1}$$

*   **경계 외삽(Extrapolation) 규칙:**
    *   실측 최소 탭(Tap 1)의 좌측 외곽 영역은 최소 실측 정규화 시간값으로 일정하게 수렴 제어합니다.
    *   실측 최대 탭(Tap 292)의 우측 외곽 영역은 최대 실측 정규화 시간값으로 유지 제어합니다.

---

### [Step 5] Hardware Quantization: 최종 LUT 생성 및 정밀 산출 검증
하드웨어 ROM 저장소에 내장하기 위하여 복원된 연속 절대 지연 데이터에 다시 한 차례 클럭 한계 주기 모듈러($\pmod{5000}$) 연산을 적용하고, 정수형 연산 장치가 인식하도록 소수점 첫째 자리에서 반올림을 실시합니다.

*   **수학적 모델:**
$$\text{LUT}(\text{tap}) = \text{round} \left( t_{\text{interp}}(\text{tap}) \pmod{T_{\text{clk}}} \right)$$

*   **지정된 핵심 탭별 데이터 산출 연산 과정:**

#### 1) Tap 0 (최좌측 경계 외삽)
*   보간 연산: $t_{\text{interp}}(0) = t_{\text{norm}}(1) = 0.0 \text{ ps}$
*   양자화:
    $$\text{LUT}(0) = \text{round}(0.0 \pmod{5000}) = \mathbf{0}$$

#### 2) Tap 1 (기준점 실측 탭)
*   보간 연산: $t_{\text{interp}}(1) = t_{\text{norm}}(1) = 0.0 \text{ ps}$
*   양자화:
    $$\text{LUT}(1) = \text{round}(0.0 \pmod{5000}) = \mathbf{0}$$

#### 3) Tap 2 (소실 구간 선형 보간)
*   데이터 분포 상 Tap 1($0.0 \text{ ps}$)과 Tap 3($53.57143 \text{ ps}$) 사이에 유실되어 있으므로 1차 보간법으로 유추합니다.
    $$t_{\text{interp}}(2) = 0.0 + (2 - 1) \frac{53.57143 - 0.0}{3 - 1} = 26.78571 \text{ ps}$$
*   양자화:
    $$\text{LUT}(2) = \text{round}(26.78571 \pmod{5000}) = \mathbf{27}$$

#### 4) Tap 3 (실측 탭)
*   보간 연산: $t_{\text{interp}}(3) = 2392.85714 - 2339.28571 = 53.57143 \text{ ps}$
*   양자화:
    $$\text{LUT}(3) = \text{round}(53.57143 \pmod{5000}) = \mathbf{54}$$

#### 5) Tap 4 (실측 탭)
*   보간 연산: $t_{\text{interp}}(4) = 2437.5 - 2339.28571 = 98.21429 \text{ ps}$
*   양자화:
    $$\text{LUT}(4) = \text{round}(98.21429 \pmod{5000}) = \mathbf{98}$$

#### 6) Tap 5 (실측 탭)
*   보간 연산: $t_{\text{interp}}(5) = 2473.21429 - 2339.28571 = 133.92858 \text{ ps}$
*   양자화:
    $$\text{LUT}(5) = \text{round}(133.92858 \pmod{5000}) = \mathbf{134}$$

#### 7) Tap 155 (전이 경계 직전 탭)
*   보간 연산: $t_{\text{interp}}(155) = 4982.14286 - 2339.28571 = 2642.85715 \text{ ps}$
*   양자화:
    $$\text{LUT}(155) = \text{round}(2642.85715 \pmod{5000}) = \mathbf{2643}$$

#### 8) Tap 156 (오프셋 갱신 개시 탭)
*   보간 연산: $t_{\text{interp}}(156) = 5000.0 - 2339.28571 = 2660.71429 \text{ ps}$
*   양자화:
    $$\text{LUT}(156) = \text{round}(2660.71429 \pmod{5000}) = \mathbf{2661}$$

#### 9) Tap 292 (실측 보정 상한 탭)
*   보간 연산: $t_{\text{interp}}(292) = 7267.85714 - 2339.28571 = 4928.57143 \text{ ps}$
*   양자화:
    $$\text{LUT}(292) = \text{round}(4928.57143 \pmod{5000}) = \mathbf{4929}$$

#### 10) Tap 319 (최우측 경계 외삽 탭)
*   보간 연산: $t_{\text{interp}}(319) = t_{\text{norm}}(292) = 4928.57143 \text{ ps}$
*   양자화:
    $$\text{LUT}(319) = \text{round}(4928.57143 \pmod{5000}) = \mathbf{4929}$$

---

## 4. 핵심 탭 데이터 정량적 정합성 총괄표

| Tap Index | 보정 데이터 상태 구분 | 정규화 시간 ($t_{\text{norm}}$, ps) | 양자화 산출 수식 | LUT 대입 정수값 |
| :---: | :---: | :---: | :--- | :---: |
| **0** | 외부 클램핑 영역 (Left) | $0.00000$ | $\text{round}(0.0 \pmod{5000})$ | **0** |
| **1** | 실측 데이터 원점 (Minimum) | $0.00000$ | $\text{round}(0.0 \pmod{5000})$ | **0** |
| **2** | 데이터 유실에 따른 선형 보간 | $26.78571$ | $\text{round}(26.78571 \pmod{5000})$ | **27** |
| **3** | 정상 실측 상태 | $53.57143$ | $\text{round}(53.57143 \pmod{5000})$ | **54** |
| **4** | 정상 실측 상태 | $98.21429$ | $\text{round}(98.21429 \pmod{5000})$ | **98** |
| **5** | 정상 실측 상태 | $133.92858$ | $\text{round}(133.92858 \pmod{5000})$ | **134** |
| **155** | 하락 전이 구간 직전 검출 상태 | $2642.85715$ | $\text{round}(2642.85715 \pmod{5000})$ | **2643** |
| **156** | 랩어라운드 발생 보정 상태 | $2660.71429$ | $\text{round}(2660.71429 \pmod{5000})$ | **2661** |
| **292** | 조각 병합 최대 유효 수집 한계 | $4928.57143$ | $\text{round}(4928.57143 \pmod{5000})$ | **4929** |
| **319** | 외부 클램핑 영역 (Right) | $4928.57143$ | $\text{round}(4928.57143 \pmod{5000})$ | **4929** |

---

## 5. 결론 (Conclusion)
설계된 5단계 데이터 가공 모델은 하드웨어 내부 비동기 검출 회로의 Wrap-around 분절 특성을 극복하기 위해 구현되었습니다. 특히, 병합 필터링(Step 2)과 Unwrapping 수치 해석(Step 3)을 순차적으로 전개함으로써 디지털 양자화 잡음을 효과적으로 감쇄하였으며, 하드웨어 내부에 안정한 형태의 보정 어레이를 인입할 수 있도록 변환 프로세스를 표준화하였습니다.
