"""Command Line Interface (CLI) for AfinaMX Lakehouse Ingestion & Chaos Engine.

Allows local manual execution, debugging, and direct invocation from Airflow BashOperator.

Examples:
    # 1. Standard ingestion into Bronze with realistic dirty data (anomalies on by default)
    python -m src.ingest.cli generate --count 50

    # 2. Ingest clean data without anomalies
    python -m src.ingest.cli generate --count 50 --clean

    # 3. Custom corruption rate and specific anomalies
    python -m src.ingest.cli generate --count 100 --chaos-rate 0.3 --anomalies null_fields,duplicate_orders

    # 4. Preview simulated data to terminal without writing to Bronze
    python -m src.ingest.cli generate --count 5 --dry-run

    # 5. Inspect current checkpoint state
    python -m src.ingest.cli state show

    # 6. Reset checkpoint watermark
    python -m src.ingest.cli state reset --start-order-id 1000
"""

import argparse
import json
import sys
from typing import List, Optional

from src.common.logger import get_logger, setup_logging
from src.ingest import config
from src.ingest.woocommerce.anomalies import SUPPORTED_ANOMALIES
from src.ingest.woocommerce.api_client import WooCommerceAPIClient
from src.ingest.woocommerce.data_simulator import WooCommerceDataSimulator
from src.ingest.woocommerce.state_manager import WooCommerceStateManager

logger = get_logger(__name__)


def handle_generate(args: argparse.Namespace) -> int:
    """Handles the 'generate' command for simulation and ingestion."""
    enable_anomalies = not args.clean
    chaos_rate = (
        args.chaos_rate
        if args.chaos_rate is not None
        else config.SIMULATOR_ANOMALY_RATE
    )

    enabled_anomalies: Optional[List[str]] = None
    if args.anomalies:
        requested = [a.strip() for a in args.anomalies.split(",") if a.strip()]
        invalid = [a for a in requested if a not in SUPPORTED_ANOMALIES]
        if invalid:
            print(f"Error: Unsupported anomaly types: {invalid}", file=sys.stderr)
            print(f"Supported anomalies are: {SUPPORTED_ANOMALIES}", file=sys.stderr)
            return 1
        enabled_anomalies = requested

    if args.dry_run:
        print("\n[DRY RUN] Generating simulated order batch...")
        simulator = WooCommerceDataSimulator(
            enable_anomalies=enable_anomalies,
            anomaly_rate=chaos_rate,
            enabled_anomalies=enabled_anomalies,
        )
        orders = simulator.generate_orders_batch(count=args.count)
        print(
            f"Generated {len(orders)} orders (Anomalies enabled: {enable_anomalies}).\n"
        )
        sample_preview = orders[: min(len(orders), 2)]
        print(json.dumps(sample_preview, indent=2, ensure_ascii=False))
        return 0

    print(
        f"Ingesting {args.count} orders to Bronze "
        f"(Anomalies: {'Enabled' if enable_anomalies else 'Disabled [Clean]'}, "
        f"Chaos Rate: {chaos_rate:.2f})..."
    )

    client = WooCommerceAPIClient(
        use_simulator=True,
        enable_anomalies=enable_anomalies,
        anomaly_rate=chaos_rate,
        enabled_anomalies=enabled_anomalies,
    )

    result = client.extract_and_load(
        batch_size=args.count,
        execution_id=args.execution_id,
        enable_anomalies=enable_anomalies,
    )

    print("\n Ingestion Completed Successfully:")
    print(f"  - Status: {result.get('status')}")
    print(f"  - Records Ingested: {result.get('records_ingested')}")
    print(f"  - New Watermark (Last Order ID): {result.get('last_order_id')}")
    print(f"  - Storage Location: {result.get('storage_location')}")
    return 0


def handle_state_show(args: argparse.Namespace) -> int:
    """Prints current watermark and state file."""
    state_manager = WooCommerceStateManager()
    state = state_manager.load_state()
    print("\n Current WooCommerce Ingestion State:")
    print(json.dumps(state, indent=2))
    return 0


def handle_state_reset(args: argparse.Namespace) -> int:
    """Resets the state file to initial parameters."""
    state_manager = WooCommerceStateManager()
    state_manager.update_state(
        last_order_id=args.start_order_id,
        status="INITIALIZED",
        force=True,
    )
    print(f"\n State successfully reset to order_id={args.start_order_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m src.ingest.cli",
        description="AfinaMX Lakehouse Ingestion & Anomaly Injection CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: generate
    generate_parser = subparsers.add_parser(
        "generate",
        help="Simulate and ingest order batches into Bronze Layer",
    )
    generate_parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=50,
        help="Number of orders to generate in this batch (default: 50)",
    )
    generate_parser.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help="Skip anomaly injection and generate 100%% pristine valid data",
    )
    generate_parser.add_argument(
        "-r",
        "--chaos-rate",
        type=float,
        default=None,
        help="Probability rate for anomaly injection (0.0 to 1.0, default: 0.15)",
    )
    generate_parser.add_argument(
        "-a",
        "--anomalies",
        type=str,
        default=None,
        help=f"Comma-separated list of anomaly types to enable (supported: {','.join(SUPPORTED_ANOMALIES)})",
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Generate and print sample payload without persisting to storage",
    )
    generate_parser.add_argument(
        "--execution-id",
        type=str,
        default=None,
        help="Optional custom execution ID for audit logging",
    )

    # Command: state
    state_parser = subparsers.add_parser(
        "state", help="Manage checkpoint watermark state"
    )
    state_subparsers = state_parser.add_subparsers(
        dest="state_command", help="State subcommands"
    )

    # state show
    state_subparsers.add_parser("show", help="Display current checkpoint metadata")

    # state reset
    reset_parser = state_subparsers.add_parser(
        "reset", help="Reset checkpoint watermark"
    )
    reset_parser.add_argument(
        "--start-order-id",
        type=int,
        default=1000,
        help="Starting order ID checkpoint (default: 1000)",
    )

    return parser


def main() -> int:
    """Main CLI execution entrypoint."""
    setup_logging(level=config.LOG_LEVEL)
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "generate":
        return handle_generate(args)
    elif args.command == "state":
        if args.state_command == "show":
            return handle_state_show(args)
        elif args.state_command == "reset":
            return handle_state_reset(args)
        else:
            parser.parse_args(["state", "--help"])
            return 1
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
