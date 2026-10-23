"""Load realistic demo data.

Rather than inserting rows by hand, this *replays* auctions through the real services with explicit
timestamps, so every extension, cap and closure in the demo data was produced by the same engine the
API uses.

    python -m scripts.seed              # adds demo data
    python -m scripts.seed --reset      # wipes all tables first
    python -m scripts.seed --if-empty   # only on a database with no RFQs yet (used at deploy time)

Demo logins (password for all: demo1234):
    buyer@demo.com                                        buyer
    bluedart@demo.com, delhivery@demo.com, gati@demo.com,
    tci@demo.com, rivigo@demo.com, vrl@demo.com           suppliers

With SEED_DEMO=true the running API also tops the demo up with fresh live auctions whenever fewer
than two are still open (app/services/demo.py), so a deployed demo never goes stale.
"""
import argparse

from app.services.demo import DEMO_PASSWORD, SUPPLIERS, seed_demo

__all__ = ["DEMO_PASSWORD", "SUPPLIERS", "run"]   # simulate_bidding.py imports these


def run(reset: bool, if_empty: bool = False) -> None:
    print(seed_demo(reset, if_empty))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete all existing data first")
    parser.add_argument("--if-empty", action="store_true", help="only seed a database that has no RFQs yet")
    args = parser.parse_args()
    run(args.reset, args.if_empty)
