# launcher.py
import subprocess
import signal
import sys
import os

workers = [
    "backend.agents.planner",
    "backend.agents.research",
    "backend.agents.claim",
    "backend.agents.critic",
    "backend.agents.debate",
    "backend.agents.report",
]

processes = []

def start_all():
    for module in workers:
        p = subprocess.Popen(
            [sys.executable, "-m", module],
            preexec_fn=os.setsid  # each worker gets its own process group
        )
        processes.append(p)
        print(f"Started {module} (PID {p.pid})")

def shutdown(signum, frame):
    print("\nShutting down workers...")
    for p in processes:
        try:
            # Kill the entire process group (includes grandchildren)
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    # Wait for graceful exit
    for p in processes:
        p.wait()
    print("All workers stopped.")
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

if __name__ == "__main__":
    start_all()
    # Keep main thread alive
    for p in processes:
        p.wait()