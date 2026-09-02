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
# ★ 2026-08-22 수정 — CAL_CSV 를 명시 지정한다.
#   왜 : None(자동 최신) 은 위험하다. 방금 만든 val 파일이 최신이면 val 로 LUT 를
#        만들게 되고, 그러면 cal/val 분리가 깨져 교정 품질이 아니라 자기 일관성을 재게 된다.
#        Histogram.py 가 출력명을 입력명에서 물려받도록 바뀌었으므로(2026-08-22) 이름이
#        결정적이다.
CAL_CSV = "tap_histogram_ro_cal.csv"   # 집 보드 2026-08-22 Build 1 cal

# =========================================================================
# ★ 2026-09-02 추가 — 유효탭 상한/하한 수동 지정 (VALID_TAP_LO / VALID_TAP_HI)
#
#   [무엇이 문제였나]
#   아래 §2 의 자동 검출(EDGE_TRIM_FRAC = 평균의 5% 미만 끝단 컷)은
#   "히트가 충분히 있는 칸"을 유효로 잡는다. 그런데 링오실레이터(Mode 1)는
#   위상 스윕(Mode 0)이 한 주기 안에 도달하지 못하는 끝단 칸에도 히트를 쌓는다.
#   Mode 1 은 히트가 계속 반복되어 캐리가 어쩌다 평소보다 빨리 도는 순간까지
#   잡아내지만, Mode 0 은 위상을 5000 ps 딱 한 바퀴만 훑으므로 구조적으로
#   그 칸들에 닿을 수 없기 때문이다.
#
#   [왜 이게 LUT 를 망가뜨리나]
#   코드밀도 LUT 는 5000 ps 를 유효 칸들에 나눠 배분한다. 실제로 한 주기 안에
#   쓰이지 않는 칸에도 몫을 떼주면 나머지 칸이 전부 조금씩 좁게 배정되고,
#   LUT 는 누적값이라 그 편향이 체인을 따라 쌓여 INL 을 오히려 악화시킨다.
#
#   [실측 근거 — 집 보드 XC7Z010, 2026-08-23~24]
#     자동검출(298칸, 탭 2~299) : Mode 0 INL rms 19.93 ps, 클럭 경계 점프 -26.5 ps
#     수동지정(293칸, 탭 2~294) : Mode 0 INL rms 10.00 ps, 클럭 경계 점프  +0.6 ps
#     참고) 무교정 등간격             : Mode 0 INL rms 15.68 ps
#   자동검출 쪽은 무교정보다도 나빴다. 상세는 Markdown/2026-08-24_report.md §4.
#
#   [값을 어떻게 정하나 — 보드마다 다시 구해야 한다]
#   ZedBoard(XC7Z020)는 다른 칩이므로 293 을 그대로 쓰면 안 된다. 순서는:
#     (1) Mode 1 빌드로 ro_cal/ro_val1/ro_val2 히스토그램 확보
#     (2) Mode 0 빌드(선형 COE)로 전달함수 캡처 -> BEFORE 기준선
#     (3) 아래 VALID_TAP_HI 를 여러 값으로 바꿔가며 COE 를 만들고,
#         Mode 0 전달함수에서 "클럭 경계 점프"가 0 에 가장 가까운 값을 채택한다.
#         경계 점프는 INL 을 몰라도 잴 수 있는 독립적인 양이라 순환논법이 아니다.
#         (INL 최소점과 경계점프 0 이 같은 곳에서 만나는 것을 집 보드에서 확인했다)
#
#   None 이면 기존 자동 검출을 그대로 쓴다.
VALID_TAP_LO = None    # 예: 2     (None = 자동)
VALID_TAP_HI = None    # 예: 293   (None = 자동)  ← 집 보드는 293, ZedBoard 는 재측정 필요
# =========================================================================

# 출력 COE 구분 태그 (DPS vs Ring Osc 비교용 보관 파일명).
#   → tdc_calib_<SOURCE_TAG>_rom.coe 로 별도 보관.
#   → 동시에 하드웨어 IP가 참조하는 canonical(tdc_calib_mode0_rom.coe)도 항상 함께 생성.
SOURCE_TAG = "ringosc"   # 예: "dps"(Mode 0) / "ringosc"(Mode 1)

script_dir = os.path.dirname(os.path.abspath(__file__))

if CAL_CSV:
    csv_filepath = os.path.join(script_dir, CAL_CSV)
else:
    # ★ 2026-08-22 : 특정 파일명이 하드코딩돼 있던 것을 원래의 와일드카드로 되돌림.
    #   (CAL_CSV 를 명시하면 이 분기는 실행되지 않는다)
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

# ★ 2026-09-02 : 위에서 자동 검출한 값을 수동 지정으로 덮어쓴다.
#   지정 이유와 값 정하는 법은 §0 의 VALID_TAP_LO / VALID_TAP_HI 주석 참조.
_auto_lo, _auto_hi = lo, hi
if VALID_TAP_LO is not None:
    lo = int(VALID_TAP_LO)
if VALID_TAP_HI is not None:
    hi = int(VALID_TAP_HI)
if (lo, hi) != (_auto_lo, _auto_hi):
    print(f"[!] 유효구간 수동 지정 : 자동 {_auto_lo}~{_auto_hi} ({_auto_hi-_auto_lo+1}칸)"
          f"  ->  지정 {lo}~{hi} ({hi-lo+1}칸)")
else:
    print(f"[*] 유효구간 자동 검출 : {lo}~{hi} ({hi-lo+1}칸)")

if not (0 <= lo < hi < NUM_TOTAL_TAPS):
    print(f"❌ 유효구간이 잘못됐습니다: lo={lo}, hi={hi}")
    exit()
if counts_full[lo:hi + 1].sum() <= 0:
    print(f"❌ 지정한 구간 {lo}~{hi} 에 히트가 없습니다.")
    exit()

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
#   canonical : 하드웨어 IP가 참조하는 고정 이름 (빌드용, 항상 생성)
#   tagged    : DPS/RingOsc 구분 보관용 (SOURCE_TAG)
canonical_coe = os.path.join(script_dir, "tdc_calib_mode0_rom.coe")
tagged_coe    = os.path.join(script_dir, f"tdc_calib_{SOURCE_TAG}_rom.coe")

for coe_filepath in (canonical_coe, tagged_coe):
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
print(f" ✅ 빌드용(canonical) : {os.path.basename(canonical_coe)}")
print(f" ✅ 보관용(tagged)    : {os.path.basename(tagged_coe)}")
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
