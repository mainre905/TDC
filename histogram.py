import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# -------------------------------------------------------------------------
# 1. 데이터 로드 및 전처리 (Vivado ILA CSV 특성 반영)
# -------------------------------------------------------------------------
csv_filename = "iladata.csv"

# CSV 파일이 존재하는지 확인 (없을 경우 가상의 텍스트 데이터로 예시를 만들기 위함)
if not os.path.exists(csv_filename):
    print(
        f"'{csv_filename}' 파일이 경로에 없습니다. 파일명을 확인해 주세요."
    )
    exit()

# Vivado ILA CSV의 두 번째 줄(Radix 정의 행)을 건너뛰고 로드
try:
    df = pd.read_csv(csv_filename, skiprows=[1])
except Exception as e:
    print(f"파일을 읽는 중 오류가 발생했습니다: {e}")
    exit()

# 열 이름 정리 (공백 제거 및 '[8:0]' 같은 비트 너비 표기 제거)
df.columns = [c.strip().split("[")[0] for c in df.columns]

# 데이터 타입 강제 변환 및 결측치('...' 등의 문자열) 제거
for col in ["Sample in Buffer", "ts_valid_d2", "ts_fine_idx_d2", "current_loop_cnt"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.dropna(subset=["ts_fine_idx_d2", "current_loop_cnt"])
df["Sample in Buffer"] = df["Sample in Buffer"].astype(int)

# 유효한 측정 데이터만 필터링 (ts_valid_d2 == 1)
df_valid = df[df["ts_valid_d2"] == 1].copy()

# -------------------------------------------------------------------------
# 2. Golden Region (유효 선형 구간) 회귀 분석 및 해상도 추출
# -------------------------------------------------------------------------
# 첫 번째 주기 내의 안정적인 선형 구간 필터링 (current_loop_cnt 1 ~ 134)
linear_region = df_valid[
    (df_valid["current_loop_cnt"] >= 1) & (df_valid["current_loop_cnt"] <= 134)
]

if not linear_region.empty:
    X = linear_region["current_loop_cnt"].values
    Y = linear_region["ts_fine_idx_d2"].values

    # 선형 피팅 (1차 다항식 회귀)
    slope, intercept = np.polyfit(X, Y, 1)

    # 평균 Tap 지연시간 계산 (위상 천이 스텝당 17.85 ps 적용)
    # Tap 지연시간 = 17.85 ps / (스텝당 평균 증가 Tap 수)
    avg_tap_delay = 17.85 / slope
else:
    slope, avg_tap_delay = None, None

# -------------------------------------------------------------------------
# 3. 데이터 시각화 (Subplot 구성)
# -------------------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharey=False)
plt.subplots_adjust(hspace=0.3)

# Graphics Styling
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

# [PLOT 1] 시간 흐름(Sample Index)에 따른 TDC Tap 변화 및 Wrap-around 관측
ax1.scatter(
    df_valid["Sample in Buffer"],
    df_valid["ts_fine_idx_d2"],
    c=df_valid["current_loop_cnt"],
    cmap="viridis",
    s=15,
    alpha=0.8,
    label="Captured Samples",
)
ax1.set_title(
    "TDC Raw Fine Index vs ILA Sample Buffer (Time Domain Stream)",
    fontsize=14,
    fontweight="bold",
    pad=15,
)
ax1.set_xlabel("Sample Index in Buffer", fontsize=11)
ax1.set_ylabel("TDC Fine Index (Tap)", fontsize=11)
ax1.grid(True, linestyle="--", alpha=0.5)

# Wrap-around 경계 영역 강조 (Sample 5376~5415 부근)
transition_samples = df_valid[df_valid["current_loop_cnt"] == 135]
if not transition_samples.empty:
    ax1.axvspan(
        transition_samples["Sample in Buffer"].min(),
        transition_samples["Sample in Buffer"].max(),
        color="red",
        alpha=0.2,
        label="Wrap-around Boundary (Metastability Zone)",
    )
ax1.legend(loc="upper left")

# [PLOT 2] MMCM Phase Shift 스텝에 따른 캘리브레이션 특성 곡선
# 전체 분포 플롯
ax2.scatter(
    df_valid["current_loop_cnt"],
    df_valid["ts_fine_idx_d2"],
    color="#475569",
    s=12,
    alpha=0.5,
    label="Raw Data Points",
)

# 선형 구간 트렌드 라인 플롯
if slope is not None:
    x_range = np.linspace(1, 134, 100)
    y_fit = slope * x_range + intercept
    ax2.plot(
        x_range,
        y_fit,
        color="#f97316",
        linewidth=2.5,
        label=f"Golden Region Fit Line (Slope: {slope:.3f} Tap/Step)",
    )

    # 캘리브레이션 데이터 텍스트 박스 출력
    stats_text = (
        f"■ TDC Calibration Analysis\n"
        f" - Golden Region: Step 1 ~ 134\n"
        f" - Est. Avg Tap Delay: {avg_tap_delay:.2f} ps/Tap\n"
        f" - Phase Shift Step: 17.85 ps"
    )
    ax2.text(
        0.05,
        0.65,
        stats_text,
        transform=ax2.transAxes,
        fontsize=11,
        fontweight="bold",
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="#0f172a",
            edgecolor="#334155",
            alpha=0.9,
        ),
        color="white",
    )

# 메타스테빌리티 임계 단계 강조 (Step 135)
ax2.axvline(
    x=135,
    color="#ef4444",
    linestyle=":",
    linewidth=2,
    label="Wrap-around Point (Step 135)",
)

ax2.set_title(
    "TDC Calibration Curve (TDC Tap vs MMCM Phase Shift Steps)",
    fontsize=14,
    fontweight="bold",
    pad=15,
)
ax2.set_xlabel("MMCM Phase Shift Steps (0 ~ 350)", fontsize=11)
ax2.set_ylabel("TDC Fine Index (Tap)", fontsize=11)
ax2.set_xlim(-10, 360)
ax2.grid(True, linestyle="--", alpha=0.5)
ax2.legend(loc="lower right")

# 이미지 출력 및 저장
plt.savefig("tdc_calibration_plot.png", dpi=300, bbox_inches="tight")
plt.show()