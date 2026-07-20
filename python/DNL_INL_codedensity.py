import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =========================================================================
# 0. 설정
# =========================================================================
# Code-Density 방식 TDC 캘리브레이션 전/후 DNL·INL 비교 (Mode 0 DPS / Mode 1 Ring Osc 공용).
#   자극 방식 무관 — tap 히스토그램(Tap_Index, Hit_Count)만 받아 code density로 계산.
#   BEFORE : raw code density  (각 tap 히트수 ∝ bin 폭)
#   AFTER  : Method B — cal LUT의 누적 시간축 위에서 val 히트를 균일 격자로
#            fractional re-binning (bin merging/interpolation). DNL·INL 개선.
T_PERIOD_PS    = 5000.0    # tdc_clk 한 주기 (200MHz)
NUM_TOTAL_TAPS = 320
EDGE_TRIM_FRAC = 0.05      # 유효 구간 양 끝단 컷 (평균의 5% 미만)

# cal/val 분리 (같은 빌드의 독립 측정 → 순환논리 회피)
CAL_CSV = "tap_histogram_20260720_191308.csv"   # LUT(교정) 생성용
VAL_CSV = "tap_histogram_20260720_195432.csv"   # 평가용

# AFTER 출력 격자 수. None이면 유효 code 수와 동일(=LSB 유지). 작게 주면 bin merging(해상도↓, DNL↑개선).
M_OUT = None

script_dir = os.path.dirname(os.path.abspath(__file__))


def load_hist(name):
    """tap_histogram CSV → 길이 NUM_TOTAL_TAPS 카운트 배열 (빠진 tap은 0)."""
    path = os.path.join(script_dir, name)
    df = pd.read_csv(path)
    ct = [c for c in df.columns if 'tap' in c.lower()][0]
    cc = [c for c in df.columns if 'count' in c.lower() or 'hit' in c.lower()][0]
    out = np.zeros(NUM_TOTAL_TAPS, dtype=float)
    for tap, cnt in zip(pd.to_numeric(df[ct], errors="coerce"),
                        pd.to_numeric(df[cc], errors="coerce")):
        if not (np.isnan(tap) or np.isnan(cnt)) and 0 <= int(tap) < NUM_TOTAL_TAPS:
            out[int(tap)] = cnt
    return out


def valid_range(counts, frac):
    """양 끝단만 트리밍한 유효 구간 [lo, hi]."""
    nz = counts[counts > 0]
    th = nz.mean() * frac
    lo = 0
    while lo < NUM_TOTAL_TAPS and counts[lo] < th:
        lo += 1
    hi = NUM_TOTAL_TAPS - 1
    while hi > lo and counts[hi] < th:
        hi -= 1
    return lo, hi


def rebin_fractional(edges, counts_val, M, T):
    """cal 누적 edge(길이 K+1) 위의 각 code 히트(counts_val)를
    폭에 비례해 균일 분포로 M개 균일 시간 격자에 재분배."""
    out = np.zeros(M)
    bw = T / M
    K = len(counts_val)
    for i in range(K):
        c = counts_val[i]
        if c <= 0:
            continue
        lo_t, hi_t = edges[i], edges[i + 1]
        w = hi_t - lo_t
        if w <= 0:                                   # 폭 0 code(측정 안 됨) → 점으로 투입
            out[min(int(lo_t / bw), M - 1)] += c
            continue
        k0 = int(lo_t / bw)
        k1 = min(int((hi_t - 1e-9) / bw), M - 1)
        for k in range(k0, k1 + 1):
            ov = min(hi_t, (k + 1) * bw) - max(lo_t, k * bw)  # 격자 k와의 겹침
            if ov > 0:
                out[k] += c * ov / w
    return out


# =========================================================================
# 1. 데이터 로드 & 유효 구간
# =========================================================================
cal = load_hist(CAL_CSV)
val = load_hist(VAL_CSV)
print(f"[*] CAL: {CAL_CSV}\n[*] VAL: {VAL_CSV}")

lo, hi = valid_range(cal, EDGE_TRIM_FRAC)
N = hi - lo + 1
LSB = T_PERIOD_PS / N

h_cal = cal[lo:hi + 1]
h_val = val[lo:hi + 1]

# =========================================================================
# 2. BEFORE — raw code density (val 기준)
# =========================================================================
w_before   = h_val / h_val.sum() * T_PERIOD_PS
dnl_before = w_before / LSB - 1.0
inl_before = np.cumsum(dnl_before)

# =========================================================================
# 3. AFTER — Method B (cal LUT 누적축 위에서 val 재격자화)
# =========================================================================
edges_cal = np.concatenate([[0.0], np.cumsum(h_cal) / h_cal.sum() * T_PERIOD_PS])  # 길이 N+1
M = N if M_OUT is None else int(M_OUT)
LSB_B = T_PERIOD_PS / M

merged    = rebin_fractional(edges_cal, h_val, M, T_PERIOD_PS)
dnl_after = merged / merged.mean() - 1.0
inl_after = np.cumsum(dnl_after)

# =========================================================================
# 4. 콘솔 요약
# =========================================================================
def pp(x):
    return float(np.max(x) - np.min(x))

print("\n" + "=" * 60)
print(" 📊 Code-Density 캘리브레이션 전/후 DNL·INL")
print("=" * 60)
print(f" 유효 구간   : tap {lo}~{hi} ({N} bins)   raw LSB = {LSB:.3f} ps")
print(f" AFTER 격자  : {M} bins   LSB_B = {LSB_B:.3f} ps")
print("-" * 60)
print(f" {'':8}{'DNL min':>10}{'DNL max':>10}{'DNL P-P':>10}{'INL P-P':>10}")
print(f" {'BEFORE':8}{dnl_before.min():>10.3f}{dnl_before.max():>10.3f}"
      f"{pp(dnl_before):>10.3f}{pp(inl_before):>10.3f}")
print(f" {'AFTER':8}{dnl_after.min():>10.3f}{dnl_after.max():>10.3f}"
      f"{pp(dnl_after):>10.3f}{pp(inl_after):>10.3f}")
print("-" * 60)
print(f" 개선   DNL P-P : {pp(dnl_before):.3f} → {pp(dnl_after):.3f} LSB"
      f"  ({pp(dnl_after)/pp(dnl_before)*100:.1f}%)")
print(f"        INL P-P : {pp(inl_before):.3f} → {pp(inl_after):.3f} LSB"
      f"  ({pp(inl_after)/pp(inl_before)*100:.1f}%)")
print("=" * 60 + "\n")

# =========================================================================
# 5. 시각화 (2x2: DNL/INL × before/after)
# =========================================================================
fig, ax = plt.subplots(2, 2, figsize=(15, 8), sharex='col')
tb = np.arange(lo, hi + 1)
ta = np.arange(M)

ax[0, 0].plot(tb, dnl_before, color='#3b82f6', lw=1.0)
ax[0, 0].fill_between(tb, dnl_before, 0, color='#3b82f6', alpha=0.3)
ax[0, 0].set_title(f"BEFORE  DNL  (P-P {pp(dnl_before):.2f} LSB)", fontweight='bold')
ax[0, 0].set_ylabel("DNL (LSB)")

ax[0, 1].plot(ta, dnl_after, color='#16a34a', lw=1.0)
ax[0, 1].fill_between(ta, dnl_after, 0, color='#16a34a', alpha=0.3)
ax[0, 1].set_title(f"AFTER (B)  DNL  (P-P {pp(dnl_after):.2f} LSB)", fontweight='bold')

ax[1, 0].plot(tb, inl_before, color='#ef4444', lw=1.2)
ax[1, 0].fill_between(tb, inl_before, 0, color='#ef4444', alpha=0.3)
ax[1, 0].set_title(f"BEFORE  INL  (P-P {pp(inl_before):.2f} LSB)", fontweight='bold')
ax[1, 0].set_xlabel("TDC Fine Index (Tap)")
ax[1, 0].set_ylabel("INL (LSB)")

ax[1, 1].plot(ta, inl_after, color='#ea580c', lw=1.2)
ax[1, 1].fill_between(ta, inl_after, 0, color='#ea580c', alpha=0.3)
ax[1, 1].set_title(f"AFTER (B)  INL  (P-P {pp(inl_after):.2f} LSB)", fontweight='bold')
ax[1, 1].set_xlabel("Calibrated uniform bin")

for a in ax.flat:
    a.axhline(0, color='black', lw=0.8, ls='--')
    a.grid(True, ls='--', alpha=0.5)

plt.suptitle("Code-Density TDC Calibration: Before vs After",
             fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(script_dir, "dnl_inl_dps_compare.png"), dpi=200)
plt.show()
