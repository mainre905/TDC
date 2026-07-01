FMCW LiDAR(Frequency Modulated Continuous Wave LiDAR)의 핵심 파라미터들은 모두 **선형 주파수 변조(Chirp)**의 특성과 밀접하게 연결되어 있습니다. 아래에서 핵심 수식들을 체계적으로 정리하고, 물리적 의미와 설계상 트레이드오프를 설명하겠습니다.

---

## 1. 기본 파라미터 정의

| 기호 | 정의 | 단위 |
|------|------|------|
| $B$ | 주파수 변조 대역폭 (Bandwidth) | Hz |
| $T_m$ | 변조 주기(Chirp duration) | s |
| $\gamma = B/T_m$ | Chirp rate (주파수 변화율) | Hz/s |
| $\tau = 2R/c$ | 광 왕복 시간 지연 | s |
| $\lambda$ | 레이저 파장 | m |
| $c$ | 빛의 속도 ($\approx 3\times 10^8$) | m/s |
| $f_b$ | 비트 주파수 (Beat frequency) | Hz |

---

## 2. 핵심 수식 및 물리적 의미

### (1) 비트 주파수 (Beat Frequency) - 거리 측정의 핵심
$$f_b = \frac{2\gamma R}{c} = \frac{2BR}{cT_m}$$

**의미:**
- 송신 신호와 수신 신호의 **순간 주파수 차이**입니다.
- 거리 $R$에 비례하며, 이 주파수를 정확히 측정하면 거리를 역산할 수 있습니다.
- 예: $\gamma = 100$ THz/s, $R = 150$ m일 때, $f_b \approx 100$ kHz (전자회로로 쉽게 처리 가능한 범위)

---

### (2) 거리 해상도 (Range Resolution)
$$\Delta R = \frac{c}{2B}$$

**의미:**
- **이웃한 두 물체를 구분할 수 있는 최소 거리 간격**입니다.
- **대역폭 $B$만 결정**하며, chirp 기간 $T_m$이나 거리와는 무관합니다.
- 광학적 파장이 아닌 **전자적 대역폭**이 정밀도를 결정하는 FMCW의 핵심 특징입니다.
- 예: $B = 1$ GHz → $\Delta R = 15$ cm; $B = 10$ GHz → $\Delta R = 1.5$ cm

---

### (3) 최대 비모호 거리 (Maximum Unambiguous Range)
$$R_{max} = \frac{cT_m}{2} = \frac{c}{2f_m}$$

($f_m = 1/T_m$은 chirp 반복 주파수)

**의미:**
- **에일리어싱(Aliasing) 없이 측정 가능한 최대 거리**입니다.
- $T_m$이 길수록 멀리 있는 물체를 감지할 수 있으나, **프레임 레이트(업데이트 속도)**가 저하됩니다.
- 실제로는 ADC 샘플링 레이트 $f_s$의 제약도 받습니다: $f_{b,max} < f_s/2$ (Nyquist)

---

### (4) 거리 측정 정확도 (Range Accuracy)
$$\delta R \approx \frac{c}{2B} \cdot \frac{1}{\sqrt{SNR}} \cdot \frac{1}{\sqrt{N}}$$

**의미:**
- **해상도(Resolution)**는 이론적 한계이고, **정확도(Accuracy)**는 실제 측정 잡음에 의해 결정됩니다.
- SNR이 높을수록, 그리고 coherent integration(누적 횟수 $N$)을 많이 할수록 정확도는 해상도보다 훨씬 좋아집니다 (mm 이하도 가능).

---

### (5) 속도 측정 (Doppler Shift)
$$f_d = -\frac{2v}{\lambda}$$

**의미:**
- 물체의 **상대 속도** $v$에 의해 발생하는 주파수 시프트입니다.
- FMCW는 단일 chirp로는 거리와 속도가 **결합(Range-Doppler coupling)**되어 구분이 어려워, 일반적으로 **업-다운(Up-Down) chirp** 또는 **삼각파 변조**를 사용합니다.

#### 삼각파 변조에서의 분리:
- Up-chirp 비트 주파수: $f_{b,up} = f_r - f_d$
- Down-chirp 비트 주파수: $f_{b,down} = f_r + f_d$

여기서 $f_r = \frac{2\gamma R}{c}$이므로:

$$R = \frac{c}{4\gamma}(f_{b,up} + f_{b,down}), \quad v = \frac{\lambda}{4}(f_{b,down} - f_{b,up})$$

---

### (6) 속도 해상도 및 최대 속도
$$\Delta v = \frac{\lambda}{2T_m}, \quad v_{max} = \frac{\lambda}{4T_{chirp}}$$

**의미:**
- **속도 해상도**는 총 관측 시간(coherent processing interval)에 반비례합니다.
- **최대 속도**는 단일 chirp 내에서 Nyquist 한계에 의해 결정됩니다.
- 거리와 속도는 **불확정성 관계**가 있어 $T_m$을 길게 하면 거리는 멀리 볼 수 있지만 속도 분해능이 떨어집니다.

---

### (7) SNR (Shot Noise Limited)
$$SNR = \frac{\eta P_{sig}P_{LO}}{h\nu \cdot B_{elec}}$$

**의미:**
- FMCW는 **헤테로다인 검출**을 사용하므로, LO(Local Oscillator) 광과의 믹싱으로 신호를 증폭합니다.
- $B_{elec}$는 전자적 대역폭으로, $B_{elec} \approx f_{b,max}$와 관련됩니다.
- 중요한 점은 **수신 광 강도 $P_{sig}$가 아닌 LO와의 혼합**으로 인해 약한 신호도 검출 가능하다는 것입니다.

---

## 3. 파라미터 간 설계 트레이드오프

| 목표 | 조치 | 부작용/희생 |
|------|------|-------------|
| **거리 해상도 향상** | $B$ 증가 | 광학 대역폭 소폭, 광원 선폭 요구 증가 |
| **최대 거리 증가** | $T_m$ 증가 | 프레임 레이트 감소, 속도 해상도 저하 |
| **속도 정밀도 향상** | $T_m$ 증가 (또는 N 누적) | 거리 측정 시간 증가, 동적 환경에서 블러 |
| **비트 주파수 낮추기** | $\gamma$ 감소 (느린 chirp) | 거리 측정 시간 증가, 속도-거리 결합 심화 |

---

## 4. 설계 예시 (수치 계산)

**조건:** 자율주행 LiDAR, 300m 거리 측정, 10cm 해상도 목표
- 필요 대역폭: $B = \frac{c}{2\Delta R} = \frac{3\times 10^8}{2\times 0.1} = 1.5$ GHz
- Chirp 주기 설정: $T_m = 100$ μs (업데이트 레이트 10 kHz)
- Chirp rate: $\gamma = 1.5\text{ GHz} / 100\text{ μs} = 15$ THz/s
- 300m에서의 비트 주파수: $f_b = \frac{2 \times 15\times 10^{12} \times 300}{3\times 10^8} = 30$ MHz
- 필요 ADC 샘플링 레이트: $> 60$ MHz (Nyquist)
- 최대 비모호 거리: $R_{max} = \frac{3\times 10^8 \times 100\times 10^{-6}}{2} = 15$ km (충분히 여유 있음)

---

## 5. 특별 고려사항 (Optical Specifics)

RADAR와 달리 **FMCW LiDAR**에서는 다음 광학적 제약이 추가됩니다:

1. **레이저 선폭(Line Width, $\Delta\nu$)**: 
   $$\Delta R_{linewidth} \approx \frac{c \cdot \Delta\nu}{\gamma}$$
   - 선폭이 넓으면 비트 신호의 위상 잡음이 증가하여 거리 정확도가 떨어집니다. (typical: < 100 kHz 필요)

2. **코히런스 길이(Coherence Length)**: $L_{coh} = c/\Delta\nu$로, 이 길이보다 먼 물체는 측정이 불가능합니다.

3. **비선형성 보정**: 레이저의 주파수 변조가 완벽한 선형이 아니면 거리 측정 오차가 발생하므로, 광학 위상 루프(OPLL) 또는 디지털 보정이 필요합니다.

이 수식들은 FMCW LiDAR 시스템의 스펙 산정부터 신호 처리 알고리즘 설계까지 모든 단계에서 기준이 되는 물리적 법칙들입니다.