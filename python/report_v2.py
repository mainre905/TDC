import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 1. 데이터 로드 (이전과 동일)
csv_file = "histo.csv"
try:
    df = pd.read_csv(csv_file, skiprows=[1])
    df.columns = df.columns.str.strip()
    df_active = df[df['readout_active'].astype(str).str.contains('1')]
    df_clean = df_active.drop_duplicates(subset=['probe_read_addr[8:0]']).sort_values(by='probe_read_addr[8:0]')
    df_plot = df_clean[(df_clean['probe_read_addr[8:0]'] >= 0) & (df_clean['probe_read_addr[8:0]'] < 320)]
except Exception as e:
    print(f"데이터 로드 실패: {e}")
    exit()

tap_index = df_plot['probe_read_addr[8:0]'].astype(int).values
hit_counts = df_plot['histo_read_data[31:0]'].astype(float).values

# 2. 유효 구간 설정 (값이 0으로 떨어지기 전까지만 계산)
# 마지막 활성 탭 찾기 (예: 카운트가 최대 카운트의 10% 이상인 마지막 탭)
threshold = np.max(hit_counts) * 0.1
last_active_tap = np.where(hit_counts > threshold)[0][-1]
total_hits = np.sum(hit_counts[:last_active_tap + 1])

print(f"유효 탭 범위: 0 ~ {last_active_tap}")
print(f"총 유효 Hit 수: {total_hits}")

# 3. 누적 분포(CDF)를 이용한 절대 시간(Picosecond) 계산
# 기준 클럭 주기 = 200MHz -> 5000ps
CLOCK_PERIOD_PS = 5000.0

time_ps_array = np.zeros(320)
cumulative_hits = 0

for i in range(320):
    if i <= last_active_tap:
        # 현재 탭 시간 = 이전 누적합 + (현재 탭 카운트의 절반)
        # 탭의 중앙을 그 탭의 대표 시간으로 산정함
        hits_for_calc = cumulative_hits + (hit_counts[i] / 2.0)
        time_ps_array[i] = (hits_for_calc / total_hits) * CLOCK_PERIOD_PS
        cumulative_hits += hit_counts[i]
    else:
        # 신호가 도달하지 않는 탭은 최대 시간(5000ps)으로 고정
        time_ps_array[i] = CLOCK_PERIOD_PS

# 4. COE 파일 생성
coe_filename = "calib_rom.coe"
with open(coe_filename, "w") as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    for i in range(512): # ROM 크기에 맞게 512 깊이로 맞춤 (안 쓰는 공간은 0)
        if i < 320:
            val = int(round(time_ps_array[i]))
        else:
            val = 0
        if i == 511:
            f.write(f"{val};\n")
        else:
            f.write(f"{val},\n")
print(f"완료: '{coe_filename}' 파일이 생성되었습니다!")

# 5. 그래프 출력 (적분의 마법 확인)
plt.figure(figsize=(10, 6))
plt.plot(tap_index[:last_active_tap], time_ps_array[:last_active_tap], color='green', linewidth=2, label='Calibrated Time Curve')
plt.plot(tap_index[:last_active_tap], tap_index[:last_active_tap] * (CLOCK_PERIOD_PS/last_active_tap), color='gray', linestyle='--', label='Ideal Linear Time')
plt.title('TDC Calibration Curve (CDF Integration)', fontsize=16)
plt.xlabel('Tap Index (Raw output from TDC)', fontsize=12)
plt.ylabel('Absolute Time (Picoseconds)', fontsize=12)
plt.legend()
plt.grid(True, linestyle='--', alpha=0.7)
plt.show()