파이썬 스크립트 실행 과정에서 지속적인 불편을 드려 죄송합니다. 개발 환경에 구애받지 않고 바로 검토 및 기록하실 수 있도록, 요청하신 모든 기술적 내용과 수식, 설정, 그리고 수정된 전체 코드를 포함한 종합 기술 보고서를 이곳에 바로 작성해 드립니다. 

복사하여 바로 활용하시기 바랍니다.

---

# [기술 보고서] STM32G474RE 기반 FMCW LiDAR 비트 신호 모사 기술

본 보고서는 STM32G474RE 개발 보드를 활용하여 FMCW LiDAR의 수신단에서 검출되는 비트(Beat) 신호(100 kHz ~ 1 MHz)를 디지털 펄스 형태로 부드럽고 왜곡 없이 모사하기 위한 기술적 구현 방법을 다룹니다.

---

## 1. 개요 및 목적
FMCW LiDAR 수신기에서는 송신광과 수신광의 간섭으로 인해 거리에 비례하는 비트 주파수(Beat Frequency) 신호가 발생합니다. 이 아날로그 신호가 비교기(Comparator)를 통과하면 주파수가 선형적으로 변화하는 디지털 펄스 스트림이 됩니다. 

본 구현의 목적은 고속 주파수 변화 시 CPU에 부하를 주지 않으면서, 펄스 폭이 자연스럽게 줄어드는(Chirp) 고속 디지털 신호를 안정적으로 모사하는 것입니다.

---

## 2. 수학적 모델링 및 시간축 계산

### 2.1 선형 주파수 Chirp 공식
시간 $t$에 따른 주파수 $f(t)$는 다음과 같은 일차함수 식으로 정의됩니다.
$$f(t) = f_{start} + \beta \times t$$

*   $f_{start}$: 시작 주파수 ($100,000 \text{ Hz}$)
*   $f_{end}$: 최종 주파수 ($1,000,000 \text{ Hz}$)
*   $T_{chirp}$: Chirp 소요 시간 ($0.005 \text{ s}$, 즉 5ms)
*   $\beta$: 주파수 변화율 (가속도 기울기)

### 2.2 주파수 변화율 ($\beta$) 계산
주파수 변화율 $\beta$는 단위 시간당 주파수 변화량입니다.
$$\beta = \frac{f_{end} - f_{start}}{T_{chirp}} = \frac{1,000,000 - 100,000}{0.005} = 180,000,000 \text{ Hz/s} \quad (180 \text{ MHz/s})$$

### 2.3 구체적 시점 계산 예시 ($t = 10\,\mu\text{s}$ 일 때)
첫 번째 펄스(100 kHz, 주기 $10\,\mu\text{s}$)가 완료된 바로 그 시점($t = 10\,\mu\text{s} = 0.000010\,\text{s}$)에서 두 번째 펄스가 가져야 할 주파수 값은 다음과 같이 계산됩니다.
$$f(0.000010) = 100,000 + (180,000,000 \times 0.000010) = 101,800 \text{ Hz} \quad (101.8 \text{ kHz})$$

### 2.4 이산적(Discrete) 시간 축 전진 메커니즘
컴퓨터 알고리즘상에서 고정된 시간 단계(예: $10\,\mu\text{s}$씩 강제 증가)로 주파수를 계산하면, 실제 출력되는 타이머의 펄스 주기와 오차가 누적되어 신호 왜곡이 발생합니다. 

이를 해결하기 위해 **가상의 시간 $t$를 방금 계산된 타이머 주기의 물리적 소요 시간만큼 누적**하여 업데이트합니다.
$$t_{next} = t_{current} + \frac{ARR + 1}{f_{sys}}$$

이 방식을 통해 하드웨어 펄스의 경계면과 수학적 공식의 시간축이 정확하게 일치하게 되어 위상 단절이 없는 부드러운 천이가 구현됩니다.

---

## 3. STM32CubeMX 설정 가이드

하드웨어 수준에서 주파수 업데이트를 전담 제어하도록 다음과 같이 구성합니다.

### 3.1 Clock Configuration
*   **HCLK (System Clock):** 최대 주파수인 `170 MHz`로 설정합니다.

### 3.2 TIM1 (타이머 1) 설정
*   **Combined Channels:** `PWM Generation CH1`을 활성화합니다.
*   **Prescaler (PSC):** `0` (170 MHz 클럭 소스 그대로 인입)
*   **Counter Period (ARR):** `1699` (임시값)
*   **Auto-reload preload:** `Enable` (반드시 활성화하여 다음 주기 시작 시점에 새로운 주기값이 갱신되도록 제어)
*   **CH1 Pulse (CCR1):** `850` (50% 듀티비 임시값)
*   **CH1 Preload:** `Enable` (반드시 활성화)

### 3.3 DMA Settings (TIM1_UP)
타이머가 한 주기를 끝낼 때마다(Update Event) 발생할 인터럽트를 DMA가 수신하도록 트리거를 설정합니다.
*   **DMA Request:** `TIM1_UP` 추가
*   **Direction:** Memory To Peripheral
*   **Mode:** Circular (주기적 Chirp 파형의 무한 반복 구동을 위해 필요)
*   **Increment Address:** Memory (체크), Peripheral (체크 해제)
*   **Data Width:** Memory `Word` (32-bit), Peripheral `Word` (32-bit)

### 3.4 GPIO Settings
*   TIM1_CH1 출력 핀(예: PA8)의 **GPIO Speed**를 **Very High**로 지정하여 1 MHz 고속 스위칭 시 발생하는 슬루율 왜곡을 방지합니다.

---

## 4. 구동 알고리즘 및 DMA Burst 메커니즘

1.  **배열(Look-Up Table)의 연속성:**
    TIM1의 레지스터 구조상 `ARR` (주기 결정)과 `CCR1` (듀티비 결정) 사이에는 `RCR` (반복 카운터) 레지스터가 물리적으로 존재합니다. 따라서 메모리에서 주소 증가식으로 단번에 데이터를 전송하려면 세 레지스터 영역을 모두 반영하는 데이터 구조(Structure)를 생성해야 합니다.
2.  **DMA Multi-Write:**
    단일 전송 함수인 `HAL_TIM_DMABurst_WriteStart` 대신, 다중 연속 버스트 제어를 보장하는 **`HAL_TIM_DMABurst_MultiWriteStart`** 함수를 사용하여 컴파일 에러를 방지하고 안정적인 데이터 전달 구조를 확립합니다.

---

## 5. 전체 C 소스 코드

이 코드는 STM32CubeMX가 생성한 프로젝트의 `Core/Src/main.c`에 기입되는 코드입니다. 지정된 `USER CODE` 구역에 각각 정확히 매칭되도록 구성되어 있습니다.

### 5.1 전역 선언부 (`/* USER CODE BEGIN PD */`)
```c
/* USER CODE BEGIN PD */
#define CHIRP_DURATION_SEC  0.005f     // Chirp 기간 (5ms)
#define F_START             100000.0f  // 시작 주파수 100 kHz
#define F_END               1000000.0f // 최종 주파수 1 MHz
#define TIMER_CLK           170000000.0f // TIM1 입력 클럭 (170 MHz)

// TIM1 레지스터 매핑 구조체 (ARR -> RCR -> CCR1 순서로 연속 배치됨)
typedef struct {
    uint32_t arr;  // Auto-Reload Register (주기 결정)
    uint32_t rcr;  // Repetition Counter Register (0으로 고정)
    uint32_t ccr;  // Capture Compare Register 1 (듀티비 결정)
} TimerConfig_t;

#define MAX_PULSES 3000 
TimerConfig_t chirp_lut[MAX_PULSES];
uint32_t total_pulses = 0;
/* USER CODE END PD */
```

### 5.2 함수 프로토타입 선언부 (`/* USER CODE BEGIN PFP */`)
```c
/* USER CODE BEGIN PFP */
void Generate_Chirp_LUT(void);
/* USER CODE END PFP */
```

### 5.3 초기화 및 실행 제어부 (`/* USER CODE BEGIN 2 */`)
```c
  /* USER CODE BEGIN 2 */
  // 1. 순시 시간 기반의 정밀 타이머 설정 테이블 사전 계산
  Generate_Chirp_LUT();

  // 2. 타이머 1 PWM 기본 채널 출력 시작
  HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);

  // 3. Update Event 마다 ARR/RCR/CCR1 레지스터를 동시에 업데이트하는 DMA 버스트 구동
  HAL_TIM_DMABurst_MultiWriteStart(
      &htim1, 
      TIM_DMABASE_ARR, 
      TIM_DMA_UPDATE, 
      (uint32_t*)chirp_lut, 
      TIM_DMABURSTLENGTH_3TRANSFERS, 
      total_pulses * 3  // 전체 전송할 32-bit 워드 수
  );
  /* USER CODE END 2 */
```

### 5.4 알고리즘 구현부 (`/* USER CODE BEGIN 4 */`)
```c
/* USER CODE BEGIN 4 */
/**
  * @brief  주파수 Chirp 특성에 부합하는 ARR, CCR 값들을 시간 정합성을 반영하여 사전 계산하는 함수
  * @param  None
  * @retval None
  */
void Generate_Chirp_LUT(void) {
    float t = 0.0f;
    float beta = (F_END - F_START) / CHIRP_DURATION_SEC; // 주파수 가속 기울기
    uint32_t idx = 0;

    while (t < CHIRP_DURATION_SEC && idx < MAX_PULSES) {
        // 1. 현재 누적 시간 t 기준의 주파수 공식 계산
        float f_inst = F_START + beta * t;
        
        // 2. 타이머 클럭 소스 기반의 ticks 수 계산 (반올림 처리 포함)
        float period_ticks = TIMER_CLK / f_inst;
        uint32_t arr_val = (uint32_t)(period_ticks + 0.5f) - 1;
        uint32_t ccr_val = (arr_val + 1) / 2; // 정확한 50% 듀티 유지

        // 3. 레지스터 테이블 배열 순차 등록
        chirp_lut[idx].arr = arr_val;
        chirp_lut[idx].rcr = 0;
        chirp_lut[idx].ccr = ccr_val;

        // 4. 물리적인 하드웨어 주기 만큼 시간 변수 t를 누적하여 오차 방지
        t += (float)(arr_val + 1) / TIMER_CLK;
        idx++;
    }
    total_pulses = idx; // 실제 생성된 전체 펄스 개수 저장
}
/* USER CODE END 4 */
```

---

## 6. 검증 및 결과 확인

1.  **소스 코드 빌드 및 라이팅:**
    코드를 반영하여 빌드 후 Nucleo-G474RE 보드에 업로드합니다.
2.  **오실로스코프 연결:**
    프로브를 타이머 1 채널 1의 출력 핀인 **PA8** 핀에 연결하고 Ground를 보드 GND에 결선합니다.
3.  **파형 분석:**
    *   신호의 전반부 시작 지점에서는 넓은 주기를 가집니다 ($10\,\mu\text{s}$, 100 kHz).
    *   후반부로 도달할수록 파형의 폭이 부드럽고 촘촘하게 좁아지며 종단에 이릅니다 ($1\,\mu\text{s}$, 1 MHz).
    *   이 모든 일련의 주파수 Sweep 과정이 끊김 현상(Glitches) 없이 5ms 주기로 부드럽게 무한히 반복 출력되는 것을 확인할 수 있습니다.