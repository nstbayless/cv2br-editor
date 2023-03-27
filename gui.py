import sys
from PySide6.QtWidgets import \
    QApplication, QMainWindow, QPushButton, QLabel, \
    QToolBar
from PySide6.QtGui import QAction, QIcon
import functools

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.setWindowTitle("RevEdit")
        self.defineActions()
        self.defineMenus()

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
    
    # load = 0
    # save = 1
    # saveas = 2
    def onFileIO(self, target, save):
        pass


app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()