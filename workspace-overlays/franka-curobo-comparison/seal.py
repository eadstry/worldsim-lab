"""Copy an inspected report draft into a new immutable artifact version."""
import argparse
import datetime
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath


def seal(source, output):
    manifest=json.loads((source/"manifest.json").read_text())
    assert re.fullmatch(r"v\d{3}",output.name)
    assert output.parent.name==manifest["artifact_id"]
    for name,expected in manifest["files"].items():
        relative=PurePosixPath(name)
        assert not relative.is_absolute() and ".." not in relative.parts
        path=source/name
        assert path.is_file() and not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,f"Draft changed: {name}"
    output.mkdir(parents=True,exist_ok=False)
    for name in manifest["files"]:
        target=output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,target)
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    manifest.update(version=output.name,created_at=now,sealed_at=now)
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2))
    return manifest


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    result=seal(args.source,args.output)
    print(f"Sealed {len(result['files'])} verified files in {args.output.resolve()}")
