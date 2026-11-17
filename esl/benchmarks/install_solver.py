"""Install only the pinned official Linux OpenCourant archive, with SHA256 verification."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

from .corner_drop import load_config


def install(destination, config):
    if sys.platform!='linux':raise RuntimeError('use Linux or WSL; native Windows is not validated')
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    cfg=load_config(config)['solver'];archive=destination/'OpenCourant_linux64.zip'
    def digest(path):
        h=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
        return h.hexdigest()
    if not archive.exists():
        temp=archive.with_suffix('.download')
        request=urllib.request.Request(cfg['linux_url'],headers={'User-Agent':'esl-corner-drop-benchmark'})
        with urllib.request.urlopen(request,timeout=120) as source,temp.open('wb') as target:
            shutil.copyfileobj(source,target)
        if digest(temp)!=cfg['linux_sha256']:
            temp.unlink();raise ValueError('OpenCourant archive SHA256 mismatch')
        temp.replace(archive)
    if digest(archive)!=cfg['linux_sha256']:raise ValueError('existing archive SHA256 mismatch; do not execute it')
    root=destination/'OpenCourant'
    if root.exists():
        if all((root/'exec'/name).is_file() for name in ['starter_linux64_gf','engine_linux64_gf']):return root
        raise FileExistsError('incomplete installation exists; choose a new destination')
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            target=(destination/member.filename).resolve()
            if not target.is_relative_to(destination) or not member.filename.startswith('OpenCourant/'):
                raise ValueError('unsafe or unexpected archive path')
        z.extractall(destination)
        for member in z.infolist():
            mode=member.external_attr>>16
            if mode and not member.is_dir(): (destination/member.filename).chmod(mode & 0o777)
    return root


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',required=True)
    parser.add_argument('--config',default=str(Path(__file__).resolve().parents[2]/'config/corner_drop_benchmark.json'))
    args=parser.parse_args();print(install(args.destination,args.config))
