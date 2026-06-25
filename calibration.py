import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import platform

# -------------------------------------------------------------------------
# 0. 한글 폰트 및 설정
# -------------------------------------------------------------------------
if platform.system() == 'Windows':
    plt.rcParams['font.family'] = 'Malgun Gothic'
elif platform.system() == 'Darwin':
    plt.rcParams['font.family'] = 'AppleGothic'
else:
    plt.rcParams['font.family'] = 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False

# -------------------------------------------------------------------------
# 1. 데이터 로드 및 VCO 1GHz 해상도 적용
# -------------------------------------------------------------------------
# MMCM VCO = 1GHz -> 1주기 = 1000ps
# 7-Series MMCM 위상 천이 스텝 = 1주기 / 56
PHASE_STEP_PS = 1000.0 / 56.0  # 약 17.8571428 ps
CLOCK_CYCLE_PS = 5000.0        # TDC 샘플링 클럭 (200MHz = 5000ps)

print(f"■ MMCM VCO 1GHz 적용: 스텝당 위상 천이 = {PHASE_STEP_PS:.7f} ps")

csv_filename = "iladata.csv"
if not os.path.exists(csv_filename):
    print(f"'{csv_filename}' 파일이 없습니다.")
    exit()

df = pd.read_csv(csv_filename, skiprows=[1])
df.columns = [c.strip().split("[")[0] for c in df.columns]

for col in ["ts_valid_d2", "ts_fine_idx_d2", "current_loop_cnt"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df_valid = df.dropna(subset=["ts_fine_idx_d2", "current_loop_cnt"]).copy()
df_valid = df_valid[df_valid["ts_valid_d2"] == 1]

# -------------------------------------------------------------------------
# 2. 데이터 분절(Segments) 파악 및 [규칙 1: 가장 긴 직선] 찾기
# -------------------------------------------------------------------------
# 스텝별 평균 탭 계산 및 절대 시간 부여
grouped = df_valid.groupby('current_loop_cnt')['ts_fine_idx_d2'].mean().reset_index()
grouped['tap_idx'] = np.round(grouped['ts_fine_idx_d2']).astype(int)
grouped['raw_time_ps'] = grouped['current_loop_cnt'] * PHASE_STEP_PS
grouped['phase_ps'] = grouped['raw_time_ps'] % CLOCK_CYCLE_PS

# Wrap-around(탭 인덱스 폭락)를 기준으로 데이터 조각(Segment) 나누기
segments = []
current_seg = []
prev_tap = -1000

for idx, row in grouped.iterrows():
    if row['tap_idx'] < prev_tap - 50:  # 탭이 50 이상 뚝 떨어지면 다음 조각으로 분리
        if current_seg:
            segments.append(pd.DataFrame(current_seg))
        current_seg = []
    current_seg.append(row)
    prev_tap = row['tap_idx']
if current_seg:
    segments.append(pd.DataFrame(current_seg))

# 규칙 1: 가장 데이터가 많은(가장 긴) 조각을 Main으로 선정
main_seg = max(segments, key=len)
print(f"■ [규칙 1] 총 {len(segments)}개의 조각 중, 데이터가 가장 많은 조각(길이: {len(main_seg)})을 최우선 기준으로 선정 완료.")

# -------------------------------------------------------------------------
# 3. [규칙 2: 없는 Tap 이어 붙이기] 병합(Stitching) 작업
# -------------------------------------------------------------------------
tap_to_phase = {}
source_map = {}

# 3-1. 가장 긴 직선의 데이터(Main) 우선 등록
main_tap_avg = main_seg.groupby('tap_idx')['phase_ps'].mean()
for tap, phase in main_tap_avg.items():
    tap_to_phase[tap] = phase
    source_map[tap] = 'Main (가장 긴 직선)'

# 3-2. Main에 없는 빈 이빨(Tap)을 나머지 조각들에서 가져와 채워 넣음
patched_count = 0
for seg in segments:
    if seg is main_seg: continue
    seg_tap_avg = seg.groupby('tap_idx')['phase_ps'].mean()
    for tap, phase in seg_tap_avg.items():
        if tap not in tap_to_phase:  # Main에 없는 탭일 경우에만!
            tap_to_phase[tap] = phase
            source_map[tap] = 'Patched (이어 붙인 데이터)'
            patched_count += 1

print(f"■ [규칙 2] Main에 없는 탭 {patched_count}개를 찾아 완벽하게 연결 완료.")

# -------------------------------------------------------------------------
# 4. Phase Unwrapping (하나의 물리적 직선으로 복원)
# -------------------------------------------------------------------------
sorted_taps = np.array(sorted(tap_to_phase.keys()))
phases = np.array([tap_to_phase[t] for t in sorted_taps])
sources = np.array([source_map[t] for t in sorted_taps])

unwrapped_time = np.zeros_like(phases)
unwrapped_time[0] = phases[0]
offset = 0.0

# 탭이 증가할 때 시간이 뚝 떨어지면 5000ps(1주기)를 더해 물리적 직선으로 편다
for i in range(1, len(phases)):
    diff = phases[i] - phases[i-1]
    if diff < -2500:  # 예: 4900ps -> 100ps 로 떨어질 때
        offset += CLOCK_CYCLE_PS
    elif diff > 2500: # 역방향 지터 예방
        offset -= CLOCK_CYCLE_PS
    unwrapped_time[i] = phases[i] + offset

# 시작점을 깔끔하게 0ps로 정규화
unwrapped_time = unwrapped_time - unwrapped_time[0]

# -------------------------------------------------------------------------
# 5. [규칙 4: 캘리브레이션 및 LUT.coe 생성]
# -------------------------------------------------------------------------
target_taps = np.arange(320)
# 복원된 거대한 1개의 직선을 이용해 320개 전체 탭 선형 보간
calibrated_abs_time = np.interp(target_taps, sorted_taps, unwrapped_time)

# 하드웨어 동작을 위해 다시 5000ps 모듈러 적용 및 정수화
lut_phase = calibrated_abs_time % CLOCK_CYCLE_PS
lut_integers = np.round(lut_phase).astype(int)

with open("tdc_calibration_lut.coe", "w") as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    for i, val in enumerate(lut_integers):
        f.write(f"{val};\n" if i == len(lut_integers)-1 else f"{val},\n")
print("■ [규칙 4] 'tdc_calibration_lut.coe' 캘리브레이션 파일 생성 완료!")

# -------------------------------------------------------------------------
# 6. [규칙 3: 병합된 직선 데이터 그림 저장]
# -------------------------------------------------------------------------
plt.figure(figsize=(14, 7))

# Main 데이터 그리기 (파란색)
main_mask = sources == 'Main (가장 긴 직선)'
plt.plot(sorted_taps[main_mask], unwrapped_time[main_mask], 'o', color='#3b82f6', 
         markersize=6, label='Main Segment (가장 긴 기준 직선)')

# Patched 데이터 그리기 (빨간색/주황색)
patch_mask = sources == 'Patched (이어 붙인 데이터)'
if np.any(patch_mask):
    plt.plot(sorted_taps[patch_mask], unwrapped_time[patch_mask], 's', color='#ef4444', 
             markersize=6, label='Patched Taps (가져와서 붙인 데이터)')

# 전체 보간된 직선 커브 그리기
plt.plot(target_taps, calibrated_abs_time, '-', color='#10b981', linewidth=2, 
         alpha=0.6, zorder=1, label='Final Interpolated Straight Line')

plt.title("Ultimate TDC Calibration: Merged Absolute Delay Line", fontsize=16, fontweight='bold', pad=15)
plt.xlabel("TDC Fine Index (Tap)", fontsize=12)
plt.ylabel("Unwrapped Absolute Time (ps)", fontsize=12)

# VCO 1GHz 해상도 정보 텍스트 박스
info_text = f"MMCM VCO: 1 GHz\nPhase Step: {PHASE_STEP_PS:.3f} ps"
plt.text(0.02, 0.95, info_text, transform=plt.gca().transAxes, fontsize=11,
         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

plt.grid(True, linestyle='--', alpha=0.6)
plt.legend(loc='lower right', fontsize=11)
plt.tight_layout()

plt.savefig("combined_straight_line.png", dpi=300)
print("■ [규칙 3] 'combined_straight_line.png' 이미지 저장 완료!\n✅ 모든 작업이 성공적으로 끝났습니다.")