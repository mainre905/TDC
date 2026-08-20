import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import norm

# 1. 파일 경로 설정
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "jitter_50.csv")

VCO_PERIOD_PS = 5000.0

def main():
    if not os.path.exists(csv_filepath):
        print(f"❌ 파일을 찾을 수 없습니다: {csv_filepath}")
        return

    df = pd.read_csv(csv_filepath)
    df.columns = df.columns.str.strip()
    df = df[~df.iloc[:, 0].astype(str).str.contains('Radix', case=False, na=False)].copy()

    ts_col = [c for c in df.columns if 'final_timestamp_ps' in c][0]
    raw_ts = pd.to_numeric(df[ts_col], errors='coerce').dropna().astype(int).values

    # 10클럭 주기 유효 히트 추출
    valid_ts = []
    prev_val = None
    for val in raw_ts:
        if val != prev_val and val > 0:
            valid_ts.append(val)
            prev_val = val

    valid_ts = np.array(valid_ts)
    fine_ps = (VCO_PERIOD_PS - (valid_ts % VCO_PERIOD_PS)) % VCO_PERIOD_PS

    mean_ps = np.mean(fine_ps)
    std_ps  = np.std(fine_ps, ddof=1)
    
    # Unique 불연속 탭 값 및 빈도 추출
    unique_vals, counts = np.unique(fine_ps, return_counts=True)

    print("\n" + "="*50)
    print(fr" 📊 TDC Jitter Analysis ($\sigma = {std_ps:.3f}$ ps)")
    print("="*50)
    print(" [검출된 불연속 탭 시간(ps) 및 검출 횟수]")
    for val, cnt in zip(unique_vals, counts):
        print(f"  • {val:7.2f} ps : {cnt:3d} 회 ({cnt/len(fine_ps)*100:5.1f}%)")
    print("="*50)

    # 시각화: 불연속 막대 + 가우시안 피팅 곡선
    plt.figure(figsize=(9, 5))
    
    # 1. 실제 측정된 불연속 탭 위치에 막대 그리기
    plt.hist(fine_ps, bins=35, density=True, alpha=0.6, color='royalblue', edgecolor='black', label='Measured Taps')

    # 2. 이론적 가우시안 분포 곡선 (Gaussian Fit) 덧씌우기
    xmin, xmax = plt.xlim()
    x_axis = np.linspace(xmin, xmax, 200)
    gaussian_pdf = norm.pdf(x_axis, mean_ps, std_ps)
    plt.plot(x_axis, gaussian_pdf, 'r--', linewidth=2.5, label=fr'Gaussian Fit ($\sigma={std_ps:.2f}$ ps)')

    plt.axvline(mean_ps, color='darkred', linestyle=':', linewidth=1.5, label=f'Mean = {mean_ps:.2f} ps')
    plt.title(fr"TDC Single-Shot Jitter & Quantized Taps ($N={len(fine_ps)}$)", fontsize=13, fontweight='bold')
    plt.xlabel("Fine Time (ps)", fontsize=11)
    plt.ylabel("Probability Density", fontsize=11)
    plt.legend(fontsize=10, loc='upper right')
    plt.grid(True, linestyle=':', alpha=0.6)

    out_png = os.path.join(script_dir, "jitter50_gaussian_fit.png")
    plt.savefig(out_png, dpi=300, bbox_inches='tight')
    print(f"🖼️ 가우시안 피팅 그래프 저장 완료: {out_png}\n")
    plt.show()

if __name__ == "__main__":
    main()