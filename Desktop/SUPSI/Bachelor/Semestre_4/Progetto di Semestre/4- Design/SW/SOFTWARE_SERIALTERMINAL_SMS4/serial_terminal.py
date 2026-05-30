"""
Serial Terminal — Science Dashboard v7.6 (Ultimate Apple UI - Polished)
Powered by PyQt6 (Bulletproof on macOS)
Features: Bi-directional Logging, True Rolling Charts, Hardware GPIO XXYY mapping.
Tweak: Expanded connection top-bar dropdowns, fixed Volt button text clipping, added top-right section titles to dashboards.
"""

import sys
import os
import threading
import queue
import time
import re
from collections import deque
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QComboBox,
                             QTextEdit, QLineEdit, QFrame, QGridLayout,
                             QMessageBox, QStackedWidget, QCheckBox, QGraphicsDropShadowEffect)
from PyQt6.QtCore import QTimer, Qt, QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QTextCursor, QPixmap

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# ── APPLE iOS / macOS SONOMA HIG PALETTE ───────────────────────────────────────
BG      = "#1C1C1E"
PANEL   = "#2C2C2E"
WIDGET  = "#3A3A3C"
BORDER  = "#38383A"
BLUE    = "#0A84FF"
GREEN   = "#30D158"
RED     = "#FF453A"
YELLOW  = "#FFD60A"
ORANGE  = "#FF9F0A"
WHITE   = "#FFFFFF"
TEXT    = "#EBEBF5"
MUTED   = "#8E8E93"
LED_R   = "#FF453A"
LED_G   = "#30D158"
LED_Y   = "#FFD60A"
LED_OFF = "#1C1C1E"

BAUDS  = ["1200","2400","4800","9600","19200","38400","57600","115200","230400","460800","921600"]
DBITS  = ["5","6","7","8"]
PARS   = ["None","Even","Odd","Mark","Space"]
STOPS  = ["1","1.5","2"]
PINS   = [f"{r}{c}" for r in "01" for c in range(8)]

VOLT_INTERVALS = {
    "100ms": 100, "200ms": 200, "500ms": 500, "1s": 1000, "2s": 2000, "4s": 4000
}

DIGIT_MAP = [
    0x5F, 0x06, 0x3B, 0x2F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F
]

def now():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def apply_shadow(widget):
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(20)
    shadow.setXOffset(0)
    shadow.setYOffset(4)
    shadow.setColor(QColor(0, 0, 0, 60))
    widget.setGraphicsEffect(shadow)

# ── PREMIUM APPLE STYLESHEET ───────────────────────────────────────────────────
STYLESHEET = f"""
    QMainWindow, QWidget#MainWidget {{ 
        background-color: {BG}; 
        color: {TEXT}; 
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif; 
        font-size: 12px; 
    }}
    QFrame#Panel {{ 
        background-color: {PANEL}; 
        border-radius: 16px; 
        border: none;
    }}
    QLabel {{ color: {WHITE}; font-weight: 500; }}
    QLabel#Title {{ font-size: 20px; font-weight: 800; color: {WHITE}; letter-spacing: 0.5px; }}
    QLabel#SectionTitle {{ font-size: 13px; font-weight: 700; color: {WHITE}; letter-spacing: 0.2px; }}
    QComboBox {{ 
        background-color: {WIDGET}; color: {WHITE}; border: none; 
        padding: 5px 15px 5px 15px; border-radius: 12px; font-weight: 600; 
    }}
    QComboBox::drop-down {{ border: none; width: 15px; }}
    QComboBox QAbstractItemView {{ 
        background-color: {WIDGET}; color: {WHITE}; selection-background-color: {BLUE}; 
        border-radius: 12px; outline: none; 
    }}
    QPushButton {{ 
        background-color: {WIDGET}; color: {WHITE}; border: none; 
        padding: 6px 14px; border-radius: 14px; font-weight: 600; 
    }}
    QPushButton:hover {{ background-color: #48484A; }}
    QPushButton:pressed {{ background-color: {BLUE}; color: {WHITE}; }}
    QLineEdit {{ 
        background-color: {BG}; color: {WHITE}; border: none; 
        padding: 6px 14px; border-radius: 12px; font-family: "SF Mono", Menlo, Consolas, monospace; 
    }}
    QTextEdit {{ 
        background-color: {BG}; color: {TEXT}; border: none; border-radius: 12px; 
        font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 11px; padding: 12px; 
    }}
    QMessageBox {{ background-color: {PANEL}; color: {WHITE}; }}
    QCheckBox {{ color: {TEXT}; font-weight: 600; font-size: 11px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; background-color: {BG}; border: none; border-radius: 9px; }}
    QCheckBox::indicator:checked {{ background-color: {BLUE}; }}
"""

# ── Widget Grafico per i Trend (Stile Apple) ───────────────────────────────────
class DashboardChart(QWidget):
    def __init__(self, title, color1, label1, color2=None, label2=None, min_v=0, max_v=50, time_window_sec=200, enable_zoom=False):
        super().__init__()
        self.setMinimumHeight(100)
        self.chart_title = title
        self.c1, self.l1 = QColor(color1), label1
        self.c2, self.l2 = QColor(color2) if color2 else None, label2
        self.min_v, self.max_v = min_v, max_v

        self.time_window_sec = time_window_sec
        self.data1 = []
        self.data2 = [] if color2 else None

        self.enable_zoom = enable_zoom
        self.zoom_level = 1.0

    def update_time_window(self, new_window_sec):
        self.time_window_sec = new_window_sec
        self._purge_old_data()
        self.update()

    def clear_chart(self):
        self.data1.clear()
        if self.data2 is not None:
            self.data2.clear()
        self.update()

    def wheelEvent(self, event):
        if not self.enable_zoom:
            event.ignore()
            return
        angle = event.angleDelta().y()
        if angle > 0:
            self.zoom_level = max(0.1, self.zoom_level - 0.1)
        else:
            self.zoom_level = min(1.0, self.zoom_level + 0.1)
        self.update()
        event.accept()

    def _purge_old_data(self):
        current_time = time.time()
        active_window = self.time_window_sec * self.zoom_level
        cutoff_time = current_time - active_window
        self.data1 = [pt for pt in self.data1 if pt[0] >= cutoff_time]
        if self.data2 is not None:
            self.data2 = [pt for pt in self.data2 if pt[0] >= cutoff_time]

    def add_data(self, val1, val2=None):
        current_time = time.time()
        if val1 is not None:
            self.data1.append((current_time, val1))
        if val2 is not None and self.data2 is not None:
            self.data2.append((current_time, val2))
        self._purge_old_data()
        self.update()

    def paintEvent(self, event):
        self._purge_old_data()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin = 20
        plot_w = w - 2 * margin
        plot_h = h - 2 * margin

        p.setBrush(QColor(28, 28, 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, w, h, 14, 14)

        p.setPen(QPen(QColor(56, 56, 58), 1, Qt.PenStyle.DashLine))
        for i in range(1, 4):
            y = int(margin + plot_h * (i / 4))
            p.drawLine(margin, y, w - margin, y)

        active_window = self.time_window_sec * self.zoom_level
        current_time = time.time()

        def draw_trend(data_list):
            if len(data_list) < 2: return
            points = []
            for t_stamp, val in data_list:
                age_sec = current_time - t_stamp
                if age_sec > active_window: continue
                x = margin + plot_w - (plot_w * (age_sec / active_window))
                norm_y = (val - self.min_v) / (self.max_v - self.min_v)
                y = h - margin - (norm_y * plot_h)
                y = max(margin, min(h - margin, y))
                points.append(QPointF(x, y))
            for idx in range(len(points) - 1):
                p.drawLine(points[idx], points[idx+1])

        p.setPen(QPen(self.c1, 3))
        draw_trend(self.data1)
        if self.data2 is not None:
            p.setPen(QPen(self.c2, 3))
            draw_trend(self.data2)

        p.setPen(QColor(WHITE))
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        zoom_text = f" [Zoom: {int(100 / self.zoom_level)}%]" if self.enable_zoom else ""
        p.drawText(margin, margin - 6, f"{self.chart_title}{zoom_text}")
        p.setPen(self.c1)
        p.drawText(w - 150, margin - 6, f"● {self.l1}")
        if self.c2:
            p.setPen(self.c2)
            p.drawText(w - 70, margin - 6, f"● {self.l2}")

# ── Serial Worker ──────────────────────────────────────────────────────────────
class Worker(threading.Thread):
    def __init__(self, q):
        super().__init__(daemon=True)
        self.q = q
        self._ser  = None
        self._kill = threading.Event()
        self._lock = threading.Lock()

    def open(self, port, baud, db, par, sb):
        self.close()
        if not HAS_SERIAL: return False, "pyserial not installed"
        par_map = {"None":"N","Even":"E","Odd":"O","Mark":"M","Space":"S"}
        sb_map  = {"1":1,"1.5":1.5,"2":2}
        try:
            self._ser = serial.Serial(port=port, baudrate=int(baud), bytesize=int(db),
                                     parity=par_map.get(par,"N"), stopbits=sb_map.get(sb,1),
                                     timeout=0.1)
            return True, ""
        except Exception as e: return False, str(e)

    def close(self):
        with self._lock:
            if self._ser:
                try:
                    self._ser.cancel_read()
                    self._ser.close()
                except: pass
                self._ser = None

    def write(self, cmd):
        with self._lock:
            if self._ser and self._ser.is_open:
                try:
                    self._ser.write((cmd+"\r\n").encode("utf-8"))
                    self._ser.flush()
                    return True
                except: pass
        return False

    def is_open(self):
        with self._lock: return bool(self._ser and self._ser.is_open)

    def run(self):
        while not self._kill.is_set():
            with self._lock:
                s = self._ser
                is_ok = s and s.is_open

            if is_ok:
                try:
                    c = s.read(1)
                    if c:
                        remainder = s.read_all()
                        full_msg = c + remainder
                        self.q.put(full_msg.decode("utf-8", errors="replace"))
                except:
                    self.close()
            else:
                time.sleep(0.05)

# ──════════════════════════════════════════════════════════════════════════════
class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Serial Terminal · Hardware Science Dashboard")
        self.resize(1350, 700)

        main_widget = QWidget()
        main_widget.setObjectName("MainWidget")
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(12)

        self.latest_spi_temp = None
        self.latest_adc_temp = None
        self.latest_volt = None

        self.usb_q  = queue.Queue()
        self.uart_q = queue.Queue()
        self.usb_w  = Worker(self.usb_q)
        self.uart_w = Worker(self.uart_q)
        self.usb_w.start()
        self.uart_w.start()

        self.temp_monitoring = False
        self.volt_monitoring = False

        self.temp_timer = QTimer()
        self.temp_timer.timeout.connect(self._poll_temperatures)

        self.volt_timer = QTimer()
        self.volt_timer.timeout.connect(self._poll_voltage)

        self.gui_timer = QTimer()
        self.gui_timer.timeout.connect(self._poll_serial_queues)
        self.gui_timer.start(20)

        self.chart_redraw_timer = QTimer()
        self.chart_redraw_timer.timeout.connect(self._force_chart_redraw)
        self.chart_redraw_timer.start(50)

        self._build_topbar()
        self._build_telemetry_dashboards()
        self._build_controls()
        self._build_logs()

        self._refresh_ports()

    def _force_chart_redraw(self):
        if self.temp_monitoring: self.temp_chart.update()
        if self.volt_monitoring: self.volt_chart.update()

    def _build_topbar(self):
        bar = QFrame(); bar.setObjectName("Panel")
        apply_shadow(bar)
        layout = QVBoxLayout(bar); layout.setContentsMargins(15, 10, 15, 10)

        hdr = QHBoxLayout()
        title = QLabel("Serial Terminal"); title.setObjectName("Title")
        hdr.addWidget(title); hdr.addStretch()

        about_btn = QPushButton("ℹ About")
        about_btn.setFixedSize(80, 28)
        about_btn.setStyleSheet(f"color: {BLUE}; font-weight: bold; background: transparent;")
        about_btn.clicked.connect(self._show_about)
        hdr.addWidget(about_btn)

        layout.addLayout(hdr)
        layout.addSpacing(5)

        # MODIFICATO: Spazi orizzontali massimizzati per evitare testi tagliati nei menu
        def make_row(title_txt, color, btn_attr, dot_attr, p_menu, b_menu, db_menu, par_menu, sb_menu, default_baud, toggle_cb):
            row = QHBoxLayout(); row.setSpacing(10)
            lbl = QLabel(title_txt); lbl.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 13px;"); lbl.setFixedWidth(85)
            row.addWidget(lbl)

            row.addWidget(QLabel("Port"))
            setattr(self, p_menu, QComboBox()); getattr(self, p_menu).setFixedWidth(200) # Allargato profondamente
            row.addWidget(getattr(self, p_menu))

            row.addWidget(QLabel("Baud"))
            setattr(self, b_menu, QComboBox()); getattr(self, b_menu).addItems(BAUDS); getattr(self, b_menu).setCurrentText(default_baud)
            getattr(self, b_menu).setFixedWidth(100) # Allargato
            row.addWidget(getattr(self, b_menu))

            row.addWidget(QLabel("Data"))
            setattr(self, db_menu, QComboBox()); getattr(self, db_menu).addItems(DBITS); getattr(self, db_menu).setCurrentText("8")
            getattr(self, db_menu).setFixedWidth(60) # Allargato
            row.addWidget(getattr(self, db_menu))

            row.addWidget(QLabel("Parity"))
            setattr(self, par_menu, QComboBox()); getattr(self, par_menu).addItems(PARS); getattr(self, par_menu).setCurrentText("None")
            getattr(self, par_menu).setFixedWidth(85) # Allargato
            row.addWidget(getattr(self, par_menu))

            row.addWidget(QLabel("Stop"))
            setattr(self, sb_menu, QComboBox()); getattr(self, sb_menu).addItems(STOPS); getattr(self, sb_menu).setCurrentText("1")
            getattr(self, sb_menu).setFixedWidth(60) # Allargato
            row.addWidget(getattr(self, sb_menu))

            row.addStretch()

            btn = QPushButton("Connect"); btn.setFixedWidth(120) # Allargato
            btn.setStyleSheet(f"background-color: {WIDGET}; color: {color};")
            btn.clicked.connect(toggle_cb); setattr(self, btn_attr, btn); row.addWidget(btn)

            dot = QLabel("●"); dot.setStyleSheet(f"color: {BORDER}; font-size: 18px;"); setattr(self, dot_attr, dot); row.addWidget(dot)
            return row

        layout.addLayout(make_row("USB", BLUE, "u_cbtn", "u_dot", "u_port_menu", "u_baud_menu", "u_db_menu", "u_par_menu", "u_sb_menu", "115200", self._toggle_usb))
        layout.addLayout(make_row("UART", ORANGE, "r_cbtn", "r_dot", "r_port_menu", "r_baud_menu", "r_db_menu", "r_par_menu", "r_sb_menu", "9600", self._toggle_uart))
        self.main_layout.addWidget(bar)

    def _build_telemetry_dashboards(self):
        dash_container = QFrame()
        main_hbox = QHBoxLayout(dash_container); main_hbox.setContentsMargins(0, 0, 0, 0); main_hbox.setSpacing(12)

        def create_display_block(label_text, color):
            w = QWidget()
            vl = QVBoxLayout(w); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(2)
            lbl = QLabel(label_text); lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700; text-transform: uppercase;")
            val = QLabel("--.-"); val.setStyleSheet(f"color: {WHITE}; font-size: 30px; font-weight: 800; font-family: 'SF Mono', Monaco, monospace; letter-spacing: -1px;")
            vl.addWidget(lbl); vl.addWidget(val)
            return w, val

        # ── Temperature Panel ──
        temp_panel = QFrame(); temp_panel.setObjectName("Panel")
        apply_shadow(temp_panel)
        temp_main_layout = QVBoxLayout(temp_panel)
        temp_main_layout.setContentsMargins(15, 10, 15, 12)
        temp_main_layout.setSpacing(5)

        # Titolo in alto a destra
        lbl_temp_title = QLabel("TEMPERATURE MEASUREMENT")
        lbl_temp_title.setStyleSheet(f"color: {MUTED}; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        temp_main_layout.addWidget(lbl_temp_title, alignment=Qt.AlignmentFlag.AlignRight)

        temp_hbox = QHBoxLayout()
        temp_hbox.setContentsMargins(0, 0, 0, 0); temp_hbox.setSpacing(15)

        temp_vbox_controls = QVBoxLayout(); temp_vbox_controls.setSpacing(8)
        self.temp_btn = QPushButton("▶ START TEMP"); self.temp_btn.setFixedSize(140, 32)
        self.temp_btn.setStyleSheet(f"background-color: {BLUE}; color: {WHITE}; font-weight: 700;")
        self.temp_btn.clicked.connect(self._toggle_temp_monitoring)
        temp_vbox_controls.addWidget(self.temp_btn)

        self.temp_reset_btn = QPushButton("❌ RESET TEMP"); self.temp_reset_btn.setFixedSize(140, 26)
        self.temp_reset_btn.setStyleSheet(f"background-color: transparent; color: {RED}; font-size: 10px; font-weight: 700;")
        self.temp_reset_btn.clicked.connect(self._reset_temp_data)
        temp_vbox_controls.addWidget(self.temp_reset_btn)

        temp_vbox_controls.addSpacing(5)
        spi_w, self.spi_lbl = create_display_block("SPI SENSOR", YELLOW)
        adc_w, self.adc_lbl = create_display_block("ADC SENSOR", GREEN)
        temp_vbox_controls.addWidget(spi_w); temp_vbox_controls.addWidget(adc_w)
        temp_hbox.addLayout(temp_vbox_controls)

        self.temp_chart = DashboardChart("Temperature", YELLOW, "SPI Temp", GREEN, "ADC Temp", min_v=-300, max_v=60, time_window_sec=200, enable_zoom=False)
        temp_hbox.addWidget(self.temp_chart, stretch=1)
        temp_main_layout.addLayout(temp_hbox)

        main_hbox.addWidget(temp_panel, stretch=1)

        # ── Voltage Panel ──
        volt_panel = QFrame(); volt_panel.setObjectName("Panel")
        apply_shadow(volt_panel)
        volt_main_layout = QVBoxLayout(volt_panel)
        volt_main_layout.setContentsMargins(15, 10, 15, 12)
        volt_main_layout.setSpacing(5)

        # Titolo in alto a destra
        lbl_volt_title = QLabel("VOLTMETER")
        lbl_volt_title.setStyleSheet(f"color: {MUTED}; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        volt_main_layout.addWidget(lbl_volt_title, alignment=Qt.AlignmentFlag.AlignRight)

        volt_hbox = QHBoxLayout()
        volt_hbox.setContentsMargins(0, 0, 0, 0); volt_hbox.setSpacing(15)

        volt_vbox_controls = QVBoxLayout(); volt_vbox_controls.setSpacing(8)
        v_rate_layout = QHBoxLayout(); v_rate_layout.setSpacing(5)

        # MODIFICATO: Pulsante Start Volt allargato per non tagliare il testo
        self.volt_btn = QPushButton("▶ START VOLT"); self.volt_btn.setFixedSize(130, 32)
        self.volt_btn.setStyleSheet(f"background-color: {BLUE}; color: {WHITE}; font-weight: 700;")
        self.volt_btn.clicked.connect(self._toggle_volt_monitoring)

        self.rate_menu = QComboBox()
        self.rate_menu.addItems(list(VOLT_INTERVALS.keys())); self.rate_menu.setCurrentText("2s"); self.rate_menu.setFixedWidth(70)
        self.rate_menu.currentTextChanged.connect(self._on_volt_rate_changed)

        v_rate_layout.addWidget(self.volt_btn); v_rate_layout.addWidget(self.rate_menu)
        volt_vbox_controls.addLayout(v_rate_layout)

        # Allineato alla somma delle larghezze sopra (130 + 5 + 70 = 205)
        self.volt_reset_btn = QPushButton("❌ RESET VOLT"); self.volt_reset_btn.setFixedSize(205, 26)
        self.volt_reset_btn.setStyleSheet(f"background-color: transparent; color: {RED}; font-size: 10px; font-weight: 700;")
        self.volt_reset_btn.clicked.connect(self._reset_volt_data)
        volt_vbox_controls.addWidget(self.volt_reset_btn)

        volt_vbox_controls.addSpacing(5)
        volt_w, self.volt_lbl = create_display_block("ADC VOLTAGE", BLUE)
        volt_vbox_controls.addWidget(volt_w); volt_vbox_controls.addStretch()
        volt_hbox.addLayout(volt_vbox_controls)

        self.volt_chart = DashboardChart("Voltage", BLUE, "ADC Volt", min_v=0, max_v=5, time_window_sec=4, enable_zoom=True)
        volt_hbox.addWidget(self.volt_chart, stretch=1)
        volt_main_layout.addLayout(volt_hbox)

        main_hbox.addWidget(volt_panel, stretch=1)

        self.main_layout.addWidget(dash_container, stretch=1)

    def _build_controls(self):
        container = QWidget(); layout = QHBoxLayout(container); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(12)

        def make_panel(title, color):
            f = QFrame(); f.setObjectName("Panel")
            apply_shadow(f)
            vl = QVBoxLayout(f); vl.setContentsMargins(15, 10, 15, 10); vl.setSpacing(8)
            lbl = QLabel(title); lbl.setObjectName("SectionTitle"); lbl.setStyleSheet(f"color: {color};")
            vl.addWidget(lbl)
            content = QVBoxLayout(); content.setSpacing(8); vl.addLayout(content); vl.addStretch()
            return f, content

        # LED Panel
        led_f, led_l = make_panel("LED Controls", RED)
        btn_toggle = QPushButton("Toggle All LEDs")
        self.led_buttons = []
        def master_toggle_click():
            self._usb_send("toggleLEDs")
            for btn in self.led_buttons: btn.on = not btn.on; btn._update_style()
        btn_toggle.clicked.connect(master_toggle_click); led_l.addWidget(btn_toggle)

        led_row = QHBoxLayout()
        for n, c, o, f in [("RED", LED_R, "redLED_on", "redLED_off"), ("YELLOW", LED_Y, "yellowLED_on", "yellowLED_off"), ("GREEN", LED_G, "greenLED_on", "greenLED_off")]:
            col = QVBoxLayout(); col.setSpacing(4)
            l = QLabel(n); l.setStyleSheet(f"color: {c}; font-weight: 800; font-size: 10px;"); l.setAlignment(Qt.AlignmentFlag.AlignCenter); col.addWidget(l)
            btn = LEDButton(c, o, f, self._usb_send); self.led_buttons.append(btn); col.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter); led_row.addLayout(col)
        led_l.addLayout(led_row); layout.addWidget(led_f)

        # GPIO Panel
        gpio_f, gpio_l = make_panel("GPIO & 7-Segment", BLUE)

        self.gpio_stack_btn = QPushButton("⇄ Switch View")
        self.gpio_stack_btn.setStyleSheet(f"background-color: {WIDGET}; color: {BLUE}; font-weight: 700;")
        self.gpio_stack_btn.clicked.connect(self._toggle_gpio_stack)
        gpio_l.addWidget(self.gpio_stack_btn)

        self.gpio_stack = QStackedWidget()
        gpio_l.addWidget(self.gpio_stack)

        # --- Pagina 0: Manual Controls ---
        page0 = QWidget()
        p0_layout = QVBoxLayout(page0); p0_layout.setContentsMargins(0, 5, 0, 0); p0_layout.setSpacing(8)

        row = QHBoxLayout(); row.addWidget(QLabel("Pin:")); self.pin_menu = QComboBox(); self.pin_menu.addItems(PINS); self.pin_menu.setFixedWidth(70); row.addWidget(self.pin_menu); row.addStretch(); p0_layout.addLayout(row)
        grid = QGridLayout(); grid.setSpacing(6)

        def send_pin_cmd(base_cmd):
            self._usb_send(f"{base_cmd} {self.pin_menu.currentText()}")

        b_set = QPushButton("Set Pin"); b_set.clicked.connect(lambda: send_pin_cmd("setExpPin")); grid.addWidget(b_set, 0, 0)
        b_res = QPushButton("Reset Pin"); b_res.clicked.connect(lambda: send_pin_cmd("resetExpPin")); grid.addWidget(b_res, 0, 1)
        b_tog = QPushButton("Toggle Pin"); b_tog.clicked.connect(lambda: send_pin_cmd("toggleExpPin")); grid.addWidget(b_tog, 1, 0)
        b_read = QPushButton("Read Pin"); b_read.clicked.connect(lambda: send_pin_cmd("readExpPin")); grid.addWidget(b_read, 1, 1)
        b_ra = QPushButton("Read All"); b_ra.clicked.connect(lambda: self._usb_send("readExpAll")); grid.addWidget(b_ra, 2, 0)
        b_ta = QPushButton("Toggle All"); b_ta.clicked.connect(lambda: self._usb_send("toggleExpAll")); grid.addWidget(b_ta, 2, 1)
        p0_layout.addLayout(grid)

        wa_row = QHBoxLayout(); wa_btn = QPushButton("Write Hex")
        self.wa_entry = QLineEdit(); self.wa_entry.setPlaceholderText("Es. FF"); self.wa_entry.setFixedWidth(100)
        wa_btn.clicked.connect(lambda: self._usb_send(f"writeExpAll {self.wa_entry.text().strip()}"))
        wa_row.addWidget(wa_btn); wa_row.addWidget(self.wa_entry); p0_layout.addLayout(wa_row)

        self.gpio_stack.addWidget(page0)

        # --- Pagina 1: 7-Segment Control ---
        page1 = QWidget()
        p1_layout = QVBoxLayout(page1); p1_layout.setContentsMargins(0, 5, 0, 0); p1_layout.setSpacing(6)

        self.anode_checkbox = QCheckBox("Common Anode")
        p1_layout.addWidget(self.anode_checkbox, alignment=Qt.AlignmentFlag.AlignRight)

        self.virt_7seg = QLabel("--.")
        self.virt_7seg.setStyleSheet(f"""
            background-color: {BG}; color: {RED}; 
            font-family: 'SF Mono', Monaco, monospace; font-size: 56px; font-weight: 900;
            border-radius: 12px; padding: 0px 10px;
        """)
        self.virt_7seg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p1_layout.addWidget(self.virt_7seg)

        btn_row = QHBoxLayout()
        btn_spi = QPushButton("SPI"); btn_spi.setStyleSheet(f"color: {YELLOW};")
        btn_adc = QPushButton("ADC"); btn_adc.setStyleSheet(f"color: {GREEN};")
        btn_vol = QPushButton("VOLT"); btn_vol.setStyleSheet(f"color: {BLUE};")

        btn_spi.clicked.connect(lambda: self._set_7seg_hardware("spi"))
        btn_adc.clicked.connect(lambda: self._set_7seg_hardware("adc"))
        btn_vol.clicked.connect(lambda: self._set_7seg_hardware("volt"))

        btn_row.addWidget(btn_spi); btn_row.addWidget(btn_adc); btn_row.addWidget(btn_vol)
        p1_layout.addLayout(btn_row)

        self.gpio_stack.addWidget(page1)

        layout.addWidget(gpio_f)
        self.main_layout.addWidget(container)

    def _toggle_gpio_stack(self):
        curr = self.gpio_stack.currentIndex()
        if curr == 0:
            self.gpio_stack.setCurrentIndex(1)
        else:
            self.gpio_stack.setCurrentIndex(0)

    def _set_7seg_hardware(self, mode):
        if not self.usb_w.is_open():
            QMessageBox.warning(self, "Warning", "Please connect USB first!")
            return

        display_str = "--."
        p0_val = 0x00
        p1_val = 0x00

        if mode == "spi":
            if self.latest_spi_temp is None: return
            val_int = int(abs(self.latest_spi_temp))
            if val_int > 99: val_int = 99
            tens = (val_int // 10) % 10
            units = val_int % 10
            p0_val = DIGIT_MAP[tens]
            p1_val = DIGIT_MAP[units] | 0x80
            display_str = f"{tens}{units}."

        elif mode == "adc":
            if self.latest_adc_temp is None: return
            val_int = int(abs(self.latest_adc_temp))
            if val_int > 99: val_int = 99
            tens = (val_int // 10) % 10
            units = val_int % 10
            p0_val = DIGIT_MAP[tens]
            p1_val = DIGIT_MAP[units] | 0x80
            display_str = f"{tens}{units}."

        elif mode == "volt":
            if self.latest_volt is None: return
            units = int(abs(self.latest_volt)) % 10
            tenths = int(abs(self.latest_volt) * 10) % 10
            p0_val = DIGIT_MAP[units] | 0x80
            p1_val = DIGIT_MAP[tenths]
            display_str = f"{units}.{tenths}"

        if self.anode_checkbox.isChecked():
            p0_val = (~p0_val) & 0xFF
            p1_val = (~p1_val) & 0xFF

        self.virt_7seg.setText(display_str)
        hex_word = ((p0_val & 0xFF) << 8) | (p1_val & 0xFF)
        self._usb_send(f"writeExpAll {hex_word:04X}")

    def _build_logs(self):
        logs = QWidget()
        logs.setMaximumHeight(130)
        layout = QHBoxLayout(logs); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(12)

        u_box = QFrame(); u_box.setObjectName("Panel")
        apply_shadow(u_box)
        u_v = QVBoxLayout(u_box); u_v.setContentsMargins(10, 8, 10, 8); u_v.setSpacing(6)
        lbl_u = QLabel("USB Console"); lbl_u.setObjectName("SectionTitle"); lbl_u.setStyleSheet(f"color: {BLUE};")
        u_v.addWidget(lbl_u)
        self.usb_txt = QTextEdit(); self.usb_txt.setReadOnly(True); u_v.addWidget(self.usb_txt)

        er = QHBoxLayout(); er.setSpacing(8)
        self.usb_entry = QLineEdit(); self.usb_entry.returnPressed.connect(self._entry_send)
        btn_send = QPushButton("Send"); btn_send.clicked.connect(self._entry_send)
        btn_send.setStyleSheet(f"background-color: {BLUE}; color: {WHITE}; border: none; padding: 4px 12px;")
        er.addWidget(self.usb_entry); er.addWidget(btn_send); u_v.addLayout(er); layout.addWidget(u_box)

        r_box = QFrame(); r_box.setObjectName("Panel")
        apply_shadow(r_box)
        r_v = QVBoxLayout(r_box); r_v.setContentsMargins(10, 8, 10, 8); r_v.setSpacing(6)
        lbl_r = QLabel("UART Console"); lbl_r.setObjectName("SectionTitle"); lbl_r.setStyleSheet(f"color: {ORANGE};")
        r_v.addWidget(lbl_r)
        self.uart_txt = QTextEdit(); self.uart_txt.setReadOnly(True); r_v.addWidget(self.uart_txt)
        layout.addWidget(r_box)

        self.main_layout.addWidget(logs)

    def _toggle_temp_monitoring(self):
        if not self.usb_w.is_open():
            QMessageBox.warning(self, "Warning", "Please connect USB first!")
            return
        self.temp_monitoring = not self.temp_monitoring
        if self.temp_monitoring:
            self.temp_btn.setText("⏹ STOP TEMP")
            self.temp_btn.setStyleSheet(f"background-color: {WIDGET}; color: {RED}; font-weight: bold; border: none;")
            self.temp_timer.start(2000)
        else:
            self.temp_btn.setText("▶ START TEMP")
            self.temp_btn.setStyleSheet(f"background-color: {BLUE}; color: {WHITE}; font-weight: bold; border: none;")
            self.temp_timer.stop()

    def _toggle_volt_monitoring(self):
        if not self.usb_w.is_open():
            QMessageBox.warning(self, "Warning", "Please connect USB first!")
            return
        self.volt_monitoring = not self.volt_monitoring
        if self.volt_monitoring:
            self.volt_btn.setText("⏹ STOP VOLT")
            self.volt_btn.setStyleSheet(f"background-color: {WIDGET}; color: {RED}; font-weight: bold; border: none;")
            interval_ms = VOLT_INTERVALS[self.rate_menu.currentText()]
            self.volt_timer.start(interval_ms)
        else:
            self.volt_btn.setText("▶ START VOLT")
            self.volt_btn.setStyleSheet(f"background-color: {BLUE}; color: {WHITE}; font-weight: bold; border: none;")
            self.volt_timer.stop()

    def _on_volt_rate_changed(self, new_rate):
        if self.volt_monitoring:
            interval_ms = VOLT_INTERVALS[new_rate]
            self.volt_timer.start(interval_ms)

    def _reset_temp_data(self):
        self.temp_chart.clear_chart()
        self.spi_lbl.setText("--.-")
        self.adc_lbl.setText("--.-")
        self.latest_spi_temp = None
        self.latest_adc_temp = None

    def _reset_volt_data(self):
        self.volt_chart.clear_chart()
        self.volt_lbl.setText("--.-")
        self.latest_volt = None

    def _poll_temperatures(self):
        self._usb_send("readSPI")
        QTimer.singleShot(100, lambda: self._usb_send("readADC 0"))

    def _poll_voltage(self):
        self._usb_send("readADC 1")

    def _parse_incoming_telemetry(self, text):
        spi_match = re.search(r"SPI Temperature Value:\s*(-?\d+)[.,](\d+)", text)
        if spi_match:
            val = float(f"{spi_match.group(1)}.{spi_match.group(2)}")
            self.latest_spi_temp = val
            self.spi_lbl.setText(f"{val:.2f} °C")
            self.temp_chart.add_data(val, None)
            return

        adc_match = re.search(r"ADC Temperature Value:\s*(-?\d+)\.(\d+)", text)
        if adc_match:
            val = float(f"{adc_match.group(1)}.{adc_match.group(2)}")
            self.latest_adc_temp = val
            self.adc_lbl.setText(f"{val:.2f} °C")
            self.temp_chart.add_data(None, val)
            return

        volt_match = re.search(r"ADC Voltage Value:\s*(-?\d+)\.(\d+)", text)
        if volt_match:
            val = float(f"{volt_match.group(1)}.{volt_match.group(2)}")
            self.latest_volt = val
            self.volt_lbl.setText(f"{val:.3f} V")
            self.volt_chart.add_data(val, None)
            return

    def _sync_connection_ui(self):
        if self.u_cbtn.text() == "Disconnect" and not self.usb_w.is_open():
            self.u_cbtn.setText("Connect")
            self.u_cbtn.setStyleSheet(f"background-color: {WIDGET}; color: {BLUE}; font-weight: bold; border: none;")
            self.u_dot.setStyleSheet(f"color: {BORDER}; font-size: 18px;")
            if self.temp_monitoring: self._toggle_temp_monitoring()
            if self.volt_monitoring: self._toggle_volt_monitoring()
            self._log_u(f"[{now()}] [SYSTEM] USB Connection Lost.\n", RED)

        if self.r_cbtn.text() == "Disconnect" and not self.uart_w.is_open():
            self.r_cbtn.setText("Connect")
            self.r_cbtn.setStyleSheet(f"background-color: {WIDGET}; color: {ORANGE}; font-weight: bold; border: none;")
            self.r_dot.setStyleSheet(f"color: {BORDER}; font-size: 18px;")
            self._log_r(f"[{now()}] [SYSTEM] UART Connection Lost.\n", RED)

    def _poll_serial_queues(self):
        self._sync_connection_ui()
        while not self.usb_q.empty():
            raw = self.usb_q.get_nowait()
            self._log_u(raw, GREEN)
            self._parse_incoming_telemetry(raw)
        while not self.uart_q.empty():
            self._log_r(self.uart_q.get_nowait(), ORANGE)

    def _log_u(self, t, color):
        html_text = t.replace("\n", "<br>")
        self.usb_txt.moveCursor(QTextCursor.MoveOperation.End)
        self.usb_txt.insertHtml(f'<span style="color: {color};">{html_text}</span>')
        self.usb_txt.moveCursor(QTextCursor.MoveOperation.End)

    def _log_r(self, t, color):
        html_text = t.replace("\n", "<br>")
        self.uart_txt.moveCursor(QTextCursor.MoveOperation.End)
        self.uart_txt.insertHtml(f'<span style="color: {color};">{html_text}</span>')
        self.uart_txt.moveCursor(QTextCursor.MoveOperation.End)

    def _refresh_ports(self):
        pts = [p.device for p in serial.tools.list_ports.comports()] if HAS_SERIAL else ["/dev/ttyUSB0", "/dev/ttyUSB1"]
        if not pts: pts = ["— no ports —"]
        for m in [self.u_port_menu, self.r_port_menu]:
            cur = m.currentText()
            m.clear(); m.addItems(pts)
            if cur in pts: m.setCurrentText(cur)

    def _toggle_usb(self):
        if self.usb_w.is_open():
            self.usb_w.close(); self.u_cbtn.setText("Connect"); self.u_cbtn.setStyleSheet(f"background-color: {WIDGET}; color: {BLUE}; font-weight: bold; border: none;")
            self.u_dot.setStyleSheet(f"color: {BORDER}; font-size: 18px;")
            if self.temp_monitoring: self._toggle_temp_monitoring()
            if self.volt_monitoring: self._toggle_volt_monitoring()
        else:
            ok, err = self.usb_w.open(self.u_port_menu.currentText(), self.u_baud_menu.currentText(),
                                      self.u_db_menu.currentText(), self.u_par_menu.currentText(), self.u_sb_menu.currentText())
            if ok:
                self.u_cbtn.setText("Disconnect"); self.u_cbtn.setStyleSheet(f"background-color: {BLUE}; color: {WHITE}; font-weight: bold; border: none;")
                self.u_dot.setStyleSheet(f"color: {GREEN}; font-size: 18px;")
            else:
                self.u_dot.setStyleSheet(f"color: {RED}; font-size: 18px;")
                QMessageBox.critical(self, "Connection Error", err)

    def _toggle_uart(self):
        if self.uart_w.is_open():
            self.uart_w.close(); self.r_cbtn.setText("Connect"); self.r_cbtn.setStyleSheet(f"background-color: {WIDGET}; color: {ORANGE}; font-weight: bold; border: none;")
            self.r_dot.setStyleSheet(f"color: {BORDER}; font-size: 18px;")
        else:
            ok, err = self.uart_w.open(self.r_port_menu.currentText(), self.r_baud_menu.currentText(),
                                       self.r_db_menu.currentText(), self.r_par_menu.currentText(), self.r_sb_menu.currentText())
            if ok:
                self.r_cbtn.setText("Disconnect"); self.r_cbtn.setStyleSheet(f"background-color: {ORANGE}; color: {WHITE}; font-weight: bold; border: none;")
                self.r_dot.setStyleSheet(f"color: {GREEN}; font-size: 18px;")
            else:
                self.r_dot.setStyleSheet(f"color: {RED}; font-size: 18px;")
                QMessageBox.critical(self, "Connection Error", err)

    def _usb_send(self, cmd):
        if self.usb_w.write(cmd): self._log_u(f"[{now()}] TX › {cmd}\n", BLUE)

    def _entry_send(self):
        c = self.usb_entry.text().strip()
        if c: self._usb_send(c); self.usb_entry.clear()

    def _show_about(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("About Science Terminal")
        msg.setText("<b>Science Terminal v1.1</b><br>Creator: Gemini<br>Supervisor: Nicolas Fontana<br><br>MacOS software for SemesterProject V1.0 board.")

        script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(script_dir, "logo.png")

        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            msg.setIconPixmap(pixmap.scaledToWidth(120, Qt.TransformationMode.SmoothTransformation))
        else:
            msg.setIcon(QMessageBox.Icon.Information)

        msg.exec()

    def closeEvent(self, e):
        self.usb_w._kill.set()
        self.uart_w._kill.set()
        self.usb_w.close()
        self.uart_w.close()
        e.accept()

# ── Support UI Classes ─────────────────────────────────────────────────────────
class LEDButton(QPushButton):
    def __init__(self, col, on, off, snd):
        super().__init__(); self.setFixedSize(36,36); self.col, self.on_c, self.off_c, self.snd = col, on, off, snd; self.on = False; self.clicked.connect(self._click); self._update_style()
    def _click(self): self.on = not self.on; self._update_style(); self.snd(self.on_c if self.on else self.off_c)
    def _update_style(self): self.setStyleSheet(f"background-color: {self.col if self.on else LED_OFF}; border: 3px solid {'#3A3A3C' if not self.on else self.col}; border-radius: 18px;")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = App()
    window.show()
    sys.exit(app.exec())