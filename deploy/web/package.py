"""Build a source and prebuilt-web archive without runtime state or secrets."""
import argparse
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {'node_modules','.venv','__pycache__','.pytest_cache','.git','work','web-data','uploads','paper_results','data'}

def package(output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files=[]
    for directory in ['backend/app','backend/tests','fastread-frontend/src','fastread-frontend/public','fastread-frontend/dist','deploy/web']:
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file())
    for pattern in ['backend/*.py','backend/requirements*.txt','fastread-frontend/*.json','fastread-frontend/*.yaml','fastread-frontend/*.ts','fastread-frontend/index.html']:
        files.extend(ROOT.glob(pattern))
    files = sorted({p for p in files if not any(part in EXCLUDED for part in p.relative_to(ROOT).parts) and not p.name.startswith('.env') and p.suffix not in {'.pyc','.key','.pem','.sqlite3','.db','.log'}})
    with tarfile.open(output,'w:gz') as archive:
        for path in files:
            archive.add(path,arcname=path.relative_to(ROOT).as_posix(),recursive=False)
    output.with_suffix('.manifest.json').write_text(json.dumps([p.relative_to(ROOT).as_posix() for p in files],indent=2))
    print(json.dumps({'archive':str(output),'files':len(files),'bytes':output.stat().st_size}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    package(parser.parse_args().output)
