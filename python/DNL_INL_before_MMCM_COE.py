import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =========================================================================
# 1. 설정 및 데이터 로드
# =========================================================================
T_PERIOD_PS    = 5000.0   # tdc_clk 한 주기 (200MHz)
EDGE_TRIM_FRAC = 0.05     # 끝단 컷 임계 (평균의 5% 미만인 양 끝 bin 제거)
                          # 1%로 두면 마지막 tap 293(4,477개)이 살아남아 최악 DNL로 잡히는데,
                          # 이 bin은 자기 그룹(tap%4==1, 평균 350,898) 대비 1.3%에 불과한
                          # '주기 경계에 잘린 bin'이라 하드웨어 특성이 아님.
                          # 5%~10% 구간에서 결과가 동일하게 수렴함(tap 1~292, INL P-P 8.320).
CSV_NAME       = None     # None이면 가장 최근 tap_histogram_*.csv 자동 선택

script_dir = os.path.dirname(os.path.abspath(__file__))

if CSV_NAME:
    csv_filepath = os.path.join(script_dir, CSV_NAME)
else:
    cands = sorted(glob.glob(os.path.join(script_dir, "tap_histogram_*.csv")))
    if not cands:
        print("❌ tap_histogram_*.csv 가 없습니다. Histogram.py를 먼저 실행하세요.")
        exit()
    csv_filepath = cands[-1]

print(f"[*] Reading: {os.path.basename(csv_filepath)}")

try:
    df = pd.read_csv(csv_filepath)
except FileNotFoundError:
    print(f"❌ '{csv_filepath}' 파일을 찾을 수 없습니다.")
    exit()

col_tap   = [c for c in df.columns if 'tap' in c.lower()][0]
col_count = [c for c in df.columns if 'count' in c.lower() or 'hit' in c.lower()][0]

taps   = pd.to_numeric(df[col_tap],   errors="coerce").to_numpy()
counts = pd.to_numeric(df[col_count], errors="coerce").to_numpy().astype(float)

mask = ~np.isnan(taps) & ~np.isnan(counts)
taps, counts = taps[mask], counts[mask]

# =========================================================================
# 2. 유효 구간 검출 (★ 양 끝단에서만 트리밍)
# =========================================================================
# 반드시 제외해야 하는 구간:
#   tap 0     : 스냅샷 조건이 tap[0]==1 이라 popcount=0 이 원천적으로 불가능 → 항상 빈 칸
#   끝단 taps : 딜레이라인(320탭 ≈ 5.4ns)이 1주기(5ns)보다 길어 도달 불가
# 포함하면 LSB가 5000/320=15.6ps로 오산되고, 빈 bin이 DNL=-1로 잡혀 INL이 30 LSB까지 폭주함.
#
# ★ 내부의 좁은 bin(예: tap 34 = 1,654개)은 실제 CARRY4 하드웨어 특성이므로
#   절대 제거하지 않는다. 그래서 '양 끝'에서만 잘라낸다.
nz = counts[counts > 0]
if nz.size == 0:
    print("❌ 유효한 데이터가 없습니다.")
    exit()

thresh = nz.mean() * EDGE_TRIM_FRAC
lo = 0
while lo < len(counts) and counts[lo] < thresh:
    lo += 1
hi = len(counts) - 1
while hi > lo and counts[hi] < thresh:
    hi -= 1

v_taps   = taps[lo:hi+1]
v_counts = counts[lo:hi+1]
n_bins   = len(v_taps)

# =========================================================================
# 3. Code Density 방식 DNL / INL 계산
# =========================================================================
# 위상 스윕이 한 주기를 균일하게 훑으므로, 각 bin에 쌓인 히트 수는 그 bin의 폭에 비례한다.
total      = v_counts.sum()
bin_widths = v_counts / total * T_PERIOD_PS   # 각 bin의 실제 폭 (ps)
LSB_ps     = T_PERIOD_PS / n_bins             # 이상적 1 LSB

DNL = bin_widths / LSB_ps - 1.0
INL = np.cumsum(DNL)      # 누적합. sum(DNL)=0 이므로 양 끝이 0으로 수렴함

# =========================================================================
# 4. 논문용 DNL / INL 시각화
# =========================================================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

ax1.plot(v_taps, DNL, color='#3b82f6', linewidth=1.2, alpha=0.9, label='DNL')
ax1.fill_between(v_taps, DNL, 0, color='#3b82f6', alpha=0.3)
ax1.set_title(f"Before Calibration: DNL (Code Density, LSB = {LSB_ps:.3f} ps)",
              fontsize=14, fontweight='bold')
ax1.set_ylabel("DNL (LSB)", fontsize=12)
ax1.axhline(0, color='black', linewidth=1, linestyle='--')
ax1.grid(True, linestyle='--', alpha=0.6)

ax2.plot(v_taps, INL, color='#ef4444', linewidth=1.5, label='INL')
ax2.fill_between(v_taps, INL, 0, color='#ef4444', alpha=0.3)
ax2.set_title("Before Calibration: INL", fontsize=14, fontweight='bold')
ax2.set_xlabel("TDC Fine Index (Tap)", fontsize=12)
ax2.set_ylabel("INL (LSB)", fontsize=12)
ax2.axhline(0, color='black', linewidth=1, linestyle='--')
ax2.grid(True, linestyle='--', alpha=0.6)

dnl_max, dnl_min = np.max(DNL), np.min(DNL)
inl_max, inl_min = np.max(INL), np.min(INL)

stats_text = (f"Valid : tap {v_taps[0]} ~ {v_taps[-1]} ({n_bins} bins)\n"
              f"Max DNL: {dnl_max:+.3f} LSB\n"
              f"Min DNL: {dnl_min:+.3f} LSB\n"
              f"Max INL: {inl_max:+.3f} LSB\n"
              f"Min INL: {inl_min:+.3f} LSB")
ax2.text(0.02, 0.05, stats_text, transform=ax2.transAxes, fontsize=11,
         bbox=dict(facecolor='white', edgecolor='black', alpha=0.9, boxstyle='round,pad=0.5'))

plt.tight_layout()

png_filepath = os.path.join(script_dir, "dnl_inl_before_calib.png")
plt.savefig(png_filepath, dpi=300)
print(f"✅ 이미지 저장: {png_filepath}")

# =========================================================================
# 5. 콘솔 결과
# =========================================================================
print("\n📊 [교정 전 하드웨어 선형성(Before Calibration)]")
print(f"▶ 유효 구간   : tap {v_taps[0]} ~ {v_taps[-1]}  ({n_bins} bins)")
print(f"▶ 총 히트     : {int(total):,}")
print(f"▶ 평균 LSB    : {LSB_ps:.3f} ps")
print(f"▶ DNL 범위    : {dnl_min:+.3f} ~ {dnl_max:+.3f} LSB (P-P: {dnl_max - dnl_min:.3f})")
print(f"▶ INL 범위    : {inl_min:+.3f} ~ {inl_max:+.3f} LSB (P-P: {inl_max - inl_min:.3f})")
worst = [int(t) for t in v_taps[np.argsort(DNL)[:5]]]
print(f"▶ 최악 DNL tap: {worst}")
print("==================================================\n")

plt.show()
