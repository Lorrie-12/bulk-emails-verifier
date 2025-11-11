thonimport argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Ensure src directory is on sys.path so namespace packages like `modules` work
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from modules.validator import EmailValidator  # type: ignore  # noqa: E402
from utils.parser import load_emails_from_file  # type: ignore  # noqa: E402
from utils.formatter import results_to_json, save_json_to_file  # type: ignore  # noqa: E402

DEFAULT_CONFIG_PATH = os.path.join(CURRENT_DIR, "config", "settings.example.json")

def load_settings(config_path: str) -> Dict[str, Any]:
    """
    Load settings from a JSON configuration file.
    Falls back to safe defaults if file is missing or invalid.
    """
    defaults: Dict[str, Any] = {
        "default_input_path": os.path.join(os.path.dirname(CURRENT_DIR), "data", "sample_emails.txt"),
        "default_output_path": os.path.join(os.path.dirname(CURRENT_DIR), "data", "output.json"),
        "dns_timeout": 5,
        "smtp_timeout": 8,
        "log_level": "INFO",
    }

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Config root must be an object")
        defaults.update(data)
    except FileNotFoundError:
        # Use defaults silently
        pass
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Warning: Failed to load config from {config_path}: {exc}. Using defaults.")

    return defaults

def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def parse_args(settings: Dict[str, Any]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk Emails Verifier - validate and enrich email lists at scale."
    )
    parser.add_argument(
        "--input",
        "-i",
        dest="input_path",
        default=settings.get("default_input_path"),
        help="Path to input file containing emails (one per line).",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_path",
        default=settings.get("default_output_path"),
        help="Path to output JSON file.",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        help="Optionally limit the number of emails processed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run validation and print results to stdout without writing output.json.",
    )
    return parser.parse_args()

def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

def main(argv: Optional[List[str]] = None) -> int:
    settings = load_settings(DEFAULT_CONFIG_PATH)
    configure_logging(settings.get("log_level", "INFO"))
    logger = logging.getLogger("main")

    args = parse_args(settings)

    logger.info("Starting Bulk Emails Verifier")
    logger.debug("Using settings: %s", settings)

    try:
        emails = load_emails_from_file(args.input_path, limit=args.limit)
    except FileNotFoundError:
        logger.error("Input file not found: %s", args.input_path)
        return 1
    except OSError as exc:
        logger.error("Failed to read input file %s: %s", args.input_path, exc)
        return 1

    if not emails:
        logger.warning("No emails found in input file. Nothing to do.")
        return 0

    logger.info("Loaded %d email(s) from %s", len(emails), args.input_path)

    validator = EmailValidator(
        dns_timeout=settings.get("dns_timeout", 5),
        smtp_timeout=settings.get("smtp_timeout", 8),
    )

    results: List[Dict[str, Any]] = []
    for idx, email in enumerate(emails, start=1):
        logger.debug("Validating %s/%s: %s", idx, len(emails), email)
        try:
            result = validator.validate(email)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while validating %s: %s", email, exc)
            results.append(
                {
                    "email": email,
                    "email_status": "unknown",
                    "message": f"Internal error during validation: {exc}",
                    "format": "unknown",
                    "mailbox_status": "unknown",
                    "mailbox_type": "unknown",
                    "domain": "",
                }
            )

    json_str = results_to_json(results)

    if args.dry_run:
        print(json_str)
        logger.info("Dry run complete - results printed to stdout.")
        return 0

    ensure_parent_dir(args.output_path)
    try:
        save_json_to_file(json_str, args.output_path)
    except OSError as exc:
        logger.error("Failed to write output file %s: %s", args.output_path, exc)
        return 1

    logger.info("Successfully wrote %d result(s) to %s", len(results), args.output_path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())