#!/usr/bin/env python3
"""Push files into the live iOS root over USB Ethernet (kernel side: bsd/dev/ishtar_push.c, boot-arg ishtarpush=1).

  push.py SRC DEST     SRC a file or a directory (sent recursively), DEST its absolute path on the phone
  push.py --rm DEST    remove the file DEST on the phone
  push.py --ls DIR     list DIR on the phone (/private/var/ only)
  push.py --get SRC OUT   copy the file SRC from the phone to OUT (/private/var/ only)
  push.py --pull DIR OUT  copy the directory DIR recursively to OUT (e.g. the unified log: /private/var/db/diagnostics)
  push.py --set NAME VALUE  set a kernel knob live (e.g. dpu.zc 0); push.py --set ? lists them
  push.py --reboot-bootloader  sync, unmount and reboot the phone into fastboot (no buttons)
  e.g. push.py ../UniXNU/build/adreno-metal-plugin/NativeAdrenoMetal.bundle /System/Library/Extensions/NativeAdrenoMetal.bundle
The phone only writes under /System/Library/Extensions/ and /private/var/. Modes are kept; owner is root.
"""
import os, socket, struct, sys, time

PHONE = ('192.168.7.2', 5141)


def entries(src, dest):
    if os.path.isfile(src):
        yield 'F', src, dest
        return
    yield 'D', src, dest
    for root, dirs, files in os.walk(src):
        dirs.sort()
        rel = os.path.relpath(root, src)
        base = dest if rel == '.' else f'{dest}/{rel}'
        for d in dirs:
            yield 'D', os.path.join(root, d), f'{base}/{d}'
        for f in sorted(files):
            yield 'F', os.path.join(root, f), f'{base}/{f}'


def request(kind, path):
    """One 'L' or 'G' request on its own connection: the answer's bytes (empty on an error)."""
    s = socket.create_connection(PHONE, timeout=60)
    p = path.encode()
    s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord(kind), 0, len(p), 0) + p)
    err, size = struct.unpack('<IQ', s.recv(12, socket.MSG_WAITALL))
    data = bytearray()
    while len(data) < size and (chunk := s.recv(min(1 << 20, size - len(data)))):
        data += chunk
    s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('X'), 0, 0, 0))
    s.close()
    return b'' if err else bytes(data)


def main():
    if sys.argv[1:] == ['--reboot-bootloader']:
        s = socket.create_connection(PHONE, timeout=60)
        s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('B'), 0, 0, 0))
        err, = struct.unpack('<I', s.recv(4, socket.MSG_WAITALL))
        print('rebooting to fastboot' if not err else f'errno {err}')
        return
    if len(sys.argv) >= 3 and sys.argv[1] == '--set':
        s = socket.create_connection(PHONE, timeout=60)
        name = sys.argv[2].encode()
        value = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
        s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('S'), 0, len(name), value) + name)
        if sys.argv[2] == '?':
            err, size = struct.unpack('<IQ', s.recv(12, socket.MSG_WAITALL))
            sys.stdout.write(s.recv(size, socket.MSG_WAITALL).decode(errors='replace'))
        else:
            err, = struct.unpack('<I', s.recv(4, socket.MSG_WAITALL))
            print(f'{sys.argv[2]} = {value}' if not err else f'{sys.argv[2]}: errno {err}')
        s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('X'), 0, 0, 0))
        return
    if len(sys.argv) < 3 or not sys.argv[2].startswith('/') or (sys.argv[1] in ('--get', '--pull')) != (len(sys.argv) == 4):
        sys.exit(__doc__)
    if sys.argv[1] == '--pull':
        total, start = 0, time.time()
        todo = [(sys.argv[2].rstrip('/'), sys.argv[3])]
        while todo:
            remote, local = todo.pop()
            os.makedirs(local, exist_ok=True)
            for line in request('L', remote).decode(errors='replace').splitlines():
                kind, name = line.split(' ', 1)
                if name in ('.', '..'):
                    continue
                if kind == '4':
                    todo.append((f'{remote}/{name}', os.path.join(local, name)))
                elif kind == '8':
                    data = request('G', f'{remote}/{name}')
                    open(os.path.join(local, name), 'wb').write(data)
                    total += len(data)
        print(f'{total / 1e6:.1f} MB in {time.time() - start:.0f} s')
        return
    if sys.argv[1] in ('--ls', '--get'):
        s = socket.create_connection(PHONE, timeout=60)
        path = sys.argv[2].encode()
        s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('L' if sys.argv[1] == '--ls' else 'G'), 0, len(path), 0) + path)
        err, size = struct.unpack('<IQ', s.recv(12, socket.MSG_WAITALL))
        data = bytearray()
        while len(data) < size and (chunk := s.recv(min(1 << 20, size - len(data)))):
            data += chunk
        s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('X'), 0, 0, 0))
        if err:
            sys.exit(f'{sys.argv[2]}: errno {err}')
        if sys.argv[1] == '--ls':
            sys.stdout.write(data.decode(errors='replace'))
        else:
            open(sys.argv[3], 'wb').write(data)
            print(f'{len(data)} of {size} bytes -> {sys.argv[3]}')
        return
    s = socket.create_connection(PHONE, timeout=60)
    sent, failed, start = 0, 0, time.time()
    if sys.argv[1] == '--rm':
        path = sys.argv[2].encode()
        s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('R'), 0, len(path), 0) + path)
        err, = struct.unpack('<I', s.recv(4, socket.MSG_WAITALL))
        s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('X'), 0, 0, 0))
        sys.exit(f'{sys.argv[2]}: errno {err}' if err else 0)
    for kind, local, remote in entries(sys.argv[1].rstrip('/'), sys.argv[2].rstrip('/')):
        if os.path.islink(local):
            sys.exit(f'{local}: symlinks are not supported')
        st = os.stat(local)
        size = st.st_size if kind == 'F' else 0
        path = remote.encode()
        s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord(kind), st.st_mode & 0o7777, len(path), size) + path)
        if kind == 'F':
            with open(local, 'rb') as f:
                while chunk := f.read(1 << 20):
                    s.sendall(chunk)
            sent += size
        err, = struct.unpack('<I', s.recv(4, socket.MSG_WAITALL))
        if err:
            failed += 1
            print(f'{remote}: errno {err}')
    s.sendall(b'ISHP' + struct.pack('<B3xIIQ', ord('X'), 0, 0, 0))
    s.recv(4, socket.MSG_WAITALL)
    t = time.time() - start
    print(f'{sent / 1e6:.1f} MB in {t:.1f} s ({sent / 1e6 / max(t, 1e-3):.1f} MB/s), {failed} failed')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
