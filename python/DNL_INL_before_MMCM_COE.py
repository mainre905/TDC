import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from scipy.stats import linregress

# =========================================================================
# 1. 설정 및 데이터 로드
# =========================================================================
PHASE_STEP_PS = 1000.0 / 56.0  # 1GHz VCO 기준 MMCM 스텝 시간 (약 17.857 ps)

script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "stitched_data.csv") # ★ 사용자님의 파일명으로 변경하세요

try:
    df = pd.read_csv(csv_filepath)
except FileNotFoundError:
    print(f"❌ '{csv_filepath}' 파일을 찾을 수 없습니다.")
    exit()

# 컬럼명 유연하게 매칭
col_loop = [c for c in df.columns if 'loop' in c.lower()][0]
col_tap = [c for c in df.columns if 'tap' in c.lower()][0]

loops = pd.to_numeric(df[col_loop], errors="coerce").values
taps_raw = pd.to_numeric(df[col_tap], errors="coerce").values

# 결측치 제거
valid_mask = ~np.isnan(loops) & ~np.isnan(taps_raw)
loops = loops[valid_mask]
taps_raw = taps_raw[valid_mask]

# =========================================================================
# 2. 절대 시간(ps) 변환 및 정수 탭(Integer Tap) 시간 추출
# =========================================================================
# MMCM loop_cnt를 피코초(ps)로 변환 (시작점 0ps 정렬)
times_raw = (loops - loops[0]) * PHASE_STEP_PS

# 보간을 위해 데이터를 Tap 기준으로 정렬 및 중복 제거 (단조 증가 확보)
df_clean = pd.DataFrame({'tap': taps_raw, 'time': times_raw}).groupby('tap')['time'].mean().reset_index()
df_clean = df_clean.sort_values(by='tap').reset_index(drop=True)

taps_sorted = df_clean['tap'].values
times_sorted = df_clean['time'].values

# 유효한 정수 탭 범위 설정 (예: 1, 2, ..., 273)
min_tap = int(np.ceil(taps_sorted.min()))
max_tap = int(np.floor(taps_sorted.max()))
integer_taps = np.arange(min_tap, max_tap + 1)

# 선형 보간을 통해 각 정수 탭의 정확한 도달 시간(ps) 추출
interp_func = interp1d(taps_sorted, times_sorted, kind='linear')
integer_times = interp_func(integer_taps)

# =========================================================================
# 3. LSB, DNL, INL 계산 (논문 표준 공식)
# =========================================================================
# 1) LSB (1탭 평균 지연 시간): 정수 탭과 시간의 선형 회귀 기울기
slope, intercept, r_value, _, _ = linregress(integer_taps, integer_times)
LSB_ps = slope

# 2) Bin Width (각 탭의 실제 지연 시간 폭): 인접한 탭 간의 시간 차이
bin_widths = np.diff(integer_times)

# 3) DNL 계산: (실제 폭 - LSB) / LSB
# 폭의 개수는 탭 개수보다 1개 적으므로, DNL을 그릴 X축도 1개 줄임
DNL = (bin_widths - LSB_ps) / LSB_ps
dnl_taps = integer_taps[:-1] 

# 4) INL 계산: (실제 누적 시간 - 이상적 누적 시간) / LSB
ideal_times = (integer_taps * LSB_ps) + intercept
INL = (integer_times - ideal_times) / LSB_ps

# =========================================================================
# 4. 논문용 DNL / INL 분석 결과 시각화
# =========================================================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

# [상단 그래프] DNL (미분 비선형성)
ax1.plot(dnl_taps, DNL, color='#3b82f6', linewidth=1.2, alpha=0.9, label='DNL')
ax1.fill_between(dnl_taps, DNL, 0, color='#3b82f6', alpha=0.3)
ax1.set_title(f"Before Calibration: DNL Analysis (Average LSB = {LSB_ps:.3f} ps)", fontsize=14, fontweight='bold')
ax1.set_ylabel("DNL (LSB)", fontsize=12)
ax1.axhline(0, color='black', linewidth=1, linestyle='--')
ax1.grid(True, linestyle='--', alpha=0.6)

# [하단 그래프] INL (적분 비선형성)
ax2.plot(integer_taps, INL, color='#ef4444', linewidth=1.5, label='INL')
ax2.fill_between(integer_taps, INL, 0, color='#ef4444', alpha=0.3)
ax2.set_title("Before Calibration: INL Analysis", fontsize=14, fontweight='bold')
ax2.set_xlabel("TDC Fine Index (Integer Tap)", fontsize=12)
ax2.set_ylabel("INL (LSB)", fontsize=12)
ax2.axhline(0, color='black', linewidth=1, linestyle='--')
ax2.grid(True, linestyle='--', alpha=0.6)

# 통계 수치 텍스트 박스 출력
dnl_max, dnl_min = np.max(DNL), np.min(DNL)
inl_max, inl_min = np.max(INL), np.min(INL)

stats_text = (f"Max DNL: {dnl_max:.3f} LSB\n"
              f"Min DNL: {dnl_min:.3f} LSB\n"
              f"Max INL: {inl_max:.3f} LSB\n"
              f"Min INL: {inl_min:.3f} LSB")

ax2.text(0.02, 0.05, stats_text, transform=ax2.transAxes, fontsize=11,
         bbox=dict(facecolor='white', edgecolor='black', alpha=0.9, boxstyle='round,pad=0.5'))

plt.tight_layout()

# 이미지 저장 및 출력
png_filepath = os.path.join(script_dir, "dnl_inl_before_calib.png")
plt.savefig(png_filepath, dpi=300)
print(f"✅ DNL/INL 분석 완료 및 이미지 저장: {png_filepath}")

# 콘솔 출력
print("\n📊 [교정 전 하드웨어 선형성(Before Calibration) 결과]")
print(f"▶ 측정된 평균 LSB : {LSB_ps:.3f} ps")
print(f"▶ DNL 범위 : {dnl_min:.3f} ~ {dnl_max:.3f} LSB (P-P: {dnl_max - dnl_min:.3f})")
print(f"▶ INL 범위 : {inl_min:.3f} ~ {inl_max:.3f} LSB (P-P: {inl_max - inl_min:.3f})")
print("==================================================\n")

plt.show()