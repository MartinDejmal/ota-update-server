import argparse, urllib.request
from .db import init_db
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd"); sub.add_parser("db").add_subparsers().add_parser("upgrade"); h=sub.add_parser("healthcheck"); h.add_argument("--url",required=True); sub.add_parser("serve").add_argument("--host",default="0.0.0.0"); args=p.parse_args()
    if args.cmd=="db": init_db(); return
    if args.cmd=="healthcheck":
        try: urllib.request.urlopen(args.url,timeout=3); return
        except Exception: raise SystemExit(1)
    if args.cmd=="serve":
        import uvicorn; uvicorn.run("app.main:app",host=getattr(args,"host","0.0.0.0"),port=getattr(args,"port",8000))
if __name__=="__main__": main()
