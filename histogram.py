import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

print("1. 데이터 로딩 중...")
df = pd.read_csv('iladata.csv', skiprows=[1], dtype=str)

cnt_col = [col for col in df.columns if 'current_loop_cnt' in col][0]
idx_col = [col for col in df.columns if 'ts_fine_idx' in col][0]
valid_col = [col for col in df.columns if 'Sample in Buffer' in col][0]

df['loop_cnt'] = df[cnt_col].apply(lambda x: int(str(x).strip(), 16) if pd.notnull(x) else np.nan)
df['fine_idx'] = df[idx_col].apply(lambda x: int(str(x).strip(), 10) if pd.notnull(x) else np.nan)
df['sample_idx'] = df[valid_col].apply(lambda x: int(str(x).strip(), 10) if pd.notnull(x) else np.nan)

df_clean = df[df['sample_idx'] >= 15].dropna()

print("2. 같은 COUNT에 대한 TAP의 평균 계산 중...")
grouped = df_clean.groupby('loop_cnt')['fine_idx'].mean().reset_index()
grouped['time_ps'] = grouped['loop_cnt'] * 17.85

print("3. TAP을 기준으로 오름차순 정렬 중...")
df_sorted = grouped.sort_values(by='fine_idx').reset_index(drop=True)

print("4. 그래프 그리기 (COUNT 텍스트 표시)...")
plt.figure(figsize=(18, 10))  # 텍스트가 겹치지 않도록 넓게 설정

# 정렬된 데이터를 선과 점으로 그리기
plt.plot(df_sorted['fine_idx'], df_sorted['time_ps'], marker='o', linestyle='-', color='blue', markersize=4)

# ★ 요구사항: 점 옆에 COUNT 값 표시 ★
for i in range(len(df_sorted)):
    tap = df_sorted['fine_idx'].iloc[i]
    time = df_sorted['time_ps'].iloc[i]
    count = df_sorted['loop_cnt'].iloc[i]
    
    # 점 바로 옆에 빨간색으로 COUNT 값 출력
    plt.text(tap, time, f" {int(count)}", fontsize=8, color='red', alpha=0.8)

plt.title("Raw Data: Sorted by TAP with COUNT Labels")
plt.xlabel("TDC Fine Index (Tap) - Sorted Ascending")
plt.ylabel("Absolute Time (ps) = COUNT * 17.85")
plt.grid(True)
plt.tight_layout()
plt.savefig("sorted_count_raw.png")
print("✅ 완료! 어떠한 조작도 없는 'sorted_count_raw.png'가 생성되었습니다.")