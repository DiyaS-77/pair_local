import dbus
import dbus.mainloop.glib
import os
import subprocess
import time
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from libraries.bluetooth import constants
from libraries.bluetooth.agent import Agent
from Utils.utils import run
from dbus.mainloop.glib import DBusGMainLoop

DBusGMainLoop(set_as_default=True)


class BluetoothDeviceManager:
    """A class for managing Bluetooth devices using the BlueZ D-Bus API."""

    def __init__(self, log=None, interface=None):
        """Initialize the BluetoothDeviceManager by setting up the system bus and adapter.

        Args:
            log: Logger instance.
            interface: Bluetooth adapter interface (e.g., hci0).
        """
        self.bus = dbus.SystemBus()
        self.interface = interface
        self.log = log
        self.adapter_path = f'{constants.bluez_path}/{self.interface}'
        self.adapter_proxy = self.bus.get_object(constants.bluez_service, self.adapter_path)
        self.adapter_properties = dbus.Interface(self.adapter_proxy, constants.properties_interface)
        self.adapter = dbus.Interface(self.adapter_proxy, constants.adapter_interface)
        self.object_manager = dbus.Interface(self.bus.get_object(constants.bluez_service, "/"), constants.object_manager_interface)
        self.last_session_path = None
        self.opp_process = None
        self.stream_process = None

    def get_paired_devices(self):
        """Retrieves all Bluetooth devices that are currently paired with the adapter.

        Returns:
            paired_devices: A dictionary of paired devices.
        """
        paired_devices = {}
        for path, interfaces in self.object_manager.GetManagedObjects().items():
            if constants.device_interface in interfaces:
                device = interfaces[constants.device_interface]
                if device.get("Paired") and device.get("Adapter") == self.adapter_path:
                    address = device.get("Address")
                    name = device.get("Name", "Unknown")
                    paired_devices[address] = name
        return paired_devices

    def start_discovery(self):
        """Start scanning for nearby Bluetooth devices, if not already discovering."""
        try:
            if not self.adapter_properties.Get(constants.adapter_interface, "Discovering"):
                self.adapter.StartDiscovery()
                self.log.info("Discovery started.")
            else:
                self.log.info("Discovery already in progress.")
        except dbus.exceptions.DBusException as error:
            self.log.error("Failed to start discovery: %s", error)

    def stop_discovery(self):
        """Stop Bluetooth device discovery, if it's running."""
        try:
            if self.adapter_properties.Get(constants.adapter_interface, "Discovering"):
                self.adapter.StopDiscovery()
                self.log.info("Discovery stopped.")
            else:
                self.log.info("Discovery is not running.")
        except dbus.exceptions.DBusException as error:
            self.log.error("Failed to stop discovery: %s", error)

    def get_discovered_devices(self):
        """Retrieve discovered Bluetooth devices under the current adapter.

        Returns:
            discovered_devices: List of discovered Bluetooth devices.
        """
        discovered_devices = []
        for path, interfaces in self.object_manager.GetManagedObjects().items():
            device = interfaces.get(constants.device_interface)
            if not device or device.get("Adapter") != self.adapter_path:
                continue
            address = device.get("Address")
            alias = device.get("Alias", "Unknown")
            if address:
                discovered_devices.append({
                    "path": path,
                    "address": address,
                    "alias": alias})
            else:
                self.log.warning("Failed to extract device info from %s", path)
        return discovered_devices

    def find_device_path(self, address):
        """Find the D-Bus object path of a device by address under the correct adapter.

        Args:
            address: Bluetooth address of remote device.

        Returns:
            path: D-Bus object path.
        """
        formatted_interface_path = f"{constants.bluez_path}/{self.interface}/"
        for path, interfaces in self.object_manager.GetManagedObjects().items():
            if constants.device_interface in interfaces and formatted_interface_path in path:
                    properties = interfaces[constants.device_interface]
                    if properties.get("Address") == address:
                        return path
                    else:
                        pass

    '''def register_agent(self, capability=None, ui_callback=None):
        """Register this object as a Bluetooth pairing agent."""
        try:
            self.agent=Agent(self.bus, constants.agent_path, ui_callback, self.log)
            agent_manager = dbus.Interface(self.bus.get_object(constants.bluez_service, constants.bluez_path), constants.agent_interface)
            agent_manager.RegisterAgent(constants.agent_path, capability)
            agent_manager.RequestDefaultAgent(constants.agent_path)
            self.log.info("Registered with capability:%s", capability)
        except dbus.exceptions.DBusException as error:
            self.log.error("Failed to register agent:%s", error)
            return False'''

    def register_agent(self, capability=None, ui_callback=None):
        """Register this object as a Bluetooth pairing agent."""
        try:

            self.agent = Agent(self.bus, constants.agent_path, ui_callback, self.log)
            agent_manager = dbus.Interface(
                self.bus.get_object(constants.bluez_service, constants.bluez_path),
                constants.agent_interface
            )

            agent_manager.RegisterAgent(constants.agent_path, capability)
            agent_manager.RequestDefaultAgent(constants.agent_path)  # ✅ VERY IMPORTANT

            self.log.info("Registered Agent successfully with capability: %s", capability)
            return True

        except dbus.exceptions.DBusException as error:
            self.log.error("Failed to register agent: %s", error)
            return False

    def unregister_agent(self):
        """Unregister the Bluetooth pairing agent and remove D-Bus object."""
        try:
            agent_manager = dbus.Interface(self.bus.get_object(constants.bluez_service, constants.bluez_path), constants.agent_interface)
            agent_manager.UnregisterAgent(constants.agent_path)
            self.log.info("Unregistered agent from BlueZ.")
            if hasattr(self, "agent") and self.agent:
                self.agent.remove_from_connection()
                self.log.info("Removed agent object from D-Bus.")
                self.agent = None
        except dbus.exceptions.DBusException as error:
            self.log.error("Failed to unregister agent: %s", error)
            raise

    def pair(self, address):
        """Pairs with a Bluetooth device using the given controller interface.

        Args:
            address: Bluetooth address of remote device.

        Returns:
            True if successfully paired, False otherwise.
        """
        device_path = self.find_device_path(address)
        if not device_path:
            # self.log.info("Device path not found for %s on %s", address, self.interface)
            return False
        try:
            device_proxy = self.bus.get_object(constants.bluez_service, device_path)
            device = dbus.Interface(device_proxy, constants.device_interface)
            properties = dbus.Interface(device_proxy, constants.properties_interface)
            paired = properties.Get(constants.device_interface, "Paired")
            if paired:
                self.log.info("Device %s is already paired.", address)
                return True
            self.log.info("Initiating pairing with %s", address)
            device.Pair()
            paired = properties.Get(constants.device_interface, "Paired")
            if paired:
                self.log.info("Successfully paired with %s", address)
                return True
            self.log.warning("Pairing not confirmed with %s within the timeout period.", address)
            return False
        except dbus.exceptions.DBusException as error:
            self.log.error("Pairing failed with %s: %s", address, error)

    def connect(self, address):
        """Establish a  connection to the specified Bluetooth device.

        Args:
            address: Bluetooth device address of remote device.

        Returns:
            True if connected, False otherwise.
        """
        device_path = self.find_device_path(address)
        if device_path:
            try:
                device = dbus.Interface(self.bus.get_object(constants.bluez_service, device_path), constants.device_interface)
                device.Connect()
                properties = dbus.Interface(self.bus.get_object(constants.bluez_service, device_path), constants.properties_interface)
                connected = properties.Get(constants.device_interface, "Connected")
                if connected:
                    self.log.info("Connection successful to %s", address)
                    return True
            except Exception as error:
                self.log.info("Connection failed:%s", error)
                return False
        else:
            self.log.info("Device path not found for address %s", address)
            return False

    def disconnect(self, address):
        """Disconnect a Bluetooth  device from the specified adapter.

        Args:
            address: Bluetooth  address of the remote device.

        Returns:
            True if disconnected or already disconnected, False if an error occurred.
        """
        device_path = self.find_device_path(address)
        if device_path:
            try:
                device = dbus.Interface(self.bus.get_object(constants.bluez_service, device_path), constants.device_interface)
                properties = dbus.Interface(self.bus.get_object(constants.bluez_service, device_path), constants.properties_interface)
                connected = properties.Get(constants.device_interface, "Connected")
                if not connected:
                    self.log.info("Device %s is already disconnected.", address)
                    return True
                device.Disconnect()
                return True
            except dbus.exceptions.DBusException as error:
                self.log.info("Error disconnecting device %s:%s", address, error)
        else:
            self.log.warning("Device path not found for address: %s", address)
        self.log.info("Disconnection failed for device: %s", address)
        return False

    def unpair_device(self, address):
        """Unpairs a paired or known Bluetooth device from the system using BlueZ D-Bus.

        Args:
            address: The Bluetooth address of the remote device.

        Returns:
            True if the device was unpaired successfully or already not present,
            False if the unpairing failed or the device still exists afterward.
        """
        try:
            target_path = None
            for path, interfaces in self.object_manager.GetManagedObjects().items():
                if constants.device_interface in interfaces and interfaces[constants.device_interface].get("Address") == address and path.startswith(self.adapter_path):
                    target_path = path
                    break
            if not target_path:
                self.log.info("Device with address %s not found on %s", address, self.interface)
                return True
            self.adapter.RemoveDevice(target_path)
            self.log.info("Requested unpair of device %s at path %s", address, target_path)
            time.sleep(0.5)
            for path, interfaces in self.object_manager.GetManagedObjects().items():
                if constants.device_interface in interfaces and interfaces[constants.device_interface].get("Address") == address:
                        self.log.warning("Device %s still exists after attempted unpair", address)
                        return False
            self.log.info("Device %s unpaired successfully", address)
            return True
        except dbus.exceptions.DBusException as error:
            self.log.error("DBusException while unpairing device %s: %s", address, error)
            return False

    def is_device_paired(self, device_address):
        """Checks if the specified device is paired.

        Args:
            device_address: Bluetooth address of remote device.

        Returns:
            True if paired, False otherwise.
        """
        device_path = self.find_device_path(device_address)
        if not device_path:
            return False
        properties = dbus.Interface(self.bus.get_object(constants.bluez_service, device_path), constants.properties_interface)
        try:
            return properties.Get(constants.device_interface, "Paired")
        except dbus.exceptions.DBusException as error:
            self.log.debug("DBusException while checking pairing:%s", error)
            return False

    def is_device_connected(self, device_address):
        """Checks if the specified device is connected.

        Args:
            device_address: Bluetooth address of remote device.

        Returns:
            True if connected, False otherwise.
        """
        device_path = self.find_device_path(device_address)
        if not device_path:
            self.log.debug("Device path not found for %s on %s", device_address, self.interface)
            return False
        try:
            properties = dbus.Interface(self.bus.get_object(constants.bluez_service, device_path), constants.properties_interface)
            connected = properties.Get(constants.device_interface, "Connected")
            if self.interface not in device_path:
                self.log.debug("Device path %s does not match interface %s", device_path, self.interface)
                return False
            return connected
        except dbus.exceptions.DBusException as error:
            self.log.debug("DBusException while checking connection:%s", error)
            return False

    def start_a2dp_stream(self, address, filepath=None):
        """Initiates an A2DP audio stream to a Bluetooth device using PulseAudio.

        Args:
            address: Bluetooth address of the target device.
            filepath: Path to the audio file.

        Returns:
            True if the stream was started, False otherwise.
        """
        device_path = self.find_device_path(address)
        self.log.info("Device path:%s",device_path)
        if not device_path:
            self.log.info("Device path not found")
        try:
            self.log.info("Starting A2DP stream to device path: %s with file: %s", device_path, filepath)
            self.stream_process = run(self.log, ["paplay", filepath], block=False)
            return True
        except Exception as error:
            self.log.error("Stream error:%s", error)
            return False

    def stop_a2dp_stream(self):
        """Stop the current A2DP audio stream."""
        if hasattr(self, 'stream_process') and self.stream_process:
            if self.stream_process.poll() is None:
                self.stream_process.terminate()
                self.stream_process.wait()
                self.log.info("Stream terminated successfully.")
            else:
                self.log.info("Stream was already stopped.")
            self.stream_process = None
            return True
        self.log.info("No active stream to stop.")
        return False

    def media_control(self, command, address=None):
        """Sends AVRCP (Audio/Video Remote Control Profile) media control commands to a connected Bluetooth device.

        Args:
            command: The AVRCP command to send. Must be one of: "play", "pause", "next", "previous", "rewind".
            address: Bluetooth address of the target device.
        """
        valid_commands= {"play":"Play",
                 "pause":"Pause",
                 "next":"Next",
                 "previous":"Previous",
                 "rewind":"Rewind"
                }
        if command not in valid_commands:
            self.log.info("Invalid media control command:%s", command)
        media_control_interface = self.get_media_control_interface(address)
        if not media_control_interface:
            self.log.info(" MediaControl1 interface NOT FOUND")
        self.log.info(" MediaControl1 interface FOUND")
        try:
            getattr(media_control_interface, valid_commands[command])()
            self.log.info("AVRCP %s sent successfully to %s", command, address)
        except Exception as error:
            self.log.warning("AVRCP command %s failed with exception:%s", command, error)

    def get_media_control_interface(self, address):
        """Retrieve the `org.bluez.MediaControl1` D-Bus interface for a given Bluetooth device.

        Args:
            address: The Bluetooth address of the target Bluetooth device.

        Returns:
            The MediaControl1 D-Bus interface if found, otherwise None.
        """
        try:
            formatted_addr = address.replace(":", "_").upper()
            for path, interfaces in self.object_manager.GetManagedObjects().items():
                if constants.media_control_interface in interfaces:
                    if formatted_addr in path and path.startswith(self.adapter_path):
                        self.log.info("Found MediaControl1 at %s", path)
                        return dbus.Interface(self.bus.get_object(constants.bluez_service, path), constants.media_control_interface)
            self.log.info(" No MediaControl1 interface found for %s under %s", address, self.adapter_path)
        except Exception as error:
            self.log.info(" Exception while getting MediaControl1 interface:%s", error)

    def get_a2dp_role_for_device(self, device_address):
        """Get the A2DP role (sink or source) for a specific connected Bluetooth device.

        Args:
            device_address: Bluetooth address of the connected device.

        Returns:
            sink or source
        """
        uuid_map = {"source": "110a", "sink": "110b"}
        for path, interfaces in self.object_manager.GetManagedObjects().items():
            if constants.device_interface in interfaces:
                properties = interfaces[constants.device_interface]
                if properties.get("Address") == device_address and properties.get("Connected") and properties.get("Adapter") == self.adapter_path:
                    uuids = properties.get("UUIDs", [])
                    for role, uuid_role in uuid_map.items():
                        if any(uuid_role in uuid.lower() for uuid in uuids):
                            return role
                        else:
                            self.log.warning("Unknown A2DP role %s", device_address)

    def send_file(self, device_address, file_path, session_path=None):
        """Send a file via OBEX OPP and wait for real-time transfer status."""
        if not os.path.exists(file_path):
            self.log.info("File does not exist: %s", file_path)
            return "error"
        try:
            if not session_path:
                session_path = self.create_obex_session(device_address)
            opp_interface = dbus.Interface(self.session_bus.get_object(constants.obex_service, session_path), constants.obex_object_push)
            transfer_path, _ = opp_interface.SendFile(file_path)
            self.log.info("Started transfer: %s", transfer_path)
            self.transfer_status = {"status": "unknown"}
            self.session_bus.add_signal_receiver(
                self.obex_properties_changed,
                dbus_interface=constants.properties_interface,
                signal_name="PropertiesChanged",
                arg0=constants.obex_object_transfer,
                path=transfer_path,
                path_keyword="path")
            self.transfer_loop = GLib.MainLoop()
            self.transfer_loop.run()
            status = self.transfer_status["status"]
            self.remove_obex_session(session_path)
            return status
        except Exception as error:
            self.log.info("OBEX send failed: %s", error)
            return "error"

    def receive_file(self, save_directory="/tmp", timeout=20, user_confirm_callback=None):
        """Start an OBEX Object Push server and wait for a file to be received."""
        try:
            if not os.path.exists(save_directory):
                os.makedirs(save_directory)
            run(self.log, "killall -9 obexpushd")
            self.log.info("Killed existing obexpushd processes..")
            existing_files = set(os.listdir(save_directory))
            self.opp_process = subprocess.Popen(["obexpushd", "-B", "-o", save_directory, "-n"])
            self.log.info("OPP server started. Waiting for incoming file...")
            start_time = time.time()
            while time.time() - start_time < timeout:
                current_files = set(os.listdir(save_directory))
                new_files = current_files - existing_files
                if new_files:
                    received_file = new_files.pop()
                    full_path = os.path.join(save_directory, received_file)
                    self.log.info("Incoming file: %s", received_file)
                    user_accepted = True
                    if user_confirm_callback:
                        user_accepted = user_confirm_callback(full_path)
                    if user_accepted:
                        self.log.info("User accepted file.")
                        self.stop_opp_receiver()
                        return full_path
                    else:
                        self.log.info("User rejected file.")
                        os.remove(full_path)
                        self.stop_opp_receiver()
        except Exception as error:
            self.stop_opp_receiver()
            self.log.error("Error in receive_file:%s", error)

    def stop_opp_receiver(self):
        """Stop the OBEX Object Push server if it's currently running."""
        if self.opp_process and self.opp_process.poll() is None:
            self.opp_process.terminate()
            self.opp_process.wait()
            self.log.info("OPP server stopped.")
        else:
            self.log.info("No OPP server running or already stopped.")

    def obex_properties_changed(self, interface, changed, invalidated, path):
        """Handle the PropertiesChanged signal for an OBEX file transfer.

        Args:
            interface: The D-Bus interface name where the property change occurred.
            changed: A dictionary containing the properties that changed and their new values.
            invalidated: A list of properties that are no longer valid.
            path: The D-Bus object path for the signal.
        """
        if "Status" in changed:
            status = str(changed["Status"])
            self.log.info("Signal: Transfer status changed to:%s", status)
            self.transfer_status["status"] = status
            if status in ["complete", "error", "cancelled"]:
                if hasattr(self, "transfer_loop") and self.transfer_loop.is_running():
                    self.transfer_loop.quit()
            else:
                self.log.warning("PropertiesChanged received without 'Status': %s", changed)

    def set_discoverable_mode(self, enable):
        """Enable or disable discoverable mode on the Bluetooth adapter.

        Args:
            enable: True to enable, False to disable.
        """
        if enable:
            command = f"hciconfig {self.interface} piscan"
            subprocess.run(command, shell=True)
            self.log.info("Bluetooth device is now discoverable.")
        else:
            self.log.info("Setting Bluetooth device to be non-discoverable...")
            command = f"hciconfig {self.interface} noscan"
            subprocess.run(command, shell=True)
            self.log.info("Bluetooth device is now non-discoverable.")

    def create_obex_session(self, device_address):
        """Creates an OBEX Object Push (OPP) session.

        Returns:
            session_path: The OBEX session path if successful, else return False.
        """
        DBusGMainLoop(set_as_default=True)
        try:
            self.session_bus = dbus.SessionBus()
            self.obex_manager = dbus.Interface(self.session_bus.get_object(constants.obex_service, constants.obex_path), constants.obex_client)
            if getattr(self, "last_session_path", None):
                self.obex_manager.RemoveSession(self.last_session_path)
                self.log.info("Removed previous OBEX session: %s", self.last_session_path)
                self.last_session_path = None
            session_path = self.obex_manager.CreateSession(device_address, {"Target": dbus.String("opp")})
            self.last_session_path = session_path
            self.log.info("Created OBEX OPP session: %s", session_path)
            return session_path
        except Exception as error:
            self.log.error("OBEX session creation failed for device %s: %s", device_address, error)
            return False

    def remove_obex_session(self, session_path):
        """Removes the given OBEX session."""
        try:
            self.obex_manager.RemoveSession(session_path)
            self.log.info("Removed OBEX session: %s", session_path)
        except Exception as error:
            self.log.warning("Failed to remove session: %s", error)
        self.last_session_path = None
