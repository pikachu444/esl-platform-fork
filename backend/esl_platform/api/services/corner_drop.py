"""Project-authorized, fixed-preset experiment runner, separate from production jobs.

One shared Linux flock is inherited by the detached worker, surviving API restarts.
No commands, paths or physical settings are accepted from a browser request.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile

from esl.mech.drop_surrogates import METHODS
from esl.mech.shape_methods import PLANS as SHAPE_METHODS
from esl.benchmarks.experiment import write_json
from ...core.errors import DomainError, forbidden, not_found
from .common import require_config_ok, require_execute

REPO = Path(__file__).resolve().parents[4]
PRESETS = {'full': 'corner_drop_benchmark.json', 'smoke': 'corner_drop_smoke.json',
           'shape_corner':'shape_method_validation.json','shape_flat':'shape_method_control_flat.json'}
TERMINAL = {'completed','failed','canceled','interrupted'}


def settings(ctx):
    from ...core.config import CornerDropCfg
    section = ctx.settings.bead_doe
    return section.corner_drop if section is not None else CornerDropCfg()


def check_view(principal, project_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',project_id):
        raise DomainError('INVALID_PARAMS','프로젝트 ID가 올바르지 않습니다',status=422)
    if principal.role(project_id) is None: raise forbidden('이 프로젝트의 조회 권한이 없습니다')


def root(ctx):
    return Path(ctx.settings.storage.esl_root)/'_corner_drop'


def project_root(ctx,project_id):
    return root(ctx)/hashlib.sha256(project_id.encode()).hexdigest()


def run_path(ctx,principal,project_id,rid):
    check_view(principal,project_id)
    if not re.fullmatch('[0-9a-f]{32}',rid): raise not_found()
    path=project_root(ctx,project_id)/rid
    if not (path/'run.json').is_file(): raise not_found()
    return path


def process_identity(pid):
    try:
        tail=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
        if tail[0]=='Z': return None
        return tail[19]  # field 22: process start ticks since boot
    except (FileNotFoundError,ProcessLookupError): return None


def status_at(path):
    run=json.loads((path/'run.json').read_text())
    progress=json.loads((path/'progress.json').read_text()) if (path/'progress.json').exists() else dict(status='starting')
    alive = process_identity(run['pid']) == run['start_identity'] and run['start_identity'] is not None
    if not alive and progress['status'] not in TERMINAL:
        progress=dict(status='interrupted',stage='stopped',error='작업 프로세스가 종료되었습니다. 로그를 확인하고 다시 실행하세요.')
        write_json(path/'progress.json',progress)
    result_path=path/('method_results.json' if run.get('preset','').startswith('shape_') else 'result.json')
    result=json.loads(result_path.read_text()) if result_path.exists() else None
    return dict(**run,progress=progress,result=result,alive=alive)


def info(ctx,principal,project_id):
    check_view(principal,project_id); cfg=settings(ctx)
    available=(sys.platform=='linux' and cfg.enabled and cfg.solver_root is not None and
               all((Path(cfg.solver_root)/'exec'/name).is_file() for name in
                   ['starter_linux64_gf','engine_linux64_gf','anim_to_vtk_linux64_gf','th_to_csv_linux64_gf']))
    reason=None
    if not cfg.enabled: reason='서버 설정 bead_doe.corner_drop.enabled를 켜야 합니다.'
    elif sys.platform!='linux': reason='이 실행기는 Linux/WSL에서 지원합니다. Windows 네이티브는 검증하지 않았습니다.'
    elif not available: reason='서버의 OpenCourant solver_root와 실행 파일을 확인해야 합니다.'
    return dict(available=bool(available),reason=reason,can_execute=principal.can_execute(project_id),
                methods=[dict(id=k,**asdict(v)) for k,v in METHODS.items()],
                shape_methods=[dict(id=k,**asdict(v)) for k,v in SHAPE_METHODS.items()],presets=list(PRESETS),
                max_runtime_s=cfg.max_runtime_s)


def list_runs(ctx,principal,project_id):
    check_view(principal,project_id); base=project_root(ctx,project_id)
    paths=sorted(base.glob('*/run.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:settings(ctx).max_listed_runs]
    return [status_at(p.parent) for p in paths]


def start(ctx,principal,project_id,method,preset):
    check_view(principal,project_id); require_config_ok(ctx); require_execute(principal,project_id)
    state=info(ctx,principal,project_id)
    if not state['available']: raise DomainError('CORNER_DROP_UNAVAILABLE',state['reason'],status=503)
    if preset not in PRESETS: raise DomainError('INVALID_PARAMS','지원하지 않는 프리셋입니다',status=422)
    method_table=SHAPE_METHODS if preset.startswith('shape_') else METHODS
    if method!='all' and method not in method_table: raise DomainError('INVALID_PARAMS','이 프리셋에서 지원하지 않는 방법입니다',status=422)
    import fcntl
    folder=root(ctx);folder.mkdir(parents=True,exist_ok=True)
    lock=os.open(folder/'runner.lock',os.O_CREAT|os.O_RDWR,0o600)
    try:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise DomainError('CORNER_DROP_BUSY','다른 비교 실험이 실행 중입니다. 완료 후 실행하세요.',status=409)
        rid=uuid.uuid4().hex;path=project_root(ctx,project_id)/rid;path.mkdir(parents=True)
        cfg=settings(ctx)
        command=[sys.executable,'-m','esl.benchmarks.service_worker','--lock-fd',str(lock),
                 '--timeout',str(cfg.max_runtime_s),'--out',str(path),'--solver',cfg.solver_root,
                 '--config',str(REPO/'config'/PRESETS[preset])]
        if preset.startswith('shape_'):command+=['--study','shape']
        if method!='all':command+=['--method',method]
        env=os.environ.copy()
        env['PYTHONPATH']=os.pathsep.join([str(REPO),str(REPO/'packages/beadgraph/src'),env.get('PYTHONPATH','')])
        env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        write_json(path/'progress.json',dict(status='starting',stage='queued',message='실제 해석 실행 준비'))
        with (path/'worker.log').open('w') as log:
            process=subprocess.Popen(command,cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,
                                     start_new_session=True,pass_fds=(lock,))
        write_json(path/'run.json',dict(id=rid,project_id=project_id,method=method,preset=preset,
                   created_by=principal.user_id,created_at=time.time(),pid=process.pid,
                   start_identity=process_identity(process.pid)))
        threading.Thread(target=process.wait,daemon=True).start()
        return status_at(path)
    finally: os.close(lock)


def get(ctx,principal,project_id,rid):
    return status_at(run_path(ctx,principal,project_id,rid))


def cancel(ctx,principal,project_id,rid):
    require_config_ok(ctx);require_execute(principal,project_id)
    path=run_path(ctx,principal,project_id,rid);state=status_at(path)
    if state['alive']:
        write_json(path/'progress.json',dict(status='canceled',stage='stopping',message='사용자 요청으로 종료 중',updated_at=time.time()))
        # Only our still-matching process group; no arbitrary PID is accepted from requests.
        try: os.killpg(state['pid'],signal.SIGTERM)
        except ProcessLookupError: pass
    return dict(id=rid,status='cancel_requested' if state['alive'] else state['progress']['status'])


def artifact(ctx,principal,project_id,rid,name):
    path=run_path(ctx,principal,project_id,rid)
    names={'comparison.csv','result.json','method_results.json','report.html','report.md','benchmark.png','sensitivity.png','contours.png','drop_comparison.gif','worker.log','bundle.zip'}
    if name not in names:raise not_found()
    state=status_at(path)
    if name=='bundle.zip':
        if state['alive']:raise DomainError('CORNER_DROP_BUSY','작업 종료 후 원자료를 받을 수 있습니다',status=409)
        target=path/name
        if not target.exists():
            files=[p for p in path.rglob('*') if p.is_file() and p.suffix in {'.npz','.rad','.json','.csv','.log','.md','.html','.png','.gif'}]
            if sum(p.stat().st_size for p in files)>settings(ctx).download_max_mb*1024**2:
                raise DomainError('ARTIFACT_TOO_LARGE','원자료가 다운로드 크기 한도를 넘었습니다',status=413)
            temp=target.with_suffix('.tmp')
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                for p in files:archive.write(p,p.relative_to(path))
            temp.replace(target)
        return target
    target=path/name
    if not target.is_file():raise not_found('RESULT_NOT_READY','아직 생성되지 않은 파일입니다')
    return target
