import logging
import time

from plyer import notification
import winsound

_last_alert = 0

def alert(cooldown=5):
    global _last_alert
    now = time.time()

    if now - _last_alert < cooldown:
        return

    _last_alert = now

    # 🔔 Windows notification
    try:
        notification.notify(
            title="Frame Trace",
            message="Dialogue option detected!",
            app_name="Frame Trace",
            timeout=3
        )
    except Exception:
        logging.error("Notification backend failure", exc_info=True)

    # 🔊 Sound alert
    try:
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        logging.error("Sound backend failure", exc_info=True)
