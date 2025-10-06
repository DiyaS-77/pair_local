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
        event = threading.Event()
        response_holder = {}

        def callback():
            response_holder['resp'] = self.ui_callback("pin", device)
            event.set()

        threading.Thread(target=callback, daemon=True).start()
        event.wait(timeout=30)
        return response_holder.get('resp', "0000")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        self.log.info("[Agent] RequestPasskey called for %s", device)
        event = threading.Event()
        response_holder = {}

        def callback():
            response_holder['resp'] = self.ui_callback("passkey", device)
            event.set()

        threading.Thread(target=callback, daemon=True).start()
        event.wait(timeout=30)
        passkey = response_holder.get('resp')
        return dbus.UInt32(passkey if isinstance(passkey, int) else 0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        self.log.info("[Agent] RequestConfirmation called for %s passkey=%s", device, passkey)
        event = threading.Event()
        response_holder = {}

        def callback():
            response_holder['resp'] = self.ui_callback("confirm", device, passkey)
            event.set()

        threading.Thread(target=callback, daemon=True).start()
        event.wait(timeout=30)
        if not response_holder.get('resp', False):
            raise dbus.exceptions.DBusException("org.bluez.Error.Rejected", "User rejected confirmation")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        self.log.info("[Agent] AuthorizeService called for %s uuid=%s", device, uuid)
        event = threading.Event()
        response_holder = {}

        def callback():
            response_holder['resp'] = self.ui_callback("authorize", device, uuid)
            event.set()

        threading.Thread(target=callback, daemon=True).start()
        event.wait(timeout=30)
        if not response_holder.get('resp', False):
            raise dbus.exceptions.DBusException("org.bluez.Error.Rejected", "User rejected service authorization")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        self.log.info("[Agent] Cancel called")
