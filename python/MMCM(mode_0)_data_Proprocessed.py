import os
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# =========================================================================
# 1. 파일 경로 설정 및 로드
# =========================================================================
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "iladata.csv")

if not os.path.exists(csv_filepath):
    raise FileNotFoundError(f"❌ 파일을 찾을 수 없습니다: {csv_filepath}")

df_raw = pd.read_csv(csv_filepath, skiprows=[1])
df_raw.columns = df_raw.columns.str.strip()

# =========================================================================
# 2. 데이터 모드 자동 인식 (Before vs After)
# =========================================================================
col_loop = [c for c in df_raw.columns if 'loop' in c.lower()][0]

if any('timestamp' in c.lower() for c in df_raw.columns):
    MODE = "AFTER (Timestamp)"
    col_val = [c for c in df_raw.columns if 'timestamp' in c.lower()][0]
    DROP_THRESHOLD = -1000  # 타임스탬프는 ~5000ps 떨어짐
    STABLE_MARGIN = 10.0
    Y_LABEL = "Timestamp Average (ps)"
else:
    MODE = "BEFORE (Tap Index)"
    col_val = [c for c in df_raw.columns if 'fine' in c.lower() or 'tap' in c.lower()][0]
    DROP_THRESHOLD = -30    # 탭은 ~270 떨어짐
    STABLE_MARGIN = 0.1
    Y_LABEL = "Tap Average"

print(f"\n▶ 감지된 데이터 모드: {MODE}")
print(f"▶ 분석 타겟 컬럼: {col_val}")

df_raw[col_loop] = pd.to_numeric(df_raw[col_loop], errors="coerce")
df_raw[col_val] = pd.to_numeric(df_raw[col_val], errors="coerce")
df_raw = df_raw.dropna(subset=[col_loop, col_val])

# =========================================================================
# 3. 그룹화 및 [스티칭 전] CSV 저장
# =========================================================================
df_grouped = df_raw.groupby(col_loop)[col_val].mean().reset_index()
df_grouped.columns = ["loop_cnt", "val_avg"]
df_grouped = df_grouped.sort_values(by="loop_cnt").reset_index(drop=True)

pre_stitch_csv = os.path.join(script_dir, "pre_stitch_data.csv")
df_grouped.round(4).to_csv(pre_stitch_csv, index=False)
print(f"✅ [스티칭 전] 데이터 저장 완료: {pre_stitch_csv}")

# =========================================================================
# 4. 과도상태(Metastability) 탐색 및 스티칭
# =========================================================================
df_grouped["diff"] = df_grouped["val_avg"].diff()
drop_indices = df_grouped[df_grouped["diff"] < DROP_THRESHOLD].index.tolist()

# 💡 안전 장치: 절벽이 없거나 유효하지 않으면 그대로 패스
if len(drop_indices) == 0:
    print("⚠️ 하강 포인트가 없습니다. 원본 데이터를 그대로 유지합니다.")
    final_df = df_grouped.copy()
    metastable_indices = []
    main_branch = df_grouped.copy()
    second_branch = pd.DataFrame(columns=["loop_cnt", "val_avg"])

else:
    metastable_indices = []
    for drop_idx in drop_indices:
        back_idx = drop_idx - 1
        while back_idx > 0:
            if df_grouped.loc[back_idx, 'val_avg'] >= df_grouped.loc[back_idx - 1, 'val_avg']:
                break
            back_idx -= 1
            
        forw_idx = drop_idx
        while forw_idx < len(df_grouped) - 1:
            if df_grouped.loc[forw_idx + 1, 'val_avg'] > df_grouped.loc[forw_idx, 'val_avg'] + STABLE_MARGIN:
                break
            forw_idx += 1
            
        metastable_indices.extend(range(back_idx + 1, forw_idx + 1))

    metastable_indices = sorted(list(set(metastable_indices)))
    print(f"▶ 제거된 Metastability 인덱스 개수: {len(metastable_indices)}개")

    df_original_clean = df_grouped.copy()
    df_cleaned = df_grouped.drop(metastable_indices).reset_index(drop=True)

    split_loop_start = df_original_clean.loc[metastable_indices[0], "loop_cnt"]
    split_loop_end = df_original_clean.loc[metastable_indices[-1], "loop_cnt"]

    branch_1 = df_cleaned[df_cleaned["loop_cnt"] < split_loop_start].copy()
    branch_2 = df_cleaned[df_cleaned["loop_cnt"] >= split_loop_end].copy()

    # 💡 안전 장치 2: 만약 한 쪽 덩어리가 텅 비어버렸다면 에러 방지
    if branch_1.empty or branch_2.empty:
        print("⚠️ 분할 후 한 쪽 데이터가 비어 있습니다. 원본 유지.")
        final_df = df_cleaned.copy()
        main_branch = df_cleaned.copy()
        second_branch = pd.DataFrame(columns=["loop_cnt", "val_avg"])
    else:
        if branch_1["val_avg"].min() < branch_2["val_avg"].min():
            main_branch, second_branch = branch_1, branch_2
        else:
            main_branch, second_branch = branch_2, branch_1

        max_main_val = main_branch["val_avg"].max()
        append_data = second_branch[second_branch["val_avg"] > max_main_val].copy()
        append_data = append_data.sort_values(by="loop_cnt")

        max_main_loop = main_branch["loop_cnt"].max()
        append_data["new_loop_cnt"] = range(int(max_main_loop) + 1, int(max_main_loop) + 1 + len(append_data))
        main_branch["new_loop_cnt"] = main_branch["loop_cnt"]

        final_df = pd.concat([main_branch[["new_loop_cnt", "val_avg"]], append_data[["new_loop_cnt", "val_avg"]]]).reset_index(drop=True)
        final_df.rename(columns={"new_loop_cnt": "loop_cnt"}, inplace=True)

# =========================================================================
# 5. [스티칭 후] CSV 저장
# =========================================================================
post_stitch_csv = os.path.join(script_dir, "post_stitch_data.csv")
final_df.round(4).to_csv(post_stitch_csv, index=False)
print(f"✅ [스티칭 후] 데이터 저장 완료: {post_stitch_csv}\n")

# =========================================================================
# 6. 결과 플롯 (바로 띄움)
# =========================================================================
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
fig.canvas.manager.set_window_title(f"Data Processing - {MODE}")

# [좌측] 이어붙이기 전
ax1.scatter(main_branch["loop_cnt"], main_branch["val_avg"], color="blue", label="Main Branch", s=15, alpha=0.7)
if not second_branch.empty:
    ax1.scatter(second_branch["loop_cnt"], second_branch["val_avg"], color="orange", label="Second Branch", s=15, alpha=0.7)

if 'metastable_indices' in locals() and len(metastable_indices) > 0:
    metastable_data = df_original_clean.loc[metastable_indices]
    if not metastable_data.empty:
        ax1.scatter(metastable_data["loop_cnt"], metastable_data["val_avg"], color="red", marker="x", s=40, label="Removed Metastability")

ax1.set_title(f"Before Stitching ({MODE})", fontsize=13, fontweight='bold')
ax1.set_xlabel("Original Loop Count", fontsize=11)
ax1.set_ylabel(Y_LABEL, fontsize=11)
ax1.grid(True, linestyle="--", alpha=0.5)
ax1.legend()

# [우측] 이어붙인 후
if not second_branch.empty:
    main_size = len(main_branch)
    ax2.scatter(final_df.loc[: main_size - 1, "loop_cnt"], final_df.loc[: main_size - 1, "val_avg"], color="blue", label="Main Branch", s=15, alpha=0.7)
    ax2.scatter(final_df.loc[main_size:, "loop_cnt"], final_df.loc[main_size:, "val_avg"], color="orange", label="Appended Data", s=15, alpha=0.7)
else:
    ax2.scatter(final_df["loop_cnt"], final_df["val_avg"], color="blue", label="Original Data", s=15, alpha=0.7)

ax2.set_title("After Stitching (Appended Sequentially)", fontsize=13, fontweight='bold')
ax2.set_xlabel("Processed Loop Count", fontsize=11)
ax2.set_ylabel(Y_LABEL, fontsize=11)
ax2.grid(True, linestyle="--", alpha=0.5)
ax2.legend()

plt.tight_layout()
plt.show()