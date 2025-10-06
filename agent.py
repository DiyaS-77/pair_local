def pair(self, address):
    def _pairing_thread():
        device_path = self.find_device_path(address)
        if not device_path:
            self.log.warning("Device path not found for %s", address)
            return

        try:
            device_proxy = self.bus.get_object(constants.bluez_service, device_path)
            device = dbus.Interface(device_proxy, constants.device_interface)
            properties = dbus.Interface(device_proxy, constants.properties_interface)

            paired = properties.Get(constants.device_interface, "Paired")
            if paired:
                self.log.info("Device %s is already paired.", address)
                return

            self.log.info("Initiating pairing with %s", address)
            device.Pair()

            # Wait a bit for pairing to complete
            for _ in range(30):  # ~30 seconds max
                time.sleep(1)
                paired = properties.Get(constants.device_interface, "Paired")
                if paired:
                    self.log.info("Successfully paired with %s", address)
                    return

            self.log.warning("Pairing not confirmed with %s within timeout.", address)

        except dbus.exceptions.DBusException as error:
            self.log.error("Pairing failed with %s: %s", address, error)

    threading.Thread(target=_pairing_thread, daemon=True).start()
    return True  # Return immediately to keep UI responsive




from PyQt6.QtCore import QMetaObject, Q_ARG, Qt

def pairing_ui_callback(self, request_type, device, uuid=None):
    self.log.info("[DEBUG] Immediate pairing request: %s %s %s", request_type, device, uuid)
    event = threading.Event()
    req = {'type': request_type, 'device': device, 'uuid': uuid, 'event': event, 'resp': None}

    def show_dialog():
        self._process_pairing_request(req)
        event.set()

    QMetaObject.invokeMethod(self, show_dialog, Qt.ConnectionType.QueuedConnection)
    event.wait(timeout=30)
    return req.get('resp')

def pairing_ui_callback(self, request_type, device, uuid=None):
    event = threading.Event()
    req = {'type': request_type, 'device': device, 'uuid': uuid, 'event': event, 'resp': None}
    QTimer.singleShot(0, lambda: self._process_pairing_request(req))
    event.wait(timeout=30)
    return req.get('resp')


def _process_pairing_request(self, req):
    request_type = req['type']
    device = req['device']
    uuid = req.get('uuid')
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
        req['resp'] = reply == QMessageBox.StandardButton.Yes
        if req['resp']:
            self.add_paired_device_to_list(device_address)

    elif request_type == "authorize":
        reply = QMessageBox.question(self, "Authorize Service",
                                     f"Device {device_address} wants to use service {uuid}\nAllow?",
                                     QMessageBox.StandardButton.Yes |
                                     QMessageBox.StandardButton.No)
        req['resp'] = reply == QMessageBox.StandardButton.Yes
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

    # Signal back to waiting thread
    if 'event' in req and req['event']:
        req['event'].set()
