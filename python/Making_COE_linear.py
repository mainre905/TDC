import os
import glob
import numpy as np
import pandas as pd

# =========================================================================
# 선형(미교정) COE 생성 — "BEFORE" 빌드용
# =========================================================================
# 목적: 캘리브레이션 전/후를 '동일한 하드웨어·동일한 ILA'로 비교하기 위해,
#       ROM에 넣을 BEFORE 값을 만든다.
#   BEFORE = 선형 램프  (모든 tap 폭이 같다고 가정 = 미교정 TDC)
#            LUT[N] = (N - lo + 0.5) * LSB_nominal,   LSB_nominal = 5000 / N_valid
#   AFTER  = code-density COE (Making_COE_Mode_0.py) = 실제 tap 폭 반영
#   두 COE는 '같은 유효 구간'을 써야 공정하므로, code-density와 동일하게
#   최신 히스토그램에서 유효 구간을 검출한다.
T_PERIOD_PS    = 5000.0
NUM_TOTAL_TAPS = 320
ROM_MAX_VALUE  = 8191
EDGE_TRIM_FRAC = 0.05
SOURCE_TAG     = "linear"        # tdc_calib_linear_rom.coe 로 보관

CAL_CSV = None   # None이면 최신 tap_histogram_*.csv (유효 구간 검출용)

script_dir = os.path.dirname(os.path.abspath(__file__))

if CAL_CSV:
    csv_filepath = os.path.join(script_dir, CAL_CSV)
else:
    cands = sorted(glob.glob(os.path.join(script_dir, "tap_histogram_*.csv")))
    if not cands:
        print("❌ tap_histogram_*.csv 가 없습니다.")
        exit()
    csv_filepath = cands[-1]

print(f"[*] 유효구간 기준 히스토그램: {os.path.basename(csv_filepath)}")

# --- 히스토그램 로드 & 유효 구간 (code-density와 동일 로직) ---
df = pd.read_csv(csv_filepath)
col_tap   = [c for c in df.columns if 'tap' in c.lower()][0]
col_count = [c for c in df.columns if 'count' in c.lower() or 'hit' in c.lower()][0]

counts = np.zeros(NUM_TOTAL_TAPS)
for tap, cnt in zip(pd.to_numeric(df[col_tap], errors="coerce"),
                    pd.to_numeric(df[col_count], errors="coerce")):
    if not (np.isnan(tap) or np.isnan(cnt)) and 0 <= int(tap) < NUM_TOTAL_TAPS:
        counts[int(tap)] = cnt

nz = counts[counts > 0]
th = nz.mean() * EDGE_TRIM_FRAC
lo = 0
while lo < NUM_TOTAL_TAPS and counts[lo] < th:
    lo += 1
hi = NUM_TOTAL_TAPS - 1
while hi > lo and counts[hi] < th:
    hi -= 1
N = hi - lo + 1
LSB_nom = T_PERIOD_PS / N

# --- 선형 램프 LUT (bin 중심) ---
lut_ps = np.zeros(NUM_TOTAL_TAPS)
for i in range(N):
    lut_ps[lo + i] = (i + 0.5) * LSB_nom      # tap lo → 0.5·LSB, tap hi → (N-0.5)·LSB
lut_ps[hi + 1:] = lut_ps[hi]                  # 미도달 끝단 클램프 (단조성)
lut_int = np.clip(np.round(lut_ps), 0, ROM_MAX_VALUE).astype(int)

# --- COE 저장 (canonical + tagged) ---
canonical_coe = os.path.join(script_dir, "tdc_calib_mode0_rom.coe")
tagged_coe    = os.path.join(script_dir, f"tdc_calib_{SOURCE_TAG}_rom.coe")
for coe_filepath in (canonical_coe, tagged_coe):
    with open(coe_filepath, "w") as f:
        f.write("memory_initialization_radix=10;\n")
        f.write("memory_initialization_vector=\n")
        for i, val in enumerate(lut_int):
            f.write(f"{val}" + (";" if i == len(lut_int) - 1 else ",\n"))

print("\n" + "=" * 55)
print(" 📏 LINEAR (미교정) CALIBRATION LUT  — BEFORE 빌드용")
print("=" * 55)
print(f" 유효 구간   : tap {lo} ~ {hi} ({N} bins)")
print(f" LSB_nominal : {LSB_nom:.3f} ps")
print(f" LUT 범위    : {lut_int[lo]} ~ {lut_int[hi]} ps")
print(f" 단조 증가   : {'OK' if np.all(np.diff(lut_int[lo:hi+1]) >= 0) else '❌'}")
print("-" * 55)
print(f" ✅ 빌드용(canonical) : {os.path.basename(canonical_coe)}")
print(f" ✅ 보관용(tagged)    : {os.path.basename(tagged_coe)}")
print("=" * 55)
print("\n ⚠️ BEFORE 빌드 후 반드시 AFTER용 code-density COE를 다시 생성해서")
print("    canonical(tdc_calib_mode0_rom.coe)을 덮어써야 AFTER 빌드가 맞습니다.\n")
