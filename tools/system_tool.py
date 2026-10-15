"""
tools/system_tool.py — System and desktop application launcher for JARVIS.

Supports launching native Windows apps:
- Calculator (calc.exe)
- Notes / Notepad (notepad.exe)
- Task Manager (taskmgr.exe)
- Web Browser / Search (via default system browser)
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import urllib.parse
import webbrowser
from typing import Optional

logger = logging.getLogger(__name__)

# Allowed application mappings
_APP_MAP = {
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "notes": "notepad.exe",
    "notepad": "notepad.exe",
    "note": "notepad.exe",
    "task_manager": "taskmgr.exe",
    "task manager": "taskmgr.exe",
    "taskmanager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "tasks": "taskmgr.exe",
    "browser": "browser",
    "web": "browser",
    "internet": "browser",
}


def open_app(app_name: str) -> dict:
    """
    Launch a local application (calculator, notes/notepad, task manager, web browser).
    """
    clean_name = (app_name or "").strip().lower()
    if clean_name not in _APP_MAP:
        allowed = sorted(set(_APP_MAP.keys()))
        raise ValueError(
            f"Unsupported application '{app_name}'. "
            f"Allowed applications: {allowed}"
        )

    target = _APP_MAP[clean_name]

    if target == "browser":
        success = webbrowser.open("https://www.google.com")
        return {
            "success": True,
            "app_name": clean_name,
            "target": "Default Web Browser",
            "message": "Opened default web browser",
        }

    # Locate executable
    exec_path = shutil.which(target)
    if not exec_path:
        # Fallback to system32 standard path on Windows
        sys32_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", target)
        if os.path.exists(sys32_path):
            exec_path = sys32_path
        else:
            raise RuntimeError(f"Executable '{target}' not found on system path.")

    try:
        proc = subprocess.Popen([exec_path], shell=False)
        logger.info("Launched %s (PID: %s)", target, proc.pid)
        return {
            "success": True,
            "app_name": clean_name,
            "executable": exec_path,
            "pid": proc.pid,
            "message": f"Successfully launched {clean_name} ({target})",
        }
    except Exception as exc:
        logger.exception("Failed to launch %s: %s", target, exc)
        raise RuntimeError(f"Failed to launch '{clean_name}': {exc}") from exc


def verify_app_opened(result: dict) -> dict:
    """Verify that the application launch command completed successfully."""
    if not isinstance(result, dict) or not result.get("success"):
        return {"verified": False, "reason": "App launch did not succeed"}
    return {
        "verified": True,
        "app_name": result.get("app_name"),
        "message": result.get("message", "App launched successfully"),
    }


def open_web(url: Optional[str] = None, query: Optional[str] = None) -> dict:
    """
    Open a web URL or perform a web search in the default web browser.
    """
    if not url and not query:
        target_url = "https://www.google.com"
    elif query:
        encoded = urllib.parse.quote_plus(query.strip())
        target_url = f"https://www.google.com/search?q={encoded}"
    else:
        target_url = url.strip()
        if not target_url.startswith(("http://", "https://")):
            target_url = "https://" + target_url

    try:
        webbrowser.open(target_url)
        return {
            "success": True,
            "url": target_url,
            "query": query,
            "message": f"Opened {target_url} in web browser",
        }
    except Exception as exc:
        logger.exception("Failed to open web URL %s: %s", target_url, exc)
        raise RuntimeError(f"Failed to open web browser: {exc}") from exc


def verify_web_opened(result: dict) -> dict:
    """Verify web opening action."""
    if not isinstance(result, dict) or not result.get("success"):
        return {"verified": False, "reason": "Failed to open web"}
    return {
        "verified": True,
        "url": result.get("url"),
        "message": result.get("message", "Web opened successfully"),
    }
