import threading
import dbus
import dbus.service

class Agent(dbus.service.Object):
    def __init__(self, bus, path, ui_callback, log):
        super().__init__(bus, path)
        self.bus = bus
        self.ui_callback = ui_callback
        self.log = log

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        self.log.info("[Agent] RequestPinCode called for %s", device)
        try:
            threading.Thread(target=self.ui_callback, args=("pin", device), daemon=True).start()
        except Exception:
            self.log.exception("ui_callback thread failed")
        # Return a default PIN immediately (so BlueZ doesn’t time out)
        return "0000"

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        self.log.info("[Agent] RequestPasskey called for %s", device)
        try:
            threading.Thread(target=self.ui_callback, args=("passkey", device), daemon=True).start()
        except Exception:
            self.log.exception("ui_callback thread failed")
        # Return a default numeric passkey (UInt32)
        return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        self.log.info("[Agent] RequestConfirmation called for %s passkey=%s", device, passkey)
        try:
            threading.Thread(target=self.ui_callback, args=("confirm", device, passkey), daemon=True).start()
        except Exception:
            self.log.exception("ui_callback thread failed")
        return  # immediate OK (no exception → confirmation accepted)

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        self.log.info("[Agent] AuthorizeService called for %s uuid=%s", device, uuid)
        try:
            threading.Thread(target=self.ui_callback, args=("authorize", device, uuid), daemon=True).start()
        except Exception:
            self.log.exception("ui_callback thread failed")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        self.log.info("[Agent] Cancel called")
