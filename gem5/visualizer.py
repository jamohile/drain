"""
Quick script to help visualize log output.
Warning: this code is *incredibly* badly written right now.
         It will be cleaned up later, when there's time, but for now it achieves its purpose.

Usage: After starting a simulation run, run this tool. It will display something resembling the following, live.
"""

import re
from collections import defaultdict
import os
import time

LOG_FILE = "result/log.log"


with open(LOG_FILE, "r") as f:
  start_time = time.time()

  while True:
    experiments = set()
    completed_experiments = set()
    peak_latencies = defaultdict(lambda: 0)

    # Experiments to workers.
    workers = defaultdict(set)
    completed_workers = defaultdict(set)

    for log in f.readlines():
      match = re.match("Experiment: ([^\s]+) ->", log)
      if match is not None:
        experiment_name = match.group(1)
        experiments.add(experiment_name)

        match = re.match(".*worker ([\d\.]+).*", log)
        if match is not None:
          worker_name = match.group(1)
          # Worker level log.
          if "starting" in log:
            workers[experiment_name].add(worker_name)
          if "done" in log:
            completed_workers[experiment_name].add(worker_name)
            match = re.match(".*latency ([\d\.]+).*", log)
            latency = float(match.group(1))
            peak_latencies[experiment_name] = max(peak_latencies[experiment_name], latency)

        else:
          # Experiment level log.
          if "exited" in log:
            completed_experiments.add(experiment_name)

    print(chr(27) + "[2J")

    print("Elapsed Time: %10.1f" % (time.time() - start_time))
    print("")
    print("Experiments %55s" % "%d / %d" % (len(completed_experiments), len(experiments)))
    print("")

    num_workers = sum(len(w) for w in workers.values())
    num_completed_workers = sum(len(w) for w in completed_workers.values())
    print("Workers %57s" % "%3d  / %3d" % (num_completed_workers, num_workers))

    for experiment_name in sorted(experiments):
      w = workers[experiment_name]
      c = completed_workers[experiment_name]

      print("    %s %s    Peak: %5.2f" % ("%-50s" % ("[ %s ] %s" % ("X" if experiment_name in completed_experiments else " ", experiment_name)), "%3d  / %3d" % (len(c), len(w)), peak_latencies[experiment_name]))
    
    time.sleep(0.1)
    f.seek(0)
