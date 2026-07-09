# 🚀 TI C2000 다중 ePWM 동기화 및 정밀 제어 최종 보고서

## 1. 시스템 개요 (System Overview)
* **Target MCU:** TI TMS320F28003x / F28004x 시리즈
* **System Clock:** EPWMCLK = 100MHz (1 Tick = 10ns)
* **개발 목표:** CPU(인터럽트)의 개입 없이, 오직 하드웨어 레지스터 라우팅만으로 아래 3개의 완벽한 동기화 파형을 생성.
  1. **FSYNC (Master):** 100ms 주기, 90ms ON (무한 반복)
  2. **SSYNC (Slave 1):** FSYNC 시작 대비 **2.5us 지연** 후 시작. 33us 주기(25us ON)로 **정확히 2000번 출력 후 하드웨어 차단**
  3. **JSYNC (Slave 2):** SSYNC 시작 대비 **250ns 지연** 후 시작. 2.5us 주기(1us ON)로 **정확히 6번 출력 후 하드웨어 차단**

---

## 2. 핀 할당 및 역할 (Pin Allocation)
이 시스템은 실제 파형이 나가는 3개의 핀과, 내부 로직을 위해 사용하는 2개의 가상(Dummy) 핀으로 구성됩니다.

### 🟢 실제 출력 핀 (Real Output Pins)
* **EPWM1_A (예: GPIO0):** `FSYNC` 파형이 실제로 출력되는 핀.
* **EPWM2_A (예: GPIO2):** `SSYNC` 파형이 실제로 출력되는 핀.
* **EPWM3_A (예: GPIO4):** `JSYNC` 파형이 실제로 출력되는 핀.

### 🔴 루프백 가상 핀 (Dummy / Loopback Pins)
타이머가 계산한 '차단 시점'을 칩 외부로 내보냈다가 다시 내부망으로 읽어 들이기 위한 용도입니다. 보드 상에서 아무것도 연결하지 않고 비워두어야 합니다.
* **EPWM4_A (예: GPIO19):** SSYNC의 **66ms(2000번)** 차단 시점을 알리는 핀. (66ms 지점에서 3.3V로 켜짐)
* **EPWM5_A (예: GPIO20):** JSYNC의 **15us(6번)** 차단 시점을 알리는 핀. (15us 지점에서 3.3V로 켜짐)

---

## 3. 핵심 동작 원리 (Core Principles)

### ① 역산 위상 지연 로직 (Phase Shift Logic)
ePWM을 `Up-Count` 모드로 사용할 때, 딜레이 카운트를 그대로 입력하면 카운터가 끝까지 도달하는 데 걸리는 시간이 오히려 길어집니다. 따라서 **"전체 주기 카운트 - 원하는 지연 카운트"** 를 입력해야 완벽한 지연이 생성됩니다.
* **JSYNC 250ns 지연 예시:** 
  * 목표 지연 25 카운트(250ns) / 전체 주기 250 카운트
  * 입력할 Phase 값: `250 - 25 = 225`
  * 동작: 동기화 시 225부터 카운트 시작 ➡️ 25 카운트만 세면 0에 도달하여 파형 발사 (정확히 250ns 지연 달성)

### ② 하드웨어 차단 서브시스템 (X-BAR, DC, TZ)
소프트웨어 카운팅 대신, 특정 시간에만 열려있는 '창문(Window)'을 만들어 핀을 제어합니다.
* **1. INPUT X-BAR (감시자):** GPIO19, GPIO20 등 외부 핀의 전기적 상태(High/Low)를 실시간으로 감시하여 칩 내부망으로 끌어옵니다.
* **2. EPWM X-BAR (전달망):** INPUT X-BAR에서 감지한 신호를 고속 고속도로(TRIP4, TRIP5)에 실어 ePWM 모듈들로 배달합니다.
* **3. Digital Compare (디지털 번역기):** Trip Zone은 TRIP4/TRIP5 신호를 직접 읽지 못합니다. 따라서 DC 모듈이 "TRIP 신호가 High가 되면 -> DCAEVT(디지털 비교 이벤트) 알람을 울려라!" 하고 신호를 번역해 줍니다.
* **4. Trip Zone (차단 실행기):** DCAEVT 알람을 듣는 즉시, 현재 핀으로 나가고 있는 출력(SSYNC, JSYNC)의 멱살을 잡고 `Force Low (0V)` 로 영구 차단합니다. 주기가 새로 시작되면 차단은 자동 해제됩니다.

---

## 4. SysConfig 상세 설정 값

### [1] FSYNC (Master - EPWM1)
* **Time Base:** /64, /10 분주 적용. Period `15624`. Phase Shift **미사용**.
* **Sync:** Sync Out Pulse = `Time-base counter equal to zero`
* **Action Qualifier:** Zero ➡️ `High`, CMPA(`14062`) ➡️ `Low`

### [2] SSYNC (Slave 1 - EPWM2)
* **Time Base:** /1, /1 분주. Period `3299`.
* **Sync:** Sync In = `EPWM1 Sync-out`, **Phase Shift `3050`** (2.5us 지연). Sync Out = `Zero`.
* **Action Qualifier:** Zero ➡️ `High`, CMPA(`2500`) ➡️ `Low`
* **Trip Zone & DC:** DCAH Source = `Trip 4`. Event A2 = `DCAH is high`. CBC Source = `DCAEVT2`. Action = `Force Low`.

### [3] SSYNC 차단 스톱워치 (EPWM4 ➡️ GPIO19)
* **Time Base:** /64, /10 분주 적용. Period `15624`.
* **Sync:** Sync In = `EPWM1 Sync-out`, **Phase Shift `0`** (동시 출발).
* **Action Qualifier:** Zero ➡️ `Low`, CMPA(`10312`) ➡️ `High` (66ms 지점에서 창문 닫힘)

### [4] JSYNC (Slave 2 - EPWM3)
* **Time Base:** /1, /1 분주. Period `249`.
* **Sync:** Sync In = `EPWM2 Sync-out`, **Phase Shift `225`** (250ns 지연).
* **Action Qualifier:** Zero ➡️ `High`, CMPA(`100`) ➡️ `Low`
* **Trip Zone & DC (이중 차단):** 
  * DCAH Source = `Trip 5` (자신의 15us 닫힘), DCBH Source = `Trip 4` (형님의 66ms 닫힘).
  * CBC Source = `DCAEVT2` & `DCBEVT2` 동시 체크. Action = `Force Low`.

### [5] JSYNC 차단 스톱워치 (EPWM5 ➡️ GPIO20)
* **Time Base:** /1, /1 분주. Period `3299`.
* **Sync:** Sync In = `EPWM2 Sync-out`, **Phase Shift `0`** (동시 출발).
* **Action Qualifier:** Zero ➡️ `Low`, CMPA(`1400`) ➡️ `High` (약 14us 지점에서 창문 닫힘)

### [6] 하드웨어 라우팅 설정 (X-BAR)
1. **INPUT X-BAR:**
   * INPUT1 = `GPIO19` (SSYNC 감시)
   * INPUT2 = `GPIO20` (JSYNC 감시)
2. **EPWM X-BAR:**
   * TRIP4 Mux = `INPUTXBAR1` 체크
   * TRIP5 Mux = `INPUTXBAR2` 체크

---

## 5. 결론 (Conclusion)
위 설정을 통해 소프트웨어 인터럽트 부하(CPU Load)를 0%로 유지하면서도, 나노초(ns) 단위의 지터(Jitter) 없는 완벽한 결정론적(Deterministic) 다중 동기화 펄스를 생성할 수 있습니다. 이는 TI C2000 MCU의 하드웨어 타이머 자원을 극한으로 활용한 모범적인 설계 사례입니다.