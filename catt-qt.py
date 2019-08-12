#!/usr/bin/python3

# Copyright 2019 - Scott Moreau

import os
import sys
import catt.api
from catt.api import CattDevice
import pychromecast
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QTimer, QTime, pyqtSignal


# On Chromecast reboot, the volume is set to maximum.
# This value is used to set a custom initial volume
# if a Chromecast is rebooted while this program is
# running. The range is 0.0 - 1.0.
REBOOT_VOLUME = 0.25


def time_to_seconds(time):
    return time.hour() * 3600 + time.minute() * 60 + time.second()


class Device:
    def __init__(self, s, d, c, i=0):
        self.media_listener = MediaListener()
        self.media_listener._self = s
        self.media_listener.supports_seek = False
        self.media_listener.index = i
        self.status_listener = StatusListener()
        self.status_listener._self = s
        self.status_listener.index = i
        self.connection_listener = ConnectionListener()
        self.connection_listener._self = s
        self.cast = c
        self.index = i
        self._self = s
        self.volume = 0
        self.paused = True
        self.playing = False
        self.live = False
        self.device = d
        self.duration = 0
        self.status_text = None
        self.progress_timer = QTimer()
        self.time = QTime(0, 0, 0)
        self.progress_timer.timeout.connect(self.on_progress_tick)

    def on_progress_tick(self):
        _self = self._self
        self.time = self.time.addSecs(1)
        if _self.combo_box.currentIndex() == self.index:
            _self.progress_label.setText(self.time.toString("hh:mm:ss"))
            _self.progress_slider.setValue(time_to_seconds(self.time))


class App(QMainWindow):
    start_timer = pyqtSignal(int)
    stop_timer = pyqtSignal(int)
    add_device = pyqtSignal(str)
    remove_device = pyqtSignal(str)

    def create_devices_layout(self):
        self.devices_layout = QHBoxLayout()
        self.combo_box = QComboBox()
        self.devices_layout.addWidget(self.combo_box)

    def create_control_layout(self):
        self.control_layout = QHBoxLayout()
        self.dial = QDial()
        self.dial.setMinimum(0)
        self.dial.setMaximum(100)
        self.dial.setValue(0)
        self.dial.valueChanged.connect(self.on_dial_moved)
        self.volume_status_event_pending = False
        self.volume_event_timer = QTimer()
        self.volume_event_timer.timeout.connect(self.event_pending_expired)
        self.volume_event_timer.setSingleShot(True)
        self.textbox = QLineEdit()
        self.play_button = QPushButton()
        self.play_button.clicked.connect(self.on_play_click)
        self.set_icon(self.play_button, "SP_MediaPlay")
        self.stop_button = QPushButton()
        self.stop_button.clicked.connect(self.on_stop_click)
        self.set_icon(self.stop_button, "SP_MediaStop")
        self.control_layout.addWidget(self.play_button)
        self.control_layout.addWidget(self.stop_button)
        self.control_layout.addWidget(self.textbox)
        self.control_layout.addWidget(self.dial)

    def create_seek_layout(self):
        self.seek_layout = QHBoxLayout()
        self.progress_label = QLabel()
        self.progress_label.setText("00:00:00")
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setValue(0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderPressed.connect(self.on_progress_pressed)
        self.progress_slider.sliderReleased.connect(self.on_progress_released)
        self.skip_forward_button = QPushButton()
        self.set_icon(self.skip_forward_button, "SP_MediaSkipForward")
        self.seek_layout.addWidget(self.progress_label)
        self.seek_layout.addWidget(self.progress_slider)
        self.seek_layout.addWidget(self.skip_forward_button)

    def create_status_layout(self):
        self.status_layout = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setText("Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_layout.addWidget(self.status_label)

    def __init__(self):
        super().__init__()
        self.title = "Cast All The Things"
        self.width = 640
        self.height = 1
        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setWindowIcon(
            QIcon(os.path.dirname(os.path.realpath(__file__)) + "/chromecast.png")
        )
        self.setGeometry(640, 480, self.width, self.height)
        print("Scanning for Chromecast devices on the network...")
        self.devices = catt.api.discover()
        num_devices = len(self.devices)
        if num_devices == 0:
            print("No devices found")
            sys.exit(1)
        self.window = QWidget()
        self.main_layout = QVBoxLayout()
        self.create_devices_layout()
        self.create_control_layout()
        self.create_seek_layout()
        self.create_status_layout()
        self.skip_forward_button.setEnabled(False)
        self.skip_forward_button.clicked.connect(self.on_skip_click)
        self.start_timer.connect(self.on_start_timer)
        self.stop_timer.connect(self.on_stop_timer)
        self.add_device.connect(self.on_add_device)
        self.remove_device.connect(self.on_remove_device)
        self.device_list = []
        if num_devices > 1:
            text = "devices found"
        else:
            text = "device found"
        print(num_devices, text)
        i = 0
        for d in self.devices:
            cast = pychromecast.Chromecast(d.ip_addr)
            cast.wait()
            device = Device(self, d, cast, i)
            cast.media_controller.register_status_listener(device.media_listener)
            cast.register_status_listener(device.status_listener)
            cast.register_connection_listener(device.connection_listener)
            self.device_list.append(device)
            self.combo_box.addItem(d.name)
            # Hack: Change volume slightly to trigger
            # status listener. This way, we can get the
            # volume on startup.
            d.volumedown(0.0000001)
            print(d.name)
            i = i + 1
        self.combo_box.currentIndexChanged.connect(self.on_index_changed)
        self.main_layout.addLayout(self.devices_layout)
        self.main_layout.addLayout(self.control_layout)
        self.main_layout.addLayout(self.seek_layout)
        self.main_layout.addLayout(self.status_layout)
        self.widget = QWidget()
        self.widget.setLayout(self.main_layout)
        self.setCentralWidget(self.widget)
        self.show()

    def on_play_click(self):
        i = self.combo_box.currentIndex()
        d = self.get_device_from_index(i)
        if d == None:
            return
        if d.paused:
            if d.playing:
                d.device.play()
                self.set_icon(self.play_button, "SP_MediaPause")
                d.paused = False
                return
            text = self.textbox.text()
            if "://" in text:
                self.set_icon(self.play_button, "SP_MediaPause")
                d.device.play_url(text, resolve=True, block=False)
        elif d.playing:
            self.set_icon(self.play_button, "SP_MediaPlay")
            d.device.pause()
            d.paused = True
            d.progress_timer.stop()

    def on_stop_click(self):
        i = self.combo_box.currentIndex()
        d = self.get_device_from_index(i)
        if d == None:
            return
        d.device.stop()
        self.stop_timer.emit(i)
        d.time = QTime(0, 0, 0)
        self.progress_slider.setValue(0)
        self.progress_label.setText(d.time.toString("hh:mm:ss"))
        self.set_icon(self.play_button, "SP_MediaPlay")
        self.skip_forward_button.setEnabled(False)
        self.progress_slider.setEnabled(False)
        d.playing = False
        d.paused = True
        d.live = False

    def on_index_changed(self):
        if not self.active_devices():
            self.play_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.progress_slider.setEnabled(False)
            self.skip_forward_button.setEnabled(False)
            self.set_icon(self.play_button, "SP_MediaPlay")
            self.progress_label.setText("00:00:00")
            return
        i = self.combo_box.currentIndex()
        d = self.get_device_from_index(i)
        if d == None:
            return
        if d.playing and not d.paused:
            self.set_icon(self.play_button, "SP_MediaPause")
        else:
            self.set_icon(self.play_button, "SP_MediaPlay")
        enabled = d.playing and not d.live
        self.skip_forward_button.setEnabled(enabled)
        self.progress_slider.setEnabled(enabled)
        self.play_button.setEnabled(not d.live)
        if d.live:
            self.progress_label.setText("LIVE")
            self.stop_timer.emit(d.index)
        else:
            self.progress_label.setText(d.time.toString("hh:mm:ss"))
            if d.duration != None:
                self.progress_slider.setMaximum(d.duration)
            self.progress_slider.setValue(time_to_seconds(d.time))
            self.play_button.setEnabled(True)
            self.stop_button.setEnabled(True)
        self.dial.valueChanged.disconnect(self.on_dial_moved)
        self.dial.setValue(d.volume)
        self.dial.valueChanged.connect(self.on_dial_moved)
        self.status_label.setText(d.status_text)

    def on_skip_click(self):
        i = self.combo_box.currentIndex()
        d = self.get_device_from_index(i)
        if d == None:
            return
        d.device.seek(d.duration - 3)

    def on_dial_moved(self):
        i = self.combo_box.currentIndex()
        d = self.get_device_from_index(i)
        if d == None:
            return
        if not self.volume_status_event_pending:
            self.volume_status_event_pending = True
            d.device.volume(self.dial.value() / 100)
            self.volume_event_timer.start(250)
        elif self.dial.value() == 0:
            d.device.volume(0.0)
        elif self.dial.value() == 100:
            d.device.volume(1.0)

    def on_progress_pressed(self):
        i = self.combo_box.currentIndex()
        d = self.get_device_from_index(i)
        if d == None:
            return
        d.progress_timer.stop()
        self.current_progress = self.progress_slider.value()

    def on_progress_released(self):
        i = self.combo_box.currentIndex()
        d = self.get_device_from_index(i)
        if d == None:
            return
        value = self.progress_slider.value()
        if d.media_listener.supports_seek:
            if value > self.current_progress:
                d.device.seek(value)
            elif value < self.current_progress:
                d.device.seek(value)
        else:
            print("Stream does not support seeking")

    def on_start_timer(self, i):
        d = self.get_device_from_index(i)
        if d == None:
            return
        d.progress_timer.start(1000)

    def on_stop_timer(self, i):
        d = self.get_device_from_index(i)
        if d == None:
            return
        d.progress_timer.stop()
        d.time.setHMS(0, 0, 0)

    def set_time(self, i, h, m, s):
        d = self.get_device_from_index(i)
        if d == None:
            return
        d.time.setHMS(h, m, s)

    def set_icon(self, button, icon):
        button.setIcon(app.style().standardIcon(getattr(QStyle, icon)))

    def event_pending_expired(self):
        self.volume_status_event_pending = False

    def on_add_device(self, ip):
        for d in self.device_list:
            if d.device.ip_addr == ip:
                self.devices.remove(d.device)
                self.device_list.remove(d)
                break
        if not self.active_devices():
            self.play_button.setEnabled(True)
            self.stop_button.setEnabled(True)
        d = CattDevice(ip_addr=ip)
        d._cast.wait()
        device = Device(self, d, d._cast, self.combo_box.count())
        d._cast.media_controller.register_status_listener(device.media_listener)
        d._cast.register_status_listener(device.status_listener)
        self.devices.append(d)
        self.device_list.append(device)
        self.combo_box.addItem(d.name)
        d.volume(REBOOT_VOLUME)

    def on_remove_device(self, ip):
        d = self.get_device_from_ip(ip)
        if d == None:
            return
        try:
            d.cast.media_controller._status_listeners.remove(d.media_listener)
        except Exception as e:
            print(ip, "Unregistering media controller failed:", e)
        try:
            d.cast.socket_client.receiver_controller._status_listeners.remove(
                d.status_listener
            )
        except Exception as e:
            print(ip, "Unregistering status listener failed:", e)
        self.stop_timer.emit(d.index)
        d.time = QTime(0, 0, 0)
        d.playing = False
        d.paused = True
        d.live = False
        self.combo_box.clear()
        i = 0
        for _d in self.device_list:
            if d != _d and _d.index != -1:
                self.combo_box.addItem(_d.device.name)
                _d.media_listener.index = _d.status_listener.index = _d.index = i
                i = i + 1
            else:
                _d.media_listener.index = _d.status_listener.index = _d.index = -1
        self.on_index_changed()

    def get_device_from_ip(self, ip):
        for d in self.device_list:
            if d.device.ip_addr == ip:
                return d
        return None

    def get_device_from_index(self, i):
        for d in self.device_list:
            if d.index == i:
                return d
        return None

    def active_devices(self):
        for d in self.device_list:
            if d.index != -1:
                return True
        return False


class MediaListener:
    def new_media_status(self, status):
        _self = self._self
        i = _self.combo_box.currentIndex()
        index = self.index
        if index == -1:
            return
        self.supports_seek = status.supports_seek
        if i != index:
            d = _self.get_device_from_index(index)
            if d == None:
                return
            d.duration = status.duration
            if status.player_state == "PLAYING":
                hours, minutes, seconds = self.split_seconds(int(status.current_time))
                _self.set_time(index, hours, minutes, seconds)
                _self.start_timer.emit(index)
                d.paused = False
                d.playing = True
                if status.stream_type == "LIVE":
                    d.live = True
                    _self.stop_timer.emit(index)
            elif status.player_state == "PAUSED":
                hours, minutes, seconds = self.split_seconds(int(status.current_time))
                _self.set_time(index, hours, minutes, seconds)
                d.paused = True
                d.playing = True
            elif status.player_state == "IDLE" or status.player_state == "UNKNOWN":
                _self.stop_timer.emit(index)
                d.time = QTime(0, 0, 0)
                d.playing = False
                d.paused = True
                d.live = False
            return
        d = _self.get_device_from_index(i)
        if d == None:
            return
        d.duration = status.duration
        if status.player_state == "PLAYING":
            if status.duration != None:
                _self.progress_slider.setMaximum(status.duration)
            _self.progress_slider.setValue(status.current_time)
            hours, minutes, seconds = self.split_seconds(int(status.current_time))
            _self.set_time(i, hours, minutes, seconds)
            _self.skip_forward_button.setEnabled(True)
            _self.progress_slider.setEnabled(True)
            d.paused = False
            d.playing = True
            _self.set_icon(_self.play_button, "SP_MediaPause")
            _self.progress_label.setText(d.time.toString("hh:mm:ss"))
            _self.start_timer.emit(i)
            if status.stream_type == "LIVE":
                d.live = True
                _self.stop_timer.emit(i)
                _self.skip_forward_button.setEnabled(False)
                _self.progress_slider.setEnabled(False)
                _self.play_button.setEnabled(False)
                _self.progress_label.setText("LIVE")
        elif status.player_state == "PAUSED":
            if status.duration != None:
                _self.progress_slider.setMaximum(status.duration)
            _self.progress_slider.setValue(status.current_time)
            hours, minutes, seconds = self.split_seconds(int(status.current_time))
            _self.set_time(i, hours, minutes, seconds)
            _self.skip_forward_button.setEnabled(True)
            _self.progress_slider.setEnabled(True)
            d.paused = True
            d.playing = True
            _self.set_icon(_self.play_button, "SP_MediaPlay")
            _self.progress_label.setText(d.time.toString("hh:mm:ss"))
        elif status.player_state == "IDLE" or status.player_state == "UNKNOWN":
            _self.progress_slider.setValue(0)
            _self.stop_timer.emit(i)
            d.time = QTime(0, 0, 0)
            _self.skip_forward_button.setEnabled(False)
            _self.progress_slider.setEnabled(False)
            _self.progress_label.setText(d.time.toString("hh:mm:ss"))
            _self.set_icon(_self.play_button, "SP_MediaPlay")
            _self.play_button.setEnabled(True)
            d.playing = False
            d.paused = True
            d.live = False

    def split_seconds(self, s):
        hours = s // 3600
        minutes = (s - (hours * 3600)) // 60
        seconds = s - ((hours * 3600) + (minutes * 60))
        return hours, minutes, seconds


class StatusListener:
    def new_cast_status(self, status):
        _self = self._self
        i = _self.combo_box.currentIndex()
        index = self.index
        if index == -1:
            return
        v = status.volume_level * 100
        d = _self.get_device_from_index(index)
        if d == None:
            return
        if i != index:
            d.volume = v
            d.status_text = status.status_text
            return
        d = _self.get_device_from_index(i)
        if d == None:
            return
        d.volume = v
        d.status_text = status.status_text
        _self.status_label.setText(status.status_text)
        if not _self.volume_status_event_pending:
            _self.dial.valueChanged.disconnect(_self.on_dial_moved)
            _self.dial.setValue(v)
            _self.dial.valueChanged.connect(_self.on_dial_moved)
        _self.volume_status_event_pending = False


class ConnectionListener:
    def new_connection_status(self, status):
        _self = self._self
        if status.status == "CONNECTED":
            print(status.address.address, "connected")
            _self.add_device.emit(status.address.address)
        elif status.status == "LOST":
            print(status.address.address, "disconnected")
            _self.remove_device.emit(status.address.address)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = App()
    sys.exit(app.exec_())
