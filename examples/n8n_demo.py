# The real event procedures for this form live in n8n (see the webhook entries
# in n8n_demo.json). Python only shows problems on screen.
import time


def _log(f, text):
    f.lstLog.AddItem(time.strftime("%H:%M:%S  ") + text, 0)


def Form_Load(f):
    _log(f, "Panel started - set N8N_WEBHOOK_BASE to your n8n /webhook/ URL")


def Form_WebhookError(f, message):          # poll failures
    _log(f, "poll failed: " + message[:90])


def cmdAsk_WebhookError(f, message):
    _log(f, "Ask failed: " + message[:90])


def chkAlert_WebhookError(f, message):
    _log(f, "Alert failed: " + message[:90])
