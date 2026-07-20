import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =========================================================================
# 0. 설정
# =========================================================================
# 하드웨어 제약 (tdc_calib_rom / tdc_timestamp_calc.v 와 일치해야 함)
#   ROM  : 깊이 320, 폭 13비트(0~8191 ps), latency 2
#   연산 : timestamp = coarse*5000 - calibrated_fine_ps[fine_idx]
#   → LUT[i] = "tap i일 때 클럭 엣지보다 얼마나 앞서 도착했는가(ps)", 단조 증가, 0~5000
T_PERIOD_PS    = 5000.0    # tdc_clk 한 주기 (200MHz)
NUM_TOTAL_TAPS = 320       # ROM 깊이 = CARRY4 80단 x 4
ROM_MAX_VALUE  = 8191      # 13비트 상한
EDGE_TRIM_FRAC = 0.05      # 유효 구간 끝단 컷 (평균의 5% 미만인 양 끝 bin 제거)

# Calibration set: COE를 만들 raw 히스토그램. None이면 가장 최근 파일.
CAL_CSV = "tap_histogram_20260720_112710.csv"

script_dir = os.path.dirname(os.path.abspath(__file__))

if CAL_CSV:
    csv_filepath = os.path.join(script_dir, CAL_CSV)
else:
    cands = sorted(glob.glob(os.path.join(script_dir, "tap_histogram_*.csv")))
    if not cands:
        print("❌ tap_histogram_*.csv 가 없습니다. Histogram.py를 먼저 실행하세요.")
        exit()
    csv_filepath = cands[-1]

print(f"[*] Calibration set: {os.path.basename(csv_filepath)}")

# =========================================================================
# 1. 데이터 로드
# =========================================================================
try:
    df = pd.read_csv(csv_filepath)
except FileNotFoundError:
    print(f"❌ '{csv_filepath}' 파일을 찾을 수 없습니다.")
    exit()

col_tap   = [c for c in df.columns if 'tap' in c.lower()][0]
col_count = [c for c in df.columns if 'count' in c.lower() or 'hit' in c.lower()][0]

# tap 0 ~ NUM_TOTAL_TAPS-1 전체 길이의 배열로 정규화 (빠진 tap은 0으로 채움)
counts_full = np.zeros(NUM_TOTAL_TAPS, dtype=float)
for tap, cnt in zip(pd.to_numeric(df[col_tap], errors="coerce"),
                    pd.to_numeric(df[col_count], errors="coerce")):
    if not (np.isnan(tap) or np.isnan(cnt)):
        ti = int(tap)
        if 0 <= ti < NUM_TOTAL_TAPS:
            counts_full[ti] = cnt

# =========================================================================
# 2. 유효 구간 검출 (양 끝단에서만 트리밍)
# =========================================================================
#   tap 0     : 스냅샷 조건(tap[0]==1)상 popcount=0 불가 → 항상 빈 칸
#   끝단 taps : 딜레이라인(≈5.4ns)이 1주기(5ns)보다 길어 도달 불가
#   내부 좁은 bin(missing code)은 실제 하드웨어 특성이므로 절대 제거하지 않음.
nz = counts_full[counts_full > 0]
if nz.size == 0:
    print("❌ 유효한 데이터가 없습니다.")
    exit()

thresh = nz.mean() * EDGE_TRIM_FRAC
lo = 0
while lo < NUM_TOTAL_TAPS and counts_full[lo] < thresh:
    lo += 1
hi = NUM_TOTAL_TAPS - 1
while hi > lo and counts_full[hi] < thresh:
    hi -= 1

# =========================================================================
# 3. Cumulative Code-Density LUT 계산
# =========================================================================
#   위상 스윕이 한 주기를 균일하게 훑으므로 h[i] ∝ bin 폭.
#   LUT[i] = (T/H) * ( Σ_{k<i} h[k] + h[i]/2 )      ← bin 중심(양자화 오차 최소)
h = counts_full[lo:hi + 1]
H = h.sum()

cum_before = np.concatenate([[0.0], np.cumsum(h)[:-1]])   # Σ_{k<i} h[k]
lut_valid  = T_PERIOD_PS / H * (cum_before + h / 2.0)      # 유효 구간의 ps 값

# 전체 320칸 배열로 확장
lut_ps = np.zeros(NUM_TOTAL_TAPS, dtype=float)
lut_ps[lo:hi + 1] = lut_valid
lut_ps[:lo]       = 0.0                # tap 0 등 진입 전 (호출 안 됨)
lut_ps[hi + 1:]   = lut_valid[-1]      # 미도달 끝단 → 마지막 유효값 유지(단조성 보존)

# 단조 비감소 보장 (통계 노이즈로 인한 역전 방지) 후 양자화
lut_ps = np.maximum.accumulate(lut_ps)
lut_int = np.clip(np.round(lut_ps), 0, ROM_MAX_VALUE).astype(int)

# =========================================================================
# 4. COE 파일 생성 (radix 10, 320줄, 주석 없음)
# =========================================================================
coe_filepath = os.path.join(script_dir, "tdc_calib_mode0_rom.coe")
with open(coe_filepath, "w") as f:
    f.write("memory_initialization_radix=10;\n")
    f.write("memory_initialization_vector=\n")
    for i, val in enumerate(lut_int):
        f.write(f"{val}" + (";" if i == len(lut_int) - 1 else ",\n"))

# =========================================================================
# 5. 검증 로그
# =========================================================================
diffs = np.diff(lut_int[lo:hi + 1])
print("\n" + "=" * 55)
print(" 🔧 MODE 0 CODE-DENSITY CALIBRATION LUT")
print("=" * 55)
print(f" 유효 구간      : tap {lo} ~ {hi} ({hi - lo + 1} bins)")
print(f" 총 히트 H      : {int(H):,}")
print(f" LUT 범위       : {lut_int[lo]} ~ {lut_int[hi]} ps  (목표 0~{int(T_PERIOD_PS)})")
print(f" 단조 증가      : {'OK' if np.all(diffs >= 0) else '❌ 역전 존재'}")
print(f" 13비트 이내    : {'OK' if lut_int.max() <= ROM_MAX_VALUE else '❌ 초과'}")
print(f" 최대 step(폭)  : {diffs.max()} ps (tap {lo + int(np.argmax(diffs))})")
print(f" 최소 step(폭)  : {diffs.min()} ps  ← 0이면 missing code")
print(f" ROM 라인 수    : {len(lut_int)} (필요 {NUM_TOTAL_TAPS})")
print("-" * 55)
print(f" ✅ COE 저장    : {os.path.basename(coe_filepath)}")
print("=" * 55 + "\n")

# =========================================================================
# 6. 시각화 (확인용)
# =========================================================================
taps = np.arange(NUM_TOTAL_TAPS)
plt.figure(figsize=(11, 6))
plt.step(taps, lut_int, where='post', color='#ef4444', linewidth=1.5,
         label='Calibration LUT (cumulative code density)')
ideal = np.linspace(lut_int[lo], lut_int[hi], hi - lo + 1)
plt.plot(np.arange(lo, hi + 1), ideal, color='#3b82f6', ls='--', lw=1.2,
         label='Ideal linear ramp')
plt.title("Mode 0: Code-Density Calibration LUT", fontsize=14, fontweight='bold')
plt.xlabel("TDC Fine Index (Tap)", fontsize=12)
plt.ylabel("Calibrated time before edge (ps)", fontsize=12)
plt.grid(True, ls='--', alpha=0.6)
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(script_dir, "calib_lut_mode0.png"), dpi=150)
plt.show()
