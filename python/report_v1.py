import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
# ==========================================
# 1. 파일 설정 및 데이터 로드
# ==========================================

current_dir = os.path.dirname(os.path.abspath(__file__))
csv_filename = "histo.csv" 
csv_file_path = os.path.join(current_dir, csv_filename)

try:
    df = pd.read_csv(csv_file_path, skiprows=[1])
    df.columns = df.columns.str.strip()
except FileNotFoundError:
    print(f"Error: '{csv_file}' 파일을 찾을 수 없습니다.")
    exit()

col_readout = 'readout_active'
col_addr    = 'probe_read_addr[8:0]'
col_data    = 'histo_read_data[31:0]'

# 데이터 필터링 (0~319 탭 추출)
df_active = df[df[col_readout].astype(str).str.contains('1')]
df_clean = df_active.drop_duplicates(subset=[col_addr]).sort_values(by=col_addr)
df_plot = df_clean[(df_clean[col_addr] >= 0) & (df_clean[col_addr] < 320)].copy()

tap_index = df_plot[col_addr].astype(int).values
hit_counts = df_plot[col_data].astype(float).values

if len(tap_index) == 0:
    print("Error: 추출된 데이터가 없습니다. CSV 파일 포맷을 확인하세요.")
    exit()

# ==========================================
# 2. 유효 구간(Active Region) 자동 필터링
# ==========================================
# 최대 Hit Count의 10% 이상인 탭들만 '유효한 측정 탭'으로 간주합니다.
# 이렇게 하면 항상 0인 Tap 0과 끝부분 절벽 구간이 자동으로 제외됩니다.
threshold = np.max(hit_counts) * 0.1
valid_mask = hit_counts > threshold
valid_indices = np.where(valid_mask)[0]

# 유효 구간의 시작과 끝 탭 번호 획득
first_valid = valid_indices[0]
last_valid = valid_indices[-1]

# 통계 계산용 배열 분리
tap_index_active = tap_index[first_valid:last_valid+1]
hit_counts_active = hit_counts[first_valid:last_valid+1]

# ==========================================
# 3. 통계 및 DNL 계산 (유효 구간 내에서만)
# ==========================================
mean_count = np.mean(hit_counts_active)

# 실제 활성화된 탭들만 가지고 DNL 계산
dnl_active = (hit_counts_active - mean_count) / mean_count

print("=== TDC 통계 요약 (유효 구간 기준) ===")
print(f"전체 측정 탭 범위 : 0 ~ 319")
print(f"유효 데이터 탭 범위 : {tap_index[first_valid]} ~ {tap_index[last_valid]} (총 {len(tap_index_active)}개 탭)")
print(f"평균 Hit Count : {mean_count:.1f}")
print(f"최대 Hit Count : {np.max(hit_counts_active):.0f} (Tap {tap_index_active[np.argmax(hit_counts_active)]})")
print(f"최소 Hit Count : {np.min(hit_counts_active):.0f} (Tap {tap_index_active[np.argmin(hit_counts_active)]})")
print(f"Max DNL        : {np.max(dnl_active):.3f} LSB")
print(f"Min DNL        : {np.min(dnl_active):.3f} LSB")

# ==========================================
# 4. 그래프 처리를 위한 빈 배열 생성 (NaN 처리)
# ==========================================
# 그래프의 X축은 0~319를 유지하되, 제외된 탭들은 그래프에 그려지지 않도록 NaN(Not a Number) 처리
dnl_full = np.full(len(tap_index), np.nan)
dnl_full[first_valid:last_valid+1] = dnl_active

# ==========================================
# 5. 그래프 그리기 (2개의 서브플롯)
# ==========================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

# --- [Plot 1] 원본 히스토그램 ---
ax1.bar(tap_index, hit_counts, width=1.0, color='royalblue', edgecolor='black', linewidth=0.5)
ax1.axhline(mean_count, color='red', linestyle='--', linewidth=2, label=f'Active Mean: {mean_count:.0f}')
ax1.axvspan(-1, first_valid-0.5, color='gray', alpha=0.2, label='Inactive Region (Tap 0)')
ax1.axvspan(last_valid+0.5, 320, color='gray', alpha=0.2, label='Inactive Region (Out of Range)')

ax1.set_title('TDC Tap Histogram (Code Density Test)', fontsize=16, fontweight='bold')
ax1.set_ylabel('Hit Count (Accumulated)', fontsize=12)
ax1.legend(loc='upper right')
ax1.grid(True, axis='y', linestyle='--', alpha=0.7)

# --- [Plot 2] DNL (Differential Non-Linearity) ---
# NaN 값이 들어간 부분은 Matplotlib이 자동으로 무시하고 그리지 않습니다.
ax2.plot(tap_index, dnl_full, marker='o', markersize=3, linestyle='-', color='darkorange', linewidth=1)
ax2.axhline(0, color='black', linestyle='-', linewidth=1)
ax2.axvspan(-1, first_valid-0.5, color='gray', alpha=0.2)
ax2.axvspan(last_valid+0.5, 320, color='gray', alpha=0.2)

ax2.set_title('Differential Non-Linearity (DNL)', fontsize=14)
ax2.set_xlabel('Tap Index (0 ~ 319)', fontsize=12)
ax2.set_ylabel('DNL [LSB]', fontsize=12)
ax2.set_xlim(0, 319)

# 유효 DNL의 최대/최소값을 기준으로 Y축 범위 설정
max_dnl_abs = max(abs(np.min(dnl_active)), abs(np.max(dnl_active)))
# 만약 DNL이 너무 완벽해서 값이 작다면 최소 범위를 잡아줌
ylim_margin = max(max_dnl_abs * 1.5, 0.1) 
ax2.set_ylim(-ylim_margin, ylim_margin)

ax2.grid(True, linestyle='--', alpha=0.7)

plt.tight_layout()
plt.show()