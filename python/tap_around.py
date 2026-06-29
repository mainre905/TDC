import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import platform

# ==========================================
# ★ 한글 폰트 깨짐 방지 설정
# ==========================================
if platform.system() == 'Windows':
    plt.rcParams['font.family'] = 'Malgun Gothic' # 윈도우: 맑은 고딕
elif platform.system() == 'Darwin': # Mac
    plt.rcParams['font.family'] = 'AppleGothic'
else:
    plt.rcParams['font.family'] = 'NanumGothic' # 리눅스
plt.rcParams['axes.unicode_minus'] = False
# ==========================================

# --- 물리적 상수 정의 ---
TAP_DELAY_PS = 18.0     # 탭 1개당 평균 지연 시간 (약 18ps)
CLOCK_CYCLE_PS = 5000.0 # 200MHz 클럭의 1주기 (5000ps)
STEP_PS = 17.85         # MMCM 스윕 1스텝당 밀어내는 시간

# 특정 cnt(스텝)에서의 사진기 B의 위치 (수학적 역산)
# cnt=63일 때 사진기 B가 4986ps (277번 탭)에 있다고 가정
BASE_TIME_B = 4986.0 - (63 * STEP_PS) 

# 시뮬레이션할 3개의 주요 장면
scenarios = [
    {"cnt": 1,  "desc": "[장면 1] 스윕 시작점 (Tap 214)"},
    {"cnt": 63, "desc": "[장면 2] 5ns 한계선 도달 (Tap 277)"},
    {"cnt": 64, "desc": "[장면 3] 마법의 교대식 (Tap 1)"}
]

fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
plt.subplots_adjust(hspace=0.4)

for i, ax in enumerate(axes):
    scene = scenarios[i]
    cnt = scene["cnt"]
    
    # 1. 시간 계산
    added_delay = cnt * STEP_PS
    time_B = BASE_TIME_B + added_delay           # 사진기 B의 터지는 시간
    time_A = time_B - CLOCK_CYCLE_PS             # 사진기 A는 항상 B보다 5000ps 먼저 터짐
    
    # 누가 유효한 사진기인가? (0ps 이후에 가장 먼저 터진 사진기)
    if time_A > 0:
        active_camera = "A"
        measured_time = time_A
    else:
        active_camera = "B"
        measured_time = time_B
        
    measured_tap = int(measured_time / TAP_DELAY_PS)
    
    # 2. 배경 그리기 (T<0 구간은 데이터 출발 전이므로 어둡게 칠함)
    ax.axvspan(-2000, 0, color='gray', alpha=0.2)
    ax.axvline(0, color='black', linewidth=2, linestyle='--', label="T=0 (데이터 출발점)")
    
    # 3. 데이터(선수) 그리기 (0ps부터 오른쪽으로 달려감)
    ax.add_patch(patches.Rectangle((0, 0.2), 6000, 0.6, color='#22c55e', alpha=0.3))
    ax.text(3000, 0.5, "Data Signal (Runner) moving through Taps 👉", 
            fontsize=12, color='green', fontweight='bold', ha='center')

    # 4. 사진기 A와 B 그리기
    # 사진기 A (빨간색)
    ax.axvline(time_A, color='#ef4444', linewidth=3, label="Camera A (Clock N)")
    ax.text(time_A, 0.9, f"📸 Camera A\n({time_A:.1f}ps)", color='#ef4444', ha='center', fontweight='bold')
    
    # 사진기 B (파란색)
    ax.axvline(time_B, color='#3b82f6', linewidth=3, label="Camera B (Clock N+1)")
    ax.text(time_B, 0.9, f"📸 Camera B\n({time_B:.1f}ps)", color='#3b82f6', ha='center', fontweight='bold')
    
    # 5. 측정된 결과(찰칵!) 표시
    ax.plot(measured_time, 0.5, marker='*', color='gold', markersize=25, markeredgecolor='black')
    
    # 설명 텍스트
    info_text = (
        f"Step (cnt) = {cnt}\n"
        f"Active Camera = {active_camera}\n"
        f"Measured Time = {measured_time:.1f} ps\n"
        f"TDC Fine Index = Tap {measured_tap}"
    )
    ax.text(1.02, 0.5, info_text, transform=ax.transAxes, fontsize=11, 
            verticalalignment='center', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # 축 설정
    ax.set_title(scene["desc"], fontsize=14, fontweight='bold', pad=10)
    ax.set_yticks([]) # Y축 눈금 숨김
    ax.set_xlim(-1500, 5500)
    
    if i == 0:
        ax.legend(loc='upper left')

# X축 탭 번호 매핑 (밑에 표시)
axes[2].set_xlabel("Absolute Time (ps)", fontsize=12, fontweight='bold')
secax = axes[2].secondary_xaxis('bottom')
secax.spines['bottom'].set_position(('outward', 40))
secax.set_xticks(np.arange(0, 5500, 1000))
secax.set_xticklabels([f"Tap {int(t/TAP_DELAY_PS)}" for t in np.arange(0, 5500, 1000)])
secax.set_xlabel("Approximate TDC Tap Index", fontsize=12, color='dimgray')

plt.suptitle("TDC Wrap-around Mechanism: 두 대의 사진기(클럭) 이야기", fontsize=18, fontweight='black', y=0.98)
plt.savefig("two_cameras_simulation.png", bbox_inches='tight', dpi=300)
print("✅ 완료! 한글 깨짐 없이 'two_cameras_simulation.png' 이미지가 생성되었습니다.")
# plt.show()