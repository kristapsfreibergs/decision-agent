#!/usr/bin/env python3
"""Run A0 (baseline), C (validators), and F (full governance) evaluations with configurable reps across providers."""

import argparse
import concurrent.futures
import os
from pathlib import Path
from decision_agent.modules.evaluation.single_run import run_case_study


def run_reps(case_id: str, condition: str, reps: int, timeout_seconds: float = 600.0, provider: str | None = None, rep_offset: int = 0):
    """Run multiple reps in parallel."""
    # Save current provider if switching
    original_provider = os.environ.get("MODEL_PROVIDER")
    if provider:
        os.environ["MODEL_PROVIDER"] = provider
        # Clear any cached provider
        from decision_agent.shared.providers import registry
        # Force reload by clearing module state if needed

    provider_name = os.environ.get("MODEL_PROVIDER", "anthropic")
    print(f"\n{'='*60}")
    print(f"Running {condition} condition: {reps} reps [{provider_name.upper()}]")
    print(f"{'='*60}\n")

    def run_rep(rep):
        actual_rep = rep + rep_offset  # Offset rep number by provider
        print(f"Starting {condition} rep{actual_rep} ({provider_name})...", flush=True)
        result = run_case_study(case_id, condition, actual_rep, timeout_seconds=timeout_seconds)
        status = "OK" if not result.get("error") else f"ERROR: {result['error'][:100]}"
        print(f"Finished {condition} rep{actual_rep}: {status}", flush=True)
        return result

    # Use max_workers=1 for OpenAI (sequential, rate limits), batch of 10 for Anthropic
    max_workers = 1 if provider == "openai" else min(10, reps)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_rep, r): r for r in range(reps)}
        results = {}
        for f in concurrent.futures.as_completed(futures):
            rep = futures[f]
            try:
                results[rep] = f.result()
            except Exception as e:
                print(f"Rep {rep} raised: {e}", flush=True)
                results[rep] = {"error": str(e)}

    # Summary
    print(f"\n{'='*60}")
    print(f"Summary for {condition} [{provider_name.upper()}]")
    print(f"{'='*60}")
    ok = sum(1 for r in results.values() if not r.get("error"))
    err = sum(1 for r in results.values() if r.get("error"))
    print(f"OK: {ok}, Errors: {err}")
    for r in range(reps):
        m = results.get(r, {})
        e = m.get("error", "")
        if e:
            print(f"  rep{r}: ERROR {e[:80]}")

    # Restore original provider
    if original_provider:
        os.environ["MODEL_PROVIDER"] = original_provider
    elif provider:
        del os.environ["MODEL_PROVIDER"]

    return results


def main():
    parser = argparse.ArgumentParser(description="Run case study evaluations with multiple providers")
    parser.add_argument(
        "--case",
        default="procurement_laptops",
        help="Case study ID (default: procurement_laptops)",
    )
    parser.add_argument(
        "--a0-reps",
        type=int,
        default=5,
        help="Number of A0 (informed baseline) reps (default: 5)",
    )
    parser.add_argument(
        "--c-reps",
        type=int,
        default=5,
        help="Number of C (validators) reps (default: 5)",
    )
    parser.add_argument(
        "--skip-a0",
        action="store_true",
        help="Skip A0 baseline runs",
    )
    parser.add_argument(
        "--f-reps",
        type=int,
        default=5,
        help="Number of F (full governance) reps (default: 5)",
    )
    parser.add_argument(
        "--skip-c",
        action="store_true",
        help="Skip C validator runs",
    )
    parser.add_argument(
        "--skip-f",
        action="store_true",
        help="Skip F full governance runs",
    )
    parser.add_argument(
        "--providers",
        type=str,
        default="anthropic,openai",
        help="Comma-separated providers to test (default: anthropic,openai)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Timeout per run in seconds (default: 600)",
    )

    args = parser.parse_args()
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]

    print(f"\n{'#'*60}")
    print(f"# Evaluation Suite")
    print(f"# Case: {args.case}")
    conditions = [c for c, skip in [("A0", args.skip_a0), ("C", args.skip_c), ("F", args.skip_f)] if not skip]
    print(f"# Conditions: {conditions}")
    print(f"# Providers: {providers}")
    print(f"{'#'*60}")

    rep_offset = 0
    for i, provider in enumerate(providers):
        print(f"\n{'*'*60}")
        print(f"* Provider: {provider.upper()} (reps {rep_offset}-{rep_offset + args.a0_reps - 1})")
        print(f"{'*'*60}")

        if not args.skip_a0:
            run_reps(args.case, "A0", args.a0_reps, timeout_seconds=args.timeout, provider=provider, rep_offset=rep_offset)

        if not args.skip_c:
            run_reps(args.case, "C", args.c_reps, timeout_seconds=args.timeout, provider=provider, rep_offset=rep_offset)

        if not args.skip_f:
            run_reps(args.case, "F", args.f_reps, timeout_seconds=args.timeout, provider=provider, rep_offset=rep_offset)

        rep_offset += max(args.a0_reps, args.c_reps, args.f_reps)  # Offset by the largest count

    print(f"\n{'='*60}")
    print("All evaluations complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
