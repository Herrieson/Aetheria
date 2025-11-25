import argparse

from aetheria_simple import evaluate
from aetheria_simple.data_configs import USB_TEXT_IMG_RELABELED_DATASET_CONFIG

DATASET_PATH = ""

def non_negative_int(value: str) -> int:
    ivalue = int(value)
    if ivalue < 0:
        raise argparse.ArgumentTypeError("Skip must be a non-negative integer.")
    return ivalue


def main() -> None:
    parser = argparse.ArgumentParser(description="Run simplified multi-agent evaluation.")
    parser.add_argument("-l", "--limit", type=int, default=None, help="Limit the number of samples.")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of worker threads.")
    parser.add_argument(
        "-s",
        "--skip",
        type=non_negative_int,
        default=0,
        help="Number of samples to skip before starting the evaluation.",
    )
    parser.add_argument(
        "-d",
        "--dataset",
        type=str,
        default=DATASET_PATH,
        help="Path to the evaluation dataset JSON file.",
    )
    args = parser.parse_args()

    evaluate.run_evaluation(
        dataset_path=args.dataset,
        limit=args.limit,
        workers=args.workers,
        skip=args.skip,
        dataset_config=USB_TEXT_IMG_RELABELED_DATASET_CONFIG,
    )


if __name__ == "__main__":
    main()
