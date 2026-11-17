"""Compare the two actual corner-first input orientations, without height scaling."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from esl.benchmarks.corner_model import make_mesh,impact_coordinates

def render(out):
    root=Path(__file__).resolve().parents[1]
    font=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    if font.exists():
        font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams['axes.unicode_minus']=False
    fig=plt.figure(figsize=(12,8),facecolor='#f6f8fb')
    fig.suptitle('기존 코너 최초 접촉과, 별도로 정의한 코너 낙하',fontsize=21,weight='bold',y=.97)
    for i,(file,title,subtitle) in enumerate([
        ('shape_method_control_flat.json','기존 조건: 수평에서 약 5°','X +3° / Y −4°  |  거의 수평인 판의 코너부터 접촉'),
        ('shape_method_validation.json','추가 검증: 판을 수직으로 세움','코너-중심 대각선 수직  |  판 기울기 90°')]):
        cfg=json.loads((root/'config'/file).read_text());mesh=make_mesh(cfg);x,R=impact_coordinates(mesh,cfg['drop'])
        ax=fig.add_subplot(1,2,i+1,projection='3d');ax.set_facecolor('#f6f8fb');ax.set_proj_type('ortho')
        center=x[:,:2].mean(axis=0);x[:,:2]-=center
        q=mesh['conn'];ax.add_collection3d(Poly3DCollection(x[q],facecolor='#79adc8',edgecolor='#3f6c86',linewidth=.18,alpha=.95))
        floor=np.array([[[-600,-500,0],[600,-500,0],[600,500,0],[-600,500,0]]],float)
        ax.add_collection3d(Poly3DCollection(floor,facecolor='#dce2e8',edgecolor='#aebbc6',linewidth=.8,alpha=.5))
        ax.scatter(*x[0],color='#df7333',s=75,depthshade=False)
        ax.text(*x[0]+[0,0,55],'최저 코너',fontsize=10,color='#a84e1c')
        top=x.mean(axis=0);top[2]=max(x[:,2].max()+180,430)
        ax.quiver(*top,0,0,-190,color='#145d8c',arrow_length_ratio=.25,linewidth=3)
        ax.text(*(top+[20,0,30]),'3.431 m/s ↓',fontsize=11,color='#145d8c')
        ax.set(xlim=(-650,650),ylim=(-550,550),zlim=(0,1150),box_aspect=(1.3,1.1,1.15))
        ax.view_init(elev=18,azim=-120);ax.set_axis_off()
        ax.set_title(title,fontsize=15,weight='bold',pad=20)
        fig.text(.25+.5*i,.21,subtitle,ha='center',fontsize=10.5,color='#365064')
    fig.text(.06,.12,'두 조건 모두 고정점 없이 자유 낙하, 강체 바닥과 접촉, 탄성 재료 LAW1.',fontsize=13,color='#28475b')
    fig.text(.06,.075,'600 mm 낙하 상당 초기속도, 중력 9.81 m/s², 마찰 0.15. 형상 확대 없이 동일 축척 표시.',fontsize=11,color='#506878')
    fig.text(.06,.035,'사용자는 코너 낙하를 지시했습니다. 위 각도 수치는 사용자가 지정한 값이 아닙니다.',fontsize=11,color='#a15125')
    Path(out).parent.mkdir(parents=True,exist_ok=True);fig.savefig(out,dpi=160,bbox_inches='tight');plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');render(p.parse_args().output)
