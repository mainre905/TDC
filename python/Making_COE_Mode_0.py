import os
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.stats import linregress
import matplotlib.pyplot as plt

# =========================================================================
# 1. 설정 및 데이터 로드
# =========================================================================
PHASE_STEP_PS = 1000.0 / 56.0  # 1GHz VCO 기준 약 17.857 ps/step
NUM_TOTAL_TAPS = 320           # CARRY4 80 Stage * 4

script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "stitched_data.csv") # 사용자 전처리 파일

try:
    df = pd.read_csv(csv_filepath)
except FileNotFoundError:
    print(f"❌ '{csv_filepath}' 파일이 없습니다.")
    exit()

col_loop = [c for c in df.columns if 'loop' in c.lower()][0]
col_tap = [c for c in df.columns if 'tap' in c.lower()][0]

loops = pd.to_numeric(df[col_loop], errors="coerce").values
taps = pd.to_numeric(df[col_tap], errors="coerce").values

valid_mask = ~np.isnan(loops) & ~np.isnan(taps)
loops = loops[valid_mask]
taps = taps[valid_mask]

# 절대 시간(ps) 변환
time_ps = (loops - loops[0]) * PHASE_STEP_PS

# 동일 탭 노이즈 평균화 및 정렬
df_clean = pd.DataFrame({'tap': taps, 'time': time_ps}).groupby('tap')['time'].mean().reset_index()
df_clean = df_clean.sort_values(by='tap').reset_index(drop=True)

final_taps = df_clean['tap'].values
final_times = df_clean['time'].values

# =========================================================================
# 2. 완벽한 직선 연장 (Global Slope Extrapolation)
# =========================================================================
# 1) 전체 데이터의 평균 기울기(LSB) 계산
slope, _, _, _, _ = linregress(final_taps, final_times)
global_lsb_ps = slope

# 2) 보간 함수 생성 (외삽 끄기)
interp_func = interp1d(final_taps, final_times, kind='linear')

min_meas_tap = np.min(final_taps)
max_meas_tap = np.max(final_taps)
time_at_min_tap = final_times[np.argmin(final_taps)]
time_at_max_tap = final_times[np.argmax(final_taps)]

target_taps = np.arange(NUM_TOTAL_TAPS)
calibrated_abs_time = np.zeros(NUM_TOTAL_TAPS)

# 3) 구간별로 나누어서 시간 계산
for i, tap in enumerate(target_taps):
    if tap < min_meas_tap:
        # 왼쪽 끝단 연장
        calibrated_abs_time[i] = time_at_min_tap - (min_meas_tap - tap) * global_lsb_ps
    elif tap > max_meas_tap:
        # 오른쪽 끝단 연장
        calibrated_abs_time[i] = time_at_max_tap + (tap - max_meas_tap) * global_lsb_ps
    else:
        # 내부 구간 보간
        calibrated_abs_time[i] = interp_func(tap)

# 0번 탭을 0ps로 정렬 및 음수 방지
calibrated_abs_time = calibrated_abs_time - calibrated_abs_time[0]
calibrated_abs_time = np.clip(calibrated_abs_time, 0, None)

# =========================================================================
# 3. 양자화(Rounding) 및 COE 파일 생성 (주석 완전 제거)
# =========================================================================
lut_integers = np.round(calibrated_abs_time).astype(int)
coe_filepath = os.path.join(script_dir, "tdc_calib_mode0_rom.coe")

with open(coe_filepath, "w") as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    for i, val in enumerate(lut_integers):
        end_char = ";" if i == len(lut_integers) - 1 else ",\n"
        # ★ 주석(# Tap i)을 제거하고 숫자와 구분자만 출력
        f.write(f"{val}{end_char}")

print(f"✅ 성공: 주석이 제거된 COE 파일 생성 완료 -> {coe_filepath}")

# =========================================================================
# 4. 결과 시각화 (확인용)
# =========================================================================
plt.figure(figsize=(10, 6))

plt.scatter(final_taps, final_times - final_times[0], color='#3b82f6', alpha=0.7, s=20, label='User Processed Raw Data')
plt.plot(target_taps, calibrated_abs_time, color='#ef4444', linewidth=2, linestyle='--', label=f'Interpolated & Extrapolated (Slope: {global_lsb_ps:.2f})')

plt.title("Mode 0: Final TDC Calibration LUT Generation", fontsize=14, fontweight='bold')
plt.xlabel("TDC Fine Index (Tap 0 ~ 319)", fontsize=12)
plt.ylabel("Absolute Delay Time (ps)", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.6)
plt.legend()
plt.tight_layout()
plt.show()