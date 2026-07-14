import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 1. 파일 경로 설정 (요청하신 코드 완벽 반영)
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "iladata.csv")  # 저장하신 파일명과 일치시켜주세요

print(f"Loading data from: {csv_filepath}")

# 2. CSV 파일 불러오기 
# Vivado ILA CSV의 두 번째 줄(Radix 선언부)은 데이터가 아니므로 건너뜁니다 (skiprows=[1])
df = pd.read_csv(csv_filepath, skiprows=[1])

# 3. 데이터 필터링 (완벽하게 탭 데이터만 뽑아내기)
# CSV 구조 기준: 3번째 열=readout_active, 4번째 열=probe_read_addr, 5번째 열=histo_read_data (0-indexed)
# 에러 방지를 위해 강제로 정수형(int)으로 변환 후 비교합니다.
active_mask = df.iloc[:, 3].astype(int) == 1
df_active = df[active_mask].copy()

# 혹시 ILA 클럭 타이밍상 같은 주소가 두 번 찍혔을 경우를 대비해 중복 제거
df_active = df_active.drop_duplicates(subset=df.columns[4])

# 주소(Tap Index) 순서대로 정렬
df_active = df_active.sort_values(by=df.columns[4])

# X축(Tap 번호)과 Y축(카운트 값) 추출
tap_indices = df_active.iloc[:, 4].astype(int).values
counts = df_active.iloc[:, 5].astype(int).values

print(f"총 {len(tap_indices)}개의 Tap 데이터를 성공적으로 추출했습니다!")
print(f"전체 누적 Hit 카운트: {np.sum(counts)} 개")

# 4. 히스토그램 그리기 (막대 그래프)
plt.figure(figsize=(14, 6))

# 바 차트를 사용하여 탭별 카운트를 시각적으로 명확하게 표현
plt.bar(tap_indices, counts, width=1.0, color='royalblue', edgecolor='black', linewidth=0.5, alpha=0.8)

# 그래프 꾸미기
plt.title('FPGA TDC Tap Histogram (Code Density Test)', fontsize=16, fontweight='bold')
plt.xlabel('Tap Index (0 to 319)', fontsize=12)
plt.ylabel('Hit Counts', fontsize=12)
plt.xlim(-5, 325)  # 좌우 여백 살짝 확보

# 평균 카운트 선 긋기 (논문에서 Reference Line으로 활용하기 좋음)
average_count = np.mean(counts)
plt.axhline(y=average_count, color='red', linestyle='--', linewidth=2, label=f'Average ({average_count:.1f})')
plt.legend()

plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()

# 화면에 출력
plt.show()