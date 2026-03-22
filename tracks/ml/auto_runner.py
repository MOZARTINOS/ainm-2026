#!/usr/bin/env python3
"""
Astar Island — Autonomous Runner

Runs in a loop, checking for new rounds every 5 minutes.
When a new active round appears (unsubmitted), runs participate_v5.py.
Then monitors until round closes, saves ground truth.

Designed to run overnight unattended.
"""
import subprocess
import requests
import time
import json
import sys
import os
from datetime import datetime, timezone

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
NOTES_DIR = "F:/Workfolder/NM i AI main/repo/notes"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARTICIPATE_SCRIPT = os.path.join(SCRIPT_DIR, "participate_v8.py")

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Competition ends 2026-03-22 14:00 UTC
COMPETITION_END = datetime(2026, 3, 22, 14, 0, 0, tzinfo=timezone.utc)

# Track which rounds we've already handled
handled_rounds = set()


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    # Also append to log file
    with open(os.path.join(NOTES_DIR, "auto_runner.log"), "a") as f:
        f.write(line + "\n")


def get_my_rounds():
    try:
        r = requests.get(f"{BASE}/my-rounds", headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"API error: {e}")
        return []


def save_ground_truth(round_id, round_number):
    """Save ground truth for completed round."""
    log(f"Saving ground truth for R{round_number}...")
    gt = {}
    for seed in range(5):
        try:
            r = requests.get(f"{BASE}/analysis/{round_id}/{seed}", headers=headers, timeout=30)
            if r.status_code == 200:
                data = r.json()
                gt[f"seed_{seed}"] = data.get("ground_truth", data)
            else:
                log(f"  Seed {seed}: HTTP {r.status_code}")
        except Exception as e:
            log(f"  Seed {seed}: error {e}")

    if gt:
        path = os.path.join(NOTES_DIR, f"astar_ground_truth_r{round_number}.json")
        with open(path, "w") as f:
            json.dump(gt, f)
        log(f"  GT saved to {path}")


def run_participate():
    """Run participate_v5.py as subprocess."""
    log("Running participate_v5.py...")
    try:
        result = subprocess.run(
            [sys.executable, PARTICIPATE_SCRIPT],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        # Print output
        for line in result.stdout.strip().split("\n"):
            log(f"  | {line}")
        if result.returncode != 0:
            log(f"  STDERR: {result.stderr[-500:]}")
            log(f"  Exit code: {result.returncode}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log("  TIMEOUT after 600s")
        return False
    except Exception as e:
        log(f"  FAILED: {e}")
        return False


def main():
    log("=" * 60)
    log("=== Astar Island Auto Runner — Starting ===")
    log(f"Competition ends: {COMPETITION_END.isoformat()}")
    log(f"Participate script: {PARTICIPATE_SCRIPT}")
    log("=" * 60)

    # Load already-handled rounds from previous runs
    rounds = get_my_rounds()
    for r in rounds:
        if r.get("status") == "completed" and r.get("seeds_submitted", 0) >= 5:
            handled_rounds.add(r["round_number"])
    log(f"Already handled rounds: {sorted(handled_rounds)}")

    check_interval = 120  # Check every 2 minutes
    last_score_report = 0

    while True:
        now = datetime.now(timezone.utc)

        # Check if competition is over
        if now >= COMPETITION_END:
            log("Competition ended! Final check...")
            rounds = get_my_rounds()
            for r in sorted(rounds, key=lambda x: x["round_number"]):
                s = r.get("round_score")
                w = r.get("round_weight", 1)
                if s:
                    log(f"  R{r['round_number']}: score={s:.2f} weighted={s*w:.2f} rank={r.get('rank')}")
            log("Auto runner stopped.")
            break

        rounds = get_my_rounds()
        if not rounds:
            log("Failed to fetch rounds, retrying in 60s...")
            time.sleep(60)
            continue

        # Find active rounds that need participation
        for r in rounds:
            rn = r.get("round_number", 0)
            status = r.get("status", "")

            if status == "active" and rn not in handled_rounds:
                seeds_sub = r.get("seeds_submitted", 0)
                queries_used = r.get("queries_used", 0)

                if seeds_sub >= 5:
                    # Already submitted, just mark as handled
                    log(f"R{rn}: already submitted {seeds_sub}/5 seeds, marking handled")
                    handled_rounds.add(rn)
                elif queries_used == 0:
                    # Fresh round — run participate!
                    weight = r.get("round_weight", 1)
                    closes = r.get("closes_at", "?")[:19]
                    log(f"")
                    log(f"{'='*50}")
                    log(f"NEW ROUND {rn}! weight={weight:.4f}, closes={closes}")
                    log(f"{'='*50}")

                    success = run_participate()

                    if success:
                        log(f"R{rn}: participate completed successfully!")
                        handled_rounds.add(rn)
                    else:
                        log(f"R{rn}: participate FAILED, will retry next cycle")
                else:
                    # Partially used — something went wrong, try to submit with what we have
                    log(f"R{rn}: {queries_used}/50 queries used but {seeds_sub}/5 submitted — running participate")
                    success = run_participate()
                    if success or seeds_sub >= 5:
                        handled_rounds.add(rn)

            elif status == "completed" and rn not in handled_rounds:
                # Round completed — save GT and log score
                score = r.get("round_score")
                rank = r.get("rank")
                weight = r.get("round_weight", 1)
                seeds_sub = r.get("seeds_submitted", 0)

                if score is not None:
                    weighted = score * weight
                    log(f"R{rn} COMPLETED: score={score:.2f} weighted={weighted:.2f} rank={rank} seeds={seeds_sub}")
                    if seeds_sub > 0:
                        save_ground_truth(r["id"], rn)
                else:
                    log(f"R{rn} completed but no score (seeds_submitted={seeds_sub})")

                handled_rounds.add(rn)

        # Periodic score report (every 30 min)
        if time.time() - last_score_report > 1800:
            best_weighted = 0
            for r in rounds:
                s = r.get("round_score")
                w = r.get("round_weight", 1)
                if s:
                    ww = s * w
                    if ww > best_weighted:
                        best_weighted = ww
            remaining = (COMPETITION_END - now).total_seconds() / 3600
            log(f"Status: best_weighted={best_weighted:.1f}, handled={len(handled_rounds)} rounds, {remaining:.1f}h remaining")
            last_score_report = time.time()

        time.sleep(check_interval)


if __name__ == "__main__":
    main()
