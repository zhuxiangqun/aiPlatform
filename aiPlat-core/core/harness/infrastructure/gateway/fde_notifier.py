u"""FDE Event Notifier — 推送交付事件到企业消息通道 (v2.8)."""

import logging

import os

import time

from typing import Any, Dict



logger = logging.getLogger("fde_notifier")



_NOTIFY_ENABLED = os.getenv("AIPLAT_FDE_NOTIFY_ENABLED", "true").lower() == "true"

_DEFAULT_CHANNELS = os.getenv("AIPLAT_FDE_NOTIFY_CHANNELS", "feishu,wecom,slack")





def notify(

    event_type: str,

    domain_id: str,

    detail: Dict[str, Any] = None,

):

    u"""Send FDE event notification to configured messaging channels."""

    if not _NOTIFY_ENABLED:

        return



    channels = [c.strip() for c in _DEFAULT_CHANNELS.split(",") if c.strip()]

    if not channels:

        return



    try:

        from core.harness.infrastructure.gateway.messaging import MessagingGateway

        gw = MessagingGateway()

        for ch in channels:

            try:

                gw.send(ch, {

                    "title": f"[FDE] {event_type}",

                    "domain": domain_id,

                    "detail": detail or {},

                    "timestamp": time.time(),

                })

            except Exception:

                logging.getLogger(__name__).debug('notify failed', exc_info=True)
    except ImportError:

        logger.debug("MessagingGateway not available, skipping FDE notification")

    except Exception as e:

        logger.debug("FDE notification failed: %s", e)





def _notify_safe(event_type: str, domain_id: str, detail: Dict = None):

    """Safe wrapper — never raises."""

    try:

        notify(event_type, domain_id, detail)

    except Exception:

        logging.getLogger(__name__).debug('_notify_safe failed', exc_info=True)
