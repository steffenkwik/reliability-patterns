# Verification record

Local run on **8 October 2026**, Python 3.12 on Windows: **12 tests passed**, exit code 0. The tests used a temporary SQLite database with synthetic records. No company data, network services or credentials were involved.

The run used a writable temporary directory. These tests check behavior; their execution time is not a performance benchmark.

```sh
python -m unittest -v
```

The repository includes a GitHub Actions workflow for Python 3.12. A local pass does not imply a public CI pass; inspect the Actions tab for the actual hosted result.
