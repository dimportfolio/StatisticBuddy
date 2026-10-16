"""Main window: session controls on top, then Live / Regions / History tabs."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from statisticbuddy import PROJECT_URL, SUPPORT_URL, __version__
from statisticbuddy.core import fmt
from statisticbuddy.core.module import AppContext, TrackerModule
from statisticbuddy.core.session import SessionController
from statisticbuddy.ui.history_tab import HistoryTab
from statisticbuddy.ui.regions_tab import RegionsTab


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, modules: list[TrackerModule], controller: SessionController):
        super().__init__()
        self.ctx, self.modules, self.controller = ctx, modules, controller
        self.setWindowTitle(f"StatisticBuddy {__version__}")
        self.resize(680, 760)

        central = QWidget()
        root = QVBoxLayout(central)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Character"))
        self.character = QLineEdit(controller.character)
        self.character.setPlaceholderText("optional")
        self.character.editingFinished.connect(lambda: controller.set_character(self.character.text().strip()))
        bar.addWidget(self.character, 1)
        bar.addWidget(QLabel("Read every"))
        interval = QSpinBox()
        interval.setRange(3, 120)
        interval.setSuffix(" s")
        interval.setValue(controller.interval)
        interval.valueChanged.connect(controller.set_interval)
        bar.addWidget(interval)
        self.start_btn = QPushButton()
        self.start_btn.clicked.connect(controller.toggle)
        self.stop_btn = QPushButton("Stop && save")
        self.stop_btn.clicked.connect(controller.stop)
        for b in (self.start_btn, self.stop_btn):
            b.setMinimumHeight(30)
            bar.addWidget(b)
        root.addLayout(bar)

        info = QHBoxLayout()
        self.active = QLabel()
        self.status = QLabel("Set up the Regions tab, then start a session.")
        self.status.setWordWrap(True)
        info.addWidget(self.active)
        info.addWidget(self.status, 1)
        root.addLayout(info)

        tabs = QTabWidget()
        live = QWidget()
        live_layout = QVBoxLayout(live)
        for m in modules:
            panel = m.create_panel(ctx)
            if panel is not None:
                live_layout.addWidget(panel)
        live_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(live)
        tabs.addTab(scroll, "Live")
        regions = QScrollArea()
        regions.setWidgetResizable(True)
        regions.setWidget(RegionsTab(controller))
        tabs.addTab(regions, "Regions")
        self.history = HistoryTab(ctx, modules)
        tabs.addTab(self.history, "History")
        root.addWidget(tabs, 1)
        self.setCentralWidget(central)

        ui = ctx.settings.section("ui")
        view = self.menuBar().addMenu("View")
        self.on_top = QAction("Always on top", self, checkable=True)
        self.on_top.setChecked(bool(ui.get("always_on_top", False)))
        self.on_top.toggled.connect(self._set_on_top)
        view.addAction(self.on_top)
        self._set_on_top(self.on_top.isChecked())

        # Links open in the web browser; the app itself never connects to the internet.
        help_menu = self.menuBar().addMenu("Help")
        for text, url in (("♥ Support StatisticBuddy (Buy Me a Coffee)", SUPPORT_URL),
                          ("Project page and updates (GitHub)", PROJECT_URL)):
            action = QAction(text, self)
            action.triggered.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            help_menu.addAction(action)

        controller.status.connect(self.status.setText)
        controller.state_changed.connect(self._on_state)
        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start(1000)
        self._on_state()
        self._tick()

    def _on_state(self) -> None:
        c = self.controller
        if c.running:
            self.start_btn.setText("Pause")
        elif c.session_id is not None:
            self.start_btn.setText("Resume")
        else:
            self.start_btn.setText("Start session")
        self.stop_btn.setEnabled(c.session_id is not None)
        if c.session_id is None:
            self.history.refresh()

    def _tick(self) -> None:
        now = time.time()
        self.active.setText(f"⏱ {fmt.duration(self.controller.active_seconds())}")
        for m in self.modules:
            m.refresh(now)

    def _set_on_top(self, on: bool) -> None:
        self.ctx.settings.section("ui")["always_on_top"] = on
        self.ctx.settings.save()
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if visible:
            self.show()

    def closeEvent(self, e) -> None:
        self.controller.stop()
        self.ctx.settings.save()
        super().closeEvent(e)
