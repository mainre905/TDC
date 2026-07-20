import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

# ==========================================
# 1. 파일 경로 설정 및 데이터 로드
# ==========================================
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "iladata.csv")

print(f"데이터를 불러오는 중... 경로: {csv_filepath}")
# 두 번째 줄(UNSIGNED 등)을 건너뛰고 로드
df = pd.read_csv(csv_filepath, skiprows=[1])

# ILA CSV의 실제 컬럼명 (필요시 CSV 헤더에 맞게 수정하세요)
col_loop = 'current_loop_cnt[8:0]'
col_time = 'final_timestamp_ps[47:0]'

# 지수 형태 문자열 방어: float 거쳐서 int로 변환
loop_cnt = df[col_loop].astype(float).astype(int).values
timestamp_ps = df[col_time].astype(float).astype(int).values

# ==========================================
# 2. Coarse 시간 제거 (Modulo 5000)
# ==========================================
fine_time_ps = timestamp_ps % 5000

# ==========================================
# 3. Wrap-around 펴기 (Unwrapping)
# ==========================================
unwrapped_time = np.copy(fine_time_ps).astype(float)
offset = 0

for i in range(1, len(unwrapped_time)):
    diff = fine_time_ps[i] - fine_time_ps[i-1]
    if diff < -2500:
        offset += 5000
    elif diff > 2500:
        offset -= 5000
    unwrapped_time[i] += offset

# ==========================================
# 4. 이상적인 선형성(Ideal Line) 계산
# ==========================================
coef = np.polyfit(loop_cnt, unwrapped_time, 1) # 1차 방정식 피팅
ideal_line = np.polyval(coef, loop_cnt)

# ==========================================
# 5. INL (Integral Non-Linearity) 오차 도출
# ==========================================
inl_ps = unwrapped_time - ideal_line

# ==========================================
# ★ 6. 터미널 출력 (분석용 데이터) ★
# ==========================================
print("\n" + "="*50)
print(" 📊 TDC INL Analysis Results (Before Cal) ")
print("="*50)
print(f" - Valid Capture Points : {len(loop_cnt)} / 280 steps")
print(f" - Max INL Error        : {np.max(inl_ps):.2f} ps")
print(f" - Min INL Error        : {np.min(inl_ps):.2f} ps")
print(f" - Peak-to-Peak Error   : {np.max(inl_ps) - np.min(inl_ps):.2f} ps")
print(f" - Std Dev (RMS Error)  : {np.std(inl_ps):.2f} ps")
print("-" * 50)
print(" Raw INL Data for Analysis (Loop_cnt, INL_ps):")
print("-" * 50)

# 콤마로 구분하여 출력 (채팅창에 복사하기 좋도록)
out_str = []
for l, i in zip(loop_cnt, inl_ps):
    out_str.append(f"{l}:{i:.2f}")

# 5개씩 묶어서 가독성 좋게 출력
for i in range(0, len(out_str), 5):
    print(", ".join(out_str[i:i+5]))
print("="*50 + "\n")

# ==========================================
# 7. 결과 그래프 출력
# ==========================================
plt.figure(figsize=(12, 8))

plt.subplot(2, 1, 1)
plt.plot(loop_cnt, unwrapped_time, 'b.-', label='Measured (Uncalibrated)')
plt.plot(loop_cnt, ideal_line, 'r--', label='Ideal Linear Trend')
plt.title('Absolute Time Transfer Curve (Before Calibration)')
plt.ylabel('Time (ps)')
plt.legend()
plt.grid(True)

plt.subplot(2, 1, 2)
plt.plot(loop_cnt, inl_ps, 'g.-', label='INL Error')
plt.axhline(0, color='r', linestyle='--')
plt.title('INL Error (ps)')
plt.xlabel('MMCM Loop Count (Phase Step)')
plt.ylabel('Error (ps)')

max_inl, min_inl = np.max(inl_ps), np.min(inl_ps)
plt.text(loop_cnt[0], max_inl * 0.8, f" Max: {max_inl:.1f} ps\n Min: {min_inl:.1f} ps\n P2P: {max_inl-min_inl:.1f} ps", 
         bbox=dict(facecolor='white', alpha=0.8))

plt.legend()
plt.grid(True)

plt.tight_layout()
plt.show()