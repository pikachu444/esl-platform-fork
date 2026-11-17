import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from esl_platform.core.auth import Principal
from esl_platform.core.config import BeadDoeCfg, CornerDropCfg
from esl_platform.core.errors import DomainError
from esl_platform.api.deps import get_principal
from esl_platform.api.routers.corner_drop import router
from esl_platform.api.services import corner_drop as svc
from esl.doe import DEFAULTS


def principal(role='power',project='p1'):
    return Principal('u1','tester','Tester',False,{project:role})


def context(tmp_path,enabled=False):
    return SimpleNamespace(settings=SimpleNamespace(storage=SimpleNamespace(esl_root=str(tmp_path)),
              bead_doe=BeadDoeCfg(corner_drop=CornerDropCfg(enabled=enabled))),config=SimpleNamespace(ok=True))


def test_disabled_and_unauthorized_execution(tmp_path):
    ctx=context(tmp_path)
    with pytest.raises(DomainError) as e:svc.start(ctx,principal('general'),'p1','all','full')
    assert e.value.status==403
    with pytest.raises(DomainError) as e:svc.start(ctx,principal(),'p1','all','full')
    assert e.value.code=='CORNER_DROP_UNAVAILABLE'
    with pytest.raises(DomainError) as e:svc.list_runs(ctx,principal(),'p2')
    assert e.value.status==403


def test_no_request_commands_or_paths_and_no_unknown_methods(tmp_path):
    app=FastAPI();app.include_router(router);app.state.ctx=context(tmp_path)
    app.dependency_overrides[get_principal]=lambda:principal()
    client=TestClient(app)
    for body in [{'method':'shell-command'},{'method':'all','solver':'/tmp/other'},{'preset':'../../private'}]:
        assert client.post('/projects/p1/corner-drop/runs',json=body).status_code==422


def test_path_and_project_isolation_and_dead_process_recovery(tmp_path):
    ctx=context(tmp_path);path=svc.project_root(ctx,'p1')/('a'*32);path.mkdir(parents=True)
    (path/'run.json').write_text(json.dumps(dict(id='a'*32,pid=99999999,start_identity='123')))
    (path/'progress.json').write_text(json.dumps(dict(status='running')))
    assert svc.get(ctx,principal(),'p1','a'*32)['progress']['status']=='interrupted'
    for project,rid in [('p2','a'*32),('p1','../secret')]:
        with pytest.raises(DomainError):svc.get(ctx,principal(),project,rid)
    with pytest.raises(DomainError):svc.artifact(ctx,principal(),'p1','a'*32,'../run.json')


def test_default_values_mirror_config_examples():
    import yaml
    defaults=CornerDropCfg().model_dump()
    assert defaults==DEFAULTS['corner_drop']
    for filename in ['esl_platform.example.yaml','esl_platform.prod.example.yaml']:
        data=yaml.safe_load(Path('config',filename).read_text())
        assert data['bead_doe']['corner_drop']==defaults
