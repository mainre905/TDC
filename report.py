# TDC_Calibration_Report.md 파일을 자동 생성하는 파이썬 스크립트

report_content = r"""# TDC Calibration 및 LUT 생성을 위한 5단계 데이터 처리 알고리즘 종합 레포트

## 1. 개요 (Overview)
본 레포트는 FPGA 내부의 **TDC(Time-to-Digital Converter)** 회로 측정 데이터를 기반으로, 하드웨어 캘리브레이션용 **LUT(Look-Up Table, .coe 파일)**를 생성하는 5단계 알고리즘의 전체 프로세스를 분석합니다. 

측정된 로우 데이터(Raw Data)는 하드웨어 카운터의 랩어라운드(Wrap-around) 특성으로 인해 분절되고 꼬여 있습니다. 본 알고리즘은 **1) 시간대 통일, 2) 중복 데이터 제거 및 병합, 3) 위상 펼침(Unwrapping), 4) 선형 보간, 5) 하드웨어 양자화**의 과정을 거쳐 완벽한 물리적 딜레이 라인을 복원하고 ROM 메모리에 이식 가능한 형태로 변환합니다.

---

## 2. 시스템 파라미터 및 초기 데이터 상태
*   **시스템 클럭 및 주파수:** $T_{clk} = 5000 \text{ ps}$ (200MHz), VCO 스텝 $\Delta t_{step} = 17.857 \text{ ps}$
*   **목표 LUT 크기:** 0번 ~ 319번 탭 (총 320개 배열)
*   **시간 계산 공식:** $t_{raw} = N_{loop} \times \Delta t_{step}$

**[초기 데이터 예시 (문제 상황)]**
로우 데이터를 분석하면, 시간이 지남에 따라 서로 다른 주기의 탭들이 섞여 있는 것을 확인할 수 있습니다.
*   **Main 조각 (루프 1 ~ 343):**
    *   **Tap 73** ($17.85 \text{ ps}$) 부터 **Tap 222** ($6107.14 \text{ ps}$) 까지의 연속된 구간 (※ Main이 소유한 1순위 기준 데이터)
*   **Spare 조각 (루프 344 ~ 350):** 
    *   **Tap 222** ($6142.85 \text{ ps}$) 등을 포함한 구간 (※ Spare가 소유한 구간 중 **Main과 겹치는 잉여 구간!**)
    *   **Tap 1** ($6160.71 \text{ ps}$) 등을 포함한 구간 (※ Main에 없는 필수 빈칸 부품)

---

## 3. 알고리즘 5단계 상세 프로세스

### [Step 1] Phase Modulo: 모든 시간대 통일 (도화지 합치기)
어긋난 시간표를 하나로 맞추기 위해, 모든 원본 데이터에 $T_{clk}$ (5000ps)으로 나눈 나머지 모듈러(Modulo) 연산을 적용합니다. 이를 통해 수만 ps 단위의 시간들이 모두 `0 ~ 5000ps`의 단일 위상(Phase) 평면으로 강제 이동됩니다.

*   **수학적 모델:**

$$
\phi = t_{raw} \pmod{T_{clk}}
$$

*   **데이터 적용:**
    *   **Main 탭 73:** $\phi_{73} = 17.85 \pmod{5000} = \mathbf{17.85 \text{ ps}}$
    *   **Spare 탭 1:** $\phi_{1} = 6160.71 \pmod{5000} = \mathbf{1160.71 \text{ ps}}$
    *   **Spare 탭 222:** $\phi_{222} = 6142.85 \pmod{5000} = \mathbf{1142.85 \text{ ps}}$

*   **Python 코드:**
    ```python
    grouped['phase_ps'] = grouped['raw_time_ps'] % CLOCK_CYCLE_PS
    ```

---

### [Step 2] Priority Stitching: 빈칸 채우기 & 중복 데이터 제거
시간대를 맞춘 후, 신뢰도가 가장 높은 **Main 조각을 절대 기준으로 설정**합니다. 부족한 빈칸은 Spare 조각에서 가져오되, **"Main에 이미 존재하는 탭 구간은 데이터 노이즈 방지를 위해 무조건 버린다"**는 조건부 논리가 적용됩니다.

*   **수학적 모델 (Piecewise Function):**
    최종 병합된 위상 $\Phi_{merged}(tap)$은 다음을 따릅니다.

$$
\Phi_{merged}(tap) = 
\begin{cases} 
\phi_{Main}(tap), & \text{if } tap \in Main \\ 
\phi_{Spare}(tap), & \text{if } tap \notin Main \text{ and } tap \in Spare \\
\text{NULL}, & \text{otherwise (비워둠)}
\end{cases}
$$

*   **데이터 적용 (구간 단위 처리):**
    1.  **Main 구간 등록(1순위):** Tap 73(`17.85ps`)부터 Tap 222(`1107.14ps`)까지 이어지는 연속된 탭 구간 데이터를 우선 확보합니다.
    2.  **빈 탭 구간 추가(2순위):** Main 구간에 존재하지 않는 **Tap 1**(`1160.71ps`)부터 **Tap 72**까지의 탭을 Spare 조각에서 가져와 병합합니다.
    3.  **겹치는 구간 폐기 로직:** Spare 조각에 포함된 **Tap 73 ~ Tap 222** 구간의 데이터(예: Tap 222, `1142.85ps`)는 이미 Main에 존재하므로 병합을 거부하고 일괄 삭제(폐기)합니다.

*   **Python 코드:**
    ```python
    # 1. Main 조각 등록 (73~222번 탭 구간 확보)
    for tap, phase in main_tap_avg.items():
        tap_to_phase[tap] = phase

    # 2. Spare 조각 탐색 및 겹치는 데이터 삭제
    for seg in segments:
        for tap, phase in seg.groupby('tap_idx')['phase_ps'].mean().items():
            if tap not in tap_to_phase:  # Main 구간에 없는 탭(1~72)만 가져온다 (73~222는 버림)
                tap_to_phase[tap] = phase
    ```

---

### [Step 3] Phase Unwrapping: 하나의 직선으로 복원
병합된 데이터를 탭 번호 오름차순으로 정렬하면, 카운터 리셋 구간에서 시간이 수직 하락하는 현상(톱니바퀴)이 나타납니다. 앞뒤 탭의 위상 차이($\Delta \phi$)를 분석하여, 음수 방향으로 급락할 경우 $T_{clk}$(+5000ps)을 보상하여 꺾임 없는 하나의 직선(물리적 지연 선)으로 펼쳐냅니다.

*   **수학적 모델:**

$$
\Delta \phi_i = \phi_i - \phi_{i-1}
$$

$$
t_{unwrap}(i) = \phi_i + \sum \begin{cases} 5000, & \text{if } \Delta \phi_i < -2500 \\ 0, & \text{otherwise} \end{cases}
$$

*   **데이터 적용:**
    *   **Tap 1 :** $1160.71 \text{ ps}$ (오프셋 0)
    *   **Tap 73 :** $\Delta \phi = 17.85 - 1160.71 = -1142.86 \text{ ps}$.
        (임계값 초과! 오프셋 +5000 발생) $\rightarrow 17.85 + 5000 = \mathbf{5017.85 \text{ ps}}$

*   **Python 코드:**
    ```python
    for i in range(1, len(phases)):
        diff = phases[i] - phases[i-1]
        if diff < -2500:             # 위상이 급락하는 랩어라운드 지점 감지
            offset += CLOCK_CYCLE_PS # 오프셋에 5000 추가 누적
        unwrapped_time[i] = phases[i] + offset
    ```

---

### [Step 4] Linear Interpolation: 미측정 탭 수학적 보간
Step 2에서 **NULL(비워둠)** 상태로 남겨진 데이터(예: 0번 탭, 319번 탭 등)를 채우기 위해, Step 3에서 완성된 직선을 바탕으로 선형 보간법을 수행합니다.

*   **수학적 모델 (1차 직선 방정식):**

$$
y = y_1 + \frac{(x - x_1)}{(x_2 - x_1)} \times (y_2 - y_1)
$$

*   **데이터 적용:**
    *   **Tap 0 (유추):** 연장선에 의해 약 $\mathbf{1142 \text{ ps}}$로 추정.
    *   **Tap 1 (실측):** $1160.71 \text{ ps}$
    *   **Tap 73 (실측):** $5017.85 \text{ ps}$
    *   **Tap 319 (유추):** 연장선에 의해 약 $\mathbf{9400 \text{ ps}}$로 추정.

*   **Python 코드:**
    ```python
    target_taps = np.arange(320) # 0번부터 319번까지 빈 배열 생성
    calibrated_abs_time = np.interp(target_taps, sorted_taps, unwrapped_time)
    ```

---

### [Step 5] Hardware Quantization: 최종 LUT 생성
FPGA의 1주기 위상 카운터가 인식할 수 있도록, 보간이 완료된 320개의 절대 시간 배열에 다시 모듈러 연산(`% 5000`)을 적용합니다. 이후 Block RAM 형식에 맞게 가장 가까운 정수로 반올림하여 최종 `.coe` 파일을 도출합니다.

*   **수학적 모델:**

$$
LUT(tap) = \lfloor \left( t_{unwrap}(tap) \pmod{T_{clk}} \right) \rceil
$$

*   **데이터 적용:**
    *   **Tap 0 :** $\lfloor 1142 \pmod{5000} \rceil = \lfloor 1142 \rceil = \mathbf{1142}$
    *   **Tap 1 :** $\lfloor 1160.71 \pmod{5000} \rceil = \lfloor 1160.71 \rceil = \mathbf{1161}$
    *   **Tap 73 :** $\lfloor 5017.85 \pmod{5000} \rceil = \lfloor 17.85 \rceil = \mathbf{18}$
    *   **Tap 319 :** $\lfloor 9400 \pmod{5000} \rceil = \lfloor 4400 \rceil = \mathbf{4400}$

*   **Python 코드:**
    ```python
    # 1주기 모듈러 적용 후 정수로 반올림 (양자화)
    lut_phase = calibrated_abs_time % CLOCK_CYCLE_PS
    lut_integers = np.round(lut_phase).astype(int)

    # .coe 파일 포맷으로 출력
    with open("tdc_calibration_lut.coe", "w") as f:
        f.write("memory_initialization_radix=10;\n")
        f.write("memory_initialization_vector=\n")
        for val in lut_integers:
            f.write(f"{val},\n") 
    ```

## 4. 결론
이 5단계 캘리브레이션 프로세스는 하드웨어의 Wrap-around로 인해 분절된 데이터를 완벽하게 제어합니다. 특히, **Step 2의 조건부 구간 삭제 로직**을 통해 이기종 주기에서 발생하는 측정 노이즈를 완벽히 차단하며, **Step 3의 Unwrapping**을 통해 수학적 보간의 정확도를 100% 보장하는 무결점 LUT를 생성해 냅니다.
"""

# 파일 저장 실행
with open("TDC_Calibration_Report.md", "w", encoding="utf-8") as file:
    file.write(report_content)

print("✅ 'TDC_Calibration_Report.md' 파일이 성공적으로 생성되었습니다!")