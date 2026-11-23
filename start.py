"""One entry point: create the environment once, then start MeetPoint."""
from pathlib import Path
import hashlib,os,subprocess,sys,venv

ROOT=Path(__file__).resolve().parent

def main():
    if sys.version_info<(3,11):
        print('MeetPoint needs Python 3.11 or newer.');return 1
    os.chdir(ROOT)
    environment=ROOT/'.venv'
    python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():
        print('First start: preparing Python environment...',flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    requirements=ROOT/'requirements.txt';stamp=environment/'meetpoint-requirements.sha256'
    digest=hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text()!=digest:
        subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],check=True)
        stamp.write_text(digest)
    host=os.environ.get('MEETPOINT_HOST','127.0.0.1');port=os.environ.get('PORT','8000')
    print(f'\nMeetPoint is starting. Open http://localhost:{port}\nKeep this window open. Press Ctrl+C to stop.\n',flush=True)
    try:return subprocess.call([str(python),'-m','uvicorn','app.main:app','--host',host,'--port',port])
    except KeyboardInterrupt:return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except subprocess.CalledProcessError:
        print('Dependency installation failed. Check your internet connection and try again.');raise SystemExit(1)
