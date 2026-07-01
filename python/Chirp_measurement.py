import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def analyze_tdc_intervals(csv_file_path):
    print(f"[{csv_file_path}] \n위 경로의 파일 분석을 시작합니다...\n")
    
    # 1. CSV 데이터 로드
    try:
        df = pd.read_csv(csv_file_path)
    except FileNotFoundError:
        print("❌ 에러: CSV 파일을 찾을 수 없습니다.")
        print("이 파이썬 스크립트(.py)와 동일한 폴더에 CSV 파일이 있는지 확인해주세요.")
        return

    # 2. Vivado ILA 특유의 쓰레기 데이터(Radix 행) 필터링
    if df.iloc[0].astype(str).str.contains('Radix|Unsigned|Hex', na=False, case=False).any():
        df = df.iloc[1:].reset_index(drop=True)

    # 3. 절대 시간(Timestamp) 컬럼 자동 탐색
    time_col = None
    for col in df.columns:
        if 'timestamp' in col.lower() or 'probe2' in col.lower():
            time_col = col
            break

    if time_col is None:
        print("❌ 에러: CSV 파일에서 Timestamp 컬럼을 찾을 수 없습니다.")
        return

    # 4. 데이터 전처리 (Unsigned Int 정수형으로 변환)
    df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
    df = df.dropna(subset=[time_col]).copy() 

    # =========================================================
    # ★ 핵심 로직 1: 펄스 간 간격(Interval = 주기 T) 계산
    # =========================================================
    df['interval_ps'] = df[time_col].diff()
    df = df.dropna(subset=['interval_ps']).copy()

    # Wrap-around(오버플로우) 보상
    wrap_condition = df['interval_ps'] < 0
    if wrap_condition.any():
        MAX_48BIT = 2**48
        df.loc[wrap_condition, 'interval_ps'] += MAX_48BIT

    df['interval_us'] = df['interval_ps'] / 1_000_000.0

    # =========================================================
    # ★ 핵심 로직 2: 주파수(Frequency = 1/T) 계산
    # =========================================================
    df['frequency_kHz'] = (1.0 / df['interval_us']) * 1000.0

    # 통계 분석 결과 출력
    mean_us = df['interval_us'].mean()
    print("=====================================================")
    print("                 📊 측정 통계 결과                   ")
    print("=====================================================")
    print(f"총 측정된 펄스 수 : {len(df)} 개")
    print(f"평균 펄스 간격    : {mean_us:.4f} us")
    print(f"최소 주파수       : {df['frequency_kHz'].min():.2f} kHz")
    print(f"최대 주파수       : {df['frequency_kHz'].max():.2f} kHz")
    print("=====================================================\n")

    # =========================================================
    # ★ 7. Chirp 신호 시각화 (X축을 절대 시간으로 변경!) ★
    # =========================================================
    # 각 펄스 간격(us)을 누적해서 더하면, 측정 시작점부터 흘러간 절대 시간(us)이 됩니다.
    df['absolute_time_us'] = df['interval_us'].cumsum()

    # 보기 편하게 밀리초(ms) 단위로 변경
    df['absolute_time_ms'] = df['absolute_time_us'] / 1000.0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    
    # [위쪽 그래프] Time Interval (주기)
    # X축을 np.arange(len(df)) 대신 df['absolute_time_ms'] 로 변경!
    ax1.plot(df['absolute_time_ms'].values, df['interval_us'].values, 
             marker='.', linestyle='-', color='b', markersize=3, alpha=0.7)
    ax1.set_title("STM32 Chirp Signal Analysis (Absolute Time Domain)", fontsize=16)
    ax1.set_ylabel(r"Time Interval ($\mu s$)", fontsize=12, fontweight='bold', color='b')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    # [아래쪽 그래프] Frequency (주파수)
    # X축을 df['absolute_time_ms'] 로 변경!
    ax2.plot(df['absolute_time_ms'].values, df['frequency_kHz'].values, 
             marker='.', linestyle='-', color='r', markersize=3, alpha=0.7)
    ax2.set_ylabel("Frequency (kHz)", fontsize=12, fontweight='bold', color='r')
    ax2.set_xlabel("Absolute Time (ms)", fontsize=12, fontweight='bold') # X축 라벨 변경
    ax2.grid(True, linestyle='--', alpha=0.6)
    
    plt.tight_layout()
    print("그래프 창을 닫으면 프로그램이 종료됩니다.")
    plt.show()

# =================================================================
# 프로그램 실행부
# =================================================================
if __name__ == "__main__":
    # ★ 핵심 수정: 현재 파이썬 스크립트(.py)가 위치한 절대 경로를 가져옵니다.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 찾고자 하는 CSV 파일 이름
    target_filename = "chirp.csv"  # 추출하신 csv 파일 이름으로 변경하세요.
    
    # 스크립트 폴더 경로와 파일 이름을 합쳐서 최종 절대 경로 생성
    absolute_file_path = os.path.join(script_dir, target_filename)
    
    analyze_tdc_intervals(absolute_file_path)