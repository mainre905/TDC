# TDC 캘리브레이션을 위한 Mode 0 기반 COE 파일 생성 원리

## 1. 개요 (Introduction)
이 문서는 사용자가 수동으로 메타스테빌리티(Metastability)를 제거하고 연속적으로 이어 붙인(Stitched) 전처리 완료 CSV 데이터(`loop_cnt`, `tap_avg`)를 활용하여, FPGA TDC 캘리브레이션용 룩업 테이블(LUT, `.coe` 파일)을 생성하는 수학적 원리와 Python 구현 방법을 설명합니다.

---

## 2. COE 파일 생성의 수학적 원리 (Mathematical Model)

전처리된 데이터는 이미 단조 증가(Monotonic Increase)하는 이상적인 선형 형태를 갖추고 있습니다. 이를 320 탭 규격의 하드웨어 ROM 데이터로 변환하기 위해 다음 4단계를 거칩니다.

### Step 1. 절대 시간 변환 (Time Conversion)
MMCM 위상 천이의 1 스텝(`loop_cnt`)이 가지는 물리적 시간 $\Delta t$를 계산합니다. Xilinx 7-Series 아키텍처 기준, 위상 스텝 해상도는 VCO 주파수($F_{vco}$)에 의해 결정됩니다.

$$ \Delta t = \frac{1000 \text{ ps}}{F_{vco} \text{ (GHz)} \times 56} $$

> **예시:** $F_{vco} = 1\text{GHz}$일 경우, $1 \text{ Step} \approx 17.857 \text{ ps}$가 됩니다. 즉, `loop_cnt` 4는 $4 \times 17.857 = 71.428 \text{ ps}$의 지연을 의미합니다. 시작점(`loop_cnt` 최소값)을 0ps로 정렬하여 기준을 맞춥니다.

### Step 2. 선형 보간법 (Linear Interpolation)
ROM의 주소는 반드시 정수(0, 1, 2... 319)여야 하지만, 측정된 평균 탭은 소수점(예: Tap 3.9933)을 가집니다. 따라서 측정된 두 점 사이의 직선의 방정식을 이용하여 정수 탭에 대한 절대 시간을 추정합니다.

$$ \text{Time}(n) = T_a + \frac{T_b - T_a}{Tap_b - Tap_a} \times (n - Tap_a) $$

> **예시 계산 (Tap 4.0 시간 구하기):**
> - 측정점 A: $Tap_a = 3.9933$, 시간 $T_a = 71.428 \text{ ps}$
> - 측정점 B: $Tap_b = 4.6333$, 시간 $T_b = 89.285 \text{ ps}$
> - 대입: $71.428 + \frac{89.285 - 71.428}{4.6333 - 3.9933} \times (4.0 - 3.9933) = \mathbf{71.614\text{ ps}}$

### Step 3. 선형 외삽법 (Linear Extrapolation)
320개의 탭 중 측정 데이터의 범위를 벗어나는 양 끝단 빈 공간(예: 0~1번 탭 또는 275~319번 탭)은 측정된 전체 데이터의 기울기(1 탭당 평균 지연 시간)를 연장(Extrapolate)하여 수학적으로 채워 넣습니다.

### Step 4. 정수 양자화 (Quantization)
FPGA 내부 ROM 모듈은 정수를 기반으로 동작하므로 계산된 피코초(ps) 값을 반올림(Round)합니다.
$$ LUT\_Value[n] = \lfloor \text{Time}(n) + 0.5 \rfloor $$
> **예시:** $71.614 \text{ ps} \rightarrow \mathbf{72}$. 이 값이 `.coe` 파일의 4번 주소에 기입됩니다.

---

## 3. 자동화 Python 코드 (COE Generator)

사용자가 전처리한 `processed_data.csv` 파일을 읽어와 수학적 보간/외삽을 수행하고 최종 `tdc_calib_rom.coe` 파일을 자동 생성하는 파이썬 스크립트입니다.

```python
import os
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

# =========================================================================
# 1. 설정 및 수동 전처리 데이터 로드
# =========================================================================
PHASE_STEP_PS = 1000.0 / 56.0  # 1GHz VCO 기준 약 17.857 ps/step
NUM_TOTAL_TAPS = 320           # CARRY4 80 Stage * 4

script_dir = os.path.dirname(os.path.abspath(__file__))
# 사용자가 직접 메타스테빌리티를 제거하고 정렬한 CSV 파일명
csv_filepath = os.path.join(script_dir, "processed_data.csv")

try:
    df = pd.read_csv(csv_filepath)
except FileNotFoundError:
    print(f"❌ '{csv_filepath}' 파일이 없습니다. 수동으로 생성한 CSV 파일을 확인하세요.")
    exit()

# 컬럼명 유연하게 매칭 (loop_cnt, tap_avg)
col_loop = [c for c in df.columns if 'loop' in c.lower()][0]
col_tap = [c for c in df.columns if 'tap' in c.lower()][0]

loops = pd.to_numeric(df[col_loop], errors="coerce").values
taps = pd.to_numeric(df[col_tap], errors="coerce").values

# 결측치 제거
valid_mask = ~np.isnan(loops) & ~np.isnan(taps)
loops = loops[valid_mask]
taps = taps[valid_mask]

# =========================================================================
# 2. 절대 시간(ps) 변환
# =========================================================================
# loop_cnt를 피코초(ps)로 변환하고 시작점을 0ps로 정렬
time_ps = (loops - loops[0]) * PHASE_STEP_PS

# =========================================================================
# 3. 선형 보간 (Interpolation) 및 외삽 (Extrapolation)
# =========================================================================
# 동일한 Tap 번호에 미세한 노이즈가 있을 경우를 대비해 시간 평균화
df_clean = pd.DataFrame({'tap': taps, 'time': time_ps})
df_clean = df_clean.groupby('tap')['time'].mean().reset_index()

# 보간 함수 생성을 위해 오름차순 정렬 (단조 증가 확인)
df_clean = df_clean.sort_values(by='tap').reset_index(drop=True)

final_taps = df_clean['tap'].values
final_times = df_clean['time'].values

# Scipy를 이용한 선형 보간 및 양 끝단 선형 외삽 수행
interp_func = interp1d(final_taps, final_times, kind='linear', fill_value="extrapolate")

# 0~319 정수 탭에 대한 절대 시간(ps) 일괄 추출
target_taps = np.arange(NUM_TOTAL_TAPS)
calibrated_abs_time = interp_func(target_taps)

# 하드웨어 단조 증가 유지를 위해 Tap 0을 0ps로 클램핑
calibrated_abs_time = calibrated_abs_time - calibrated_abs_time[0]
calibrated_abs_time = np.clip(calibrated_abs_time, 0, None)

# =========================================================================
# 4. 양자화(Rounding) 및 COE 파일 생성
# =========================================================================
# 피코초(ps) 데이터를 정수로 반올림
lut_integers = np.round(calibrated_abs_time).astype(int)
coe_filepath = os.path.join(script_dir, "tdc_calib_rom.coe")

with open(coe_filepath, "w") as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    for i, val in enumerate(lut_integers):
        end_char = ";" if i == len(lut_integers) - 1 else ","
        f.write(f"{val}{end_char}  # Tap {i}\n")

print(f"✅ 성공: 수동 데이터를 기반으로 한 COE 파일 생성 완료 -> {coe_filepath}")

# =========================================================================
# 5. 결과 시각화 (확인용)
# =========================================================================
plt.figure(figsize=(10, 6))
plt.scatter(final_taps, final_times, color='#3b82f6', alpha=0.7, label='User Processed Raw Data')
plt.plot(target_taps, calibrated_abs_time, color='#ef4444', linewidth=2, linestyle='--', label='Interpolated LUT Curve')

plt.title("Mode 0: Final TDC Calibration LUT Generation", fontsize=14, fontweight='bold')
plt.xlabel("TDC Fine Index (Tap 0 ~ 319)", fontsize=12)
plt.ylabel("Absolute Delay Time (ps)", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.6)
plt.legend()
plt.tight_layout()
plt.show()