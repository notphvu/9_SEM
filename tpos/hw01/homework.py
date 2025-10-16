#!/usr/bin/env python3
import argparse
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

SESSION_NAME = "homework"


class HomeworkError(RuntimeError):
    """Custom exception for CLI errors."""


def validate_server_name(value: str) -> str:
    if not re.fullmatch(r"[a-z]{1,32}", value):
        raise argparse.ArgumentTypeError("--name must be 1..32 lowercase Latin letters [a-z]")
    return value


def validate_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--port must be an integer") from exc
    return port


def tmux_session_exists(session: str) -> bool:
    proc = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    detail = proc.stderr.strip() or f"tmux has-session exited with code {proc.returncode}"
    raise HomeworkError(detail)


def tmux_window_exists(session: str, window: str) -> bool:
    proc = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        if proc.returncode == 1:
            return False
        detail = proc.stderr.strip() or f"tmux list-windows exited with code {proc.returncode}"
        raise HomeworkError(detail)
    names = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    return window in names


def tmux_list_windows(session: str) -> List[str]:
    proc = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        if proc.returncode == 1:
            return []
        detail = proc.stderr.strip() or f"tmux list-windows exited with code {proc.returncode}"
        raise HomeworkError(detail)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def run_tmux_command(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        command_text = " ".join(cmd)
        detail = proc.stderr.strip() or f"exit code {proc.returncode}"
        raise HomeworkError(f"tmux command failed ({command_text}): {detail}")


def start_instance(args: argparse.Namespace) -> None:
    cwd = Path.cwd()
    server_source = cwd / "server.py"
    if not server_source.exists():
        raise HomeworkError(f"server.py not found in {cwd}")

    name = args.name
    port = args.port
    target_dir = cwd / name

    if target_dir.exists():
        raise HomeworkError(f"directory {target_dir} already exists")

    session_exists = tmux_session_exists(SESSION_NAME)
    if session_exists and tmux_window_exists(SESSION_NAME, name):
        raise HomeworkError(f"tmux window '{name}' already exists in session '{SESSION_NAME}'")

    try:
        target_dir.mkdir()
    except Exception as exc:
        raise HomeworkError(f"failed to create directory {target_dir}: {exc}") from exc

    try:
        shutil.copy2(server_source, target_dir / "server.py")
    except Exception as exc:
        # Cleanup to avoid leaving a half-prepared instance directory on failure
        shutil.rmtree(target_dir, ignore_errors=True)
        raise HomeworkError(f"failed to copy server.py into {target_dir}: {exc}") from exc

    python_cmd = shlex.quote(sys.executable if sys.executable else "python3")
    command = f"INSTANCE_NAME={name} {python_cmd} server.py --name {name} --port {port} > out.txt 2>&1"

    tmux_cmd: List[str]
    if session_exists:
        tmux_cmd = [
            "tmux",
            "new-window",
            "-t",
            SESSION_NAME,
            "-n",
            name,
            "-c",
            str(target_dir),
            command,
        ]
    else:
        tmux_cmd = [
            "tmux",
            "new-session",
            "-d",
            "-s",
            SESSION_NAME,
            "-n",
            name,
            "-c",
            str(target_dir),
            command,
        ]

    try:
        run_tmux_command(tmux_cmd)
    except Exception:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise

    print(f"Started '{name}' on port {port} in tmux session '{SESSION_NAME}'.")


def stop_instance(args: argparse.Namespace) -> None:
    cwd = Path.cwd()
    name = args.name
    target_dir = cwd / name

    if not target_dir.exists():
        raise HomeworkError(f"directory {target_dir} does not exist")

    if not tmux_session_exists(SESSION_NAME):
        raise HomeworkError(f"tmux session '{SESSION_NAME}' not found")

    if not tmux_window_exists(SESSION_NAME, name):
        raise HomeworkError(f"tmux window '{name}' not found in session '{SESSION_NAME}'")

    window_ref = f"{SESSION_NAME}:{name}"
    run_tmux_command(["tmux", "kill-window", "-t", window_ref])

    backup_dir = cwd / ".backup"
    backup_dir.mkdir(exist_ok=True)

    timestamp = int(time.time())
    dest_path = backup_dir / f"out_{name}_{timestamp}.txt"
    out_path = target_dir / "out.txt"

    if out_path.exists():
        try:
            shutil.move(out_path, dest_path)
        except Exception as exc:
            raise HomeworkError(f"failed to move {out_path} to {dest_path}: {exc}") from exc
    else:
        dest_path.touch()

    try:
        shutil.rmtree(target_dir)
    except Exception as exc:
        raise HomeworkError(f"failed to remove directory {target_dir}: {exc}") from exc

    print(f"Stopped '{name}'. Logs moved to {dest_path}.")


def stop_all_instances(_args: argparse.Namespace) -> None:
    cwd = Path.cwd()
    session_existed = tmux_session_exists(SESSION_NAME)
    if session_existed:
        try:
            run_tmux_command(["tmux", "kill-session", "-t", SESSION_NAME])
        except HomeworkError as exc:
            message = str(exc)
            if "can't find session" not in message:
                raise

    backup_dir = cwd / ".backup"
    backup_dir.mkdir(exist_ok=True)

    dirs = [
        path
        for path in cwd.iterdir()
        if path.is_dir() and re.fullmatch(r"[a-z]{1,32}", path.name)
    ]

    for target_dir in sorted(dirs, key=lambda p: p.name):
        timestamp = int(time.time())
        dest_path = backup_dir / f"out_{target_dir.name}_{timestamp}.txt"
        while dest_path.exists():
            timestamp += 1
            dest_path = backup_dir / f"out_{target_dir.name}_{timestamp}.txt"
        out_path = target_dir / "out.txt"

        if out_path.exists():
            try:
                shutil.move(out_path, dest_path)
            except Exception as exc:
                raise HomeworkError(
                    f"failed to move {out_path} to {dest_path}: {exc}"
                ) from exc
        else:
            dest_path.touch()

        try:
            shutil.rmtree(target_dir)
        except Exception as exc:
            raise HomeworkError(f"failed to remove directory {target_dir}: {exc}") from exc

    if session_existed and tmux_session_exists(SESSION_NAME):
        run_tmux_command(["tmux", "kill-session", "-t", SESSION_NAME])

    print("Stopped all instances.")


def collect_all_instances(_args: argparse.Namespace) -> None:
    if not tmux_session_exists(SESSION_NAME):
        return

    window_names = sorted(tmux_list_windows(SESSION_NAME))
    if not window_names:
        return

    cwd = Path.cwd()
    first = True
    for name in window_names:
        if not first:
            print()
        first = False

        print(f"=== server: {name} ===")
        out_path = cwd / name / "out.txt"
        if not out_path.exists():
            continue
        try:
            content = out_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise HomeworkError(f"failed to read {out_path}: {exc}") from exc
        if content:
            print(content, end="" if content.endswith("\n") else "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage local homework web server instances",
    )
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start", help="start a new server instance")
    start_parser.add_argument(
        "--name",
        required=True,
        type=validate_server_name,
        help="unique instance name [a-z]{1,32}",
    )
    start_parser.add_argument(
        "--port",
        required=True,
        type=validate_port,
        help="port to bind the web server",
    )
    start_parser.set_defaults(func=start_instance)

    stop_parser = subparsers.add_parser("stop", help="stop a running server instance")
    stop_parser.add_argument(
        "--name",
        required=True,
        type=validate_server_name,
        help="name of the instance to stop [a-z]{1,32}",
    )
    stop_parser.set_defaults(func=stop_instance)

    stop_all_parser = subparsers.add_parser("stop_all", help="stop all running server instances")
    stop_all_parser.set_defaults(func=stop_all_instances)

    collect_all_parser = subparsers.add_parser(
        "collect_all",
        help="print combined logs of all active server instances",
    )
    collect_all_parser.set_defaults(func=collect_all_instances)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    try:
        args.func(args)
    except HomeworkError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
