import os
import pandas as pd
import matplotlib.pyplot as plt

# ============================================================
# 0. 파일 경로 설정
# ============================================================
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, 'iladata.csv')

print(f"📂 읽어올 파일 경로: {csv_filepath}")

# ============================================================
# 1. 데이터 불러오기
# ============================================================
try:
    df = pd.read_csv(csv_filepath)
    print("✅ CSV 파일을 성공적으로 불러왔습니다.")
except FileNotFoundError:
    print(f"❌ 에러: '{csv_filepath}' 파일을 찾을 수 없습니다.")
    exit()

# ============================================================
# 2. Vivado ILA 컬럼 이름 자동 매칭
# ============================================================
try:
    loop_col = [col for col in df.columns if 'current_loop_cnt' in col][0]
    fine_col = [col for col in df.columns if 'aligned_fine_idx' in col][0]
except IndexError:
    print("❌ 에러: CSV 파일에서 해당 신호 이름을 찾을 수 없습니다.")
    exit()

df[loop_col] = pd.to_numeric(df[loop_col], errors='coerce')
df[fine_col] = pd.to_numeric(df[fine_col], errors='coerce')
df = df.dropna()

# ============================================================
# 3. 데이터 통계 처리 (Averaging)
# ============================================================
calibration_curve = df.groupby(loop_col)[fine_col].mean()

# ★ 판다스 출력 제한 해제 (전체 행 출력) ★
pd.set_option('display.max_rows', None)

print("\n==================================================")
print("--- 전체 캘리브레이션 데이터 (Wrap Around 확인용) ---")
print("==================================================")
print(calibration_curve)
print("==================================================")

# 출력 제한 원상복구
pd.reset_option('display.max_rows')

# ============================================================
# 4. 논문용 그래프 출력 (Wrap-around 눈으로 확인하기)
# ============================================================
plt.figure(figsize=(10, 6))
calibration_curve.plot(marker='.', linestyle='-', color='r', markersize=6, alpha=0.8)

plt.title("Raw Calibration Curve with Wrap Around", fontsize=14, fontweight='bold')
plt.xlabel("MMCM Phase Step [current_loop_cnt]", fontsize=12)
plt.ylabel("Average TDC Tap Index", fontsize=12)
plt.grid(True, which='both', linestyle='--', linewidth=0.5)

plt.tight_layout()
plt.show()