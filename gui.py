import sys
import rom
import model
from PySide6.QtWidgets import \
    QApplication, QMainWindow, QPushButton, QLabel, \
    QToolBar, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, \
    QComboBox
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import Qt, QAbstractListModel
import functools

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.nes, self.j = model.loadRom("base-us.gb")
        self.sel_level = 1 # plant=1 index
        self.sel_sublevel = {}
        self.sel_screen = {}
        self.qcb_levels = []
        self.qcb_sublevels = []
        self.qcb_screens = []
        self.setWindowTitle("RevEdit")
        self.defineActions()
        self.defineMenus()
        self.defineTabs()
        self.setLevel(1)

    def defineActions(self):
        self.actLoad = QAction("&Open Hack...", self)
        self.actLoad.triggered.connect(functools.partial(self.onFileIO, "hack", 0))
        
        self.actSave = QAction("&Save Hack", self)
        self.actSave.triggered.connect(functools.partial(self.onFileIO, "hack", 1))
        
        self.actSaveAs = QAction("&Save Hack As...", self)
        self.actSaveAs.triggered.connect(functools.partial(self.onFileIO, "hack", 2))
        
    def defineMenus(self):
        menu = self.menuBar()
        
        file_menu = menu.addMenu("&File")
        file_menu.addAction(self.actLoad)
        file_menu.addAction(self.actSave)
        file_menu.addAction(self.actSaveAs)
        
    def defineTabs(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        TAB_LABELS = [
            "Layout", "Screen", "Chunks"
        ]
        TAB_DEFS = [
            self.defineLevelLayTab,
            self.defineScreenTab,
            self.defineChunksTab
        ]
        for i, (label, define) in enumerate(zip(TAB_LABELS, TAB_DEFS)):
            tab = QWidget()
            define(tab)
            self.tabs.addTab(tab, label)
    
    def defineLevelLayTab(self, tab):
        self.defineWidgetLayoutWithLevelDropdown(tab, 1)
    
    def defineScreenTab(self, tab):
        self.defineWidgetLayoutWithLevelDropdown(tab, 2)
        
    def defineChunksTab(self, tab):
        self.defineWidgetLayoutWithLevelDropdown(tab, 0)
        
    # depth=0: level only
    # depth=1: level and sublevel
    # depth=2: level, sublevel, screen
    def defineWidgetLayoutWithLevelDropdown(self, w, depth=0):
        vlay = QVBoxLayout()
        hlay = QHBoxLayout()
        
        vlay.addLayout(hlay)
        
        levelDropdown = QComboBox()
        levelDropdown.addItems(["Plant Castle", "Crystal Castle", "Cloud Castle", "Rock Castle", "Dracula I", "Dracula II", "Dracula III"])
        hlay.addWidget(levelDropdown)
        levelDropdown.currentIndexChanged.connect(self.setLevel)
        self.qcb_levels.append(levelDropdown)
        
        for i in range(1,depth+1):
            dropdown = QComboBox()
            if i == 1:
                dropdown.currentIndexChanged.connect(self.setSublevel)
                self.qcb_sublevels.append(dropdown)
            if i == 2:
                dropdown.currentIndexChanged.connect(self.setScreen)
                self.qcb_screens.append(dropdown)
            hlay.addWidget(dropdown)
        
        w.setLayout(vlay)
        return vlay
        
    def setLevel(self, level):
        sender = self.sender()
        self.sel_level = level+1
        for qcb in self.qcb_levels:
            if qcb != sender:
                qcb.blockSignals(True)
                qcb.setCurrentIndex(level)
                qcb.blockSignals(False)
        
        self.setSublevel(self.sel_sublevel.get(self.sel_level, 0), True)
    
    def setSublevel(self, sublevel, levelChanged=False):
        sender = self.sender()
        self.sel_sublevel[self.sel_level] = sublevel
        sublevels = [f"Sublevel {i+1}" for i, sl in enumerate(self.j.levels[self.sel_level].sublevels)]
        for qcb in self.qcb_sublevels:
            if qcb != sender:
                qcb.blockSignals(True)
                if levelChanged:
                    qcb.clear()
                    qcb.addItems(sublevels)
                qcb.setCurrentIndex(sublevel)
                qcb.blockSignals(False)
        
        self.setScreen(self.sel_screen.get((self.sel_level, self.sel_sublevel[self.sel_level]), 0), True)
        
    def setScreen(self, screen, sublevelChanged=False):
        sender = self.sender()
        self.sel_screen[(self.sel_level, self.sel_sublevel[self.sel_level])] = screen
        screens = [f"Screen ${i:02X}" for i, sc in enumerate(self.j.levels[self.sel_level].sublevels[self.sel_sublevel[self.sel_level]].screens)]
        for qcb in self.qcb_screens:
            if qcb != sender:
                qcb.blockSignals(True)
                if sublevelChanged:
                    qcb.clear()
                    qcb.addItems(screens)
                qcb.setCurrentIndex(screen)
                qcb.blockSignals(False)
    
    # load = 0
    # save = 1
    # saveas = 2
    def onFileIO(self, target, save):
        pass
        


app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()