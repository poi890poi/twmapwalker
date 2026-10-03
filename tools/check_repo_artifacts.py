"""Reject accidental research artifacts and oversized additions in the Git index."""
import pathlib
import subprocess
import sys

MAX_FILE = 1024 * 1024
MAX_CHANGE = 10 * MAX_FILE
MODELS = {'.npy', '.npz', '.pt', '.pth', '.onnx', '.safetensors'}


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    names = git('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z').split(b'\0')
    errors = []
    total = 0
    for raw in filter(None, names):
        name = raw.decode('utf-8')
        path = pathlib.PurePosixPath(name)
        size = int(git('cat-file', '-s', ':' + name))
        total += size
        if size > MAX_FILE:
            errors.append('{}: {:.2f} MiB exceeds 1 MiB review limit'.format(name, size / MAX_FILE))
        if path.suffix.lower() in MODELS or path.parts[0] in ('data', 'tmp', '.research-cleanup'):
            errors.append(name + ': generated data/model/cache must remain outside Git')
        if path.parts[0] == 'evidence':
            if path.suffix.lower() != '.md' and path.name != 'report.html':
                errors.append(name + ': only text conclusions belong in evidence history')
            elif size > 128 * 1024:
                errors.append(name + ': conclusion exceeds 128 KiB')
            else:
                content = git('show', ':' + name).lower()
                if any(marker in content for marker in (b'data:image/', b'<img', b'<script', b'<svg', b'<iframe', b'<object')):
                    errors.append(name + ': conclusion contains embedded media or scripts')
    if total > MAX_CHANGE:
        errors.append('Staged additions total {:.2f} MiB; limit is 10 MiB'.format(total / MAX_FILE))
    if errors:
        print('Repository artifact check failed:\n- ' + '\n- '.join(errors), file=sys.stderr)
        return 1
    print('Repository artifact check passed ({:.2f} MiB staged).'.format(total / MAX_FILE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
