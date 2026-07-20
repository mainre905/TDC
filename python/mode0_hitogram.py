import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ==========================================
# 1. 파일 경로 설정 및 데이터 로드
# ==========================================
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "histo.csv")

print(f"히스토그램 데이터 로드 중... 경로: {csv_filepath}")
# ILA에서 내보낸 CSV의 두 번째 줄(UNSIGNED) 무시
df = pd.read_csv(csv_filepath, skiprows=[1])

# 컬럼명 (Vivado Export 이름에 맞게 수정 필요)
# probe1 = Tap 번호 (0~319), probe2 = 누적 카운트
col_tap = 'probe1[8:0]'      
col_count = 'probe2[31:0]'   

tap_idx = df[col_tap].astype(int).values
counts = df[col_count].astype(float).astype(int).values

# ==========================================
# 2. 통계 기반 캘리브레이션 연산 (Code Density)
# ==========================================
TOTAL_TIME_PS = 5000.0  # 1 클럭 주기 (200MHz)
TOTAL_HITS = np.sum(counts)

print(f" - 분석된 총 탭 수: {len(counts)} Taps")
print(f" - 누적된 총 Hit 수: {TOTAL_HITS:,} Hits")

# 1) 각 탭의 실제 물리적 길이 (Bin Width) 계산
# 원리: 히트가 많이 쌓인 탭일수록 물리적 길이가 길다.
actual_tap_width_ps = TOTAL_TIME_PS * (counts / float(TOTAL_HITS))

# 2) 진짜 DNL (Differential Non-Linearity) 계산
ideal_tap_width_ps = TOTAL_TIME_PS / len(counts)
dnl_ps = actual_tap_width_ps - ideal_tap_width_ps

# 3) 보정된 절대 시간 (Absolute Time / Calibrated INL) 계산
# 원리: 이전 탭들의 길이를 모두 누적 더함 + 자기 자신 길이의 절반
absolute_time_ps = np.zeros(len(counts))
cumulative_time = 0.0

for i in range(len(counts)):
    absolute_time_ps[i] = cumulative_time + (actual_tap_width_ps[i] / 2.0)
    cumulative_time += actual_tap_width_ps[i]

# ==========================================
# 3. 보정용 COE 파일 자동 생성
# ==========================================
coe_filepath = os.path.join(script_dir, "calibrated_rom.coe")

# ROM 512번지를 꽉 채우기 위해 빈 공간은 0으로 패딩하거나 선형 증가시킴
with open(coe_filepath, "w") as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    
    for i in range(512):
        if i < len(counts):
            val = int(round(absolute_time_ps[i]))
        else:
            # 320번 탭 이후 (사용 안함)는 그냥 선형적으로 증가하는 더미 값
            val = int(round(cumulative_time + (i - len(counts)) * ideal_tap_width_ps))
            
        if i == 511:
            f.write(f"{val};\n")
        else:
            f.write(f"{val},\n")

print(f"\n✅ 캘리브레이션 완료! [{coe_filepath}] 파일이 생성되었습니다.")
print("이 파일을 Vivado ROM IP에 넣고 재합성 하세요.")

# ==========================================
# 4. 분석 결과 그래프 (진짜 DNL / INL)
# ==========================================
plt.figure(figsize=(12, 8))

# 진짜 DNL 그래프 (물리적 탭 불균일성)
plt.subplot(2, 1, 1)
plt.plot(tap_idx, dnl_ps, 'b-', alpha=0.7)
plt.fill_between(tap_idx, dnl_ps, 0, color='blue', alpha=0.3)
plt.axhline(0, color='r', linestyle='--')
plt.title('True DNL (Differential Non-Linearity) from Histogram')
plt.ylabel('DNL Error (ps)')
plt.grid(True)

# 탭 폭에 따른 절대 시간 곡선 (COE 파일에 들어갈 내용)
plt.subplot(2, 1, 2)
plt.plot(tap_idx, absolute_time_ps, 'g.-')
plt.title('Calibrated Absolute Time Transfer Curve (COE Data)')
plt.xlabel('TDC Tap Index (0 ~ 319)')
plt.ylabel('Absolute Time (ps)')
plt.grid(True)

plt.tight_layout()
plt.show()