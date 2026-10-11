"""Linux seccomp egress guard, inherited across exec; no native socket bypass."""

import ctypes
import errno
import platform


def install():
    machine = platform.machine()
    profiles = {
        "x86_64": (0xC000003E, 41, 42, 44, 46),
        "aarch64": (0xC00000B7, 198, 203, 206, 211),
    }
    if platform.system() != "Linux" or machine not in profiles:
        raise RuntimeError("offline_os_guard_platform_unsupported")
    arch, socket_nr, connect_nr, sendto_nr, sendmsg_nr = profiles[machine]

    class Filter(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint32),
        ]

    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

    # Check ABI, deny connect, and block network socket creation. UNIX
    # socketpair send operations remain available for asyncio/stdio IPC.
    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, arch),
        (0x06, 0, 0, 0x00050000 | errno.EPERM),
        (0x20, 0, 0, 0),
    ]
    if machine == "x86_64":
        # x32 uses the same audit arch; reject its alternate syscall numbers.
        instructions.extend(
            [(0x45, 0, 1, 0x40000000), (0x06, 0, 0, 0x00050000 | errno.EPERM)]
        )
    # No io_uring alternative for asynchronous native networking.
    for nr in (connect_nr, 425, 426, 427):
        instructions.extend([(0x15, 0, 1, nr), (0x06, 0, 0, 0x00050000 | errno.EPERM)])
    instructions.extend(
        [
            (0x15, 0, 6, socket_nr),
            (0x20, 0, 0, 16),
            (0x15, 3, 0, 2),
            (0x15, 2, 0, 10),
            (0x15, 1, 0, 17),
            (0x06, 0, 0, 0x7FFF0000),
            (0x06, 0, 0, 0x00050000 | errno.EPERM),
            (0x06, 0, 0, 0x7FFF0000),
        ]
    )
    filters = (Filter * len(instructions))(*(Filter(*row) for row in instructions))
    program = Program(len(instructions), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if (
        libc.prctl(38, 1, 0, 0, 0) != 0
        or libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0
    ):
        raise RuntimeError("offline_os_guard_install_failed")
