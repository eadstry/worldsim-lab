# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Verify and prepare the supplied GS package locally, without installing dependencies."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

PACKAGE_SHA256='4664f143fe5904d1d7cc0dd8e1fa18e4bdc9f5ac6780434a5952acfe92ab21df'

def prepare(package,destination):
    if destination.exists():raise ValueError('Destination must be new: '+str(destination))
    digest=hashlib.sha256(package.read_bytes()).hexdigest()
    if digest!=PACKAGE_SHA256:raise ValueError('GS package differs from reviewed input')
    with zipfile.ZipFile(package) as archive:
        names=archive.namelist()
        if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in names):
            raise ValueError('Unsafe package path')
        manifests=[n for n in names if n.count('/')==1 and n.endswith('/MANIFEST.json')]
        if len(manifests)!=1:raise ValueError('Expected one manifest')
        prefix=manifests[0].rsplit('/',1)[0]+'/'
        manifest=json.loads(archive.read(manifests[0]))
        for entry in manifest['files']:
            data=archive.read(prefix+entry['path'])
            if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
                raise ValueError('Manifest mismatch: '+entry['path'])
        destination.mkdir(parents=True)
        for entry in manifest['files']:
            relative=PurePosixPath(entry['path'])
            if relative.parts[:2]!=('AutoData','openarm_autodata') or relative.suffix=='.md':continue
            target=destination/Path(*relative.parts[1:]);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(prefix+entry['path']))
        result={'package_sha256':digest,'manifest_files_verified':len(manifest['files']),'source_commit':manifest['source_commit']}
        (destination/'preparation.json').write_text(json.dumps(result,indent=2)+'\n')
        return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    p.add_argument('--destination',type=Path,default=Path(__file__).resolve().parent/'runtime')
    args=p.parse_args();print(json.dumps(prepare(args.package,args.destination),indent=2))
