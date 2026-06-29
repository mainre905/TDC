import pandas as pd
import numpy as np
import os

# ============================================================
# 0. 파일 확인
# ============================================================
csv_filename = "iladata.csv"

if not os.path.exists(csv_filename):
    print(f"❌ '{csv_filename}' 파일이 없습니다.")
    exit()

# ============================================================
# 1. 데이터 로드
# ============================================================
df = pd.read_csv(csv_filename, skiprows=[1])

# 컬럼 이름 정리
df.columns = [c.strip().split("[")[0] for c in df.columns]

# 필요한 컬럼 숫자형 변환
for col in ["ts_valid_d2", "ts_fine_idx_d2", "current_loop_cnt"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# 유효 데이터만 필터링
df_valid = df.dropna(subset=["ts_fine_idx_d2", "current_loop_cnt"]).copy()
df_valid = df_valid[df_valid["ts_valid_d2"] == 1]

# ============================================================
# 2. 시간 계산 (Step 1)
# ============================================================
PHASE_STEP_PS = 1000.0 / 56.0
df_valid["time_ps"] = df_valid["current_loop_cnt"] * PHASE_STEP_PS

# ============================================================
# 3. loop_cnt 기준 평균 tap 계산 (Step 2)
# ============================================================
result = df_valid.groupby("current_loop_cnt").agg({
    "ts_fine_idx_d2": "mean",
    "time_ps": "first"   # 같은 loop_cnt라 동일 값
}).reset_index()

# tap 정수화
result["tap_avg"] = np.round(result["ts_fine_idx_d2"]).astype(int)

# 컬럼 정리
result = result[["current_loop_cnt", "tap_avg", "time_ps"]]

# ============================================================
# 4. CSV 저장 (하나의 파일)
# ============================================================
output_file = "loopcnt_tap_time.csv"
result.to_csv(output_file, index=False)

# ============================================================
# 5. 출력 확인
# ============================================================
print(f"\n✅ 저장 완료: {output_file}")
print("\n📌 일부 결과:")
print(result.head(10))