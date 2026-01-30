from plyer import notification
import winsound
import time

_last_alert = 0

def alert(cooldown=5):
    global _last_alert
    now = time.time()

    if now - _last_alert < cooldown:
        return

    _last_alert = now

    # 🔔 Windows notification
    notification.notify(
        title="Blue Archive",
        message="Dialogue option detected!",
        app_name="B.A Game Analysis",
        timeout=3
    )

    # 🔊 Sound alert
    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
