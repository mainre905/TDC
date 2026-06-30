import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

# ==========================================
# 1. 파일 설정 및 데이터 로드
# ==========================================
report_filename = 'tdc_analysis_report.txt'


# 1. 현재 실행 중인 파이썬 스크립트 파일(.py)이 있는 폴더의 절대 경로를 가져옵니다.
script_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 그 폴더 경로와 'iladata.csv' 파일 이름을 합쳐서 정확한 전체 경로를 만듭니다.
csv_filepath = os.path.join(script_dir, 'iladata_ring.csv')

print("CSV 데이터를 불러오고 분석하는 중...")
# 첫 번째 데이터 행(인덱스 1, Radix 정보) 제외하고 로드
df = pd.read_csv(csv_filepath, skiprows=[1])
df.columns = df.columns.str.strip()

# 열 이름 식별
valid_col = [col for col in df.columns if 'final_ts_valid' in col][0]
fine_idx_col = [col for col in df.columns if 'aligned_fine_idx' in col][0]
ts_col = [col for col in df.columns if 'final_timestamp_ps' in col][0]

# ==========================================
# 2. 데이터 처리 및 필터링
# ==========================================
# Valid == 1 인 유효 데이터만 추출
df[valid_col] = pd.to_numeric(df[valid_col], errors='coerce')
valid_hits = df[df[valid_col] == 1].copy()

total_samples = len(df)
valid_count = len(valid_hits)

if valid_count == 0:
    print("유효한(Valid=1) 데이터가 없습니다.")
    exit()

# 보정 전(Raw) 데이터: 0 ~ 320 탭 번호
raw_data = valid_hits[fine_idx_col].values

# 보정 후(Calibrated) 데이터: 최종 절대 시간을 5ns(5000ps)로 나눈 나머지 위상 시간
# 결과값 범위: 0 ~ 4999 ps
valid_hits['calibrated_fine_ps'] = valid_hits[ts_col] % 5000
calib_data = valid_hits['calibrated_fine_ps'].values

# ==========================================
# 3. 통계 계산 (균일도 분석)
# ==========================================
# 보정 전 히스토그램 연산 (321개 구간)
raw_hist, _ = np.histogram(raw_data, bins=321, range=(0, 321))
raw_mean = np.mean(raw_hist)
raw_std = np.std(raw_hist)

# 보정 후 히스토그램 연산 (100개 구간, 구간당 50ps)
calib_hist, _ = np.histogram(calib_data, bins=100, range=(0, 5000))
calib_mean = np.mean(calib_hist)
calib_std = np.std(calib_hist)

# 상대 표준편차 (CV = 편차/평균) - 값이 작을수록 평평(Uniform)함을 의미
raw_cv = (raw_std / raw_mean) * 100 if raw_mean != 0 else 0
calib_cv = (calib_std / calib_mean) * 100 if calib_mean != 0 else 0

# ==========================================
# 4. 분석 결과 TXT 파일로 출력
# ==========================================
with open(report_filename, 'w', encoding='utf-8') as f:
    f.write("========================================================\n")
    f.write("             TDC 캘리브레이션 분석 리포트               \n")
    f.write("========================================================\n\n")
    
    f.write("[1. 데이터 추출 요약]\n")
    f.write(f"- 전체 캡처된 샘플 수 : {total_samples:,} 개\n")
    f.write(f"- 유효한 Hit (Valid=1): {valid_count:,} 개\n\n")
    
    f.write("[2. 보정 전 (Raw Fine Index) 통계]\n")
    f.write("  * 링 오실레이터가 탭을 때린 날것의 횟수 (예상: 삐쭉삐쭉함)\n")
    f.write(f"  - 평균 Hit 수 (Bin당)   : {raw_mean:.1f}\n")
    f.write(f"  - 최대 Hit 수 (제일 넓은 탭): {np.max(raw_hist)}\n")
    f.write(f"  - 최소 Hit 수 (제일 좁은 탭): {np.min(raw_hist)}\n")
    f.write(f"  - 편차(Standard Dev)    : {raw_std:.1f} (평균 대비 {raw_cv:.1f}% 요동침)\n\n")

    f.write("[3. 보정 후 (MMCM ROM 적용 후 위상 시간) 통계]\n")
    f.write("  * 최종 절대 시간을 5ns 단위로 잘랐을 때의 분포 (예상: 평평함)\n")
    f.write(f"  - 평균 Hit 수 (Bin당)   : {calib_mean:.1f}\n")
    f.write(f"  - 최대 Hit 수           : {np.max(calib_hist)}\n")
    f.write(f"  - 최소 Hit 수           : {np.min(calib_hist)}\n")
    f.write(f"  - 편차(Standard Dev)    : {calib_std:.1f} (평균 대비 {calib_cv:.1f}% 요동침)\n\n")

    f.write("[4. 결론 및 해석]\n")
    if calib_cv < raw_cv:
        f.write(f"  => MMCM 캘리브레이션 적용 후 데이터의 요동침이 {raw_cv:.1f}%에서 {calib_cv:.1f}%로 감소했습니다.\n")
        f.write("  => 캘리브레이션(ROM)이 정상적으로 작동하여 선형성(Linearity)이 개선되었습니다.\n\n")
    else:
        f.write("  => 경고: 캘리브레이션 후 데이터가 더 불균일합니다. ROM 데이터를 확인하세요.\n\n")

    f.write("[5. 상위 10개 유효 데이터 샘플 (ps 단위)]\n")
    f.write("   Hit_Seq | Timestamp (ps) | Raw Index | Calibrated Phase (0~4999ps)\n")
    f.write("   ------------------------------------------------------------------\n")
    
    sample_df = valid_hits[[ts_col, fine_idx_col, 'calibrated_fine_ps']].head(10)
    for i, (_, row) in enumerate(sample_df.iterrows()):
        f.write(f"      {i:02d}   | {int(row[ts_col]):14d} | {int(row[fine_idx_col]):9d} | {int(row['calibrated_fine_ps']):7d} \n")

print(f"\n분석이 완료되었습니다. 결과가 '{report_filename}'에 저장되었습니다.")

# ==========================================
# 5. 데이터 시각화 (그래프 출력)
# ==========================================
plt.style.use('default')
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

# 보정 전 그래프
ax1.hist(raw_data, bins=321, range=(0, 321), color='royalblue', edgecolor='black', alpha=0.7)
ax1.set_title(f'Raw Tap Index Distribution (Before Calibration) - CV: {raw_cv:.1f}%', fontsize=13)
ax1.set_xlabel('Raw Tap Index (0 ~ 320)', fontsize=11)
ax1.set_ylabel('Hit Count', fontsize=11)
ax1.grid(axis='y', linestyle='--', alpha=0.7)

# 보정 후 그래프
ax2.hist(calib_data, bins=100, range=(0, 5000), color='seagreen', edgecolor='black', alpha=0.7)
ax2.set_title(f'Calibrated Time Distribution in 5ns (After MMCM ROM) - CV: {calib_cv:.1f}%', fontsize=13)
ax2.set_xlabel('Time within 1 Clock Cycle (0 ~ 4999 ps)', fontsize=11)
ax2.set_ylabel('Hit Count', fontsize=11)
ax2.grid(axis='y', linestyle='--', alpha=0.7)

plt.tight_layout()
# 그래프 이미지를 파일로도 저장
plt.savefig('tdc_calibration_result.png', dpi=150)
plt.show()