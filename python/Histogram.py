import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime  # 날짜 및 시간 생성을 위한 라이브러리 추가

# ---------------------------------------------------------
# 1. 파일 경로 설정
# ---------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filepath = os.path.join(script_dir, "iladata.csv")

def main():
    print(f"[*] Reading data from: {csv_filepath}")
    
    try:
        # Vivado CSV는 보통 2번째 줄(인덱스 1)에 'Hex', 'Unsigned' 등 Radix 정보가 있어 파싱 에러를 유발하므로 무시
        df = pd.read_csv(csv_filepath, skiprows=[1])
    except FileNotFoundError:
        print("[!] Error: 'iladata.csv' file not found in the script directory.")
        return
    except Exception as e:
        print(f"[!] Error reading CSV: {e}")
        return

    # ---------------------------------------------------------
    # 2. ILA 데이터 컬럼 매핑 (실제 Vivado 네트 이름으로 매핑)
    # ---------------------------------------------------------
    addr_col = None
    data_col = None
    
    for col in df.columns:
        # 주소: 'probe_read_addr' 또는 'probe1'이 포함된 컬럼
        if 'probe_read_addr' in col or 'probe1' in col:  
            addr_col = col
        # 카운트: 'histo_read_data' 또는 'probe2'가 포함된 컬럼
        elif 'histo_read_data' in col or 'probe2' in col:  
            data_col = col
            
    if not addr_col or not data_col:
        print("[!] Error: Could not find Address or Data columns in CSV headers.")
        print("    Available columns:", list(df.columns))
        return

    # 데이터 타입 변환 함수 (Vivado가 Hex로 뽑았을 경우를 대비)
    def parse_value(val):
        if isinstance(val, str):
            val = val.strip()
            # 16진수 문자열인 경우 (0x가 있든 없든)
            if val.startswith('0x') or any(c in val.upper() for c in 'ABCDEF'):
                try:
                    return int(val, 16)
                except ValueError:
                    return 0
            else:
                try:
                    return int(val)
                except ValueError:
                    return 0
        return int(val)

    # 주소와 카운트 데이터 추출
    df['Address'] = df[addr_col].apply(parse_value)
    df['Count']   = df[data_col].apply(parse_value)

    # ---------------------------------------------------------
    # 3. 데이터 필터링 (0 ~ 319번 탭 데이터만 추출)
    # ---------------------------------------------------------
    # ILA 캡처 중 중복된 주소(트리거 대기 시간 등)가 있을 수 있으므로 max()로 안전하게 병합
    tap_data = df[(df['Address'] >= 0) & (df['Address'] < 320)].groupby('Address')['Count'].max()
    
    taps = tap_data.index.to_numpy()
    counts = tap_data.values

    if len(taps) == 0:
        print("[!] Error: No valid tap data (0-319) found in the CSV.")
        return

    # ---------------------------------------------------------
    # 4. 통계 계산
    # ---------------------------------------------------------
    total_hits = np.sum(counts)
    mean_hits  = np.mean(counts)
    std_hits   = np.std(counts)
    max_count  = np.max(counts)
    min_count  = np.min(counts)
    max_tap    = taps[np.argmax(counts)]
    min_tap    = taps[np.argmin(counts)]

    # ---------------------------------------------------------
    # 5. 터미널 결과 출력
    # ---------------------------------------------------------
    print("\n" + "="*50)
    print(" 📊 TDC FMCW CORE - HISTOGRAM ANALYSIS")
    print("="*50)
    print(f" Total Taps Analyzed : {len(taps)} Taps")
    print(f" Total Hits Captured : {total_hits:,} Hits")
    print("-" * 50)
    print(f" Mean Hits per Tap   : {mean_hits:,.1f}")
    print(f" Std Dev (DNL Proxy) : {std_hits:,.1f}")
    print(f" Max Hits (Widest)   : {max_count:,} Hits (at Tap {max_tap})")
    print(f" Min Hits (Narrowest): {min_count:,} Hits (at Tap {min_tap})")
    
    if min_count == 0:
        print("\n [!] WARNING: Some taps have 0 hits (Dead Zones detected).")
        
    # ---------------------------------------------------------
    # 6. 각 탭별 데이터를 새로운 CSV 파일로 내보내기 (현재 시간 기준)
    # ---------------------------------------------------------
    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") # 예: 20231024_153045
    output_filename = f"tap_histogram_{current_time}.csv"
    output_filepath = os.path.join(script_dir, output_filename)
    
    # DataFrame 생성 및 저장
    export_df = pd.DataFrame({
        'Tap_Index': taps,
        'Hit_Count': counts
    })
    export_df.to_csv(output_filepath, index=False)
    
    print("-" * 50)
    print(f" [v] Extracted Data Saved to: {output_filename}")
    print("="*50 + "\n")

    # ---------------------------------------------------------
    # 7. Matplotlib 시각화
    # ---------------------------------------------------------
    plt.figure(figsize=(14, 6))
    
    # 막대 그래프 (Edge를 줘서 Tap간 구분을 명확히 함)
    plt.bar(taps, counts, color='royalblue', width=1.0, edgecolor='black', linewidth=0.3)
    
    # 평균선 및 Max/Min 마커
    plt.axhline(mean_hits, color='red', linestyle='--', linewidth=2, label=f'Mean = {mean_hits:.1f}')
    plt.plot(max_tap, max_count, 'gv', markersize=8, label=f'Max (Tap {max_tap})')
    plt.plot(min_tap, min_count, 'r^', markersize=8, label=f'Min (Tap {min_tap})')

    # 그래프 디자인
    plt.title('TDC Delay Line Code Density (Tap Histogram)', fontsize=18, fontweight='bold', pad=15)
    plt.xlabel('CARRY4 Tap Index (0 - 319)', fontsize=14)
    plt.ylabel('Hit Count (Density)', fontsize=14)
    plt.xlim(-5, 325)
    
    # Y축은 0부터 시작, 약간의 여백(10%) 추가
    plt.ylim(0, max_count * 1.1 if max_count > 0 else 100)
    
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend(fontsize=12)
    plt.tight_layout()

    # ---------------------------------------------------------
    # 8. CARRY4 내부 위치별(tap % 4) 분포 분석
    # ---------------------------------------------------------
    # 유효 구간 자동 검출:
    #   tap 0      → 스냅샷 조건(tap[0]==1)상 popcount=0이 불가능하여 항상 비어있음
    #   끝단 taps  → 딜레이라인이 1클럭(5ns)보다 길어 도달하지 못함
    #   → 이 구간을 포함하면 그룹 평균이 0에 끌려가 왜곡되므로 반드시 제외
    nz = np.nonzero(counts)[0]
    if len(nz) == 0:
        print("[!] No non-zero bins; skipping CARRY4 analysis.")
        return
    v_taps   = taps[nz[0]:nz[-1]+1]
    v_counts = counts[nz[0]:nz[-1]+1]

    total_v  = v_counts.sum()
    ideal_ps = 5000.0 / len(v_taps)   # 200MHz 한 주기(5000ps)를 유효 bin 수로 분배

    print("\n" + "="*50)
    print(" 🔬 CARRY4 POSITION ANALYSIS (tap % 4)")
    print("="*50)
    print(f" Valid Range   : tap {v_taps[0]} ~ {v_taps[-1]} ({len(v_taps)} bins)")
    print(f" Ideal Bin     : {ideal_ps:.2f} ps")
    print("-"*50)

    group_mean = {}
    for m in range(4):
        sel = v_counts[v_taps % 4 == m]
        group_mean[m] = sel.mean()
        w = sel.mean() / total_v * 5000.0     # 코드밀도 → 실제 폭(ps)
        print(f" tap%4=={m} : mean={sel.mean():>10,.0f}  width={w:6.2f} ps  ({w/ideal_ps:.2f}x)")

    ratio = max(group_mean.values()) / max(min(group_mean.values()), 1)
    print("-"*50)
    print(f" Widest/Narrowest Ratio : {ratio:.2f}x")
    print("="*50 + "\n")

    # ---------------------------------------------------------
    # 9. CARRY4 위치별 Scatter 시각화
    # ---------------------------------------------------------
    _, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red']
    rng = np.random.default_rng(0)

    # [좌] CARRY4 내 위치별 분포
    for m in range(4):
        sel = v_counts[v_taps % 4 == m]
        x = m + rng.uniform(-0.28, 0.28, size=len(sel))   # 점 겹침 방지용 jitter
        ax1.scatter(x, sel, s=18, alpha=0.55, color=colors[m], edgecolors='none')
        ax1.hlines(group_mean[m], m-0.38, m+0.38, color='black', lw=2.5, zorder=5)
        ax1.text(m, group_mean[m]*1.06, f'{group_mean[m]:,.0f}',
                 ha='center', fontsize=10, fontweight='bold')

    ax1.axhline(v_counts.mean(), color='red', ls='--', lw=1.5,
                label=f'Overall Mean = {v_counts.mean():,.0f}')
    ax1.set_xticks(range(4))
    ax1.set_xticklabels([f'O[{m}]\n(tap%4=={m})' for m in range(4)])
    ax1.set_xlabel('Position within CARRY4', fontsize=13)
    ax1.set_ylabel('Hit Count  (∝ bin width)', fontsize=13)
    ax1.set_title(f'CARRY4 Position Distribution\n(Widest/Narrowest = {ratio:.2f}x)',
                  fontsize=14, fontweight='bold')
    ax1.grid(axis='y', ls='--', alpha=0.6)
    ax1.legend()

    # [우] 체인 위치에 따른 분포
    for m in range(4):
        ax2.scatter(v_taps[v_taps % 4 == m], v_counts[v_taps % 4 == m],
                    s=14, alpha=0.7, color=colors[m], label=f'tap%4=={m}')
    ax2.axhline(v_counts.mean(), color='red', ls='--', lw=1.2)
    ax2.set_xlabel('Tap Index', fontsize=13)
    ax2.set_ylabel('Hit Count', fontsize=13)
    ax2.set_title('Distribution along the Delay Line', fontsize=14, fontweight='bold')
    ax2.grid(axis='y', ls='--', alpha=0.6)
    ax2.legend(markerscale=2)

    plt.tight_layout()

    # 창 띄우기 (막대그래프 + Scatter 2창이 함께 뜸)
    plt.show()

if __name__ == "__main__":
    main()