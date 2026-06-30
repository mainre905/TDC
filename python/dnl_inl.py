import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

# ==========================================
# 1. 데이터 로드 및 필터링
# ==========================================
# 1. 현재 실행 중인 파이썬 스크립트 파일(.py)이 있는 폴더의 절대 경로를 가져옵니다.
script_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 그 폴더 경로와 'iladata.csv' 파일 이름을 합쳐서 정확한 전체 경로를 만듭니다.
csv_filepath = os.path.join(script_dir, 'iladata_ring.csv')

df = pd.read_csv(csv_filepath, skiprows=[1])
df.columns = df.columns.str.strip()

valid_col = [col for col in df.columns if 'final_ts_valid' in col][0]
fine_idx_col = [col for col in df.columns if 'aligned_fine_idx' in col][0]

df[valid_col] = pd.to_numeric(df[valid_col], errors='coerce')
valid_hits = df[df[valid_col] == 1].copy()

total_hits = len(valid_hits)
print(f"분석에 사용된 유효 Hit 수: {total_hits} 개")

# Raw 탭 데이터 (0 ~ max_tap)
raw_taps = valid_hits[fine_idx_col].values
max_tap = int(np.max(raw_taps))
print(f"활성화된 최대 탭 번호: {max_tap}")

# ==========================================
# 2. DNL / INL 계산 (Code Density Test)
# ==========================================
T_clk_ps = 5000.0  # 시스템 클럭 주기 (200MHz = 5000ps)

# 1. 히스토그램 (각 탭별 Hit 빈도수 계산)
# 탭 번호는 0부터 max_tap까지 존재함
hit_counts, _ = np.histogram(raw_taps, bins=max_tap+1, range=(0, max_tap+1))

# 2. 각 탭의 실제 딜레이 시간 (Width) 계산
# Width = (해당 탭 Hit 수 / 전체 Hit 수) * T_clk
tap_widths = (hit_counts / total_hits) * T_clk_ps

# 3. 이상적인 LSB (평균 탭 딜레이) 계산
# 유효한(Hit가 1개라도 있는) 탭들의 개수를 기준으로 평균을 구함
active_taps_count = np.count_nonzero(hit_counts)
lsb_ps = T_clk_ps / active_taps_count
print(f"이상적인 평균 LSB: {lsb_ps:.2f} ps")

# 4. DNL 계산 (단위: LSB)
# DNL = (실제 Width - LSB) / LSB
dnl = (tap_widths - lsb_ps) / lsb_ps

# 5. INL 계산 (단위: LSB)
# INL = DNL의 누적합 (Cumulative Sum)
inl = np.cumsum(dnl)

# 통계 출력
print("-" * 40)
print(f"DNL Max: {np.max(dnl):.2f} LSB, Min: {np.min(dnl):.2f} LSB")
print(f"INL Max: {np.max(inl):.2f} LSB, Min: {np.min(inl):.2f} LSB")
print("-" * 40)

# ==========================================
# 3. DNL / INL 그래프 시각화
# ==========================================
plt.style.use('default')
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

# 탭 번호 배열 (X축)
taps = np.arange(max_tap + 1)

# --- [그래프 1] DNL ---
ax1.plot(taps, dnl, color='royalblue', linewidth=1.2, alpha=0.9)
ax1.axhline(0, color='black', linestyle='-', linewidth=1)
ax1.axhline(1, color='red', linestyle='--', linewidth=1, alpha=0.5)
ax1.axhline(-1, color='red', linestyle='--', linewidth=1, alpha=0.5)
ax1.set_title(f'Differential Non-Linearity (DNL) [LSB = {lsb_ps:.2f} ps]', fontsize=14)
ax1.set_ylabel('DNL (LSB)', fontsize=12)
ax1.grid(True, linestyle='--', alpha=0.6)
ax1.set_xlim(0, max_tap)

# --- [그래프 2] INL ---
ax2.plot(taps, inl, color='crimson', linewidth=1.5, alpha=0.9)
ax2.axhline(0, color='black', linestyle='-', linewidth=1)
ax2.set_title('Integral Non-Linearity (INL)', fontsize=14)
ax2.set_xlabel('Tap Index', fontsize=12)
ax2.set_ylabel('INL (LSB)', fontsize=12)
ax2.grid(True, linestyle='--', alpha=0.6)

plt.tight_layout()
plt.savefig('tdc_dnl_inl_plot.png', dpi=150)
plt.show()