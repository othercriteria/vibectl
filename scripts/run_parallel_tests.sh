#!/bin/bash
# Run tests in parallel without coverage
# Usage: ./scripts/run_parallel_tests.sh

# Determine number of CPU cores for optimal parallelism
CPUS=$(nproc)

# Use 75% of available CPU cores for testing (leave some for the system)
NUM_WORKERS=$(( CPUS * 3 / 4 ))
if [ $NUM_WORKERS -lt 1 ]; then
    NUM_WORKERS=1
fi

echo "Running tests on $NUM_WORKERS workers..."

# When running without coverage, we can use pytest-xdist
python -m pytest -n $NUM_WORKERS --no-cov "$@"

# Print message about coverage
echo "Note: Coverage data was not collected in parallel mode."
echo "For coverage reporting, run 'python -m pytest' without the -n flag."
