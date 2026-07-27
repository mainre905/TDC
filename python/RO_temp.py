import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 1. 파일 경로 설정
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "iladata.csv")

def main():
    # 2. CSV 파일 읽기
    try:
        df = pd.read_csv(csv_filepath)
    except FileNotFoundError:
        print(f"오류: '{csv_filepath}' 파일을 찾을 수 없습니다.")
        return

    # 3. Vivado CSV 'Radix' 문자열 행 필터링
    if df.iloc[0].astype(str).str.contains('UNSIGNED|HEX|Radix').any():
        df = df.drop(index=0).reset_index(drop=True)

    # 4. 목적 컬럼 찾기
    ro_col = [col for col in df.columns if 'ro_meas_cnt' in col][0]
    temp_col = [col for col in df.columns if 'die_temp_at_meas' in col][0]

    # 5. 숫자형(Unsigned Integer) 데이터로 변환
    df[ro_col] = pd.to_numeric(df[ro_col], errors='coerce').astype(np.uint32)
    df[temp_col] = pd.to_numeric(df[temp_col], errors='coerce').astype(np.uint16)
    df = df.dropna(subset=[ro_col, temp_col])

    # ====================================================================
    # 6. [핵심] 수식 변환 (카운트 -> MHz 주파수 / XADC -> 섭씨 온도)
    # ====================================================================
    # RO 주파수(MHz) = (Count * 4(분주비) * 100(10ms->1s)) / 1,000,000
    df['Frequency_MHz'] = (df[ro_col] * 400.0) / 1_000_000.0
    
    # 섭씨 온도(℃) = ((Raw / 16) * 503.975 / 4096) - 273.15
    df['Temperature_C'] = ((df[temp_col] / 16.0) * 503.975 / 4096.0) - 273.15

    # 7. 주파수 통계값 계산 (Min, Max, Mean)
    freq_min = df['Frequency_MHz'].min()
    freq_max = df['Frequency_MHz'].max()
    freq_mean = df['Frequency_MHz'].mean()

    # 8. Matplotlib 차트 그리기
    plt.figure(figsize=(10, 6), facecolor='white')
    
    # 산점도(Scatter) 그리기: X축=온도, Y축=주파수(MHz)
    plt.scatter(df['Temperature_C'], df['Frequency_MHz'], 
                alpha=0.6, color='royalblue', edgecolor='black', 
                label='Measured Frequency', s=40)

    # 통계값 가로선 추가
    plt.axhline(y=freq_max, color='crimson', linestyle='--', linewidth=2, label=f'Max: {freq_max:.3f} MHz')
    plt.axhline(y=freq_mean, color='forestgreen', linestyle='-', linewidth=2.5, label=f'Mean: {freq_mean:.3f} MHz')
    plt.axhline(y=freq_min, color='darkorange', linestyle='--', linewidth=2, label=f'Min: {freq_min:.3f} MHz')

    # 차트 꾸미기
    plt.title('Ring Oscillator Frequency Drift by Die Temperature', fontsize=15, fontweight='bold', pad=15)
    plt.xlabel('FPGA Die Temperature (℃)', fontsize=12, fontweight='bold')
    plt.ylabel('RO Frequency (MHz)', fontsize=12, fontweight='bold')
    
    # 텍스트 박스로 통계 요약 표시
    stats_text = (f"Total Samples: {len(df)}\n"
                  f"Max Freq: {freq_max:.3f} MHz\n"
                  f"Mean Freq: {freq_mean:.3f} MHz\n"
                  f"Min Freq: {freq_min:.3f} MHz\n"
                  f"Delta: {freq_max - freq_min:.3f} MHz")
    
    props = dict(boxstyle='round,pad=0.6', facecolor='white', alpha=0.9, edgecolor='silver')
    plt.gca().text(0.97, 0.95, stats_text, transform=plt.gca().transAxes, fontsize=11,
                   verticalalignment='top', horizontalalignment='right', bbox=props)

    # 그리드 및 범례 설정
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend(loc='lower left', fontsize=10)
    plt.tight_layout()

    # 차트 출력
    plt.show()

if __name__ == "__main__":
    main()