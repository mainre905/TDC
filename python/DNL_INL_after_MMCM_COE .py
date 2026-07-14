import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import linregress

# =========================================================================
# 1. 스티칭 완료된 파일 로드 (post_stitch_data.csv)
# =========================================================================
script_dir = os.path.dirname(os.path.abspath(__file__))
# ★ 스티칭 코드가 만들어낸 최종 결과물 파일
csv_filepath = os.path.join(script_dir, "post_stitch_data.csv") 

try:
    df = pd.read_csv(csv_filepath)
except FileNotFoundError:
    print(f"❌ '{csv_filepath}' 파일이 없습니다. 스티칭 코드를 먼저 돌려주세요.")
    exit()

# 컬럼명 매칭 (스티칭 코드의 출력 포맷)
loops = df['loop_cnt'].values
times_measured = df['val_avg'].values

# =========================================================================
# ★ 추가할 핵심 로직: 수백억 단위 Coarse 시간 제거 및 순수 위상 복원
# =========================================================================
CLOCK_PERIOD_PS = 5000.0

# 1. 인접 스텝 간의 원시 차이 계산 (수백억 단위 포함)
raw_diffs = np.diff(times_measured)

# 2. 5000ps 단위의 Coarse 쓰레기값 제거 (순수 위상 변화량만 추출)
# +2500 % 5000 - 2500 을 하면 -2500ps ~ +2500ps 사이의 순수 변화량만 남음
phase_steps = (raw_diffs + CLOCK_PERIOD_PS/2) % CLOCK_PERIOD_PS - CLOCK_PERIOD_PS/2

# (선택) MMCM 스윕 방향에 따라 값이 음수(-17.8ps)로 나올 수 있으므로, 
# 직관적인 분석을 위해 양수(우상향)로 강제 뒤집기
if np.mean(phase_steps) < 0:
    phase_steps = -phase_steps

# 3. 순수 변화량을 누적합(cumsum)하여 완벽하게 연속적인 절대 시간 복원
times_clean = np.concatenate(([0], np.cumsum(phase_steps)))

# 이후 연산에서는 times_measured 대신 times_clean을 사용합니다!
times_measured = times_clean
# =========================================================================

# =========================================================================
# 2. LSB (1스텝 평균 지연 시간) 도출
# =========================================================================
# 스티칭된 연속적인 루프 카운트와 측정 시간의 선형 회귀를 통해 
# 시스템의 실제 평균 1스텝 시간(LSB)을 매우 정밀하게 구합니다.
slope, intercept, _, _, _ = linregress(loops, times_measured)
LSB_avg = slope

# =========================================================================
# 3. DNL / INL 계산 (논문 표준 공식)
# =========================================================================
# 1) INL 계산 (단위: LSB)
# (내가 측정한 보정 시간 - 선형 회귀로 구한 이상적인 직선 시간) / LSB
ideal_times = slope * loops + intercept
INL = (times_measured - ideal_times) / LSB_avg

# INL 그래프를 0점 기준으로 중앙 정렬
INL = INL - np.mean(INL)

# 2) DNL 계산 (단위: LSB)
# (현재 스텝의 증가 폭 - 평균 1스텝의 폭) / LSB
step_widths = np.diff(times_measured)
DNL = (step_widths - LSB_avg) / LSB_avg
dnl_loops = loops[:-1]

# =========================================================================
# 4. 논문용 시각화
# =========================================================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

# [상단] DNL
ax1.plot(dnl_loops, DNL, color='#10b981', linewidth=1.5, alpha=0.9, marker='.')
ax1.fill_between(dnl_loops, DNL, 0, color='#10b981', alpha=0.3)
ax1.set_title(f"[After Calibration] DNL Analysis (LSB = {LSB_avg:.3f} ps)", fontsize=14, fontweight='bold')
ax1.set_ylabel("DNL (LSB)", fontsize=12)
ax1.axhline(0, color='black', linestyle='--', linewidth=1)
ax1.grid(True, linestyle='--', alpha=0.6)

# [하단] INL
ax2.plot(loops, INL, color='#f59e0b', linewidth=1.5, marker='.')
ax2.fill_between(loops, INL, 0, color='#f59e0b', alpha=0.3)
ax2.set_title("[After Calibration] INL Analysis", fontsize=14, fontweight='bold')
ax2.set_xlabel("Processed Virtual Phase Step (loop_cnt)", fontsize=12)
ax2.set_ylabel("INL (LSB)", fontsize=12)
ax2.axhline(0, color='black', linestyle='--', linewidth=1)
ax2.grid(True, linestyle='--', alpha=0.6)

dnl_max, dnl_min = np.max(DNL), np.min(DNL)
inl_max, inl_min = np.max(INL), np.min(INL)

stats_text = (f"Max DNL: {dnl_max:.3f} LSB\n"
              f"Min DNL: {dnl_min:.3f} LSB\n"
              f"Max INL: {inl_max:.3f} LSB\n"
              f"Min INL: {inl_min:.3f} LSB")
ax2.text(0.02, 0.05, stats_text, transform=ax2.transAxes, fontsize=11,
         bbox=dict(facecolor='white', edgecolor='black', alpha=0.9, boxstyle='round,pad=0.5'))

plt.tight_layout()
plt.savefig(os.path.join(script_dir, "After_DNL_INL_Final.png"))
plt.show()

# =========================================================================
# 5. 콘솔 출력
# =========================================================================
print(f"\n📊 [교정 후(After Calibration) 하드웨어 성능 최종 결과]")
print(f"▶ 분석된 데이터 샘플 수: {len(loops)} 스텝 (Stitched Data)")
print(f"▶ 산출된 시스템 LSB: {LSB_avg:.3f} ps")
print(f"▶ DNL 범위 : {dnl_min:.3f} ~ {dnl_max:.3f} LSB (P-P: {dnl_max - dnl_min:.3f})")
print(f"▶ INL 범위 : {inl_min:.3f} ~ {inl_max:.3f} LSB (P-P: {inl_max - inl_min:.3f})")
print("==================================================\n")