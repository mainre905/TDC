import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def analyze_tdc_intervals(csv_file_path):
    df = pd.read_csv(csv_file_path)
    
    # 1. Vivado 헤더 필터링 및 Timestamp 추출
    if df.iloc[0].astype(str).str.contains('Radix|Unsigned|Hex', na=False, case=False).any():
        df = df.iloc[1:].reset_index(drop=True)
    
    time_col = [col for col in df.columns if 'timestamp' in col.lower() or 'probe2' in col.lower()][0]
    df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
    df = df.dropna(subset=[time_col]).copy()

    # 2. 펄스 간격(T) 및 주파수(f) 계산
    df['interval_ps'] = df[time_col].diff()
    df = df.dropna(subset=['interval_ps']).copy()
    
    # Wrap-around 보상
    wrap_condition = df['interval_ps'] < 0
    if wrap_condition.any():
        df.loc[wrap_condition, 'interval_ps'] += 2**48

    df['interval_us'] = df['interval_ps'] / 1_000_000.0
    df['frequency_kHz'] = (1.0 / df['interval_us']) * 1000.0

    # 3. 누적 절대 시간(Absolute Time) 계산 (착시 현상 제거)
    df['absolute_time_ms'] = df['interval_us'].cumsum() / 1000.0

    # 4. 시각화 (Subplots)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    
    ax1.plot(df['absolute_time_ms'].values, df['interval_us'].values, marker='.', color='b', markersize=3, alpha=0.7)
    ax1.set_title("STM32 Chirp Signal Analysis (Absolute Time Domain)", fontsize=16)
    ax1.set_ylabel(r"Time Interval ($\mu s$)", fontsize=12, fontweight='bold', color='b')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    ax2.plot(df['absolute_time_ms'].values, df['frequency_kHz'].values, marker='.', color='r', markersize=3, alpha=0.7)
    ax2.set_ylabel("Frequency (kHz)", fontsize=12, fontweight='bold', color='r')
    ax2.set_xlabel("Absolute Time (ms)", fontsize=12, fontweight='bold')
    ax2.grid(True, linestyle='--', alpha=0.6)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    absolute_file_path = os.path.join(script_dir, "line.csv")
    analyze_tdc_intervals(absolute_file_path)