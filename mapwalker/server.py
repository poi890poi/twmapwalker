"""Importable Uvicorn factory so reloaded children retain data and access settings."""
import json
import os
import multiprocessing
import signal
import threading
import logging

from .app import create_app
from .auth import AccessConfig
from .live import signature
from .paths import ROOT


def application():
    options = json.loads(os.environ['MAPWALKER_SERVE_OPTIONS'])
    access = AccessConfig.load(required=options['protected'])
    return create_app(options['data'], worker_enabled=options['worker'],
                      access_config=access, live_reload=True)


def serve_child(config, sockets, stop):
    import asyncio
    import uvicorn
    if os.name == 'nt':
        # A shared listener must not stay associated with a previous child's IOCP.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    config.configure_logging()
    server = uvicorn.Server(config)
    def watch_stop():
        stop.wait()
        server.should_exit = True
    threading.Thread(target=watch_stop,daemon=True).start()
    server.run(sockets=sockets)


def run_reload(port):
    """Keep the listening socket and use an Event (works without a Windows console)."""
    import uvicorn
    config = uvicorn.Config('mapwalker.server:application',factory=True,
                            host='127.0.0.1',port=port,proxy_headers=False)
    socket = config.bind_socket()
    context = multiprocessing.get_context('spawn')
    shutdown = threading.Event()
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, lambda *_: shutdown.set())
    process = None
    stop = None
    logger = logging.getLogger('uvicorn.error')
    try:
        revision = signature((ROOT/'mapwalker').rglob('*.py'))
        while not shutdown.is_set():
            stop = context.Event()
            process = context.Process(target=serve_child,args=(config,[socket],stop))
            process.start()
            logger.info('Auto-update child started [%s]',process.pid)
            candidate = revision
            while not shutdown.wait(1):
                current = signature((ROOT/'mapwalker').rglob('*.py'))
                # Two identical observations avoid restarting during a file save.
                if current != revision and current == candidate:
                    revision = current
                    logger.info('Python changed; draining active work before automatic reload')
                    break
                candidate = current
            stop.set()
            # Lifespan finishes active jobs; a second server never overlaps the old worker.
            process.join()
            process.close()
            process = None
    finally:
        if process is not None:
            stop.set()
            process.join()
            process.close()
        socket.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
