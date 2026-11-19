import json
import subprocess
import sys
import time
from datetime import datetime

from select_pages import RUN


def main(segment):
    directory = RUN / f'run-{segment:02d}'
    start = json.loads((directory / 'controller-start.json').read_text())
    plan = json.loads((directory / 'prepared-plan.json').read_text())
    expected = {worker['worker_id'] for worker in plan['workers']}
    previous, peak = None, 0
    with (directory / 'worker-observations.jsonl').open('x', buffering=1) as stream:
        while True:
            processes = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,command='], text=True)
            workers = {}
            controller_alive = False
            for line in processes.splitlines():
                parts = line.split(None, 2)
                if len(parts) != 3:
                    continue
                controller_alive |= parts[0] == str(start['pid'])
                if parts[1] != str(start['pid']) or '-m webcollect.candidate_consumer run ' not in parts[2]:
                    continue
                command = parts[2].split()
                worker = command[command.index('--worker-id') + 1]
                if worker in expected:
                    workers[worker] = int(parts[0])
            peak = max(peak, len(workers))
            if previous != workers:
                stream.write(json.dumps({'at': datetime.now().astimezone().isoformat(), 'live': len(workers),
                    'peak': peak, 'workers': workers}) + '\n')
                previous = workers
            if not workers and (not controller_alive or (directory / 'summary.json').is_file()):
                break
            time.sleep(2 if peak < len(expected) else 8)


if __name__ == '__main__':
    main(int(sys.argv[1]))
