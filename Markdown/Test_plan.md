요청하신 **TDC 성능 평가 및 캘리브레이션 실험 계획서**를 Markdown (`.md`) 형식으로 작성했습니다. 

아래 내용을 복사하여 `.md` 파일로 저장하시거나 Notion, GitHub 등에 바로 붙여넣어 팀원들과 공유 및 실험 매뉴얼로 활용하실 수 있습니다.

---

# 🔬 TDC 성능 평가 및 캘리브레이션 실험 계획서

**문서 목적:** 본 문서는 FPGA 기반 TDC(Time-to-Digital Converter)의 비선형성(DNL/INL)을 Code Density Test 기법으로 측정하고, LUT(Look-Up Table) 기반의 COE 파일을 생성하여 캘리브레이션을 수행하는 전체 실험 절차를 정의합니다.

**실험 환경 파라미터:**
- 클럭 주기: `5ns (200MHz)`
- 딜레이 체인 길이: `320 Taps (CARRY4 80 Stage)`
- 이상적인 1 Tap 분해능: `15.625ps`

---

## 🚀 Phase 1: MODE 0 (MMCM Phase Sweep 캘리브레이션)
**목표:** 고정된 주기의 동기화 신호를 이용해 각 탭의 실제 물리적 지연 시간을 추출하고, 비선형성(INL/DNL)을 보정하는 COE 파일을 생성 및 검증합니다.

### Step 1. 초기 상태(Uncalibrated) 선형성 측정
1. **Vivado 프로젝트 설정**
   - `OPERATION_MODE = 0` 으로 설정.
   - 이상적인 선형 데이터(Dummy 데이터)가 들어있는 `dummy.coe` 파일을 생성하여 `tdc_calib_rom` IP에 적용. *(값: 0, 16, 31, 47 ...)*
   - 코드 하단의 **Timestamp 확인용 ILA**의 주석을 해제 (트리거: `loop_cnt` 변경 시점 1회 캡처).
2. **측정 및 데이터 저장**
   - Bitstream 생성 후 보드 다운로드.
   - `btn_shift` 버튼을 눌러 스윕 실행.
   - ILA에 캡처된 280개의 스텝 데이터(`current_loop_cnt` vs `final_timestamp_ps`)를 `uncalibrated_inl.csv`로 Export.

### Step 2. Code Density(히스토그램) 데이터 추출
1. **Vivado ILA 설정 변경**
   - 코드 하단의 **히스토그램 캡처용 ILA** 주석 해제 (트리거: `readout_active`, Depth: 1024).
   - Bitstream 재성성 후 다운로드.
2. **스윕 및 BRAM Readout**
   - `btn_shift` 버튼 입력 후 약 3초(280 스텝 대기시간) 대기.
   - BRAM에서 뿜어져 나오는 320 Taps의 누적 카운트 값을 ILA로 캡처.
   - 데이터를 `histogram_raw.csv`로 Export.

### Step 3. 데이터 분석 및 COE 파일 생성 (PC 작업)
- 파이썬(Python) 스크립트를 이용하여 `histogram_raw.csv`를 분석합니다.
- **연산 공식:**
  - $Total\_Count = \sum Count[i]$ (전체 히트 수)
  - $Bin\_Width[i] = 5000ps \times \left( \frac{Count[i]}{Total\_Count} \right)$
  - $Absolute\_Time[i] = \sum_{k=0}^{i-1} Bin\_Width[k] + \frac{Bin\_Width[i]}{2}$
- 계산된 $Absolute\_Time$ 배열을 정수로 반올림하여 `calibrated_rom.coe` 파일로 저장.

### Step 4. 캘리브레이션 적용 및 최종 검증
1. **COE 업데이트**
   - Vivado `tdc_calib_rom` IP의 초기화 파일을 `calibrated_rom.coe`로 변경.
2. **최종 선형성 측정 (Step 1 반복)**
   - 다시 **Timestamp 확인용 ILA**를 활성화하고 Bitstream 다운로드.
   - 스윕 실행 후 `calibrated_inl.csv` Export.
3. **결과 비교 (그래프 작성)**
   - X축: `MMCM Phase Step` / Y축: `Timestamp (ps)`
   - **기대 결과:** 보정 전(Step 1) 그래프의 물결무늬(INL 오차)가 보정 후(Step 4) 완벽한 직선 형태로 펴지는 것을 확인.

---

## 🌀 Phase 2: MODE 1 (Ring Oscillator 비동기 난수 테스트)
**목표:** 캘리브레이션이 완료된 시스템에 비동기(Asynchronous) 난수 신호인 Ring Oscillator 출력을 인가하여, 실전 환경에서의 백그라운드 데이터 누적 안정성과 탭 밀도를 확인합니다.

### Step 1. 테스트 환경 설정
1. **Vivado 프로젝트 설정**
   - `OPERATION_MODE = 1` 로 변경.
   - `gated_ts_valid = final_ts_valid` 조건에 의해 백그라운드에서 항상 히트가 누적됨.
   - **히스토그램 캡처용 ILA** 활성화.
   - Bitstream 생성 및 보드 다운로드.

### Step 2. 백그라운드 누적 및 캡처
1. **데이터 누적**
   - 보드 전원 인가 후 약 1~2분간 대기. (Ring Oscillator에서 생성된 비동기 Hit가 수억 번 이상 BRAM에 자연스럽게 누적됨).
2. **Readout 트리거**
   - 이 모드에서도 `btn_shift`를 누르면 MMCM 스윕 대기 로직이 가동되며, 완료 후 `readout_active`가 1이 됨.
   - `btn_shift`를 누르고 대기하여 누적된 히스토그램을 ILA로 캡처.
   - 데이터를 `ro_histogram.csv`로 Export.

### Step 3. 데이터 분석 및 검증
- **비동기 신호의 균일성(Uniformity) 검증:**
  Ring Oscillator와 System Clock은 비동기 관계이므로, 히트 이벤트는 5ns 주기 내에서 완전히 랜덤하게 떨어져야 합니다. 
  - **기대 결과:** `ro_histogram.csv`의 데이터 프로파일이 Mode 0에서 추출했던 물리적 딜레이 프로파일(`histogram_raw.csv`)과 형태가 거의 일치해야 합니다. (Bin Width가 넓은 탭에 비례하여 난수 히트도 많이 쌓임).
- **시스템 안정성 검증:**
  장시간(수 분~수 시간) 켜두어도 시스템이 정지하지 않고, 오버플로우 없이 카운트가 정상적으로 유지됨을 확인합니다.

---

## 🛠 부록 (Appendix)
### Python COE 생성 스크립트 (예시)
```python
import pandas as pd
import numpy as np

# 1. 데이터 로드 (X: Tap Index, Y: Count)
df = pd.read_csv('histogram_raw.csv')
counts = df['probe2_count_value'].values # ILA CSV 컬럼명에 맞게 수정

# 2. 파라미터
T_clk = 5000.0 # ps (200MHz)
total_hits = np.sum(counts)

# 3. Bin Width (DNL 계산용) 및 절대 시간(INL) 계산
bin_widths = T_clk * (counts / total_hits)
absolute_times = np.zeros(len(counts))

cumulative_time = 0.0
for i in range(len(counts)):
    absolute_times[i] = cumulative_time + (bin_widths[i] / 2.0)
    cumulative_time += bin_widths[i]

# 4. COE 파일 작성
with open('calibrated_rom.coe', 'w') as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    for i, t in enumerate(absolute_times):
        val = int(round(t))
        if i == len(absolute_times) - 1:
            f.write(f"{val};\n")
        else:
            f.write(f"{val},\n")

print("calibrated_rom.coe 생성 완료!")
```