import os
import sys
import time
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QPalette
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QDialog
from PyQt6.QtWidgets import QGridLayout
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QListWidget
from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtWidgets import QToolButton
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget

import style_sheet as styles
from controller_ui import TestControllerUI
from host_ui import TestApplication
from Utils.logger import Logger
from Utils.utils import controller_enable
from Utils.utils import get_controllers_connected
from Utils.utils import get_controller_interface_details
from Utils.utils import start_bluetooth_daemon
from Utils.utils import start_dbus_daemon
from Utils.utils import start_dump_logs
from Utils.utils import start_pulseaudio_daemon
from Utils.utils import stop_daemons
from Utils.utils import stop_dump_logs
from Utils.utils import stop_pulseaudio_daemon


class CustomDialog(QDialog):
    """Dialog window shown when no controller is selected but an action is attempted."""
    def __init__(self, parent=None):
        """Initializes a simple warning dialog with a message to select the controller.

        Args:
            parent: Parent widget of the dialog.
        """
        super().__init__(parent)
        self.setWindowTitle("Warning!")
        layout = QVBoxLayout()
        message = QLabel("Select the controller!!")
        layout.addWidget(message)
        self.setLayout(layout)

    def showEvent(self, event):
        """Centers the dialog box on top of the parent widget when displayed

         Args :
            event: Qt show event object
        """
        parent_geometry = self.parent().geometry()
        dialog_geometry = self.geometry()
        center_x = (parent_geometry.x() + (parent_geometry.width() - dialog_geometry.width()) // 2)
        center_y = (parent_geometry.y() + (parent_geometry.height() - dialog_geometry.height()) // 2)
        self.move(center_x, center_y)
        super().showEvent(event)


class BluetoothUIApp(QMainWindow):
    """Main window for the Bluetooth testing UI application.
    Handles controller discovery, logger setup and UI navigation between modules"""
    def __init__(self):
        """Initializes the main Bluetooth UI application."""
        super().__init__()
        self.log = Logger("UI")
        self.controllers_list_layout = None
        self.controllers_list_widget = None
        self.test_application = None
        self.test_controller = None
        self.previous_row_selected = None
        self.bd_address = None
        self.interface = None
        self.background_path = None
        self.controllers_list = {}

    def list_controllers(self):
        """Creates and displays the main UI layout to list Bluetooth controllers and
        provide navigation options."""
        self.setWindowTitle("Bluetooth UI Application")
        self.background_path = "UI/media/main_window_background.jpg"
        self.setAutoFillBackground(True)
        self.update_background()
        main_layout = QVBoxLayout()
        main_layout.addStretch(1)
        application_label_layout = QHBoxLayout()
        application_label = QLabel("BLUETOOTH TEST APPLICATION")
        font = QFont("Aptos Black", 28, QFont.Weight.Bold)
        application_label.setFont(font)
        application_label.setStyleSheet(styles.color_style_sheet)
        application_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        application_label_layout.addStretch(1)
        application_label_layout.addWidget(application_label)
        application_label_layout.addStretch(1)
        main_layout.addLayout(application_label_layout)
        main_layout.addStretch(1)
        self.controllers_list_layout = QHBoxLayout()
        self.controllers_list_widget = QListWidget()
        self.controllers_list_widget.setMinimumSize(800, 400)
        self.controllers_list = get_controllers_connected(self.log)
        self.add_items(
            self.controllers_list_widget,
            list(self.controllers_list.keys()),
            Qt.AlignmentFlag.AlignHCenter
        )
        self.controllers_list_widget.setStyleSheet(styles.list_widget_style_sheet)
        self.controllers_list_widget.itemClicked.connect(self.controller_selected)
        self.controllers_list_layout.addStretch(1)
        self.controllers_list_layout.addWidget(self.controllers_list_widget)
        self.controllers_list_layout.addStretch(1)
        main_layout.addLayout(self.controllers_list_layout)
        main_layout.addStretch(1)
        buttons_layout = QGridLayout()
        controller_button_layout = QHBoxLayout()
        self.test_controller = QToolButton()
        self.test_controller.setText("Test Controller")
        self.test_controller.setFixedSize(200, 80)
        self.test_controller.clicked.connect(self.check_controller_selected)
        self.test_controller.setStyleSheet(styles.select_button_style_sheet)
        controller_button_layout.addWidget(self.test_controller)
        buttons_layout.addLayout(controller_button_layout, 0, 0)
        host_button_layout = QHBoxLayout()
        self.test_application = QToolButton()
        self.test_application.setText("Test Host")
        self.test_application.clicked.connect(self.check_application_selected)
        self.test_application.setFixedSize(200, 80)
        self.test_application.setStyleSheet(styles.select_button_style_sheet)
        host_button_layout.addWidget(self.test_application)
        buttons_layout.addLayout(host_button_layout, 0, 1)
        main_layout.addLayout(buttons_layout)
        main_layout.addStretch(1)
        widget = QWidget()
        widget.setLayout(main_layout)
        self.setCentralWidget(widget)
        self.test_controller.show()
        self.test_application.show()

    def update_background(self):
        """Updates the background of the current widget using the image specified by `self.background_path`.
        The background image is scaled to fit the current size of the widget, ignoring the aspect ratio,
        and is applied smoothly to maintain visual quality."""
        pixmap = QPixmap(self.background_path)
        scaled_pixmap = pixmap.scaled(self.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
        palette = self.palette()
        palette.setBrush(QPalette.ColorRole.Window, QBrush(scaled_pixmap))
        self.setPalette(palette)

    def resizeEvent(self, event):
        """Updates the background when the window is resized.

        Args:
            event: The resize event containing the old and new size.
        """
        self.update_background()
        super().resizeEvent(event)

    def add_items(self, widget, items, align):
        """Adds a list of items to a QListWidget with a specified alignment.

        Args:
             widget: The target widget to populate.
             items: List of string items to be added.
             align: Alignment setting for each item.
        """
        for test_item in items:
            item = QListWidgetItem(test_item)
            item.setTextAlignment(align)
            widget.addItem(item)

    def controller_selected(self, address):
        """Handles logic when  a controller is selected from the list. Stores the bd_address and interface.

        Args:
            address: selected controller bd_address.
        """
        self.bd_address = address.text()
        self.log.info("Controller Selected: %s", self.bd_address)

        if self.bd_address in self.controllers_list:
            self.interface = self.controllers_list[self.bd_address]

        controller_enable(self.log, self.interface)
        start_dump_logs(self.interface, self.log, self.log.log_path)
        if self.previous_row_selected:
            self.controllers_list_widget.takeItem(self.previous_row_selected)

        row = self.controllers_list_widget.currentRow()
        item = QListWidgetItem(get_controller_interface_details(self.log, self.interface, detail_level='basic_info'))
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.controllers_list_widget.insertItem(row + 1, item)
        self.previous_row_selected = row + 1

    def check_controller_selected(self):
        """Checks if a controller is selected before navigating to the controller testing screen.
        Displays a warning dialog if None is selected."""
        if self.bd_address:
            self.setWindowTitle('Test Controller')
            self.setCentralWidget(TestControllerUI(interface=self.interface, back_callback=self.show_main, log=self.log))

        else:
            dlg = CustomDialog(self)
            if not dlg.exec():
                self.list_controllers()

    def check_application_selected(self):
        """Checks if controller is selected before navigating to the application testing screen.
        Displays a warning dialog if None is selected."""
        if self.bd_address:
            self.test_application_clicked()
        else:
            dlg = CustomDialog(self)
            if not dlg.exec():
                self.list_controllers()

    def test_application_clicked(self):
        """Launches the test Host window inside the main application using the
        selected controller."""
        if self.centralWidget():
            self.centralWidget().deleteLater()

        self.setWindowTitle('Test Host')
        if not hasattr(self, 'daemons_started') :
            start_dbus_daemon(log=self.log)
            start_pulseaudio_daemon(log=self.log)
            start_bluetooth_daemon(log=self.log)
            self.daemons_started = True

        self.setWindowTitle('Test Host')
        self.setCentralWidget(TestApplication(interface=self.interface, back_callback=self.show_main, log=self.log))

    def show_main(self):
        """Navigates the UI back to the main controller list screen from test views."""
        self.list_controllers()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app_window = BluetoothUIApp()
    app_window.setWindowIcon(QIcon('UI/media/app_icon.jpg'))
    app_window.list_controllers()
    app_window.showMaximized()

    def stop_logs():
        """Stops hcidump logging processes before application quit"""
        stop_daemons(app_window.log)
        stop_pulseaudio_daemon(app_window.log)
        stop_dump_logs(app_window.log)

    app.aboutToQuit.connect(stop_logs)
    sys.exit(app.exec())
