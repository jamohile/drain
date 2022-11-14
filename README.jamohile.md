Working Name:
# DRANO: DRAIN, optimized.

**Goal**: improve performance of DRAIN by dynamically optimizing drain frequency based on workload performance.

This will be formalized later, but for now, will track major changes to the existing DRAIN work.

- Completely rewrote run_script, to achieve a very high degree of parallelism. Now, the whole benchmark suite runs in under 15 minutes (vs, I'm pretty sure a few hours?)
  - TODO: still some weird issues with stragglers getting by the locks.
  - Has been cross-validated against baseline.

- Creation of a visualizer to help track simulation output.
  - `python visualizer.py`