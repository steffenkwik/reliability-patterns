# Verification record

Local run on **8 October 2026**, Python 3.12 on Windows: **12 tests passed**, exit code 0. The tests used a temporary SQLite database with synthetic records. No company data, network services or credentials were involved.

The run used a writable temporary directory. These tests check behavior; their execution time is not a performance benchmark.

```sh
python -m unittest -v
```

The first hosted GitHub Actions run also passed on 8 October 2026, using Ubuntu and Python 3.12: [inspect the run](https://github.com/steffenkwik/reliability-patterns/actions/runs/37674096518). The workflow badge in the README reports the current hosted result.
