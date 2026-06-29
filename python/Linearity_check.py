import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 1. ILA에서 Export한 CSV 파일 로드
df = pd.read_csv('iladata.csv', skiprows=[1])
df.columns = [c.strip().split("[")[0] for c in df.columns]

df['current_loop_cnt'] = pd.to_numeric(df['current_loop_cnt'], errors='coerce')
df['final_timestamp_ps'] = pd.to_numeric(df['final_timestamp_ps'], errors='coerce')
df = df.dropna().reset_index(drop=True)

# 2. (-Absolute Time) % 5000 공식을 통한 Fine 위상 완벽 추출
df['raw_fine_ps'] = (-df['final_timestamp_ps']) % 5000

# ====================================================================
# [버그 수정 완료] 무한 증식 오류를 막기 위해 "원본 데이터" 끼리만 비교!
# ====================================================================
raw_fine = df['raw_fine_ps'].values
unwrapped_fine = np.zeros_like(raw_fine)
unwrapped_fine[0] = raw_fine[0]
offset = 0

for i in range(1, len(raw_fine)):
    # ★ 수정된 부분: 변형된 값이 아니라 무조건 원본(raw_fine)끼리 차이를 구함!
    diff = raw_fine[i] - raw_fine[i-1] 
    
    if diff < -2500:
        offset += 5000
    elif diff > 2500:
        offset -= 5000
        
    # 구해진 offset을 원본 값에 더해서 저장
    unwrapped_fine[i] = raw_fine[i] + offset
# ====================================================================

df['unwrapped_fine_ps'] = unwrapped_fine

# 3. 스파이크가 제거된 후 루프 단위 평균(Mean) 내기
grouped = df.groupby('current_loop_cnt')['unwrapped_fine_ps'].mean().reset_index()

loop_counts = grouped['current_loop_cnt'].values
final_phase_shift = grouped['unwrapped_fine_ps'].values

# 시작점을 0ps로 정규화
final_phase_shift = final_phase_shift - final_phase_shift[0]

# 4. 처리된 완벽한 데이터를 CSV 파일로 저장
grouped['normalized_phase_shift_ps'] = final_phase_shift
csv_output_filename = 'final_processed_phase_shift.csv'
grouped.to_csv(csv_output_filename, index=False)
print(f"✅ 처리가 완료된 데이터가 '{csv_output_filename}' 이름으로 저장되었습니다!")

# 5. 최종 시각화
plt.figure(figsize=(12, 6))
plt.plot(loop_counts, final_phase_shift, 'b.-', markersize=4)
plt.title("Ultimate Fine Phase Shift (Mathematical Bug Fixed!)", fontsize=14, fontweight='bold')
plt.xlabel("MMCM Loop Count", fontsize=12)
plt.ylabel("Accumulated Phase Shift (ps)", fontsize=12)
plt.grid(True, linestyle='--')
plt.tight_layout()
plt.show()