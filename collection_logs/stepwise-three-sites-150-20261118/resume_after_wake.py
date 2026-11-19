"""在这台 Mac 恢复正常唤醒后，执行原固定名单的第三段一次。"""
import os
import plistlib
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from progress import write
from select_pages import ROOT, RUN


ARCHIVE = Path(__file__).resolve().parent
PENDING = RUN / 'resume-on-wake-03'
SEGMENT = RUN / 'run-03'


def power_state():
    data = subprocess.check_output(['/usr/sbin/ioreg', '-r', '-n', 'IOPMrootDomain', '-d', '1', '-a'])
    power = plistlib.loads(data)[0]
    return {'capabilities': power['System Capabilities'], 'wake_type': power.get('Wake Type'),
            'lid_closed': power.get('AppleClamshellState')}


def record(state, **detail):
    write(PENDING / 'state.json', {'state': state, 'at': datetime.now().astimezone().isoformat(),
              'coordinator_pid': os.getpid(), **detail})


def run_script(name, log, *options):
    with (RUN / log).open('a') as stream:
        return subprocess.Popen([sys.executable, '-u', str(ARCHIVE / name), '3', *options], cwd=ROOT,
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)


def main():
    PENDING.mkdir(exist_ok=False)
    try:
        if SEGMENT.exists():
            raise FileExistsError(SEGMENT)
        power = power_state()
        record('WAITING_FOR_FULL_WAKE', power=power)
        while not (PENDING / 'stop.request').exists():
            # The macOS IOPM graphics capability (0x02) is absent in the observed maintenance wakes.
            if power['capabilities'] & 0x02:
                break
            time.sleep(15)
            power = power_state()
        else:
            record('STOPPED_BEFORE_LAUNCH')
            return
        controller = run_script('launch_run.py', 'controller-03.log')
        record('STARTING', controller_pid=controller.pid, power=power)
        subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(controller.pid)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not (SEGMENT / 'controller-start.json').exists():
            if controller.poll() is not None:
                raise RuntimeError(f'Controller exited before startup receipt ({controller.returncode})')
            time.sleep(1)
        watchers = [run_script('observe_workers.py', 'process-observer-03.log'),
                    run_script('progress.py', 'observer-03.log', '--watch'),
                    run_script('close_segment.py', 'close-03.log', '--push')]
        record('RUNNING', controller_pid=controller.pid, observers=[p.pid for p in watchers])
        exit_code = controller.wait()
        record('CONTROLLER_EXIT', controller_pid=controller.pid, returncode=exit_code)
    except Exception as error:
        record('FAILED', error_type=type(error).__name__, reason=str(error))
        raise


if __name__ == '__main__':
    main()
