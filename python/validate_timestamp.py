import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =========================================================================
# 캘리브레이션 검증: timestamp vs 위상 기준 선형성 (COE 적용 전/후 동일 방법)
# =========================================================================
# ILA 캡처 컬럼: final_ts_valid, aligned_fine_idx, final_timestamp_ps[47:0], current_loop_cnt
#
# 원리:
#   측정 fine = (-timestamp) mod 5000 = (5000 - timestamp % 5000) % 5000   ← ROM 통과 결과(ps)
#     (timestamp = coarse*5000 - calib_fine 이므로 coarse 성분이 소거됨)
#   참 시간   = loop_cnt * PHASE_STEP_PS                                     ← MMCM 위상 스텝
#   → fine vs loop_cnt 가 직선이면 선형(=교정 성공). 직선 잔차 = INL, 스텝간 Δ = DNL.
#
# 같은 스크립트로 before(선형 COE)·after(code-density COE) 캡처를 각각 처리해 비교.
T_PERIOD_PS   = 5000.0
PHASE_STEP_PS = 1000.0 / 56.0   # ≈ 17.857 ps/step (1GHz VCO 기준)

script_dir = os.path.dirname(os.path.abspath(__file__))

# 처리할 캡처 파일: (라벨, 파일명). 없으면 무시.
CAPTURES = [
    ("BEFORE (linear COE)", "before_capture.csv"),
    ("AFTER (code-density COE)", "after_capture.csv"),
]


def load_capture(path):
    """Vivado ILA CSV 로드 → (tap, timestamp, loop_cnt) valid 샘플만."""
    # 2번째 줄(Radix 선언)은 건너뜀
    df = pd.read_csv(path, skiprows=[1])
    cols = {c.lower(): c for c in df.columns}

    def find(*keys):
        for k in keys:
            for lc, orig in cols.items():
                if k in lc:
                    return orig
        return None

    c_valid = find('final_ts_valid', 'ts_valid', 'valid')
    c_tap   = find('aligned_fine_idx', 'fine_idx', 'tap')
    c_ts    = find('timestamp')
    c_loop  = find('loop_cnt', 'loop')

    if not all([c_ts, c_loop]):
        raise ValueError(f"필수 컬럼 없음. 발견: {list(df.columns)}")

    def to_int(s):
        s = str(s).strip()
        if s.lower().startswith('0x'):
            return int(s, 16)
        try:
            return int(s)                      # 10진 정수 (UNSIGNED radix)
        except ValueError:
            pass
        try:
            return int(round(float(s)))        # float 형식
        except ValueError:
            pass
        try:
            return int(s, 16)                  # 16진 (a-f 포함)
        except ValueError:
            return np.nan

    ts   = df[c_ts].map(to_int).to_numpy(dtype=float)
    loop = df[c_loop].map(to_int).to_numpy(dtype=float)
    tap  = df[c_tap].map(to_int).to_numpy(dtype=float) if c_tap else np.full_like(ts, np.nan)
    if c_valid:
        v = df[c_valid].map(to_int).to_numpy(dtype=float)
        m = v == 1
    else:
        m = np.ones_like(ts, dtype=bool)
    m &= ~np.isnan(ts) & ~np.isnan(loop)
    return tap[m], ts[m].astype(np.int64), loop[m].astype(int)


def analyze(label, tap, ts, loop):
    """loop_cnt별 측정 fine 평균 → 선형성(DNL/INL)."""
    # 측정 fine (ps): coarse 성분 제거
    fine = ((-ts) % 5000).astype(float)

    # loop_cnt별 평균 (한 위상 스텝의 여러 히트를 평균화)
    steps = np.unique(loop)
    fine_of_step = np.array([np.mean(fine[loop == s]) for s in steps])

    # 참 시간축 (스텝 시작을 0으로 정렬)
    true_t = (steps - steps.min()) * PHASE_STEP_PS

    # 위상 wrap 방지: fine이 5000 근처에서 접히면 언랩
    fine_uw = np.unwrap(fine_of_step / T_PERIOD_PS * 2 * np.pi) / (2 * np.pi) * T_PERIOD_PS

    # 직선 피팅 (측정 fine vs 참 시간)
    A = np.polyfit(true_t, fine_uw, 1)          # [기울기, 절편]
    fit = np.polyval(A, true_t)
    lsb_fit = abs(A[0]) * PHASE_STEP_PS         # 스텝당 측정 증가량(ps) → 유효 LSB

    # INL = (측정 - 직선) / 스텝당증가량
    inl = (fine_uw - fit) / (abs(A[0]) * PHASE_STEP_PS) if A[0] != 0 else fine_uw * 0
    # DNL = 스텝간 실제 증가 / 평균 증가 - 1
    d = np.diff(fine_uw)
    dnl = d / np.mean(d) - 1.0

    stats = dict(label=label, steps=steps, true_t=true_t, fine=fine_uw, fit=fit,
                 inl=inl, dnl=dnl, slope=A[0])
    return stats


def pp(x):
    return float(np.max(x) - np.min(x)) if len(x) else 0.0


# =========================================================================
# 실행
# =========================================================================
results = []
for label, name in CAPTURES:
    path = os.path.join(script_dir, name)
    if not os.path.exists(path):
        print(f"[skip] {name} 없음")
        continue
    tap, ts, loop = load_capture(path)
    print(f"[*] {label}: {name}  ({len(ts):,} valid samples, {len(np.unique(loop))} phase steps)")
    results.append(analyze(label, tap, ts, loop))

if not results:
    print("\n캡처 파일이 없습니다. ILA 캡처 후 before_capture.csv / after_capture.csv 로 저장하세요.")
    raise SystemExit

# --- 콘솔 요약 ---
print("\n" + "=" * 60)
print(" 📐 캘리브레이션 선형성 (timestamp vs MMCM 위상 기준)")
print("=" * 60)
print(f" {'':26}{'기울기':>10}{'INL P-P':>12}{'DNL P-P':>12}")
for r in results:
    print(f" {r['label']:26}{r['slope']:>10.3f}{pp(r['inl']):>11.3f}L{pp(r['dnl']):>11.3f}L")
print(f"\n (기울기 1.0 = 측정 ps가 참 위상시간과 1:1. INL/DNL 단위 = LSB)")
print("=" * 60 + "\n")

# --- 시각화 ---
fig, ax = plt.subplots(1, 3, figsize=(18, 5))
colors = ['#3b82f6', '#16a34a', '#ef4444', '#a855f7']

for i, r in enumerate(results):
    c = colors[i % len(colors)]
    ax[0].plot(r['true_t'], r['fine'], color=c, lw=1.3, label=r['label'])
    ax[1].plot(r['true_t'], r['inl'], color=c, lw=1.3, label=f"{r['label']} (P-P {pp(r['inl']):.2f})")
    ax[2].plot(r['true_t'][:-1], r['dnl'], color=c, lw=1.0, label=f"{r['label']} (P-P {pp(r['dnl']):.2f})")

# 이상 직선
if results:
    tt = results[0]['true_t']
    ax[0].plot(tt, tt, 'k--', lw=1, alpha=0.6, label='ideal (slope 1)')

ax[0].set_title("Measured fine vs Reference time", fontweight='bold')
ax[0].set_xlabel("Reference time = loop_cnt × 17.857 (ps)")
ax[0].set_ylabel("Measured fine (ps)")
ax[1].set_title("INL", fontweight='bold')
ax[1].set_xlabel("Reference time (ps)"); ax[1].set_ylabel("INL (LSB)")
ax[2].set_title("DNL", fontweight='bold')
ax[2].set_xlabel("Reference time (ps)"); ax[2].set_ylabel("DNL (LSB)")
for a in ax:
    a.grid(True, ls='--', alpha=0.5); a.legend(fontsize=9); a.axhline(0, color='k', lw=0.6, ls='--')

plt.suptitle("DPS Calibration Validation: Before vs After COE (same method)", fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(script_dir, "validate_timestamp_compare.png"), dpi=180)
plt.show()
