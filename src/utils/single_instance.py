"""
Win32 Named Mutex 单例运行守护 (遵循 python_exe_build_skill.md 规范)
在任何耗时的 Qt 组件加载之前毫秒级检测互斥量，防止多开。
"""
import sys
import ctypes
from ctypes import wintypes


class SingleInstanceGuard:
    ERROR_ALREADY_EXISTS = 183

    def __init__(self, mutex_name: str):
        self._mutex_name = mutex_name
        self._handle = None
        self._already_running = False
        self._acquire()

    def _acquire(self):
        kernel32 = ctypes.windll.kernel32
        self._handle = kernel32.CreateMutexW(None, False, self._mutex_name)
        if kernel32.GetLastError() == self.ERROR_ALREADY_EXISTS:
            self._already_running = True

    def is_already_running(self) -> bool:
        return self._already_running

    def restore_and_activate_existing_window(self, window_title: str):
        """寻找已有主窗口并置顶唤醒"""
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, window_title)
        if hwnd:
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)

    def __del__(self):
        if self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
