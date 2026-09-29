import argparse
import json
from pathlib import Path

from .app import ROOT, create_app
from .db import Store
from .detectors import specs
from .geo import tiles, tile_range, validate_bbox
from .sources import HISTORICAL, SOURCES, TileCache
from .worker import Worker
from .paths import default_data
from .auth import AccessConfig


def main():
    parser = argparse.ArgumentParser(description='Mapwalker local map discovery')
    parser.add_argument('--data',type=Path,default=default_data())
    sub = parser.add_subparsers(dest='command',required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--port',type=int,default=8765)
    serve.add_argument('--no-worker',action='store_true')
    access_mode=serve.add_mutually_exclusive_group()
    access_mode.add_argument('--public',action='store_true',help='Require configured sign-in on every app/data route')
    access_mode.add_argument('--tailscale',action='store_true',help='Dedicated loopback listener for private Tailscale Serve')
    plan = sub.add_parser('plan')
    plan.add_argument('--bbox',required=True,help='west,south,east,north')
    plan.add_argument('--max-tiles',type=int,default=2500)
    plan.add_argument('--source',choices=HISTORICAL,action='append')
    plan.add_argument('--estimate-only',action='store_true')
    sub.add_parser('status')
    sub.add_parser('pause')
    sub.add_parser('resume')
    worker = sub.add_parser('work')
    worker.add_argument('--once',action='store_true')
    args = parser.parse_args()
    if args.command=='serve':
        import uvicorn
        access=AccessConfig.load(required=args.public or args.tailscale)
        if args.tailscale and (access.mode!='tailscale' or args.port in (8765,8767)):
            parser.error('Tailscale needs tailscale auth configuration and its own port (for example 8768).')
        if access.mode=='tailscale' and access.enabled and not args.tailscale:
            parser.error('Tailscale identity is accepted only by the dedicated --tailscale listener.')
        uvicorn.run(create_app(args.data,not args.no_worker,access_config=access),host='127.0.0.1',port=args.port,
                    proxy_headers=False)
        return
    store = Store(args.data/'mapwalker.sqlite3')
    store.register(specs())
    if args.command=='plan':
        bbox = validate_bbox(list(map(float,args.bbox.split(','))))
        sources = set(args.source or HISTORICAL)
        count = sum(len(xs)*len(ys) for xs,ys in [tile_range(bbox,SOURCES[s]['max_zoom']) for s in sources])
        print(json.dumps(dict(tiles=count,jobs=count*len(specs()))))
        if args.estimate_only:
            return
        if count>args.max_tiles:
            parser.error(f'{count} tiles exceeds --max-tiles {args.max_tiles}; choose a smaller batch or explicitly raise the limit')
        print('Added jobs:',sum(store.enqueue(s,tiles(bbox,SOURCES[s]['max_zoom'])) for s in sources))
    elif args.command in ('pause','resume'):
        store.pause(args.command=='pause')
    elif args.command=='status':
        print(json.dumps(store.status(),ensure_ascii=False,indent=2))
    elif args.command=='work':
        worker = Worker(store,TileCache(args.data))
        worker.once() if args.once else worker.run()


if __name__=='__main__':
    main()
