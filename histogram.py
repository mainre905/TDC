import os
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

FOLDER_PATH = "./"          # 데이터 저장 폴더
FILE_PATTERN = "iladata_*.csv" 
T_CLK_PS = 5000.0           # 200 MHz 주클럭의 주기 (5000 ps)
NUM_TAPS = 320              # 총 탭 수

def run_calibration_flow():
    # 1. 파일 자동 탐색 및 통합
    search_path = os.path.join(FOLDER_PATH, FILE_PATTERN)
    file_list = sorted(glob.glob(search_path))
    if not file_list:
        raise FileNotFoundError("대상 CSV 파일을 찾을 수 없습니다.")
        
    df_list = []
    for file in file_list:
        # 두 번째 줄의 Radix 라인 스킵
        temp_df = pd.read_csv(file, skiprows=[1])
        temp_df.columns = [col.split('[')[0].strip() for col in temp_df.columns]
        # ts_coarse HEX를 int로 변환
        temp_df['ts_coarse'] = temp_df['ts_coarse'].apply(
            lambda x: int(str(x).strip(), 16) if pd.notnull(x) else np.nan
        )
        df_list.append(temp_df)
        
    combined_df = pd.concat(df_list, ignore_index=True)
    fine_data = combined_df['ts_fine_idx'].dropna().astype(int).values
    total_samples = len(fine_data)
    
    # 2. 코드 밀도 기반 캘리브레이션 알고리즘 계산
    hist, _ = np.histogram(fine_data, bins=range(NUM_TAPS + 1))
    tap_widths_ps = T_CLK_PS * (hist / total_samples) # W(i) = T_CLK * (H(i)/N_total)
    calibration_lut = np.cumsum(tap_widths_ps)       # Cumulative_Delay_ps = Sum(W(i))
    
    # 3. 보정표 CSV 내보내기
    lut_df = pd.DataFrame({
        'Fine_Index': range(NUM_TAPS),
        'Hit_Count': hist,
        'Tap_Width_ps': tap_widths_ps,
        'Cumulative_Delay_ps': calibration_lut
    })
    lut_df.to_csv("tdc_calibration_lut.csv", index=False)
    print("-> 캘리브레이션 CSV 파일 저장 완료: tdc_calibration_lut.csv")
    
    # 4. 분석 리포트 그래프 시각화 및 PNG 파일 저장
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    ax1.bar(range(NUM_TAPS), hist, color='royalblue', width=1.0)
    ax1.set_title("Fine Index Frequency (Code Density Test)")
    ax1.set_xlabel("Fine Index"), ax1.set_ylabel("Occurrence Count")
    ax1.grid(True, linestyle='--', alpha=0.5)
    
    ax2.plot(range(NUM_TAPS), calibration_lut, color='crimson', linewidth=2.5)
    ax2.set_title("Cumulative Delay Curve (TDC Calibration LUT)")
    ax2.set_xlabel("Fine Index"), ax2.set_ylabel("Calibrated Time (ps)")
    ax2.axhline(y=T_CLK_PS, color='darkgreen', linestyle=':', label=f"Clock Period ({T_CLK_PS} ps)")
    ax2.legend(loc='lower right'), ax2.grid(True, linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig("tdc_analysis_results.png", dpi=300)
    print("-> 캘리브레이션 분석 결과 이미지 저장 완료: tdc_analysis_results.png")

if __name__ == "__main__":
    run_calibration_flow()
