import os
import matplotlib.pyplot as plt
import pandas as pd

# 1. 파일 경로 설정 (현재 스크립트 디렉토리 기준)
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "iladata.csv")

if not os.path.exists(csv_filepath):
    raise FileNotFoundError(f"파일을 찾을 수 없습니다: {csv_filepath}")

# 2. CSV 파일 로드 (두 번째 행인 Radix 표시 줄은 skiprows=[1]로 제외)
df_raw = pd.read_csv(csv_filepath, skiprows=[1])

# 열 이름 정리 (공백 제거)
df_raw.columns = df_raw.columns.str.strip()

# 필요한 컬럼 데이터 타입을 숫자로 변환
df_raw["current_loop_cnt[8:0]"] = pd.to_numeric(
    df_raw["current_loop_cnt[8:0]"], errors="coerce"
)
df_raw["aligned_fine_idx[8:0]"] = pd.to_numeric(
    df_raw["aligned_fine_idx[8:0]"], errors="coerce"
)

# 결측치 제거
df_raw = df_raw.dropna(
    subset=["current_loop_cnt[8:0]", "aligned_fine_idx[8:0]"]
)

# 3. 동일한 loop_cnt 내의 값들을 평균(tap_avg) 내어 1차원 데이터로 변환
df_grouped = (
    df_raw.groupby("current_loop_cnt[8:0]")["aligned_fine_idx[8:0]"]
    .mean()
    .reset_index()
)
df_grouped.columns = ["loop_cnt", "tap_avg"]

# loop_cnt 기준으로 정렬
df_grouped = df_grouped.sort_values(by="loop_cnt").reset_index(drop=True)

# 4. 값이 급격히 떨어지는 포인트(Drop Point) 찾기
df_grouped["diff"] = df_grouped["tap_avg"].diff()

# 급격한 변화를 감지하기 위한 임계값 설정 (예: -30 이하로 감소)
drop_threshold = -30
drop_indices = df_grouped[df_grouped["diff"] < drop_threshold].index.tolist()

if len(drop_indices) >= 3:
    raise ValueError(
        f"에러: 뚝 떨어지는 포인트가 3개 이상 검출되었습니다. (검출 개수: {len(drop_indices)}개)"
    )
elif len(drop_indices) < 2:
    raise ValueError(
        "에러: 하강 포인트가 2개 미만입니다. 데이터를 분할할 수 없습니다."
    )

# 5. 과도상태(Metastability) 데이터 제거 전 원본 데이터 보관 (비교용)
df_original_clean = df_grouped.copy()

# 6. 뚝 떨어지는 포인트 사이의 과도상태(Metastability) 데이터 제거
d1, d2 = drop_indices
metastable_indices = list(range(d1, d2))
df_cleaned = df_grouped.drop(metastable_indices).reset_index(drop=True)

# 7. 각각의 덩어리(Branch)로 분할
split_loop_start = df_grouped.loc[d1, "loop_cnt"]
split_loop_end = df_grouped.loc[d2, "loop_cnt"]

branch_1 = df_cleaned[df_cleaned["loop_cnt"] < split_loop_start].copy()
branch_2 = df_cleaned[df_cleaned["loop_cnt"] >= split_loop_end].copy()

# 8. 각 덩어리 중 최솟값이 가장 작은 것을 Main Branch로 선정
min_1 = branch_1["tap_avg"].min()
min_2 = branch_2["tap_avg"].min()

if min_1 < min_2:
    main_branch = branch_1
    second_branch = branch_2
else:
    main_branch = branch_2
    second_branch = branch_1

# 9. Main Branch의 tap_avg 최댓값보다 큰 값이 Second Branch에 있다면 가져와서 붙임
max_main_tap = main_branch["tap_avg"].max()
append_data = second_branch[second_branch["tap_avg"] > max_main_tap].copy()
append_data = append_data.sort_values(by="loop_cnt")

# Main Branch의 최종 loop_cnt 다음 번호부터 순차적으로 새로운 번호 부여
max_main_loop = main_branch["loop_cnt"].max()
append_data["new_loop_cnt"] = range(
    int(max_main_loop) + 1, int(max_main_loop) + 1 + len(append_data)
)

main_branch["new_loop_cnt"] = main_branch["loop_cnt"]

# 10. 최종 결합
final_df = pd.concat(
    [
        main_branch[["new_loop_cnt", "tap_avg"]],
        append_data[["new_loop_cnt", "tap_avg"]],
    ]
).reset_index(drop=True)

final_df.rename(columns={"new_loop_cnt": "loop_cnt"}, inplace=True)


# --- Matplotlib 시각화 (이어붙이기 전 vs 후) ---
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# [좌측 그래프] 이어붙이기 전 (원래의 Loop Count 구조)
ax1.scatter(
    main_branch["loop_cnt"],
    main_branch["tap_avg"],
    color="blue",
    label="Main Branch (Original Loop)",
    s=15,
    alpha=0.7,
)
ax1.scatter(
    second_branch["loop_cnt"],
    second_branch["tap_avg"],
    color="orange",
    label="Second Branch (Original Loop)",
    s=15,
    alpha=0.7,
)
# 제거된 metastability 지점 시각화 (빨간색 x 표시)
metastable_data = df_original_clean.loc[metastable_indices]
if not metastable_data.empty:
    ax1.scatter(
        metastable_data["loop_cnt"],
        metastable_data["tap_avg"],
        color="red",
        marker="x",
        s=40,
        label="Removed Metastability",
    )

ax1.set_title("Before Stitching (Original Loop Counts)", fontsize=13)
ax1.set_xlabel("Original Loop Count", fontsize=11)
ax1.set_ylabel("Tap Average", fontsize=11)
ax1.grid(True, linestyle="--", alpha=0.5)
ax1.legend()

# [우측 그래프] 이어붙인 후 (가상 Loop Count 구조)
main_size = len(main_branch)
ax2.scatter(
    final_df.loc[: main_size - 1, "loop_cnt"],
    final_df.loc[: main_size - 1, "tap_avg"],
    color="blue",
    label="Main Branch",
    s=15,
    alpha=0.7,
)
ax2.scatter(
    final_df.loc[main_size:, "loop_cnt"],
    final_df.loc[main_size:, "tap_avg"],
    color="orange",
    label="Appended & Shifted (from Second)",
    s=15,
    alpha=0.7,
)

ax2.set_title("After Stitching (Appended to Tail)", fontsize=13)
ax2.set_xlabel("Processed Loop Count (Virtual)", fontsize=11)
ax2.set_ylabel("Tap Average", fontsize=11)
ax2.grid(True, linestyle="--", alpha=0.5)
ax2.legend()

plt.tight_layout()
plt.show()