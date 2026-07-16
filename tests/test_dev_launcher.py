import io
import socket
import sys

from scripts.dev import _pump, format_output_line, port_in_use


def test_logging_survives_a_console_that_cannot_encode_vite_output(monkeypatch) -> None:
    # vite는 "➜"를 출력하지만 한국어 Windows 콘솔(cp949)은 이 문자를 못 낸다.
    # 로그 한 줄 때문에 pump 스레드가 죽으면 그 뒤 서버 로그가 통째로 사라진다.
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp949", errors="strict")
    monkeypatch.setattr(sys, "stdout", console)

    _pump(io.BytesIO("➜  Local: http://localhost:5173\n".encode()), "web")
    console.flush()

    printed = console.buffer.getvalue().decode("cp949")
    assert "[web]" in printed
    assert "Local: http://localhost:5173" in printed


def test_output_lines_are_tagged_with_their_source() -> None:
    assert format_output_line("api", b"INFO: started\r\n") == "[api] INFO: started"


def test_output_line_survives_broken_encoding() -> None:
    # uvicorn·vite는 Windows 콘솔 코드페이지에 따라 깨진 바이트를 흘린다.
    # 로그 한 줄 때문에 런처가 죽으면 안 된다.
    assert format_output_line("web", b"ready \xff\xfe").startswith("[web] ready ")


def test_port_in_use_detects_a_bound_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        port = taken.getsockname()[1]

        assert port_in_use(port)


def test_port_in_use_is_false_for_a_free_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    assert not port_in_use(port)
