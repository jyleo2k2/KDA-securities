"""연금 코파일럿 서비스를 한 번에 띄운다. dev.bat이 이 스크립트를 부른다.

백엔드(uvicorn)와 프론트(vite)를 함께 실행해 로그를 한 콘솔에 합치고,
프론트가 실제로 응답하면 브라우저를 연다. Ctrl+C나 창 닫기로 둘 다 정리한다.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
API_PORT = 8000
WEB_PORT = 5173
WEB_URL = f"http://localhost:{WEB_PORT}"
READY_TIMEOUT_SECONDS = 90


def format_output_line(tag: str, raw: bytes) -> str:
    """서버 출력 한 줄에 출처 꼬리표를 붙인다."""

    return f"[{tag}] " + raw.decode("utf-8", errors="replace").rstrip()


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _write_line(line: str) -> None:
    # vite는 "➜" 같은 문자를 흘리는데 한국어 Windows 콘솔(cp949)은 못 낸다.
    # 로그 한 줄 때문에 런처가 죽으면 서버가 고아로 남으므로, 콘솔이 낼 수
    # 있는 문자로 낮춰서라도 계속 출력한다.
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    printable = line.encode(encoding, errors="replace").decode(
        encoding, errors="replace"
    )
    print(printable, flush=True)


def _say(message: str) -> None:
    _write_line(f"[dev] {message}")


def _pump(stream, tag: str) -> None:
    for raw in iter(stream.readline, b""):
        _write_line(format_output_line(tag, raw))


def _spawn(command: list[str], cwd: Path) -> subprocess.Popen:
    # 새 프로세스 그룹으로 띄워야 콘솔의 Ctrl+C가 자식에게 먼저 닿아
    # 반쯤 죽은 상태로 남지 않는다. 종료는 아래에서 명시적으로 처리한다.
    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    return subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )


def _kill_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    # npm이 vite를 손자로 띄우기 때문에 부모만 죽이면 vite가 포트를 문 채
    # 고아로 남는다. Windows에서는 트리째 지워야 다음 실행이 깨지지 않는다.
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _wait_until_ready(url: str) -> bool:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.3)
    return False


def _ensure_frontend_dependencies(npm: str) -> None:
    if (FRONTEND / "node_modules").is_dir():
        return
    _say("frontend 의존성을 설치합니다 (최초 1회, 몇 분 걸릴 수 있음)...")
    subprocess.run([npm, "install"], cwd=FRONTEND, check=True)


def _preflight() -> str | None:
    npm = shutil.which("npm")
    if npm is None:
        _say("npm을 찾지 못했습니다. Node.js를 설치한 뒤 다시 실행해 주세요.")
        return None
    for port, name in ((API_PORT, "백엔드"), (WEB_PORT, "프론트")):
        if port_in_use(port):
            _say(f"포트 {port}({name})가 이미 사용 중입니다.")
            _say("기존에 띄운 서버를 끄고 다시 실행해 주세요.")
            return None
    if not (ROOT / ".env").is_file():
        _say(".env가 없어 공시·뉴스·Claude 재서술 없이 뜹니다(계좌 규칙은 정상).")
    _ensure_frontend_dependencies(npm)
    return npm


def _use_utf8_console() -> None:
    # dev.bat이 콘솔 코드페이지를 65001로 올려두므로 stdout도 맞춰야 한글이
    # 깨지지 않는다. 콘솔이 아닌 곳으로 리다이렉트되면 조용히 넘어간다.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _use_utf8_console()
    npm = _preflight()
    if npm is None:
        return 1

    _say("백엔드와 프론트를 실행합니다...")
    servers = [
        (
            _spawn(
                [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--reload"],
                ROOT,
            ),
            "api",
        ),
        (_spawn([npm, "run", "dev"], FRONTEND), "web"),
    ]
    for process, tag in servers:
        threading.Thread(target=_pump, args=(process.stdout, tag), daemon=True).start()

    try:
        if _wait_until_ready(WEB_URL):
            _say(f"첫 화면을 엽니다 → {WEB_URL}")
            webbrowser.open(WEB_URL)
        else:
            _say("프론트가 시간 안에 뜨지 않았습니다. 위 로그를 확인해 주세요.")
        while all(process.poll() is None for process, _ in servers):
            time.sleep(0.3)
        for process, tag in servers:
            if process.poll() is not None:
                _say(f"{tag}가 코드 {process.returncode}으로 종료됐습니다.")
    except KeyboardInterrupt:
        _say("종료합니다...")
    finally:
        for process, _ in servers:
            _kill_tree(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
