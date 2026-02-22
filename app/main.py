from __future__ import annotations

import signal
import sys
import threading
import time
from app.config import AppConfig
from app.features.base import Feature
from app.features.base import FeatureContext
from app.registry import FEATURES
from app.utils.log import Logger


def _run_feature_worker(feature_key: str, feature: Feature, ctx: FeatureContext, logger: Logger) -> None:
    try:
        feature.run_forever(ctx)
    except Exception as e:
        logger.error(f"Feature crashed: {feature_key} | {e}")


def main() -> None:
    cfg = AppConfig.load()
    logger = Logger(log_file=cfg.logs_dir / "alfred.log")

    if not cfg.enabled_features:
        logger.warn("No enabled_features configured. Exiting.")
        return

    for key in cfg.enabled_features:
        if key not in FEATURES:
            logger.error(f"Unknown feature: {key}")
            return

    def handle_sigterm(_signum, _frame):
        logger.info("Shutdown signal received. Exiting.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    ctx = FeatureContext(config=cfg.feature_config)
    workers: list[threading.Thread] = []

    for feature_key in cfg.enabled_features:
        feature_cls = FEATURES[feature_key]
        feature = feature_cls()
        worker = threading.Thread(
            target=_run_feature_worker,
            args=(feature_key, feature, ctx, logger),
            name=f"feature-{feature_key}",
            daemon=True,
        )
        workers.append(worker)
        worker.start()
        logger.info(f"Started feature={feature_key}")

    while True:
        if not any(worker.is_alive() for worker in workers):
            logger.error("All features stopped. Exiting.")
            return
        time.sleep(1)


if __name__ == "__main__":
    main()
