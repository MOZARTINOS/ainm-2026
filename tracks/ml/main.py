"""
Astar Island — Main Orchestrator
NM i AI 2026

Usage:
  python main.py --token YOUR_JWT_TOKEN
  python main.py --token YOUR_JWT_TOKEN --round ROUND_ID
  python main.py --token YOUR_JWT_TOKEN --poll  (continuous mode)
"""
import argparse
import json
import time
import sys

from api_client import AstarClient
from predictor import DirichletPredictor
from observation import generate_phase_a_queries, generate_phase_b_queries


def run_round(client: AstarClient, round_id: str, verbose: bool = True):
    """Execute full prediction pipeline for one round."""

    if verbose:
        print(f"\n{'='*60}")
        print(f"ROUND: {round_id}")
        print(f"{'='*60}")

    # 1. Get round details (initial map state)
    round_data = client.get_round(round_id)
    width = round_data.get("width", 40)
    height = round_data.get("height", 40)
    num_seeds = len(round_data.get("seeds", [0, 1, 2, 3, 4]))

    if verbose:
        print(f"Map: {width}×{height}, Seeds: {num_seeds}")

    # 2. Check budget
    budget = client.get_budget()
    remaining = budget.get("remaining", 50)
    if verbose:
        print(f"Budget: {remaining} queries remaining")

    if remaining <= 0:
        print("No budget remaining! Submitting with priors only.")
        predictor = DirichletPredictor(width, height)
        _submit_all_seeds(client, round_id, predictor, num_seeds, verbose)
        return

    # 3. Initialize predictor
    predictor = DirichletPredictor(width, height, alpha=2.0)

    # Try to set initial state from round data
    seeds_data = round_data.get("seeds", [])
    for seed_data in seeds_data:
        initial_map = seed_data.get("initial_map") or seed_data.get("map")
        if initial_map:
            predictor.set_initial_state(initial_map)
            if verbose:
                print("Set initial state from round data")
            break

    # 4. Phase A: Systematic observation (40 queries)
    phase_a_budget = min(remaining, 40)
    phase_a_queries = generate_phase_a_queries(num_seeds)[:phase_a_budget]

    if verbose:
        print(f"\nPhase A: {len(phase_a_queries)} observations...")

    for i, (seed, x, y, w, h) in enumerate(phase_a_queries):
        try:
            result = client.simulate(round_id, seed, x, y, w, h)

            # Extract grid from result
            grid = result.get("grid", result.get("cells", []))
            viewport = result.get("viewport", {})
            vx = viewport.get("x", x)
            vy = viewport.get("y", y)

            if grid:
                predictor.update(vx, vy, grid,
                                 result.get("settlements"))
                if verbose and (i + 1) % 10 == 0:
                    print(f"  Observed {i+1}/{len(phase_a_queries)}")

        except Exception as e:
            print(f"  Query {i+1} failed: {e}")
            if "429" in str(e):
                time.sleep(2)
            continue

    # 5. Phase B: Targeted observation (remaining budget)
    budget_after_a = client.get_budget()
    remaining_b = budget_after_a.get("remaining", 0)

    if remaining_b > 0:
        phase_b_queries = generate_phase_b_queries(
            predictor, remaining_b, num_seeds)

        if verbose:
            print(f"\nPhase B: {len(phase_b_queries)} targeted observations...")

        for i, (seed, x, y, w, h) in enumerate(phase_b_queries):
            try:
                result = client.simulate(round_id, seed, x, y, w, h)
                grid = result.get("grid", result.get("cells", []))
                viewport = result.get("viewport", {})
                vx = viewport.get("x", x)
                vy = viewport.get("y", y)
                if grid:
                    predictor.update(vx, vy, grid)
            except Exception as e:
                print(f"  Phase B query {i+1} failed: {e}")
                if "429" in str(e):
                    time.sleep(2)
                continue

    # 6. Submit predictions for all seeds
    if verbose:
        obs_cells = (predictor.total_obs > 0).sum()
        total_cells = width * height
        print(f"\nCoverage: {obs_cells}/{total_cells} cells observed "
              f"({100*obs_cells/total_cells:.1f}%)")

    _submit_all_seeds(client, round_id, predictor, num_seeds, verbose)


def _submit_all_seeds(client, round_id, predictor, num_seeds, verbose):
    """Submit predictions for all seeds."""
    prediction = predictor.to_submission()

    for seed in range(num_seeds):
        try:
            result = client.submit(round_id, seed, prediction)
            if verbose:
                score = result.get("score", "?")
                print(f"  Seed {seed}: submitted (score: {score})")
        except Exception as e:
            print(f"  Seed {seed}: FAILED — {e}")


def find_open_rounds(client: AstarClient) -> list:
    """Find rounds with status 'open'."""
    rounds = client.get_rounds()
    if isinstance(rounds, list):
        return [r for r in rounds if r.get("status") == "open"]
    elif isinstance(rounds, dict):
        all_rounds = rounds.get("rounds", rounds.get("data", []))
        return [r for r in all_rounds if r.get("status") == "open"]
    return []


def poll_mode(client: AstarClient, interval: int = 60):
    """Continuously poll for new rounds and participate."""
    print("Polling mode — checking for new rounds every "
          f"{interval}s. Ctrl+C to stop.")

    participated = set()

    while True:
        try:
            open_rounds = find_open_rounds(client)

            for r in open_rounds:
                rid = r.get("id") or r.get("round_id")
                if rid and rid not in participated:
                    print(f"\nNew round found: {rid}")
                    try:
                        run_round(client, rid)
                        participated.add(rid)
                    except Exception as e:
                        print(f"Round {rid} failed: {e}")

            # Check scores
            try:
                my_rounds = client.get_my_rounds()
                if isinstance(my_rounds, list) and my_rounds:
                    latest = my_rounds[-1]
                    print(f"Latest score: {latest.get('score', '?')} "
                          f"(round: {latest.get('round_id', '?')})")
            except Exception:
                pass

        except Exception as e:
            print(f"Poll error: {e}")

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Astar Island Predictor")
    parser.add_argument("--token", required=True, help="JWT auth token")
    parser.add_argument("--round", help="Specific round ID to participate in")
    parser.add_argument("--poll", action="store_true",
                        help="Continuous polling mode")
    parser.add_argument("--interval", type=int, default=60,
                        help="Poll interval in seconds")
    parser.add_argument("--quiet", action="store_true",
                        help="Minimal output")
    args = parser.parse_args()

    client = AstarClient(args.token)
    verbose = not args.quiet

    if args.round:
        run_round(client, args.round, verbose)
    elif args.poll:
        poll_mode(client, args.interval)
    else:
        # Find and participate in all open rounds
        open_rounds = find_open_rounds(client)
        if not open_rounds:
            print("No open rounds found. Use --poll for continuous mode.")
            # Show available rounds
            try:
                all_rounds = client.get_rounds()
                print(f"All rounds: {json.dumps(all_rounds, indent=2)[:500]}")
            except Exception as e:
                print(f"Error fetching rounds: {e}")
            return

        for r in open_rounds:
            rid = r.get("id") or r.get("round_id")
            if rid:
                run_round(client, rid, verbose)


if __name__ == "__main__":
    main()
