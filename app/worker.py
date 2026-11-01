import logging
import signal
import threading

from app.config import Settings
from app.monitoring.scheduler import WatchScheduler
from app.sellers.service import SellerService
from app.supervision.agent import WatchSupervisor
from app.supervision.service import SupervisionService

logger = logging.getLogger(__name__)


def main() -> int:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s : %(message)s",
    )
    stop_event = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        logger.info("Signal %d reçu : arrêt propre du worker.", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    scheduler = WatchScheduler(
        settings.database_path,
        settings=settings,
        supervisor=WatchSupervisor(
            SupervisionService(
                settings.database_path,
                thresholds=settings.supervision_thresholds(),
                agent_key=settings.agent_key,
                ip_probe_url=settings.supervision_ip_probe_url,
            )
        ),
        seller_service=SellerService(
            per_tick=settings.seller_enrichment_per_tick,
            cache_seconds=settings.seller_cache_seconds,
        ),
    )
    try:
        scheduler.run_forever(stop_event)
    except KeyboardInterrupt:
        stop_event.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
