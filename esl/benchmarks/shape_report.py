"""Self-contained visual report for fixed-geometry elastic method validation."""
from __future__ import annotations
import argparse,base64,csv,html,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import PolyCollection
from .shape_methods import read,load
from esl.mech.shape_methods import PLANS

def configure_font():
    p=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    if p.exists():
        font_manager.fontManager.addfont(str(p));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(p)).get_name()
    plt.rcParams['axes.unicode_minus']=False

def summary_plot(out,data):
    names=data['methods'];rows=[r for r in data['cases'] if r['role']=='validation']
    a=np.array([[100*r['methods'][m].get('field_relative_l2',np.nan) for r in rows] for m in names])
    fig,ax=plt.subplots(figsize=(12,5.8),layout='constrained')
    for i,m in enumerate(names):
        ax.plot(range(len(rows)),a[i],'-o',ms=4,label=PLANS[m].label)
    ax.axhline(15,color='#b72828',ls='--',label='사전 변위장 오차 기준 15%')
    ax.set(yscale='log',ylabel='실제 동해석 대비 변위장 상대 L2 오차 (%)',
           title='고정된 독립 형상에서 방법별 정확도',xticks=range(len(rows)),
           xticklabels=[r['id'].replace('test_','') for r in rows])
    ax.tick_params(axis='x',rotation=45);ax.grid(alpha=.2);ax.legend(ncol=2,fontsize=9)
    fig.savefig(out/'benchmark.png',dpi=150);plt.close(fig)

def contour_plot(out,data,case='test_mixed_010'):
    z=load(out/'predictions'/f'{case}.npz');mesh=load(out/'runs'/case/'input_mesh.npz')
    available=[m for m in ['frozen','incremental_balanced','snapshot_esl','response_taylor'] if m in z]
    if not available:available=[m for m in data['methods'] if m in z][:4]
    names=['actual']+available
    measured=z['actual'];k=int(np.argmax(np.sqrt(np.mean(np.sum(measured**2,axis=2),axis=1))))
    magnitude=[np.linalg.norm(z[m][k],axis=1) for m in names];scale=max(magnitude[0].max(),1e-10)
    errors=[np.zeros(len(mesh['x0']))]+[np.linalg.norm(z[m][k]-measured[k],axis=1) for m in available]
    errscale=max(float(np.percentile(np.concatenate(errors[1:] or errors),95)),scale*.1,1e-10)
    fig,axes=plt.subplots(2,len(names),figsize=(3.2*len(names),6.0),squeeze=False,layout='constrained')
    for j,m in enumerate(names):
        for row,vals,vmax,cmap in [(0,magnitude[j],scale,'viridis'),(1,errors[j],errscale,'magma')]:
            ax=axes[row,j];pc=PolyCollection(mesh['x0'][mesh['conn'],:2],array=vals[mesh['conn']].mean(axis=1),cmap=cmap,clim=(0,vmax),edgecolors='none')
            ax.add_collection(pc);ax.autoscale();ax.set_aspect('equal');ax.set(xlabel='X (mm)',ylabel='Y (mm)')
            title='실제 동해석' if m=='actual' else PLANS[m].label
            ax.set_title(title+f'\n최대 {vals.max():.2f} mm',fontsize=10)
        if j==len(names)-1:
            fig.colorbar(axes[0,j].collections[0],ax=axes[0,:].tolist(),shrink=.8,label='강체 제거 변위 크기 (mm), 실제 최대값 초과는 포화')
            fig.colorbar(axes[1,j].collections[0],ax=axes[1,:].tolist(),shrink=.8,label='변위 벡터 오차 크기 (mm), 상위 5%는 포화')
    fig.suptitle(f'{case} | 동일 시각 {z["time"][k]*1000:.3f} ms | 초기 판 좌표에 표시, 변형 확대 없음',fontsize=13)
    fig.savefig(out/'contours.png',dpi=140);plt.close(fig)

def image_tag(path):
    return '<img style="width:100%;max-width:1500px" src="data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()+'">'

def generate_report(out):
    out=Path(out);data=read(out/'method_results.json');cfg=read(out/'manifest.json')['config']
    configure_font();summary_plot(out,data);contour_plot(out,data)
    def pc(v):return '미정' if v is None else f'{100*v:.2f}%'
    rows=[];records=[]
    for name,item in data['summary'].items():
        s=item['regions']['small']
        change_error = s.get('worst_change_field_l2')
        records.append([name,s['tests'],s['passed'],s['worst_field_l2'],s['worst_peak_rms_error'],s['direction_agreement'],s['worst_gauge_error'],s['median_prediction_s'],item['extra_calibration_drops'],s['recommended_in_region'],change_error])
        runtime = '미정' if s['median_prediction_s'] is None else f'{s["median_prediction_s"]:.3f} s'
        rows.append(f'<tr><td>{html.escape(item["label"])}</td><td>{s["passed"]}/{s["tests"]}</td><td>{pc(s["worst_field_l2"])}</td><td>{pc(change_error)}</td><td>{pc(s["worst_peak_rms_error"])}</td><td>{pc(s["direction_agreement"])}</td><td>{pc(s["worst_gauge_error"])}</td><td>{runtime}</td><td>{item["extra_calibration_drops"]}</td></tr>')
    with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['method','tests','passed','worst_field_l2','worst_peak_rms_error','direction_agreement','worst_gauge_error','median_prediction_s','extra_calibration_drops','recommended','worst_change_field_l2']);w.writerows(records)
    baseline=read(out/'runs/baseline/metrics.json');truecorner=cfg['drop'].get('orientation')=='corner_diagonal'
    orientation='판의 코너-중심 대각선 수직, 판 기울기 90도' if truecorner else '수평에서 약 5도: Rx +3도, Ry -4도 (대조 조건)'
    selected=[v['label'] for v in data['summary'].values() if v['regions']['small']['recommended_in_region']]
    conclusion='검증 범위에서 기준 통과: '+', '.join(selected) if selected else '사전 선정 기준을 모두 만족한 방법은 없습니다. 현재 결과로 ESL 최적화 적용을 승인할 수 없습니다.'
    details=[]
    for r in data['cases']:
        if r['role']!='validation':continue
        details.append('<tr><td>'+html.escape(r['id'])+'</td><td>'+str(r['delta_mm'])+'</td>'+''.join('<td>'+pc(r['methods'][m].get('field_relative_l2'))+'</td>' for m in data['methods'])+'</tr>')
    mesh=''.join(f'<li>{html.escape(k)}: {v["coarse_rms_mm"]:.5f} → {v["fine_rms_mm"]:.5f} mm, 차이 {pc(v["relative_difference"])}</li>' for k,v in data['mesh_checks'].items())
    text=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>탄성 코너 낙하 ESL 방법론 검증</title><style>body{{font-family:Arial,"Noto Sans CJK KR",sans-serif;max-width:1500px;margin:32px auto;padding:0 20px;color:#233b4a;line-height:1.65}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:8px;border:1px solid #ccd7df;text-align:left}}th{{background:#eaf1f7}}h1,h2{{color:#154762}}.callout{{background:#fff0e3;padding:18px}}pre{{white-space:pre-wrap}}a{{color:#136c9c}}</style><h1>탄성 코너 낙하: 비드 형상 변경용 ESL 방법론 검증</h1>
<p class="callout">{conclusion}</p><p>탄성 판의 고정된 비드 깊이 변경을 사용해 방법의 예측 정확도를 비교했습니다.</p>
<h2>실제 해석 조건</h2><p>{orientation}. 이 수치 각도는 사용자 지정값이 아니라 이 검증의 명시적 자세 정의입니다.</p>
<table><tr><th>항목</th><th>실제 조건</th></tr><tr><td>판 / 재료</td><td>800 × 450 × 0.8 mm, 960 쉘, LAW1 탄성. E 210000 MPa, ν 0.3, ρ 7.85e-9 tonne/mm³</td></tr><tr><td>동해석</td><td>600 mm 상당 초기속도 3.431035 m/s, 중력 9.81 m/s², 무구속, 강체 바닥, 마찰 0.15, 40 ms. 구조 감쇠 / 질량 스케일링 없음</td></tr><tr><td>정해석</td><td>초기 판 좌표계 선형 쉘, 바닥 접촉 없음. 1025: Ux Uy Uz, 1001: Ux Uz, 25: Uz. 회전 직접 구속 없음</td></tr><tr><td>구속 의존성 검사</td><td>1: Ux Uy Uz, 1001: Uy Uz, 25: Uz로 별도 계산. 하중 평형과 비강체장 차이를 확인</td></tr></table>
<p>실제 기준 동해석 RMS 피크 {baseline['peak_rms_mm']:.5f} mm, 최대 절점 변위 {baseline['max_node_deflection_mm']:.5f} mm. 에너지 잔차 지표 {pc(baseline['energy_balance_fraction'])}. 201개 저장 프레임을 공통 물리 시점으로 선형 보간했습니다.</p>
<h2>선정 결과</h2><p>각 비드 0.1 mm 이내 독립 검증. 사전 기준: 변위장 L2 15%, 피크 RMS 10%, 구속 변경 차이 0.01%, 변화 방향 일치 80%, 기준 왕복 오차 0.01%.</p>
<table><tr><th>방법</th><th>사례 통과</th><th>최대 변위장 오차</th><th>최대 변화량 장 오차</th><th>최대 RMS 오차</th><th>방향 일치</th><th>구속 변경 차이</th><th>중앙 예측시간</th><th>추가 보정 동해석</th></tr>{''.join(rows)}</table>
<p>기준 동해석 {data['baseline_dynamic_s']:.2f} s. 보정 동해석 총 {data['calibration_dynamic_s']:.2f} s. 변화량 장 오차는 각 형상에서 기준 변위를 뺀 뒤 계산합니다. 변위 재사용 대조군의 변화량 장 오차는 변화가 관측된 경우 100%입니다.</p>
{image_tag(out/'benchmark.png')}<h2>실제 컨투어와 예측 오차</h2><p>모든 패널은 동일 형상, 동일 절점, 동일 시각입니다. 윗줄은 강체 제거 변위 크기, 아랫줄은 실제 변위 벡터와의 오차입니다.</p>{image_tag(out/'contours.png')}
<h2>수치 검증과 한계</h2><ul>{mesh}</ul><pre>{html.escape(json.dumps(data.get('fd_step_check',{}),ensure_ascii=False,indent=2))}</pre><p>메시 비교는 RMS에 대한 확인이며 전체 장의 메시 수렴을 입증하지 않습니다. 유한차분 간격을 절반으로 했을 때 미분이 크게 바뀌면, 해당 미분을 신뢰한 최적화 방향은 미검증입니다. 충돌 접촉 이력 변화와 수치 미분 오차를 구분해야 합니다.</p>
<h2>방법의 지위</h2><p>고정 ESL은 대조군입니다. 평형 보정은 후보 형상에서의 하중 합력과 모멘트를 없애는 관성완화입니다. 증분 형상 ESL은 DiESL의 동일 절점 형상 확장이며 문헌 비드 예제 재현이 아닙니다. 1차 하중 ESL은 d(Ku)/dp를 포함하는 F-ESL형이며, 선형 동적 원문을 접촉 문제에 시험한 확장입니다.</p>
<h2>독립 사례별 변위장 오차</h2><table><tr><th>사례</th><th>비드 변화 mm</th>{''.join('<th>'+html.escape(PLANS[m].label)+'</th>' for m in data['methods'])}</tr>{''.join(details)}</table>
<h2>확인한 원문</h2><ul><li><a href="https://arxiv.org/pdf/2508.07222">F-ESL 원문 (선형 동적 범위)</a></li><li><a href="https://doi.org/10.1007/s00158-020-02830-x">DiESL 원문</a></li><li><a href="https://help.altair.com/hwsolvers/rad/topics/solvers/rad/mat_law1_elast_starter_r.htm">LAW1 탄성 재료 공식 문서</a></li></ul></html>'''
    (out/'report.html').write_text(text,encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);generate_report(p.parse_args().out)
