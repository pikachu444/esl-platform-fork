"""Fixed corner-drop research experiments, with existing project auth and CSRF."""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from ...core.auth import Principal
from ..deps import get_ctx,get_principal
from ..services import corner_drop as svc

router=APIRouter(tags=['corner-drop'])
BASE='/projects/{project_id}/corner-drop'


class StartExperiment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    method: Literal[
        'all', 'displacement', 'balanced_displacement', 'physical_acceleration', 'contact_inertia_relief',
        'incremental_geometry', 'ritz_reference', 'frozen', 'balanced', 'incremental', 'incremental_balanced',
        'first_order_load', 'first_order_balanced', 'response_taylor', 'snapshot_esl', 'reference_replay',
    ] = 'all'
    preset: Literal['full','smoke','shape_corner','shape_flat']='shape_corner'


@router.get(BASE+'/settings')
def settings(project_id:str,request:Request,principal:Principal=Depends(get_principal)):
    return svc.info(get_ctx(request),principal,project_id)


@router.get(BASE+'/runs')
def runs(project_id:str,request:Request,principal:Principal=Depends(get_principal)):
    return svc.list_runs(get_ctx(request),principal,project_id)


@router.post(BASE+'/runs',status_code=201)
def start(project_id:str,body:StartExperiment,request:Request,principal:Principal=Depends(get_principal)):
    return svc.start(get_ctx(request),principal,project_id,body.method,body.preset)


@router.get(BASE+'/runs/{rid}')
def get(project_id:str,rid:str,request:Request,principal:Principal=Depends(get_principal)):
    return svc.get(get_ctx(request),principal,project_id,rid)


@router.post(BASE+'/runs/{rid}/cancel')
def cancel(project_id:str,rid:str,request:Request,principal:Principal=Depends(get_principal)):
    return svc.cancel(get_ctx(request),principal,project_id,rid)


@router.get(BASE+'/runs/{rid}/files/{name}',response_class=FileResponse)
def artifact(project_id:str,rid:str,name:str,request:Request,principal:Principal=Depends(get_principal)):
    path=svc.artifact(get_ctx(request),principal,project_id,rid,name)
    # Report HTML downloads as attachment; never execute user/result HTML in application origin.
    return FileResponse(path,filename=name,headers={'X-Content-Type-Options':'nosniff'})
