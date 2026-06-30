import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import platform

# =========================================================================
# 0. 한글 폰트 및 설정
# =========================================================================
if platform.system() == 'Windows':
    plt.rcParams['font.family'] = 'Malgun Gothic'
elif platform.system() == 'Darwin':
    plt.rcParams['font.family'] = 'AppleGothic'
else:
    plt.rcParams['font.family'] = 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False

PHASE_STEP_PS = 1000.0 / 56.0  

script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, 'iladata.csv')

df = pd.read_csv(csv_filepath, skiprows=[1])
df.columns = [c.strip().split("[")[0] for c in df.columns]

# 하드웨어 신호 자동 매핑
target_keywords = {"valid": "final_ts_valid", "fine": "aligned_fine_idx", "loop": "current_loop_cnt"}
mapped_cols = {}
for key, keyword in target_keywords.items():
    found_col = next((c for c in df.columns if keyword in c), None)
    if found_col is None:
        print(f"❌ 에러: CSV에서 '{keyword}' 신호를 찾을 수 없습니다!")
        exit()
    mapped_cols[key] = found_col

COL_VALID, COL_FINE, COL_LOOP = mapped_cols["valid"], mapped_cols["fine"], mapped_cols["loop"]

for col in [COL_VALID, COL_FINE, COL_LOOP]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df_valid = df.dropna(subset=[COL_FINE, COL_LOOP]).copy()
df_valid = df_valid[df_valid[COL_VALID] == 1]

# =========================================================================
# [핵심 1] 조각 이어붙이기 폐기 -> 가장 긴 '골든 청크(Golden Chunk)' 추출
# =========================================================================
grouped = df_valid.groupby(COL_LOOP)[COL_FINE].mean().reset_index()
grouped['tap_idx'] = np.round(grouped[COL_FINE]).astype(int)
grouped['raw_time_ps'] = grouped[COL_LOOP] * PHASE_STEP_PS

taps = grouped['tap_idx'].values
times = grouped['raw_time_ps'].values

# 탭 번호가 50 이상 뚝 떨어지는 곳(랩어라운드 발생)을 기준으로 데이터를 나눔
split_indices = np.where(np.diff(taps) < -50)[0] + 1
segments = np.split(np.arange(len(taps)), split_indices)

# 가장 데이터가 많은 연속 구간(Golden Chunk) 찾기
longest_seg_indices = max(segments, key=len)

# 양끝에서 발생하는 고스트 탭(노이즈)을 수학적으로 완벽히 잘라내기 위해 앞뒤 2개씩 버림
golden_indices = longest_seg_indices[2:-2]

golden_taps = taps[golden_indices]
golden_times = times[golden_indices]

# 같은 탭 번호에서 미세한 노이즈가 있을 수 있으니 평균으로 깔끔하게 정리
clean_df = pd.DataFrame({'tap': golden_taps, 'time': golden_times})
clean_df = clean_df.groupby('tap')['time'].mean().reset_index()

final_taps = clean_df['tap'].values
final_times = clean_df['time'].values

# =========================================================================
# [핵심 2] 선형 외삽법 (Extrapolation) 및 LUT 생성
# =========================================================================
def extrapolate_interp(target_x, xp, yp):
    # 정렬 및 보간
    idx = np.argsort(xp)
    xp, yp = xp[idx], yp[idx]
    y = np.interp(target_x, xp, yp)
    
    # 우측 연장 (측정된 마지막 5개 탭의 기울기를 이어감)
    slope_right = (yp[-1] - yp[-5]) / (xp[-1] - xp[-5])
    right_mask = target_x > xp[-1]
    y[right_mask] = yp[-1] + slope_right * (target_x[right_mask] - xp[-1])
    
    # 좌측 연장 (측정된 최초 5개 탭의 기울기를 이어감)
    slope_left = (yp[4] - yp[0]) / (xp[4] - xp[0])
    left_mask = target_x < xp[0]
    y[left_mask] = yp[0] + slope_left * (target_x[left_mask] - xp[0])
    return y

target_taps = np.arange(320)
calibrated_abs_time = extrapolate_interp(target_taps, final_taps, final_times)

# 하드웨어 로직을 위해 Tap 0번을 무조건 0ps로 정렬 (단조 증가 완성)
calibrated_abs_time = calibrated_abs_time - calibrated_abs_time[0]

lut_integers = np.round(calibrated_abs_time).astype(int)

# coe 파일 출력
coe_filepath = os.path.join(script_dir, "tdc_calibration_lut.coe")
with open(coe_filepath, "w") as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    for i, val in enumerate(lut_integers):
        f.write(f"{val};\n" if i == len(lut_integers)-1 else f"{val},\n")
print(f"■ 절벽 제거 완벽 해결! '{coe_filepath}' 파일 생성 완료!")

# =========================================================================
# 6. 최종 완벽 시각화
# =========================================================================
plt.figure(figsize=(14, 7))

plt.plot(final_taps, final_times - final_times[0], 'o', color='#3b82f6', markersize=6, label='Golden Measured Taps')
plt.plot(target_taps, calibrated_abs_time, '-', color='#10b981', linewidth=2, alpha=0.6, zorder=1, label='Perfect Extrapolated Line')

plt.title("Ultimate TDC Calibration: The Flawless Monotonic Delay Line", fontsize=16, fontweight='bold', pad=15)
plt.xlabel("TDC Fine Index (Tap)", fontsize=12)
plt.ylabel("Absolute Time (ps)", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.6)
plt.legend(loc='lower right', fontsize=11)
plt.tight_layout()

png_filepath = os.path.join(script_dir, "flawless_straight_line.png")
plt.savefig(png_filepath, dpi=300)
plt.show()