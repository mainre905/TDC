FMCW LiDAR에서 반도체 레이저(DFB, VCSEL 등)에 선형적인 전류를 주입해도, **열적 효과(Thermal effect)와 캐리어 동역학** 때문에 주파수가 시간에 따라 완벽한 선형으로 변하지 않는 **비선형 Chirp**이 발생합니다. 

이 비선형성은 타겟의 비트 주파수를 퍼지게 하여(Spectral Broadening) **거리 분해능과 정확도를 치명적으로 저하**시킵니다. 이를 감지하고 보정(Linearization)하기 위해 사용하는 핵심 광학 소자가 바로 **비대칭 마하-젠더 간섭계(Unbalanced Mach-Zehnder Interferometer, MZI)**입니다.

MZI와 레이저 선형 제어와 관련된 핵심 수식과 물리적 의미를 정리해 드립니다.

---

## 1. MZI 기초 및 비트 주파수 수식

MZI는 길이가 다른 두 개의 광경로(Arm)를 나누었다가 다시 합치는 구조입니다. 길이가 고정된 MZI는 **"광파주파수 영역의 자(Ruler)"** 역할을 합니다.

| 기호 | 정의 | 단위 |
|------|------|------|
| $\Delta L$ | MZI 두 팔(Arm)의 물리적 길이 차이 | m |
| $n_g$ | 도파로(또는 광섬유)의 그룹 굴절률 (Group Index) | - |
| $\tau_{mzi}$ | MZI 시간 지연 (Time Delay) | s |
| $\gamma(t)$ | 순간 Chirp rate ($= df(t)/dt$) | Hz/s |
| $f_{b,mzi}$ | MZI에서 생성된 비트 주파수 | Hz |

### (1) MZI 시간 지연 (Time Delay)
$$\tau_{mzi} = \frac{n_g \cdot \Delta L}{c}$$

**의미:**
- 레이저 빛이 긴 경로를 지나면서 짧은 경로보다 겪게 되는 시간 지연입니다.
- 이 값이 고정되어 있으므로, MZI는 타겟이 고정된 $\Delta L / 2$ 거리에 있는 것처럼 동작합니다.

---

### (2) MZI 비트 주파수 (MZI Beat Frequency) ★ 가장 중요 ★
$$f_{b,mzi}(t) = \gamma(t) \cdot \tau_{mzi} = \frac{df(t)}{dt} \cdot \frac{n_g \cdot \Delta L}{c}$$

**의미:**
- 레이저 주파수 변화율($\gamma(t)$)과 MZI 비트 주파수($f_{b,mzi}$)는 **완벽한 정비례 관계**입니다.
- **선형 변조 시 ($\gamma(t) = \gamma_0$ 고정):** $f_{b,mzi}$는 일정한 단일 주파수(Pure Tone)를 유지합니다.
- **비선형 변조 시:** 레이저의 주파수가 빠르게 변하면 $f_{b,mzi}$가 높아지고, 느리게 변하면 낮아집니다. 즉, **$f_{b,mzi}(t)$의 흔들림을 관측하면 레이저의 비선형성을 실시간으로 측정**할 수 있습니다.

---

### (3) MZI 출력 위상 및 자유분광역 (FSR)
$$I_{mzi}(t) \propto \cos\left(2\pi \int f_{b,mzi}(t) dt\right) = \cos\left(2\pi \cdot \tau_{mzi} \cdot \Delta f(t)\right)$$

$$FSR = \frac{1}{\tau_{mzi}} = \frac{c}{n_g \cdot \Delta L}$$

**의미:**
- $FSR$(Free Spectral Range)은 MZI 출력 정현파 신호가 한 주기($2\pi$) 변할 때 주파수 변화량입니다.
- 예를 들어 $FSR = 20 \text{ MHz}$라면, MZI 출력 신호의 피크가 하나 지날 때마다 레이저 주파수가 정확히 $20 \text{ MHz}$ 이동했음을 의미합니다.

---

## 2. 레이저 선형화 보정(Linearization) 수식 및 원리

MZI를 활용한 선형 제어는 크게 **하드웨어적 제어(Pre-distortion / OPLL)**와 **소프트웨어적 보정(K-clock Resampling)**으로 나뉩니다.

### (1) 사전 왜곡 보정 (Iterative Pre-distortion)
$$i_{n+1}(t) = i_n(t) - K \cdot \left[ f_{b,mzi}(t) - f_{target} \right]$$

**의미:**
- 레이저에 주입하는 전류 파형 $i(t)$를 수정하는 방식입니다.
- 측정된 MZI 비트 주파수($f_{b,mzi}(t)$)가 목표 주파수($f_{target} = \gamma_{ideal} \tau_{mzi}$)보다 높으면 해당 구간의 전류 기울기를 낮추고, 낮으면 높이는 피드백 루프입니다.

---

### (2) 광학 위상 잠금 루프 (OPLL: Optoelectronic Phase-Locked Loop)
$$e(t) = \phi_{mzi}(t) - \phi_{ref}(t) \implies \text{PID Controller} \implies \text{Laser Current}$$

**의미:**
- MZI 출력 신호와 완벽한 선형 RF 고주파 기준 신호(Reference Clock)의 위상을 위상검출기(PD)로 비교합니다.
- 위상 오차 $e(t)$를 0으로 만들도록 레이저 튜닝 전류를 실시간 폐루프(Closed-loop) 제어합니다.

---

### (3) K-Clock 리샘플링 (Auxiliary MZI Resampling) ★ 현대 FMCW의 표준 ★
레이저를 강제로 선형화하지 않고, **비선형인 채로 두고 신호 처리 단계에서 보정**하는 방식입니다.

$$t_k \text{ satisfying } \int_0^{t_k} f_{b,mzi}(t) dt = k \cdot \text{constant}$$
$$S_{target\_linear}[k] = S_{target}(t_k)$$

**의미:**
- 타겟 신호를 일정한 시간 간격($\Delta t$, 일정한 ADC 샘플링 레이트)으로 샘플링하면 비선형성 때문에 FFT 시 신호가 찌그러집니다.
- 대신 **MZI 비트 신호($f_{b,mzi}$)의 영점 교차점(Zero-crossing)이나 피크를 ADC의 클럭(Clock)으로 사용**하여 타겟 신호를 샘플링합니다.
- 시간 기준이 아닌 **"광 주파수가 고정된 간격($FSR$)만큼 변할 때마다" 타겟 신호를 샘플링**하게 되므로, 수학적으로 완벽한 선형 Chirp 데이터를 얻은 것과 동일한 효과를 냅니다.

---

## 3. MZI 길이 ($\Delta L$) 설계 트레이드오프

MZI의 길이 차이 $\Delta L$을 얼마로 설계하느냐는 시스템 성능의 핵심입니다.

| 고려 항목 | 긴 $\Delta L$ 설계 시 ($\tau_{mzi}$ 증가) | 짧은 $\Delta L$ 설계 시 ($\tau_{mzi}$ 감소) |
| :--- | :--- | :--- |
| **선형화 분해능** | **우수** ($FSR$이 작아져 주파수 변화를 매우 촘촘하게 감시 가능) | **낮음** ($FSR$이 커서 미세한 비선형성 감지 불가) |
| **MZI 비트 주파수** | **높음** ($f_{b,mzi}$가 커짐 $\rightarrow$ 고속 광검출기 및 ADC 필요) | **낮음** (저렴한 전자 회로로 처리 가능) |
| **레이저 선폭 제약** | 레이저 코히런스 길이($L_{coh}$)보다 $\Delta L$이 길면 간섭 안 됨 | 레이저 선폭 요구조건이 완화됨 |
| **온도/진동 민감도**| 광섬유/도파로가 길어 온도 변화에 위상 흔들림 심함 | 비교적 안정적 |

### 수치 설계 예시:
- 목표 Chirp rate: $\gamma = 20 \text{ THz/s}$
- 광섬유 굴절률: $n_g = 1.5$
- 광섬유 길이 차이 선택: $\Delta L = 1.5 \text{ m}$

1. **시간 지연:** $\tau_{mzi} = \frac{1.5 \times 1.5}{3 \times 10^8} = 7.5 \text{ ns}$
2. **MZI 비트 주파수:** $f_{b,mzi} = 20 \times 10^{12} \times 7.5 \times 10^{-9} = 150 \text{ MHz}$
   *(150 MHz 클럭으로 리샘플링 수행)*
3. **주파수 분해능 (FSR):** $FSR = \frac{1}{7.5 \text{ ns}} \approx 133.3 \text{ MHz}$
   *(레이저 주파수가 133.3 MHz 변할 때마다 샘플이 1개씩 생성됨)*