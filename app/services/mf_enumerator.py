"""Media Foundation camera enumeration isolated to a dedicated COM worker thread.

PyQt initializes COM as STA on the UI thread. Calling CoInitializeEx with MTA on that
thread can raise RPC_E_CHANGED_MODE. To guarantee stable behavior, all Media Foundation
enumeration happens on a fresh worker thread that owns COM + MF lifetime end-to-end.
"""
from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import POINTER, Structure, byref, c_uint32, c_void_p, wintypes
from uuid import UUID

from app.services.camera_device import CameraDevice, mf_to_ffmpeg_name


class MediaFoundationError(RuntimeError):
    pass


class GUID(Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_str(cls, value: str) -> "GUID":
        raw = UUID(value)
        data4 = (ctypes.c_ubyte * 8).from_buffer_copy(raw.bytes[8:16])
        return cls(raw.time_low, raw.time_mid, raw.time_hi_version, data4)


class IUnknown(Structure):
    _fields_ = [("lpVtbl", POINTER(c_void_p))]


LPUNKNOWN = POINTER(IUnknown)

COINIT_MULTITHREADED = 0x0
MF_VERSION = 0x20070
MFSTARTUP_NOSOCKET = 0x1

MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = GUID.from_str("C6E13340-30AC-11D0-A18C-00A0C9118956")
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID = GUID.from_str("6480D5A0-CFDD-11D0-BF43-00A0C911CE86")
MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME = GUID.from_str("60DDC264-4C3A-4B2D-8A0A-40D7B3E6B4D0")
MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK = GUID.from_str("58F0AAD8-22BF-4F8A-BB3D-D2C4978CF13D")


def _as_hresult(hr: int) -> int:
    return ctypes.c_uint32(hr).value


def _check_hr(hr: int, context: str) -> None:
    value = _as_hresult(hr)
    if value & 0x80000000:
        raise MediaFoundationError(f"{context} failed (HRESULT=0x{value:08X})")


def _release(com_obj: LPUNKNOWN | None) -> None:
    if not com_obj:
        return
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(com_obj.contents.lpVtbl[2])
    release(com_obj)


def _configure_win_api(ole32: ctypes.LibraryLoader, mfplat: ctypes.LibraryLoader) -> None:
    ole32.CoInitializeEx.argtypes = [c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoTaskMemFree.argtypes = [c_void_p]
    ole32.CoTaskMemFree.restype = None

    mfplat.MFStartup.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    mfplat.MFStartup.restype = ctypes.c_long
    mfplat.MFShutdown.argtypes = []
    mfplat.MFShutdown.restype = ctypes.c_long
    mfplat.MFCreateAttributes.argtypes = [POINTER(LPUNKNOWN), ctypes.c_uint32]
    mfplat.MFCreateAttributes.restype = ctypes.c_long
    mfplat.MFEnumDeviceSources.argtypes = [LPUNKNOWN, POINTER(POINTER(LPUNKNOWN)), POINTER(c_uint32)]
    mfplat.MFEnumDeviceSources.restype = ctypes.c_long


def _enumerate_devices_on_worker_thread() -> list[CameraDevice]:
    ole32 = ctypes.windll.ole32
    mfplat = ctypes.windll.mfplat
    _configure_win_api(ole32, mfplat)

    attrs = LPUNKNOWN()
    devices_buf = POINTER(LPUNKNOWN)()
    count = c_uint32(0)
    com_initialized = False
    mf_started = False

    try:
        _check_hr(ole32.CoInitializeEx(None, COINIT_MULTITHREADED), "CoInitializeEx")
        com_initialized = True

        _check_hr(mfplat.MFStartup(MF_VERSION, MFSTARTUP_NOSOCKET), "MFStartup")
        mf_started = True

        _check_hr(mfplat.MFCreateAttributes(byref(attrs), 1), "MFCreateAttributes")

        set_guid = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(GUID))(
            attrs.contents.lpVtbl[6]
        )
        _check_hr(
            set_guid(attrs, byref(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE), byref(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID)),
            "IMFAttributes::SetGUID",
        )

        _check_hr(mfplat.MFEnumDeviceSources(attrs, byref(devices_buf), byref(count)), "MFEnumDeviceSources")

        out: list[CameraDevice] = []
        for idx in range(count.value):
            dev = devices_buf[idx]
            get_allocated_string = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                c_void_p,
                POINTER(GUID),
                POINTER(wintypes.LPWSTR),
                POINTER(c_uint32),
            )(dev.contents.lpVtbl[10])

            friendly = wintypes.LPWSTR()
            friendly_len = c_uint32(0)
            symbolic = wintypes.LPWSTR()
            symbolic_len = c_uint32(0)

            try:
                _check_hr(
                    get_allocated_string(
                        dev,
                        byref(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME),
                        byref(friendly),
                        byref(friendly_len),
                    ),
                    "IMFActivate::GetAllocatedString(friendly)",
                )
                _check_hr(
                    get_allocated_string(
                        dev,
                        byref(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK),
                        byref(symbolic),
                        byref(symbolic_len),
                    ),
                    "IMFActivate::GetAllocatedString(symbolic)",
                )

                display_name = ctypes.wstring_at(friendly, friendly_len.value)
                symbolic_link = ctypes.wstring_at(symbolic, symbolic_len.value)
                out.append(
                    CameraDevice(
                        id=symbolic_link,
                        display_name=display_name,
                        ffmpeg_name=mf_to_ffmpeg_name(display_name),
                    )
                )
            finally:
                if friendly:
                    ole32.CoTaskMemFree(friendly)
                if symbolic:
                    ole32.CoTaskMemFree(symbolic)
                _release(dev)

        return sorted(out, key=lambda d: d.display_name.lower())
    finally:
        if devices_buf:
            ole32.CoTaskMemFree(devices_buf)
        _release(attrs)
        if mf_started:
            mfplat.MFShutdown()
        if com_initialized:
            ole32.CoUninitialize()


class CameraEnumerationWorker(threading.Thread):
    """Dedicated enumeration thread that owns COM/MF init and teardown.

    This thread is intentionally isolated from the Qt UI thread so COM apartment
    mode is deterministic (MTA), preventing RPC_E_CHANGED_MODE collisions.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True, name="camera-enumeration-worker")
        self._result_queue: queue.Queue[tuple[list[CameraDevice], Exception | None]] = queue.Queue(maxsize=1)

    def run(self) -> None:
        try:
            self._result_queue.put((_enumerate_devices_on_worker_thread(), None))
        except Exception as exc:
            self._result_queue.put(([], exc))

    def get_result(self) -> list[CameraDevice]:
        devices, error = self._result_queue.get()
        if error is not None:
            raise error
        return devices


def enumerate_video_devices() -> list[CameraDevice]:
    """Enumerate cameras using a dedicated COM worker thread.

    The caller can be the Qt UI thread; COM and Media Foundation work is never
    executed there.
    """

    if not hasattr(ctypes, "windll"):
        return []

    worker = CameraEnumerationWorker()
    worker.start()
    worker.join()
    return worker.get_result()
