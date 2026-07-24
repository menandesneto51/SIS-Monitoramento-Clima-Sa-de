from __future__ import annotations

import sys
import pandas as pd

from sisclima.validation.preflight import run_preflight, summarize_preflight


def main() -> int:
    df = run_preflight()
    summary = summarize_preflight(df)

    # impressão em texto simples para fácil uso em terminal/log
    with pd.option_context("display.max_colwidth", 220, "display.width", 180):
        print(df.to_string(index=False))

    print("\nRESUMO:")
    for k, v in summary.items():
        print(f"- {k}: {v}")

    # falha com código != 0 quando há pendência crítica
    return 2 if summary["critical_fail"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
