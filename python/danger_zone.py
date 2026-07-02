import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def find_danger_zone(csv_file_path):
    print(f"[{csv_file_path}] \nMetastability 위험 구간(Danger Zone) 탐색을 시작합니다...\n")
    
    try:
        df = pd.read_csv(csv_file_path)
    except FileNotFoundError:
        print("❌ 에러: CSV 파일을 찾을 수 없습니다.")
        return

    if df.iloc[0].astype(str).str.contains('Radix|Unsigned|Hex', na=False, case=False).any():
        df = df.iloc[1:].reset_index(drop=True)

    time_col, fine_col = None, None
    for col in df.columns:
        col_lower = col.lower()
        if 'timestamp' in col_lower or 'probe2' in col_lower: time_col = col
        elif 'fine' in col_lower or 'probe3' in col_lower: fine_col = col

    df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
    df[fine_col] = pd.to_numeric(df[fine_col], errors='coerce')
    df = df.dropna(subset=[time_col]).copy()
    df.reset_index(drop=True, inplace=True)

    # 간격 및 에러 계산
    df['interval_ps'] = df[time_col].diff()
    df.loc[df['interval_ps'] < 0, 'interval_ps'] += (2**48)
    
    df['expected_interval_ps'] = df['interval_ps'].rolling(window=7, center=True, min_periods=1).median()
    df['interval_error'] = df['interval_ps'] - df['expected_interval_ps']

    # 5ns 에러가 발생한 데이터만 추출 (오차 3000ps 이상)
    error_df = df[df['interval_error'].abs() > 3000].copy()

    if len(error_df) == 0:
        print("✅ 5ns 에러가 발견되지 않았습니다. (데이터가 너무 적거나 이미 보정된 데이터입니다.)")
        return

    # 에러가 발생한 Fine_idx 값들
    error_fines = error_df[fine_col].values
    
    # 초반부(0 근처) 에러와 후반부(최대 탭 근처) 에러 분리
    # 통상적으로 320탭 기준, 160을 기준으로 나눔
    early_errors = error_fines[error_fines < 160]
    late_errors = error_fines[error_fines >= 160]

    print("=====================================================")
    print("             🚨 Metastability Danger Zone 분석            ")
    print("=====================================================")
    print(f"발견된 총 에러 수 : {len(error_df)} 건\n")
    
    threshold_low = 0
    threshold_high = 320

    if len(early_errors) > 0:
        max_early = int(early_errors.max())
        threshold_low = max_early + 10 # 안전 마진 +10
        print(f"▶ 초반부 에러 발생 구역 : Tap 0 ~ {max_early}")
        print(f"  👉 추천 하한 Threshold : {threshold_low}")
    else:
        print("▶ 초반부 에러 없음")

    if len(late_errors) > 0:
        min_late = int(late_errors.min())
        threshold_high = min_late - 10 # 안전 마진 -10
        print(f"\n▶ 후반부 에러 발생 구역 : Tap {min_late} ~ MAX")
        print(f"  👉 추천 상한 Threshold : {threshold_high}")
    else:
        print("\n▶ 후반부 에러 없음")
    
    print("=====================================================")
    print("\n💡 [Verilog 코드 적용 가이드]")
    print(f"if (ts_fine_idx < 9'd{threshold_low} || ts_fine_idx > 9'd{threshold_high}) begin")
    print("    ts_coarse <= captured_c180_stg3 + 1'b1; // Danger Zone")
    print("end else begin")
    print("    ts_coarse <= captured_c0_stg3;          // Safe Zone")
    print("end\n")

    # 시각화 (Error vs Fine_idx 산점도)
    plt.figure(figsize=(10, 6))
    plt.scatter(df[fine_col], df['interval_error'], alpha=0.3, color='blue', label='Normal (No Error)')
    plt.scatter(error_df[fine_col], error_df['interval_error'], color='red', marker='x', s=100, label='5ns Boundary Error')
    
    # 추천 Threshold 선 긋기
    plt.axvline(x=threshold_low, color='green', linestyle='--', linewidth=2, label=f'Rec. Threshold ({threshold_low})')
    plt.axvline(x=threshold_high, color='green', linestyle='--', linewidth=2, label=f'Rec. Threshold ({threshold_high})')

    plt.title("Metastability Error Distribution by Tap Index", fontsize=16, fontweight='bold')
    plt.xlabel("Tap Index (Fine_idx)", fontsize=12, fontweight='bold')
    plt.ylabel("Interval Error (ps)", fontsize=12, fontweight='bold')
    plt.axhline(y=0, color='black', linewidth=1)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_filename = "line.csv"  # 👈 단일 카운터(에러 발생) 상태로 뽑은 CSV 파일
    absolute_file_path = os.path.join(script_dir, target_filename)
    
    find_danger_zone(absolute_file_path)