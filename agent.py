def _process_pairing_queue(self):
    try:
        req = self._pairing_queue.get_nowait()
    except queue.Empty:
        return

    request_type = req['type']
    device = req['device']
    uuid = req.get('uuid')
    event = req.get('event')  # Added for synchronization
    device_address = device.split("dev_")[-1].replace("_", ":")

    if request_type == "pin":
        pin, ok = QInputDialog.getText(self, "Pairing Request",
                                       f"Enter PIN for device {device_address}:")
        req['resp'] = pin if ok and pin else None

    elif request_type == "passkey":
        passkey, ok = QInputDialog.getInt(self, "Pairing Request",
                                          f"Enter passkey for device {device_address}:")
        req['resp'] = int(passkey) if ok else None

        if req['resp'] is not None:
            self.add_paired_device_to_list(device_address)

    elif request_type == "confirm":
        reply = QMessageBox.question(self, "Confirm Pairing",
                                     f"Device {device_address} requests to pair "
                                     f"with passkey: {uuid}\nAccept?",
                                     QMessageBox.StandardButton.Yes |
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.add_paired_device_to_list(device_address)
            req['resp'] = True
        else:
            req['resp'] = False

    elif request_type == "authorize":
        reply = QMessageBox.question(self, "Authorize Service",
                                     f"Device {device_address} wants to use service {uuid}\nAllow?",
                                     QMessageBox.StandardButton.Yes |
                                     QMessageBox.StandardButton.No)
        req['resp'] = True if reply == QMessageBox.StandardButton.Yes else False
        if not req['resp']:
            self.bluetooth_device_manager.disconnect(device_address)

    elif request_type == "display_pin":
        QMessageBox.information(self, "Display PIN",
                                f"Enter this PIN on {device_address}: {uuid}")
        req['resp'] = None

    elif request_type == "display_passkey":
        QMessageBox.information(self, "Display Passkey",
                                f"Enter this passkey on {device_address}: {uuid}")
        req['resp'] = None

    else:
        req['resp'] = None

    # Signal back to waiting DBus thread
    if event:
        event.set()




import threading
import dbus
import dbus.service

class Agent(dbus.service.Object):
    def __init__(self, bus, path, ui_callback, log):
        super().__init__(bus, path)a
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
