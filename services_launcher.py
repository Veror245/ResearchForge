import subprocess
import signal
import sys
import os
import time

workers = [
    "backend.agents.planner",
    "backend.agents.research",
    "backend.agents.claim",
    "backend.agents.critic",
    "backend.agents.debate",
    "backend.agents.report",
]

processes = []
shutdown_requested = False

def start_all():
    for module in workers:
        # start_new_session=True creates a new process group (cleaner than preexec_fn=os.setsid)
        p = subprocess.Popen(
            [sys.executable, "-m", module],
            start_new_session=True
        )
        processes.append(p)
        print(f"Started {module} (PID {p.pid})")

def request_shutdown(signum, frame):
    """Signal handler: must be non-blocking. Just set the flag."""
    global shutdown_requested
    if not shutdown_requested:
        print("\nShutdown signal received. Stopping workers...")
        shutdown_requested = True

signal.signal(signal.SIGINT, request_shutdown)
signal.signal(signal.SIGTERM, request_shutdown)

def kill_all(sig):
    """Send signal to every worker's process group (kills children + grandchildren)."""
    for p in processes:
        try:
            os.killpg(os.getpgid(p.pid), sig)
        except (ProcessLookupError, OSError):
            pass  # already dead

if __name__ == "__main__":
    start_all()

    while True:
        # Reap zombies and check if everyone is already dead
        all_dead = all(p.poll() is not None for p in processes)
        if all_dead:
            break

        if shutdown_requested:
            # Phase 1: polite shutdown
            kill_all(signal.SIGTERM)

            # Wait up to 5 seconds for graceful exit
            for _ in range(25):  # 25 * 0.2s = 5s
                if all(p.poll() is not None for p in processes):
                    break
                time.sleep(0.2)

            # Phase 2: force kill anything still alive (Chromium, stuck crawlers, etc.)
            if not all(p.poll() is not None for p in processes):
                print("Force killing stubborn workers...")
                kill_all(signal.SIGKILL)

                # Give the kernel a moment to reap them
                for _ in range(15):  # 15 * 0.2s = 3s
                    if all(p.poll() is not None for p in processes):
                        break
                    time.sleep(0.2)

            break  # Exit loop after shutdown attempt

        time.sleep(0.5)

    print("All workers stopped.")
    sys.exit(0)