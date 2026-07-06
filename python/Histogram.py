import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# =========================================================================
# 0. Vivado 표기법(예: 32'h000000FF, 32'd511)을 정수형(int)으로 변환하는 함수
# =========================================================================
def clean_vivado_value(val):
    if pd.isna(val):
        return 0
    
    val_str = str(val).strip().lower()
    
    if "'" in val_str:
        parts = val_str.split("'")
        if len(parts) == 2:
            r_val = parts[1]
            if r_val.startswith('h'): # 16진수
                return int(r_val[1:], 16)
            elif r_val.startswith('d'): # 10진수
                return int(r_val[1:], 10)
            elif r_val.startswith('b'): # 2진수
                return int(r_val[1:], 2)
            elif r_val.startswith('o'): # 8진수
                return int(r_val[1:], 8)
            else:
                try:
                    return int(r_val, 10)
                except ValueError:
                    pass

    if val_str.startswith('0x'):
        return int(val_str, 16)
        
    if val_str.startswith('h'):
        try:
            return int(val_str[1:], 16)
        except ValueError:
            pass

    try:
        return int(val_str, 10)
    except ValueError:
        pass

    try:
        return int(float(val_str))
    except ValueError:
        return 0

# =========================================================================
# 1. 경로 설정 및 데이터 로드 (현재 .py 파일이 있는 폴더 기준)
# =========================================================================
# 현재 실행 중인 스크립트 파일(.py)의 절대 경로 폴더를 획득합니다.
current_dir = os.path.dirname(os.path.abspath(__file__))

# 동일 폴더 내에 위치한 CSV 파일 경로 매핑
csv_filename = "histo.csv" 
csv_file_path = os.path.join(current_dir, csv_filename)

CLOCK_PERIOD_PS = 5000.0  # 200MHz

try:
    df = pd.read_csv(csv_file_path, comment='#')
    print(f"[Info] 성공적으로 데이터를 불러왔습니다. 경로: {csv_file_path}")
except FileNotFoundError:
    print(f"[Error] 파일을 찾을 수 없습니다. 경로를 확인하십시오: {csv_file_path}")
    exit()

# 열 이름 부분 일치 검색
try:
    addr_col = [col for col in df.columns if 'probe_read_addr' in col][0]
    data_col = [col for col in df.columns if 'histo_read_data' in col][0]
except IndexError:
    print("[Error] CSV 파일 내에 'probe_read_addr' 또는 'histo_read_data' 열을 식별할 수 없습니다.")
    print("현재 열 목록:", list(df.columns))
    exit()

# =========================================================================
# 2. 데이터 클렌징 및 정렬
# =========================================================================
df[addr_col] = df[addr_col].apply(clean_vivado_value)
df[data_col] = df[data_col].apply(clean_vivado_value)

# 주소 정렬 및 중복 제거
df_sorted = df.sort_values(by=addr_col).drop_duplicates(subset=[addr_col])

raw_taps = df_sorted[addr_col].values
raw_counts = df_sorted[data_col].values

# =========================================================================
# 3. 유효 지연선 영역 검출 (Active Region Detection)
# =========================================================================
MIN_COUNT_THRESHOLD = 20  
active_indices = np.where(raw_counts > MIN_COUNT_THRESHOLD)[0]

if len(active_indices) == 0:
    print("[Error] 임계값 이상 축적된 카운트 데이터가 없습니다. 측정 환경을 확인하십시오.")
    exit()

start_tap = active_indices[0]
end_tap = active_indices[-1]

taps = raw_taps[start_tap:end_tap+1]
counts = raw_counts[start_tap:end_tap+1]

print(f"=== TDC 유효 지연선 검출 결과 ===")
print(f"전체 가용 구간: Tap {raw_taps[0]} ~ Tap {raw_taps[-1]}")
print(f"실제 동작 구간: Tap {start_tap} ~ Tap {end_tap} (총 {len(taps)}개 탭 활성화)")

# =========================================================================
# 4. DNL / INL 및 시간 캘리브레이션 연산
# =========================================================================
avg_count = np.mean(counts)

# DNL (LSB)
dnl = (counts / avg_count) - 1.0

# INL (LSB)
inl = np.cumsum(dnl)

# 실제 지연 시간 변환 (ps)
total_counts = np.sum(counts)
tap_widths_ps = (counts / total_counts) * CLOCK_PERIOD_PS
calibrated_time_ps = np.cumsum(tap_widths_ps)

# =========================================================================
# 5. 시각화 (Matplotlib Subplots)
# =========================================================================
fig, axs = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("TDC Linearity & Calibration Analysis (Ring Osc Mode)", fontsize=16, fontweight='bold')

# [Graph 1] Raw Tap Histogram
axs[0, 0].bar(raw_taps, raw_counts, color='gray', alpha=0.5, label='Inactive Taps')
axs[0, 0].bar(taps, counts, color='blue', alpha=0.8, label='Active Taps')
axs[0, 0].axhline(y=avg_count, color='red', linestyle='--', label=f'Avg Count ({avg_count:.1f})')
axs[0, 0].set_title("1. Raw Tap Histogram")
axs[0, 0].set_xlabel("Tap Index")
axs[0, 0].set_ylabel("Accumulated Hits")
axs[0, 0].legend()
axs[0, 0].grid(True, linestyle=':', alpha=0.6)

# [Graph 2] DNL Plot
axs[0, 1].step(taps, dnl, where='mid', color='darkorange', linewidth=1.5)
axs[0, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.8)
axs[0, 1].set_title("2. Differential Non-Linearity (DNL)")
axs[0, 1].set_xlabel("Tap Index")
axs[0, 1].set_ylabel("DNL (LSB)")
axs[0, 1].grid(True, linestyle=':', alpha=0.6)

# [Graph 3] INL Plot
axs[1, 0].plot(taps, inl, color='crimson', linewidth=1.8)
axs[1, 0].axhline(y=0, color='black', linestyle='-', linewidth=0.8)
axs[1, 0].set_title("3. Integral Non-Linearity (INL)")
axs[1, 0].set_xlabel("Tap Index")
axs[1, 0].set_ylabel("INL (LSB)")
axs[1, 0].grid(True, linestyle=':', alpha=0.6)

# [Graph 4] Calibrated Time (Lookup Table Curve)
axs[1, 1].plot(taps, calibrated_time_ps, color='teal', linewidth=2, label="Calibrated Time Curve")
ideal_line = np.linspace(0, CLOCK_PERIOD_PS, len(taps))
axs[1, 1].plot(taps, ideal_line, color='purple', linestyle=':', label="Ideal Linear Line")
axs[1, 1].set_title("4. Calibrated Time LUT (Transfer Function)")
axs[1, 1].set_xlabel("Tap Index")
axs[1, 1].set_ylabel("Absolute Delay (ps)")
axs[1, 1].legend()
axs[1, 1].grid(True, linestyle=':', alpha=0.6)

plt.tight_layout()

print(f"\n=== 성능 분석 요약 ===")
print(f"Max DNL : {np.max(dnl):.3f} LSB  |  Min DNL : {np.min(dnl):.3f} LSB")
print(f"Max INL : {np.max(inl):.3f} LSB  |  Min INL : {np.min(inl):.3f} LSB")
print(f"평균 단일 탭 지연 해상도(Resolution) : {CLOCK_PERIOD_PS / len(taps):.2f} ps")
print(f"===================================")

plt.show()