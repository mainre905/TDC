import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def analyze_and_correct_tdc(csv_file_path):
    print(f"[{csv_file_path}] \n데이터 분석 및 Metastability 순차적 보정을 시작합니다...\n")
    
    try:
        df = pd.read_csv(csv_file_path)
    except FileNotFoundError:
        print("❌ 에러: CSV 파일을 찾을 수 없습니다.")
        return

    # ILA 쓰레기 행 필터링
    if df.iloc[0].astype(str).str.contains('Radix|Unsigned|Hex', na=False, case=False).any():
        df = df.iloc[1:].reset_index(drop=True)

    time_col, fine_col = None, None
    for col in df.columns:
        col_lower = col.lower()
        if 'timestamp' in col_lower or 'probe2' in col_lower: time_col = col
        elif 'fine' in col_lower or 'probe3' in col_lower: fine_col = col

    df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
    if fine_col: df[fine_col] = pd.to_numeric(df[fine_col], errors='coerce')
    df = df.dropna(subset=[time_col]).copy()
    df.reset_index(drop=True, inplace=True)

    # Numpy 배열로 변환 (순차적 계산을 위해)
    times = df[time_col].values.astype(float)
    fines = df[fine_col].values if fine_col else np.zeros(len(times))

    # 원본 간격 및 오버플로우 처리
    orig_intervals = np.diff(times)
    MAX_48BIT = 2**48
    orig_intervals[orig_intervals < 0] += MAX_48BIT

    # 기대되는 정상 간격 추정 (Median Filter)
    expected_intervals = pd.Series(orig_intervals).rolling(window=7, center=True, min_periods=1).median().values

    # ★ 핵심: 순차적 보정을 위한 배열
    corrected_times = times.copy()
    correction_count = 0

    # =========================================================
    # ★ 순차적 에러 보정 루프 (에러 밀림 현상 방지)
    # =========================================================
    for i in range(1, len(times)):
        # ★ 이전 펄스가 고쳐졌다면, 그 '고쳐진 시간'을 기준으로 현재 간격을 다시 잼
        current_interval = corrected_times[i] - corrected_times[i-1]
        
        if current_interval < 0:
            current_interval += MAX_48BIT

        error = current_interval - expected_intervals[i-1]

        # 조건 1: -5ns 점프 (Coarse가 덜 카운트됨 -> 5ns 추가)
        if error < -3000 and fines[i] > 200:
            corrected_times[i] += 5000
            correction_count += 1
            
        # 조건 2: +5ns 점프 (Coarse가 더 카운트됨 -> 5ns 감소)
        elif error > 3000 and fines[i] < 50:
            corrected_times[i] -= 5000
            correction_count += 1

    # 최종 결과 정리
    final_intervals = np.diff(corrected_times)
    final_intervals[final_intervals < 0] += MAX_48BIT

    orig_us = orig_intervals / 1_000_000.0
    corr_us = final_intervals / 1_000_000.0

    print(f"총 측정된 펄스 수 : {len(times)} 개")
    print(f"발견 및 보정된 에러: {correction_count} 건\n")

    # =========================================================
    # 시각화 (위: 보정 전, 아래: 보정 후)
    # =========================================================
    # X축 절대 시간 계산
    abs_time_ms_orig = np.cumsum(np.insert(orig_us, 0, 0))[:-1] / 1000.0
    abs_time_ms_corr = np.cumsum(np.insert(corr_us, 0, 0))[:-1] / 1000.0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    
    # [위쪽 그래프] 보정 전 (Before)
    ax1.plot(abs_time_ms_orig, orig_us, marker='.', linestyle='-', color='red', markersize=4, alpha=0.8)
    ax1.set_title("Before Correction (Original TDC Data)", fontsize=16, fontweight='bold')
    ax1.set_ylabel(r"Time Interval ($\mu s$)", fontsize=12, fontweight='bold')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    # [아래쪽 그래프] 보정 후 (After)
    ax2.plot(abs_time_ms_corr, corr_us, marker='.', linestyle='-', color='blue', markersize=4, alpha=0.8)
    ax2.set_title("After Correction (Metastability Fixed)", fontsize=16, fontweight='bold')
    ax2.set_ylabel(r"Time Interval ($\mu s$)", fontsize=12, fontweight='bold')
    ax2.set_xlabel("Absolute Time (ms)", fontsize=12, fontweight='bold')
    ax2.grid(True, linestyle='--', alpha=0.6)
    
    # Y축 스케일을 동일하게 맞춰서 시각적 차이를 극대화함
    y_min = min(orig_us.min(), corr_us.min()) - 0.005
    y_max = max(orig_us.max(), corr_us.max()) + 0.005
    ax1.set_ylim(y_min, y_max)
    ax2.set_ylim(y_min, y_max)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_filename = "line.csv"  # 👈 분석할 CSV 파일 이름
    absolute_file_path = os.path.join(script_dir, target_filename)
    
    analyze_and_correct_tdc(absolute_file_path)