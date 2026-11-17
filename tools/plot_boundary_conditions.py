"""Exact mesh locations and boundary conditions, presented as a Korean schematic."""
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import PolyCollection
from matplotlib.patches import Polygon,FancyBboxPatch

def render(mesh_path,out):
    font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    if Path(font).exists():
        font_manager.fontManager.addfont(font)
        plt.rcParams['font.family']=font_manager.FontProperties(fname=font).get_name()
    plt.rcParams['axes.unicode_minus']=False
    with np.load(mesh_path) as z:mesh=dict(z)
    fig=plt.figure(figsize=(13,13.3),facecolor='#f4f7fa')
    fig.text(.065,.952,'실제로 썼던 동해석과 정해석 조건',fontsize=25,weight='bold',color='#123952')
    fig.text(.065,.915,'같은 판이지만, 해석에서 잡아 둔 곳이 다릅니다.',fontsize=17,color='#466478')
    for y,h in [(.54,.34),(.115,.39)]:
        fig.patches.append(FancyBboxPatch((.04,y),.92,h,boxstyle='round,pad=0.008,rounding_size=0.018',transform=fig.transFigure,facecolor='white',edgecolor='#d6e2ea',linewidth=1,zorder=-1))
    fig.text(.065,.844,'① 동해석: 판을 잡지 않고 떨어뜨림',fontsize=21,weight='bold',color='#146b8c')
    fig.text(.065,.803,'충돌 직전부터 계산  |  코너가 먼저 바닥에 닿는 자세',fontsize=14,color='#486577')
    def project(x):return np.column_stack([x[:,0]+.45*x[:,1],.5*x[:,1]+2*x[:,2]])
    ax=fig.add_axes([.055,.57,.58,.22]);ax.axis('off');ax.set_aspect('equal')
    q=mesh['conn'];uv=project(mesh['world_initial'])
    floor=project(np.array([[-70,-60,.4],[870,-60,.4],[870,510,.4],[-70,510,.4]],float))
    ax.add_patch(Polygon(floor,facecolor='#d9e0e6',edgecolor='#a8b7c2',lw=1))
    ax.add_collection(PolyCollection(uv[q],array=mesh['x0'][:,2][q].mean(axis=1),cmap='Blues',clim=(0,7),edgecolors='#5b859e',linewidth=.15))
    ax.annotate('',xy=(470,245),xytext=(470,495),arrowprops=dict(arrowstyle='-|>',mutation_scale=30,color='#126ead',lw=5))
    ax.text(520,405,'낙하 방향',fontsize=13,color='#126ead')
    ax.text(520,355,'3.431 m/s',fontsize=17,color='#126ead',weight='bold')
    ax.plot(*uv[0],'o',color='#ed8b2b',ms=9)
    ax.annotate('먼저 접촉하는 코너',xy=uv[0],xytext=(50,-80),fontsize=12,color='#a85b1d',arrowprops=dict(arrowstyle='->',color='#a85b1d'))
    ax.set_xlim(-100,1120);ax.set_ylim(-100,520)
    fig.text(.69,.755,'고정점 없음',fontsize=23,weight='bold',color='#126ead')
    fig.text(.69,.71,'600 mm 낙하 상당 초기속도\n중력 9.81 m/s²\n기울기: X +3° / Y −4°\n강체 바닥 · 마찰 0.15\n40 ms 응답 계산',fontsize=14,linespacing=1.8,color='#365468',va='top')
    fig.text(.065,.552,'표시를 위해 높이 방향을 2배로 확대. 절점 위치·요소 연결은 실제 입력에서 가져옴.',fontsize=10.5,color='#68818e')
    fig.text(.065,.474,'② 정해석: 바닥을 없애고, 세 점만 구속',fontsize=21,weight='bold',color='#8e3d34')
    fig.text(.065,.434,'A·B·C에서 합계 6개 병진 자유도 구속  |  회전 자유도는 직접 구속하지 않음',fontsize=13.4,color='#486577')
    ax=fig.add_axes([.055,.205,.59,.205]);ax.axis('off');ax.set_aspect('equal');uv=project(mesh['x0'])
    ax.add_collection(PolyCollection(uv[q],array=mesh['x0'][:,2][q].mean(axis=1),cmap='Blues',clim=(0,7),edgecolors='#5b859e',linewidth=.18))
    for idx,label,col in [(1024,'A','#bd4a3b'),(1000,'B','#e09024'),(24,'C','#8051a3')]:
        x,y=uv[idx];ax.plot(x,y,'o',ms=14,mec='white',mew=2,color=col);ax.text(x+18,y+18,label,fontsize=20,weight='bold',color=col)
    ax.set_xlim(-90,1130);ax.set_ylim(-85,330)
    origin=np.array([70.,-48.])
    for d,l,col in [(np.array([140.,0.]),'X','#d95d55'),(np.array([55.,65.]),'Y','#4a976d'),(np.array([0.,85.]),'Z','#4f77aa')]:
        ax.annotate('',xy=origin+d,xytext=origin,arrowprops=dict(arrowstyle='-|>',color=col,lw=2));ax.text(*(origin+d+[7.,0.]),l,color=col,fontsize=15,weight='bold')
    for y,label,col,txt in [(.365,'A','#bd4a3b','X·Y·Z 이동을 막음'),(.30,'B','#e09024','X·Z 이동을 막음'),(.235,'C','#8051a3','Z 이동만 막음')]:
        fig.text(.69,y,label,color='white',fontsize=19,weight='bold',bbox=dict(boxstyle='circle,pad=.3',fc=col,ec='none'))
        fig.text(.735,y,txt,fontsize=12.5,color='#27465a',va='center')
    fig.text(.065,.159,'A = (800,450,0)   B = (800,0,0)   C = (0,450,0) mm',fontsize=12.6,color='#486577')
    fig.patches.append(FancyBboxPatch((.055,.025),.89,.068,boxstyle='round,pad=.008,rounding_size=.01',transform=fig.transFigure,facecolor='#fff1e7',edgecolor='none',zorder=-1))
    fig.text(.075,.073,'핵심: 동해석에는 고정점이 없지만, 정해석에는 A·B·C가 있습니다.',fontsize=15,weight='bold',color='#884623')
    fig.text(.075,.043,'하중이 새 형상에서 평형을 잃으면, 이 구속점의 반력이 변형에 섞일 수 있습니다.',fontsize=12.8,color='#884623')
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(out,dpi=160,bbox_inches='tight',facecolor=fig.get_facecolor());plt.close(fig)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('input_mesh');ap.add_argument('output');a=ap.parse_args();render(a.input_mesh,a.output)
