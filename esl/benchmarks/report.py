"""Standalone report, exact plots and animation of actual solver coordinates."""
from __future__ import annotations

import argparse
import base64
from html import escape
import io
import json
from pathlib import Path

import numpy as np


def load(path):
    with np.load(path) as z:return dict(z)


def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'


def plot_results(out,result,actual,search):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.tri import Triangulation
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    baseline_id=search['baseline_id'];best=result['best_observed_id']
    basepath=out/'baseline';bestpath=basepath if best==baseline_id else out/'drops'/best
    mesh0=load(basepath/'input_mesh.npz');mesh1=load(bestpath/'input_mesh.npz')
    h0=load(basepath/'history.npz');h1=load(bestpath/'history.npz')
    fig=plt.figure(figsize=(14,12),layout='constrained');axes=[fig.add_subplot(3,2,i+1) for i in range(4)]
    maximum=max(mesh0['x0'][:,2].max(),mesh1['x0'][:,2].max())
    for ax,mesh,title in zip(axes[:2],[mesh0,mesh1],['Baseline initial beads','Best observed initial beads (validation pool)']):
        x=mesh['x0'];q=mesh['conn'];tri=np.concatenate([q[:,[0,1,2]],q[:,[0,2,3]]])
        color=ax.tripcolor(Triangulation(x[:,0],x[:,1],tri),x[:,2],shading='gouraud',vmin=0,vmax=maximum,cmap='viridis')
        ax.set_aspect('equal');ax.set_title(title);ax.set_xlabel('x [mm]');ax.set_ylabel('y [mm]')
        fig.colorbar(color,ax=ax,label='Initial bead height [mm]')
    rows=[r for r in result['methods'] if r['status']=='completed']
    codes=[r['code'] for r in rows];values=[r['improvement_fraction']*100 for r in rows]
    axes[2].bar(codes,values,color=['#238a65' if r['accepted'] else '#c56b31' for r in rows])
    axes[2].axhline(5,color='#777777',linestyle='--',label='5% target');axes[2].axhline(0,color='black',linewidth=.7)
    axes[2].set_ylabel('Actual RMS improvement [%]');axes[2].set_title('Surrogate-selected designs: actual re-drop')
    axes[2].legend();axes[2].grid(axis='y',alpha=.2)
    for h,label in [(h0,'Baseline'),(h1,'Best observed')]:
        rms=np.sqrt(np.mean(np.sum(h['u']**2,axis=2),axis=1))
        axes[3].plot(h['time']*1000,rms,label=label)
    axes[3].set_xlabel('Time [ms]');axes[3].set_ylabel('Rigid-removed RMS [mm]');axes[3].legend();axes[3].grid(alpha=.2)
    for index,(h,mesh,title) in enumerate([(h0,mesh0,'Baseline at its peak'),(h1,mesh1,'Best observed at its peak')]):
        ax=fig.add_subplot(3,2,index+5,projection='3d');peak=int(np.sum(h['u']**2,axis=(1,2)).argmax())
        x=mesh['x0']+h['u'][peak];faces=x[mesh['conn']]
        colors=plt.get_cmap('magma')(np.clip(h['plastic'][peak]/max(float(h0['plastic'].max()),float(h1['plastic'].max()),1e-12),0,1))
        ax.add_collection3d(Poly3DCollection(faces,facecolors=colors,edgecolors=(0,0,0,.12),linewidth=.15))
        ax.set_xlim(0,800);ax.set_ylim(0,450);ax.set_zlim(-30,35);ax.set_box_aspect((800,450,180))
        ax.set_title(title+' (deformation ×1)');ax.set_xlabel('x [mm]');ax.set_ylabel('y [mm]');ax.set_zlabel('z [mm]')
    fig.suptitle('Actual nonlinear corner drop | 800 × 450 × 0.8 mm steel | equivalent fall 600 mm',fontsize=14)
    fig.savefig(out/'benchmark.png',dpi=150);plt.close(fig)
    candidates=json.loads((out/'candidates.json').read_text())
    common=[i for i in search['local_ids'] if i in actual and all(candidates[i]['methods'].get(m,{}).get('status')=='completed' for m in ['displacement','balanced_displacement'])]
    if common:
        fig,ax=plt.subplots(figsize=(12,5.5),layout='constrained')
        x=np.arange(len(common));width=.25
        for offset,method,label,color in [(-width,'displacement','D0: frozen ESL','#db843e'),(0,'balanced_displacement','D1: force/moment balanced','#8a5ec4')]:
            ax.bar(x+offset,[candidates[i]['methods'][method]['score_mm'] for i in common],width,label=label,color=color)
        ax.bar(x+width,[actual[i]['peak_rms_mm'] for i in common],width,label='Actual nonlinear re-drop',color='#238a65')
        ax.axhline(result['baseline']['peak_rms_mm'],ls='--',color='#333333',label='Baseline actual RMS')
        ax.set_yscale('log');ax.set_ylabel('Rigid-removed peak RMS [mm, logarithmic scale]')
        ax.set_xticks(x,[f'b{j//2+1} {"-1" if j%2==0 else "+1"} mm' for j in range(len(common))],rotation=35,ha='right')
        ax.set_title('Same node IDs and connectivity: changing one bead by 1 mm')
        ax.legend(ncol=2);ax.grid(axis='y',alpha=.2);fig.savefig(out/'sensitivity.png',dpi=160);plt.close(fig)
    # Actual world coordinates: no amplified deformation, interpolation or simulated trajectory.
    from PIL import Image
    frames=[];indices=np.unique(np.rint(np.linspace(0,min(len(h0['time']),len(h1['time']))-1,60)).astype(int))
    fig=plt.figure(figsize=(10,4.4),layout='constrained')
    for idx in indices:
        fig.clear()
        for j,(h,mesh,title) in enumerate([(h0,mesh0,'Baseline'),(h1,mesh1,'Best observed in validation pool')]):
            ax=fig.add_subplot(1,2,j+1,projection='3d');x=h['x'][idx]
            patch=Poly3DCollection(x[mesh['conn']],facecolors='#3b82b1' if j==0 else '#1b9878',edgecolors=(0,0,0,.12),linewidth=.2)
            ax.add_collection3d(patch);ax.add_collection3d(Poly3DCollection([np.array([[-50,-50,0],[850,-50,0],[850,550,0],[-50,550,0]])],facecolors=(.7,.7,.7,.2)))
            ax.set_xlim(-30,850);ax.set_ylim(-30,550);ax.set_zlim(0,110);ax.set_box_aspect((800,450,200));ax.view_init(20,-60)
            ax.set_title(title+f'\nt={h["time"][idx]*1000:.2f} ms');ax.set_xlabel('x [mm]');ax.set_ylabel('y [mm]');ax.set_zlabel('z [mm]')
        fig.canvas.draw();image=Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[:,:,:3]).convert('P',palette=Image.Palette.ADAPTIVE)
        frames.append(image)
    frames[0].save(out/'drop_comparison.gif',save_all=True,append_images=frames[1:],duration=80,loop=0)
    plt.close(fig)


def generate_report(directory):
    out=Path(directory);result=json.loads((out/'result.json').read_text());search=json.loads((out/'search.json').read_text())
    actual=json.loads((out/'actual.json').read_text())['results'];base=result['baseline'];cfg=json.loads((out/'manifest.json').read_text())['config']
    plot_results(out,result,actual,search)
    rows=[]
    for row in result['methods']:
        if row['status']!='completed':rows.append([row['method'],'실패',row.get('error',''),'','','','']);continue
        rows.append([row['code'],f'{row["predicted_mm"]:.3f}',f'{row["actual_mm"]:.3f}',f'{row["improvement_fraction"]*100:+.2f}%',
                     f'{row["plastic_p95"]:.6f}',f'{row["mass_ratio"]:.5f}',
                     '거친 메시 기준 충족' if row['accepted'] else '미충족'])
    fine=[];base_fine=result['fine'].get(search['baseline_id'],{})
    for ident,row in result['fine'].items():
        if 'error' in row:fine.append([ident,row['error'],'','','','']);continue
        gain=1-row['peak_rms_mm']/base_fine['peak_rms_mm'] if 'peak_rms_mm' in base_fine else None
        plastic_ratio=row['plastic_p95']/base_fine['plastic_p95'] if base_fine.get('plastic_p95',0)>0 else None
        fine.append([ident,f'{row["peak_rms_mm"]:.4f}',f'{gain*100:+.2f}%' if gain is not None else '–',
                     f'{plastic_ratio:.3f}' if plastic_ratio is not None else '분모 0',
                     f'{row["energy_balance_fraction"]*100:.2f}%',str(row['quality_passed'])])
    variations=[]
    for case,results in result['variations'].items():
        ref=results.get(search['baseline_id'],{})
        for ident,row in results.items():
            if 'peak_rms_mm' not in row or 'peak_rms_mm' not in ref:variations.append([case,ident,'실패','','','']);continue
            plastic_ratio=row['plastic_p95']/ref['plastic_p95'] if ref['plastic_p95']>0 else None
            variations.append([case,ident,f'{row["peak_rms_mm"]:.4f}',f'{(1-row["peak_rms_mm"]/ref["peak_rms_mm"])*100:+.2f}%',str(row['quality_passed'])])
            variations[-1].insert(4,f'{plastic_ratio:.3f}' if plastic_ratio is not None else '분모 0')
    accepted=[r['code'] for r in result['methods'] if r.get('accepted')]
    conclusion=('거친 메시의 모든 개선 기준을 통과한 방법: '+', '.join(accepted)+'. 최종 판단에는 아래 자세/세분화 결과를 함께 사용해야 한다.' if accepted else
                f'이번 1회 외부 반복에서 실행한 {len(result["methods"])}개 대체방법의 선택안 중 거친 메시의 개선·소성변형·질량·해석품질 기준을 모두 통과한 안은 없다. 정적 점수 감소를 실제 낙하 성능 개선으로 해석할 수 없다.')
    best_id=result['best_observed_id'];obs=actual[best_id]
    control_cases=[]
    for case,results in result['variations'].items():
        ref=results.get(search['baseline_id'],{});candidate=results.get(best_id,{})
        if 'peak_rms_mm' not in candidate or 'peak_rms_mm' not in ref:
            control_cases.append(dict(case=case,passed=False,error='missing result'));continue
        gain=1-candidate['peak_rms_mm']/ref['peak_rms_mm']
        ratio=candidate['plastic_p95']/ref['plastic_p95'] if ref['plastic_p95']>0 else None
        passed=(gain>=cfg['acceptance']['min_improvement_fraction'] and
                candidate['plastic_p95']<=ref['plastic_p95']*cfg['acceptance']['max_plastic_p95_ratio']+1e-12 and
                candidate['quality_passed'] and ref['quality_passed'])
        control_cases.append(dict(case=case,improvement_fraction=gain,plastic_p95_ratio=ratio,passed=bool(passed)))
    control=dict(id=best_id,selection='observed control from validation pool; not selected by a surrogate',
                 depths_mm=obs['depths_mm'],cases=control_cases,all_variations_passed=all(c['passed'] for c in control_cases))
    (out/'observed_control.json').write_text(json.dumps(control,ensure_ascii=False,indent=2)+'\n')
    provenance=json.loads((out/'baseline/field_provenance.json').read_text());quality=json.loads((out/'baseline/quality.json').read_text())
    completed=sum(1 for _ in out.rglob('complete.json'))
    md=['# 코너 낙하 비드 설계 비교 — 실제 실행 결과','',conclusion,'',
        f'기준: 800 × 450 × 0.8 mm 탄소성 강판, 등가 낙하 높이 600 mm, 자세 Rx=3°, Ry=-4°, 마찰 0.15, {cfg["drop"]["end_time_s"]*1000:g} ms. 거친 메시 {cfg["plate"]["nx"]*cfg["plate"]["ny"]}개 쉘, 세분화 {4*cfg["plate"]["nx"]*cfg["plate"]["ny"]}개 쉘.',
        f'기준 순수 변형 RMS 최대 {base["peak_rms_mm"]:.4f} mm, 최대 절점 변형 {base["peak_def_mm"]:.4f} mm, 요소 소성변형 p95 {base["plastic_p95"]:.6f}.',
        f'실제 솔버 실행 {completed}건(캐시 포함), 기준/명목 자세 비교 {result["actual_drops"]}개 설계. 정적 공통 후보는 {len(search["pool_ids"])}개이며 형상 제약 위반은 제외했다.',
        '', '## 방법별 선택안','', '| 방법 | 정적 예측 mm | 실제 낙하 mm | 실제 개선율 | 소성변형 p95 | 질량비 | 거친 메시 판정 |','|---|---:|---:|---:|---:|---:|---|']
    md.extend('| '+' | '.join(map(str,row))+' |' for row in rows)
    md+=['','정적 예측과 실제 낙하는 서로 다른 모델의 값이다. 개선율은 실제 기준 낙하를 분모로 계산했다. D0/I0의 기준 변위 재현 성공은 설계 변경 예측 성공을 뜻하지 않는다.',
         'P0는 실제 접촉·전체 가속도를 사용하지만 기하·소성 상태를 초기 선형 탄성 강성으로 대체하므로 기준 동해석 변위 자체도 같아질 필요가 없다.',
         'R0의 계산은 같은 변형 벡터의 에너지 변화로 추정한 값이며, 실제 힘 재풀이와 재낙하를 대체하지 못한다.',
         '', '## 독립 재검증','',f'검증 집합에서 관측된 최소 RMS 설계는 `{best_id}`이며 {obs["peak_rms_mm"]:.4f} mm, 기준 대비 {(1-obs["peak_rms_mm"]/base["peak_rms_mm"])*100:.2f}% 감소다. 이는 검증 집합에서 사후 관측된 안이며, 대체모델이 선택한 최선안과 구분한다.',
         '','| 세분화 설계 ID | 실제 RMS mm | 동일 메시 기준 대비 개선 | 소성 p95 비율 | 에너지 오차 | 품질 통과 |','|---|---:|---:|---:|---:|---|']
    md.extend('| '+' | '.join(row)+' |' for row in fine)
    md+=['','| 자세 조건 | 설계 ID | 실제 RMS mm | 동일 자세 기준 대비 개선 | 소성 p95 비율 | 품질 통과 |','|---|---|---:|---:|---:|---|']
    md.extend('| '+' | '.join(row)+' |' for row in variations)
    md+=['','검증 집합 관측안의 자세별 개선·소성·품질 기준 전체 충족: **'+str(control['all_variations_passed'])+'**.']
    for case in control_cases:
        if case.get('plastic_p95_ratio') is not None and case['plastic_p95_ratio']>cfg['acceptance']['max_plastic_p95_ratio']:
            md.append(f'`{case["case"]}`에서는 소성변형 p95가 동일 조건 기준보다 {(case["plastic_p95_ratio"]-1)*100:.1f}% 증가했다. 변위가 줄었어도 강건한 개선안으로 판정할 수 없다.')
    candidates=json.loads((out/'candidates.json').read_text())
    diagnostics=[]
    for ident in search['local_ids']:
        if ident not in actual:continue
        row=candidates[ident];d0=row['methods'].get('displacement',{});d1=row['methods'].get('balanced_displacement',{})
        if d0.get('status')=='completed' and d1.get('status')=='completed':
            diagnostics.append([str(row['depths_mm']),f'{d0["score_mm"]:.3f}',f'{d1["score_mm"]:.3f}',f'{actual[ident]["peak_rms_mm"]:.3f}'])
    if diagnostics:
        md+=['','## 원래 문제와 같은 현상: 동일 절점·요소의 비드 모핑','',
             '비드 하나만 ±1 mm 바꿔도 고정 ESL 정적해는 크게 변했다. 그러나 같은 형상의 실제 낙하 변위는 그만큼 증가하지 않았다. 합력·합모멘트를 모두 보정한 D1에서도 큰 정적 변위가 남거나 더 커졌다. 따라서 전체 모멘트 불평형 하나만을 유일한 원인이라고 결론 내릴 수 없다.',
             '', '| 비드 깊이 6개 mm | 고정 ESL D0 mm | 평형 보정 D1 mm | 실제 재낙하 mm |','|---|---:|---:|---:|']
        md.extend('| '+' | '.join(row)+' |' for row in diagnostics)
        md+=['','![같은 메시에서 1 mm 비드 변화의 예측과 실제](sensitivity.png)']
    md+=['','독립 검증의 형상 유효 후보는 '+str(len(search['holdout_ids']))+'개다. 방법별 Spearman은 해석품질을 통과한 쌍만 사용하므로 유효 쌍 수가 작을 수 있다. 이를 안정적인 통계 결론으로 사용하지 않는다.','',
         '| 방법 | holdout 유효 쌍 | Spearman | 국부 개선/악화 방향 일치 |','|---|---:|---:|---:|']
    for row in result['methods']:
        if row['status']=='completed':md.append(f'| {row["code"]} | {row["holdout_pairs"]} | {row["holdout_spearman"]} | {row["local_direction_agreement"]} |')
    md+=['','## 품질과 한계','',
         f'- 기준 선운동량 오차 {quality["momentum_residual_fraction"]*100:.4f}%, 순간 절점력 평형 오차 {quality["instantaneous_force_residual_fraction"]*100:.6f}%, 에너지 수지 오차 {base["energy_balance_fraction"]*100:.2f}%.',
         f'- 기준 총 질량 {base["initial_mass_tonne"]*1000:.6f} kg, 질량 조립 상대오차 {provenance["mass_relative_error"]:.3g}. 질량 스케일링과 요소 삭제는 사용하지 않았다.',
         '- 거친 메시의 약 8% 에너지 손실은 시간 간격을 절반으로 줄여도 유지됐다. 후보 결과를 보기 전 거친 메시 허용값을 10%, 세분화 허용값을 5%로 명세에 기록했다. 품질 위반 선택안은 좋은 변위가 나와도 성공으로 판정하지 않는다.',
         '- 바닥 접촉은 운동학적 RWALL이며 판 자체 접촉·포장·체결·충돌 부품은 없다. 탄소성 재료는 공개 벤치마크 가정이다.',
         '- 40 ms 마지막 값은 그 시점 변형이며, 완전한 탄성 진동 소멸 뒤 영구 변형을 측정한 값이 아니다.',
         '- 소성변형은 두께 방향 5개 적분점의 요소별 최대다. 접촉력은 판 절점 FREAC이며, TH/RWALL은 벽 충격량으로 별도 운동량 확인에 사용했다.',
         '- 동해석 강체 제거는 유한 Kabsch, 선형 정적해는 미소 강체 제거를 사용했다. 관성완화는 합력·합모멘트만 보정하며 연한 탄성 굽힘을 지우지 않는다.',
         '- 새 비드가 충돌 중 실제로 어떻게 찌그러지는지는 재낙하가 계산한다. I0의 법선 매핑은 이를 사전에 알고 있는 해법이 아니다.',
         '- I0는 변형된 기준 형상에서 선형 탄성 강성을 조립하며, 초기 응력 강성이나 이력 의존 소성 접선 강성은 포함하지 않는다.',
         '- 이번 작업은 한 번의 외부 반복이다. 최적화 수렴·전역 최적·실제 TV 낙하 강건성은 입증하지 않았다.',
         '- 검증 결과를 보고 후보 목적함수나 성공 기준을 유리하게 바꾸지 않았다. 실패한 후보/해석도 JSON에 남겼다.',
         '', '## 해석과 실용적인 다음 단계','',
         '고정 ESL은 기준 변위를 재현하더라도 비드 설계의 실제 개선 방향을 보장하지 않는다. 후보 좌표의 힘·모멘트 평형 보정은 필요한 진단이지만 그것만으로 기하·소성·접촉 경로 오차를 해결하지 못했다.',
         '실무에서는 작은 설계 변경을 정적으로 제안하고 실제 낙하에서 수용 여부를 확인한 뒤, 수용한 설계의 동해석으로 하중과 기준 상태를 다시 만드는 외부 반복이 필요하다. 이 반복의 비용은 줄일 수 있어도 검증 낙하를 생략할 근거는 이번 결과에서 얻지 못했다.',
         '현재 실행기는 6개 후보방법의 비교와 1회 재낙하 검증을 구현했다. 다회 외부 갱신의 수렴 알고리즘까지 구현했다고 주장하지 않는다. 검증 집합의 최소 RMS 설계도 다른 조건에서 소성변형이 악화되면 강건한 개선안으로 판정하지 않는다.',
         '', '## 재현과 원자료','',
         '```bash', 'python -m esl.benchmarks.corner_drop all --solver /path/to/OpenCourant --out /path/to/results',
         'python -m esl.benchmarks.report /path/to/results','```',
         f'솔버: OpenCourant {cfg["solver"]["tag"]}. Linux ZIP SHA256 `{cfg["solver"]["linux_sha256"]}`.',
         f'계산 코드 커밋 `{result["source_sha"]}`. 설정·실행 파일 해시는 manifest.json, 개별 덱·로그·필드는 각 해석 디렉터리에 저장했다.',
         '비교 CSV: comparison.csv. 전체 결과: result.json. 절점/요소 원자료: history.npz. 힘/모멘트/반력 진단: candidates.json.',
         '', '![실제 형상과 결과](benchmark.png)','', '![실제 좌표의 낙하 영상](drop_comparison.gif)','',
         '## 문헌과 이번 구현의 지위','',
         '- Clemens & Schumacher (2023), NOCS: https://doi.org/10.1016/j.istruc.2023.06.015',
         '- 후속 학위논문 §5·§7.2: https://oms.uni-wuppertal.de/en/publications/dissertation/dr-ing-philipp-clemens/',
         '- DiESL: https://doi.org/10.1007/s00158-020-02830-x',
         '- 실제 비드 외부반복 사례: https://lsdyna.ansys.com/wp-content/uploads/attachments/CrashSafety-4.pdf',
         '- 힘 기반 P0/P1의 자유 판 관성완화와 I0의 비드 법선 매핑은 이번 연구용 확장이다. 위 논문의 동일 조건 검증으로 표현하지 않는다.',
         '- 공식 출력 설명: https://help.altair.com/hwsolvers/rad/topics/solvers/rad/th_rwall_starter_r.htm',
         '- 공식 소성 출력 설명: https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/faq_rad_post_processing_r.htm']
    full_cfg=json.loads((Path(__file__).resolve().parents[2]/'config/corner_drop_benchmark.json').read_text())
    smoke=cfg['drop']['end_time_s']<full_cfg['drop']['end_time_s']
    if smoke:md.insert(2,'**연결 확인용 축소 실행입니다. 낙하 성능 판정에 사용하지 마세요.**')
    (out/'report.md').write_text('\n'.join(md)+'\n')
    png=base64.b64encode((out/'benchmark.png').read_bytes()).decode()
    html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>코너 낙하 방법 비교</title><style>body{font:16px system-ui;max-width:1100px;margin:35px auto;padding:0 20px;line-height:1.7;color:#152b3b}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px;border:1px solid #cad4da;text-align:right}th:first-child,td:first-child{text-align:left}h1,h2{line-height:1.3}img{max-width:100%}pre{white-space:pre-wrap;background:#f1f5f7;padding:20px}p{margin:14px 0}</style>'
    html+='<h1>코너 낙하 비드 설계 비교</h1>'
    if smoke:html+='<p><strong>연결 확인용 축소 실행입니다. 낙하 성능 판정에 사용하지 마세요.</strong></p>'
    html+='<p>'+escape(conclusion)+'</p>'
    html+='<p>실제 기준 RMS '+f'{base["peak_rms_mm"]:.4f} mm'+f' · 실제 솔버 실행 {completed}건 · 단일 외부 반복</p>'
    html+=table(['방법','정적 mm','실제 mm','실제 개선','소성 p95','질량비','거친 메시 판정'],rows)
    html+='<h2>메시 세분화</h2>'+table(['설계 ID','RMS mm','동일 메시 개선','소성 p95 비율','에너지 오차','품질 통과'],fine)
    html+='<h2>자세 변화</h2>'+table(['조건','설계 ID','RMS mm','동일 자세 개선','소성 p95 비율','품질 통과'],variations)
    html+='<h2>실제 형상·응답</h2><img alt="actual nonlinear solver results" src="data:image/png;base64,'+png+'">'
    html+='<h2>방법·품질·한계·재현 기록</h2><pre>'+escape('\n'.join(md))+'</pre></html>'
    (out/'report.html').write_text(html)
    return out/'report.html'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args();print(generate_report(args.directory))
