"""Media Foundation device enumeration for Windows 10/11."""
from __future__ import annotations

import ctypes
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


def _check_hr(hr: int, context: str) -> None:
    if hr < 0:
        raise MediaFoundationError(f"{context} failed (HRESULT=0x{hr & 0xFFFFFFFF:08X})")


def _release(com_obj: LPUNKNOWN | None) -> None:
    if not com_obj:
        return
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(com_obj.contents.lpVtbl[2])
    release(com_obj)


def enumerate_video_devices() -> list[CameraDevice]:
    """Enumerate camera endpoints via Media Foundation only (no stream activation)."""

    if not hasattr(ctypes, "windll"):
        return []

    ole32 = ctypes.windll.ole32
    mfplat = ctypes.windll.mfplat

    COINIT_MULTITHREADED = 0x0
    MF_VERSION = 0x20070
    MFSTARTUP_NOSOCKET = 0x1

    MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = GUID.from_str("C6E13340-30AC-11D0-A18C-00A0C9118956")
    MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID = GUID.from_str("6480D5A0-CFDD-11D0-BF43-00A0C911CE86")
    MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME = GUID.from_str("60DDC264-4C3A-4B2D-8A0A-40D7B3E6B4D0")
    MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK = GUID.from_str("58F0AAD8-22BF-4F8A-BB3D-D2C4978CF13D")

    attrs = LPUNKNOWN()
    devices_buf = POINTER(LPUNKNOWN)()
    count = c_uint32(0)

    ole32.CoTaskMemFree.argtypes = [c_void_p]

    _check_hr(ole32.CoInitializeEx(None, COINIT_MULTITHREADED), "CoInitializeEx")
    try:
        _check_hr(mfplat.MFStartup(MF_VERSION, MFSTARTUP_NOSOCKET), "MFStartup")
        try:
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

                _check_hr(
                    get_allocated_string(dev, byref(MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME), byref(friendly), byref(friendly_len)),
                    "IMFActivate::GetAllocatedString(friendly)",
                )
                _check_hr(
                    get_allocated_string(dev, byref(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK), byref(symbolic), byref(symbolic_len)),
                    "IMFActivate::GetAllocatedString(symbolic)",
                )

                display_name = ctypes.wstring_at(friendly, friendly_len.value)
                symbolic_link = ctypes.wstring_at(symbolic, symbolic_len.value)

                ole32.CoTaskMemFree(friendly)
                ole32.CoTaskMemFree(symbolic)

                out.append(
                    CameraDevice(
                        id=symbolic_link,
                        display_name=display_name,
                        ffmpeg_name=mf_to_ffmpeg_name(display_name),
                    )
                )
                _release(dev)

            if devices_buf:
                ole32.CoTaskMemFree(devices_buf)
            return sorted(out, key=lambda d: d.display_name.lower())
        finally:
            mfplat.MFShutdown()
    finally:
        _release(attrs)
        ole32.CoUninitialize()
