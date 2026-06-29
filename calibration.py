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

# =========================================================================
# 1. 데이터 로드 및 VCO 설정
# =========================================================================
PHASE_STEP_PS = 1000.0 / 56.0  
CLOCK_CYCLE_PS = 5000.0        

print(f"■ MMCM VCO 1GHz 적용: 스텝당 위상 천이 = {PHASE_STEP_PS:.7f} ps")

csv_filename = "iladata.csv"
if not os.path.exists(csv_filename):
    print(f"❌ '{csv_filename}' 파일이 없습니다.")
    exit()

df = pd.read_csv(csv_filename, skiprows=[1])
df.columns = [c.strip().split("[")[0] for c in df.columns]

for col in ["ts_valid_d2", "ts_fine_idx_d2", "current_loop_cnt"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df_valid = df.dropna(subset=["ts_fine_idx_d2", "current_loop_cnt"]).copy()
df_valid = df_valid[df_valid["ts_valid_d2"] == 1]

# =========================================================================
# 2. 벡터 연산을 이용한 데이터 분할 및 [Ghost Tap 필터링]
# =========================================================================
grouped = df_valid.groupby('current_loop_cnt')['ts_fine_idx_d2'].mean().reset_index()
grouped['tap_idx'] = np.round(grouped['ts_fine_idx_d2']).astype(int)
grouped['raw_time_ps'] = grouped['current_loop_cnt'] * PHASE_STEP_PS
grouped['phase_ps'] = grouped['raw_time_ps'] % CLOCK_CYCLE_PS

# NumPy diff를 활용해 역방향 하락 지점을 기준으로 고속 분할
diffs = np.diff(grouped['tap_idx'].values)
split_indices = np.where(diffs < 0)[0] + 1
segments_raw = np.split(grouped, split_indices)

segments = []
for seg in segments_raw:
    # ★ 길이가 짧은 Ghost Tap (노이즈) 조각은 폐기
    if len(seg) > 5:
        segments.append(pd.DataFrame(seg))

main_seg = max(segments, key=len)
print(f"■ 필터링 완료: 노이즈 제거 후 총 {len(segments)}개 유효 조각 확보.")

# =========================================================================
# 3. 빈 탭 이어 붙이기 (Priority Stitching)
# =========================================================================
tap_to_phase = {}
source_map = {}

# Main 우선 등록
for tap, phase in main_seg.groupby('tap_idx')['phase_ps'].mean().items():
    tap_to_phase[tap] = phase
    source_map[tap] = 'Main (가장 긴 직선)'

# 나머지 빈칸 채우기
for seg in segments:
    if seg is main_seg: continue
    for tap, phase in seg.groupby('tap_idx')['phase_ps'].mean().items():
        if tap not in tap_to_phase:  
            tap_to_phase[tap] = phase
            source_map[tap] = 'Patched (결측치 보충)'

# =========================================================================
# 4. 위상 펼침 (Phase Unwrapping)
# =========================================================================
sorted_taps = np.array(sorted(tap_to_phase.keys()))
phases = np.array([tap_to_phase[t] for t in sorted_taps])
sources = np.array([source_map[t] for t in sorted_taps])

unwrapped_time = np.zeros_like(phases)
unwrapped_time[0] = phases[0]
offset = 0.0

for i in range(1, len(phases)):
    diff = phases[i] - phases[i-1]
    if diff < -2500:  
        offset += CLOCK_CYCLE_PS
    elif diff > 2500: 
        offset -= CLOCK_CYCLE_PS
    unwrapped_time[i] = phases[i] + offset

unwrapped_time = unwrapped_time - unwrapped_time[0] 

# =========================================================================
# 5. 선형 외삽법 (Extrapolation) 및 LUT 생성
# =========================================================================
def extrapolate_interp(target_x, xp, yp):
    """ 범위를 벗어나는 데이터에 대해 마지막 기울기를 연장하여 외삽 """
    y = np.interp(target_x, xp, yp)
    
    # 우측 외삽
    if len(xp) > 5:
        slope_right = (yp[-1] - yp[-5]) / (xp[-1] - xp[-5])
        right_mask = target_x > xp[-1]
        y[right_mask] = yp[-1] + slope_right * (target_x[right_mask] - xp[-1])
        
        slope_left = (yp[4] - yp[0]) / (xp[4] - xp[0])
        left_mask = target_x < xp[0]
        y[left_mask] = yp[0] + slope_left * (target_x[left_mask] - xp[0])
    return y

target_taps = np.arange(320)
calibrated_abs_time = extrapolate_interp(target_taps, sorted_taps, unwrapped_time)

lut_phase = calibrated_abs_time % CLOCK_CYCLE_PS
lut_integers = np.round(lut_phase).astype(int)

with open("tdc_calibration_lut.coe", "w") as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    for i, val in enumerate(lut_integers):
        f.write(f"{val};\n" if i == len(lut_integers)-1 else f"{val},\n")
print("■ 4929 평탄화 문제 해결! 'tdc_calibration_lut.coe' 파일 생성 완료!")

# =========================================================================
# 6. 시각화 (그래프 출력)
# =========================================================================
plt.figure(figsize=(14, 7))
main_mask = sources == 'Main (가장 긴 직선)'
plt.plot(sorted_taps[main_mask], unwrapped_time[main_mask], 'o', color='#3b82f6', markersize=6, label='Main Segment')

patch_mask = sources == 'Patched (결측치 보충)'
if np.any(patch_mask):
    plt.plot(sorted_taps[patch_mask], unwrapped_time[patch_mask], 's', color='#ef4444', markersize=6, label='Patched Taps')

plt.plot(target_taps, calibrated_abs_time, '-', color='#10b981', linewidth=2, alpha=0.5, zorder=1, label='Extrapolated Final Curve')

plt.title("Ultimate TDC Calibration: Merged & Extrapolated Delay Line", fontsize=16, fontweight='bold', pad=15)
plt.xlabel("TDC Fine Index (Tap)", fontsize=12)
plt.ylabel("Unwrapped Absolute Time (ps)", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.6)
plt.legend(loc='lower right', fontsize=11)
plt.tight_layout()
plt.savefig("combined_straight_line.png", dpi=300)
plt.show() 