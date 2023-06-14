import sys
import rom
import model
import math
from PySide6.QtWidgets import \
    QApplication, QMainWindow, QPushButton, QLabel, \
    QToolBar, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, \
    QComboBox, QGridLayout, QScrollArea, QListWidget, QListWidgetItem, \
    QAbstractItemView, QSpinBox, QRadioButton, QButtonGroup, QPushButton, \
    QCheckBox, QFrame, QStyle, QFileDialog, QMessageBox, QDialog, QLineEdit
from PySide6.QtGui import QColor, QAction, QIcon, QPainter, QPen, QFont, QFontMetrics, QImage, QKeySequence, QPolygon
from PySide6.QtCore import Qt, QAbstractListModel, QSize, QRect, QEvent, Slot, QPoint, QTimer, Signal
import functools
import copy
import signal
import time
import threading
import os
import glob
import json
import tempfile
import subprocess
import re
import shutil

try:
    # (incantation)
    from ctypes import windll  # Only exists on Windows.
    myappid = 'Rev.Ed.It.0'
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass

APPNAME_SMALL = f"RevEdit"
APPNAME = f"{APPNAME_SMALL} {model.VERSION_NAME}"
IO_OPEN = 0
IO_SAVE = 1
IO_SAVEAS = 2

TAB_COMBO_LEVEL = 0
TAB_COMBO_SUBLEVEL = 1
TAB_COMBO_SCREEN = 2
TAB_COMBO_SPRITE = 3

DEFAULT_EMUPATH = ""
# find an emulator

for emubase in ["bgb", "sameboy"]: # TODO: add some more, but make sure to check the command actually works verbatim! retroarch requires -L, for example.
    for emu in [emubase, f"{emubase}.exe"]:
        if shutil.which(emu):
            DEFAULT_EMUPATH = emu
            print("detected default emulator:", DEFAULT_EMUPATH)
            break

guipath = "."
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle, the PyInstaller bootloader
    # extends the sys module by a flag frozen=True and sets the app 
    # path into variable _MEIPASS'.
    guipath = sys._MEIPASS
else:
    guipath = os.path.dirname(os.path.abspath(__file__))


# allows PyQt to close with ctrl+C
signal.signal(signal.SIGINT, signal.SIG_DFL)

def split_unquoted(text):
    # This function implemented by ChatGPT
    # Split text by spaces, but not those that are inside quotes
    # Use negative lookbehind and lookahead assertions to split on spaces
    # that are not inside quotes
    return re.split(r'(?<!\\)\s+(?=(?:[^"]*"[^"]*")*[^"]*$)', text)

def plural(i, singular, plural=None):
    if plural is None:
        plural = singular + 's'
    return singular if i == 1 else plural

# sets value in list
def lset(l, i, v):
    l[i] = v
    
CATS = ["misc", "enemies", "items"]
SCREENSCROLLS = {
    "Empty": 0x0,
    "Free Scrolling": 0x8, 
    "Enclosed": 0xB,
    "Start": 0xA,
    "End": 0x9,
    "Top": 0xA,
    "Bottom": 0x9,
    "Left": 0xA,
    "Right": 0x9
}
SCREENSCROLLNAMES_H = ["Free Scrolling", "Enclosed", "Left", "Right"]
SCREENSCROLLNAMES_V = ["Free Scrolling", "Enclosed", "Top", "Bottom"]

class FilePathSelector(QWidget):
    # This class implemented by ChatGPT
    valueChanged = Signal(str)
    
    def __init__(self, value="", parent=None, label="Path:"):
        super().__init__(parent)

        self._path = value

        self._path_label = QLabel(label)
        self._path_edit = QLineEdit(self._path)
        self._path_browse_button = QPushButton("Browse...")
        self._path_browse_button.clicked.connect(self._on_browse_button_clicked)

        layout = QHBoxLayout()
        layout.addWidget(self._path_label)
        layout.addWidget(self._path_edit)
        layout.addWidget(self._path_browse_button)

        self.setLayout(layout)

        self._path_edit.textChanged.connect(self._on_text_changed)

    @property
    def path(self):
        return self._path

    def _on_text_changed(self, text):
        self._path = text
        self.valueChanged.emit(self._path)

    def _on_browse_button_clicked(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_dialog = QFileDialog(self, "Select Emulator", options=options)
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if len(selected_files) > 0:
                self._path_edit.setText(selected_files[0])

class List2DHelper:
    def __init__(self, getData, offset):
        self.getData = getData
        self.offset = offset
    
    def __getitem__(self, index):
        return self.getData()[self.offset+index]
    
    def __setitem__(self, index, value):
        self.getData()[self.offset+index] = value

class List2D:
    def __init__(self, getData, width):
        self.getData = getData
        self.width = width
    
    def __getitem__(self, index):
        return List2DHelper(self.getData, index*self.width)

class UsageBar(QWidget):
    def __init__(self, label=None, shortname=None):
        super().__init__()
        self.used = None
        self.max = None
        self.label = label
        self.shortname = shortname
        self.start = None
        self.end = None
        self.subranges = []
        self.setMinimumHeight(15)
        self.setMaximumHeight(40)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMouseTracking(True)
    
    def getSubrangeColor(self, i, brightness=0.4, alpha=0.5):
        i *= 1.1
        cols = [(math.sin(i + j) + 1) / 2 for j in range(3)]
        cols = [0xFF * brightness + (0xFF * (1-brightness)) * col for col in cols]
        return QColor(*cols, 0xFF * alpha)
        
    def mouseMoveEvent(self, event):
        hoverP = event.position().x() / self.width()
        label = (self.shortname + " ") if self.shortname is not None else ""
        text = f"{label}{self.bank:X}:[${self.start:04X}–${self.end:04X}]"
        for key, subrange in self.subranges.items():
            p0 = (subrange.start - self.start) / self.max
            p1 = (subrange.end - self.start) / self.max
            if hoverP >= p0 and hoverP < p1:
                b = subrange.end - subrange.start
                text += f" | {key} [${subrange.start:04X}–${subrange.end:04X}] = ${b:X} {plural(b, 'byte')}"
                if "units" in self.region and b % self.region.unitdiv == 0:
                    u = b // self.region.unitdiv
                    text += f" ({u} {plural(u, *self.region.units)})"
                break
        self.setToolTip(text)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        
        painter.setPen(Qt.NoPen)
        painter.fillRect(QRect(0, 0, w, h), Qt.black)
        
        nullUsage = self.used is None or self.max is None
        text = "" if not self.label else f"{self.label}: "
        if not nullUsage:
            p = self.used/self.max
            if p > 1:
                color = Qt.red
            else:
                color = QColor(0x30, 0x33, 0xE0)
            painter.fillRect(0, 0, w*p, h, color)
            text += f"{self.used:X}/{self.max:X} ({self.used/self.max*100:2.2f}%)"
        else:
            text += "~"
            pass
        
        # subranges
        for i, (key, subrange) in enumerate(self.subranges.items()):
            color = self.getSubrangeColor(i)
            p0 = (subrange.start - self.start) / self.max
            p1 = (subrange.end - self.start) / self.max
            painter.fillRect(math.floor(w*p0), 0, math.floor(w*p1) - math.floor(w*p0), h, color)
        
        # border
        pen = QPen(Qt.black)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRect(0, 0, w, h))
        
        pen = QPen(Qt.white)
        painter.setPen(pen)
        painter.drawText(QRect(0, 0, w, h), Qt.AlignCenter, text)
        

# Undoable Action
class UAction:
    def __init__(self, do, undo, restorecontext=None, refreshcontext=None):
        self.type = type
        self.do = do
        self.undo = undo
        self.restorecontext = restorecontext if restorecontext is not None else (lambda app: None)
        self.refreshcontext = refreshcontext if refreshcontext is not None else (lambda app: None)
        
class UndoBuffer:
    def __init__(self, app, cb=None):
        self.idx = 0
        self.buff = []
        self.app = app
        self.max = 1023
        if cb:
            self.cb = cb
        else:
            cb = lambda kind: None
    
    def undo(self):
        self.idx -= 1
        if self.idx < 0:
            self.idx = 0
        else:
            ua = self.buff[self.idx]
            ua.restorecontext(self.app)
            ua.undo(self.app)
            ua.refreshcontext(self.app)
        self.cb("undo")
        
    def redo(self):
        self.idx += 1
        if self.idx > len(self.buff):
            self.idx = len(self.buff)
        else:
            ua = self.buff[self.idx-1]
            ua.restorecontext(self.app)
            ua.do(self.app)
            ua.refreshcontext(self.app)
        self.cb("redo")
    
    def clear(self):
        self.idx = 0
        self.buff = []

    def push(self, do, undo, restorecontext=None, refreshcontext=None):
        self.buff = self.buff[:self.idx]
        self.idx += 1
        self.buff.append(UAction(do, undo, restorecontext, refreshcontext))
        
        # maximum size
        if self.idx >= self.max:
            self.idx -= 1
            self.buff[:1] = []
            
        self.buff[-1].do(self.app)
        self.buff[-1].refreshcontext(self.app)
        self.cb("push")

class VRam:
    def __init__(self, j, nes):
        self.j = j
        self.nes = nes
        self.tileset = [QImage(QSize(8, 8), QImage.Format_RGB32) for i in range(0x200)]
        self.spritetileset = [[QImage(QSize(8, 16), QImage.Format_ARGB32) for i in range(0x200)] for flip in range(4)]
        self.defimg = QImage(QSize(8, 8), QImage.Format_RGB32)
        self.defimg.fill(QColor(0xff, 0x00, 0xff))
        self.cached_vram_descriptor = None
        
    def getVramBGTile(self, tileidx):
        if tileidx > 0x80:
            return self.tileset[tileidx]
        return self.tileset[0x100 + tileidx]
    
    def getVramSpriteTile(self, tileidx, flip=0):
        return self.spritetileset[flip][tileidx]
        
    def loadVramTile(self, destaddr, srcaddr, srcbank, loadSprites):
        # create an 8x8 QImage with Format_RGB32
        if loadSprites:
            aimage = [QImage(QSize(8, 16), QImage.Format_ARGB32) for i in range(4)]
        else:
            image = QImage(QSize(8, 8), QImage.Format_RGB32)
        
        destaddr -= 0x8000
        destaddr //= 0x10
        
        def readbyte(srcbank, addr):
            return self.nes[0x4000 * srcbank + (addr)%0x4000]

        for y in range(16):
            b1 = readbyte(srcbank, srcaddr + y*2)
            b2 = readbyte(srcbank, srcaddr + y*2 + 1)
            for x in range(8):
                c1 = (b1 >> (7-x)) & 1
                c2 = (b2 >> (7-x)) & 1
                if y < 8 and not loadSprites:
                    image.setPixelColor(x, y, QColor(*rom.PALETTE[c1 + c2*2]))
                elif loadSprites:
                    for i in range(4):
                        _x = x if (i % 2 == 0) else 7-x
                        _y = y if (i // 2 == 0) else 15-y
                        aimage[i].setPixelColor(_x, _y, QColor(*rom.PALETTE[c1 + c2*2], 0 if c1 + c2*2 == 0 else 255))
        
        if loadSprites:
            for i in range(4):
                self.spritetileset[i][destaddr] = aimage[i]
        else:
            self.tileset[destaddr] = image
        
    def getDefaultImage(self):
        return self.defimg
        
    def clearVram(self):
        for i in range(0x200):
            self.tileset[i] = self.getDefaultImage()
            for flip in range(4):
                self.spritetileset[flip][i] = self.getDefaultImage()
        
    def loadVramFromBuffer(self, buff, loadSprites):
        for entry in buff:
            destaddr = entry.destaddr
            srcaddr = entry.srcaddr
            for i in range(entry.destlen // 0x10):
                self.loadVramTile(destaddr + i * 0x10, srcaddr + i * 0x10, entry.srcbank, loadSprites)
        
    def loadVramForStage(self, level, sublevel=0, **kwargs):
        loadSprites = kwargs.get("load_sprites", False)
        desc = f"l{level}s{sublevel}{'-s' if loadSprites else ''}"
        if self.cached_vram_descriptor == desc:
            return
        self.cached_vram_descriptor = desc
        self.clearVram()
        
        # not sure what loads tile 0x100 to white (maybe nothing)
        # but it should be white.
        self.tileset[0x100] = QImage(QSize(8, 8), QImage.Format_RGB32)
        self.tileset[0x100].fill(Qt.white)
        
        self.loadVramFromBuffer(self.j.tileset_common, loadSprites)
        self.loadVramFromBuffer(self.j.levels[level].tileset, loadSprites)
        for jsl in self.j.levels[level].sublevels[1:sublevel+1]:
            for tilePatch in jsl.tilePatches:
                for i in range(tilePatch.count):
                    self.loadVramTile(tilePatch.dst + 0x10 * i, tilePatch.source + i * 0x10, tilePatch.bank, loadSprites)

def paintTile(painter, vram, x, y, tileidx, scale):
    x2 = x + scale * 8
    y2 = y + scale * 8
    if tileidx >= 0:
        img = vram.getVramBGTile(tileidx)
    else:
        img = vram.getDefaultImage()
    f = math.floor
    painter.drawImage(QRect(f(x), f(y), f(x2 - x + 1), f(y2 - y + 1)), img)

class NonScrollableComboBox(QComboBox):
    def wheelEvent(self, *args, **kwargs):
        return

class HotkeySpinBox(QSpinBox):
    def __init__(self, app):
        super().__init__()
        self.app = app
        # Install an event filter on the spin box
        self.installEventFilter(self)
        
    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                newvalue = min(self.value() + 8, self.maximum())
            else:
                newvalue = max(self.value() - 8, self.minimum())
            if newvalue != self.value():
                self.setValue(newvalue)
        else:
            super().wheelEvent(event)
    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyRelease:
            if event.key() == Qt.Key_Z and event.modifiers() == Qt.ControlModifier:
                self.app.undo()

            if event.key() == Qt.Key_Z and event.modifiers() == Qt.ControlModifier | Qt.ShiftModifier:
                self.app.redo()
                
            if event.key() == Qt.Key_Y and event.modifiers() == Qt.ControlModifier:
                self.app.redo()
        
        # Call the base class's eventFilter() method to handle the event
        return super().eventFilter(obj, event)

class ChunkWidget(QWidget):
    width=8*4
    def __init__(self, parent=None, scale=4, fixed=False):
        super().__init__(parent)
        self.app = parent
        self.scale = scale
        if fixed:
            self.setFixedWidth(scale * 8 * 4)
            self.setFixedHeight(scale * 8 * 4)
        self.id = 0
        
    def getChunk(self):
        level, sublevel, screen = self.app.getLevel()
        chunks = model.getLevelChunks(self.app.j, level)
        if self.id is None or self.id >= len(chunks):
            return None
        else:
            return chunks[self.id]
    
    def paintEvent(self, event):
        painter = QPainter(self)
        level, sublevel, screen = self.app.getLevel()
        vram = self.app.vram
        vram.loadVramForStage(level, sublevel)
        chunks = model.getLevelChunks(self.app.j, level)
        if self.id >= len(chunks):
            painter.fillRect(QRect(0, 0, 8*4*self.scale, 8*4*self.scale), QColor(128, 128, 128))
        else:
            chunk = chunks[self.id]
            for ci in range(4):
                for cj in range(4):
                    tileidx = chunk[ci + cj * 4]
                    x = ci * 8 * self.scale
                    y = cj * 8 * self.scale
                    paintTile(painter, vram, x, y, tileidx, self.scale)

class ChunkEdit(ChunkWidget):
    width=8*4
    def __init__(self, parent=None, restoreTab=None, scale=5):
        super().__init__(parent, scale, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMouseTracking(True)
        self.hoverPos = None
        self.gridSpacing = 8
        self.restoreTab = restoreTab
    
    def mouseMoveEvent(self, event):
        prevHoverPos = self.hoverPos
        self.hoverPos = (math.floor(event.position().x() / self.gridSpacing / self.scale), math.floor(event.position().y() / self.gridSpacing / self.scale))
        if self.hoverPos[0] < 0 or self.hoverPos[0] * self.gridSpacing >= 4*8:
            self.hoverPos = None
        elif self.hoverPos[1] < 0 or self.hoverPos[1] * self.gridSpacing >= 4*8:
            self.hoverPos = None
        if prevHoverPos != self.hoverPos:
            self.update()
            self.app.updateChunkLabel()
        
    def leaveEvent(self, event):
        self.hoverPos = None
        self.update()
        
    def getRestoreContext(self):
        level, sublevel, screen = self.app.getLevel()
        chidx = self.app.chunkSelected.get(level, None)
        def restore(app):
            assert app.sender() not in app.qcb_levels + app.qcb_sublevels + app.qcb_screens
            app.setLevel(level-1)
            app.setChunk(chidx)
            if self.restoreTab is not None:
                app.tabs.setCurrentWidget(self.restoreTab)
                
        return restore
        
    def editable(self):
        level = self.app.sel_level
        chidx = self.app.chunkSelected.get(level, None)
        chunks = model.getLevelChunks(self.app.j, level)
        if self.app.j.levels[level].get("chunks", None) is None:
            return False
        return chidx is not None and chidx < len(chunks) and chidx > 0
            
    def mousePressEvent(self, event):
        self.mouseMoveEvent(event)
        level = self.app.sel_level
        tidx = self.app.tileSelected.get(level, None) or 0
        chidx = self.app.chunkSelected.get(level, None)
        chunks = model.getLevelChunks(self.app.j, level)
        if self.hoverPos is not None and chidx is not None:
            chunk = chunks[chidx]
            i, j = self.hoverPos
            idx = j*4 + i
            prev = chunk[idx]
            if self.editable() and event.button() == Qt.LeftButton and chidx and tidx is not None:
                self.app.undoBuffer.push(
                    lambda app: lset(model.getLevelChunks(app.j, level)[chidx], idx, tidx),
                    lambda app: lset(model.getLevelChunks(app.j, level)[chidx], idx, prev),
                    self.getRestoreContext()
                )
            elif event.button() == Qt.RightButton:
                self.app.setTile(None)
            elif event.button() == Qt.MiddleButton:
                self.app.setTile(chunk[idx])
        self.update()
    
    def paintEvent(self, event):
        level, sublevel, screen = self.app.getLevel()
        self.id = self.app.chunkSelected.get(level, None) or 0
        super().paintEvent(event)
        painter = QPainter(self)
        if self.hoverPos is not None and self.app.tileSelected.get(level, None) is not None and self.editable():
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)
            paintTile(painter, self.app.vram, self.hoverPos[0]*8*self.scale, self.hoverPos[1]*8*self.scale, self.app.tileSelected[level], self.scale)
            painter.fillRect(QRect(8*self.hoverPos[0]*self.scale, 8*self.hoverPos[1]*self.scale, 8*self.scale, 8*self.scale), QColor(128, 128, 255))
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        
        # border
        pen = QPen(Qt.black)
        pen.setWidth(2)
        painter.drawRect(QRect(0, 0, self.scale * 8 * 4-2, self.scale * 8 * 4-2))

class ChunkSelectorWidget(ChunkWidget):
    width=8*4
    def __init__(self, id, parent=None, scale=3):
        super().__init__(parent, scale, True)
        self.id = id
    
    def isSelected(self):
        level, sublevel, screen = self.app.getLevel()
        return self.app.chunkSelected.get(level, None) == self.id
        
    def mousePressEvent(self, event):
        level, sublevel, screen = self.app.getLevel()
        chunks = model.getLevelChunks(self.app.j, level)
        if self.id < len(chunks):
            self.app.setChunk(self.id)
    
    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)
        if self.app.chunkEdit is not None:
            self.app.tabs.setCurrentWidget(self.app.chunkEdit.restoreTab)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isSelected():
            painter = QPainter(self)
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)
            painter.fillRect(QRect(0, 0, 8*4*self.scale, 8*4*self.scale), QColor(128, 128, 255))
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

class TileSelectorWidget(QWidget):
    width = 8
    def __init__(self, id, parent=None, scale=4):
        super().__init__(parent)
        self.app = parent
        self.id = id
        self.scale = scale
        self.setFixedSize(scale * 8, scale * 8)
    
    def isSelected(self):
        level, sublevel, screen = self.app.getLevel()
        return self.app.tileSelected.get(level, None) == self.id
        
    def mousePressEvent(self, event):
        level, sublevel, screen = self.app.getLevel()
        if self.id < 0x100:
            self.app.setTile(self.id)
            
    def paintEvent(self, event):
        painter = QPainter(self)
        paintTile(painter, self.app.vram, 0, 0, self.id, self.scale)
        if self.isSelected():
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)
            painter.fillRect(QRect(0, 0, 8*self.scale, 8*self.scale), QColor(128, 128, 255))
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

class SelectorPanel(QScrollArea):
    def __init__(self, parent, type=ChunkSelectorWidget, scale=2, w=4, h=0x40, **kwargs):
        super().__init__()
        self.idxremap = kwargs.get("idxremap", lambda x: x)
        self.app = parent
        self.scale = scale
        self.w = w
        self.h = h
        self.type = type
        self.margin = 4
        self.spacing = 3
        self.widgets = dict()
        grid_layout = QGridLayout()
        grid_layout.setSpacing(self.spacing)
        grid_layout.setContentsMargins(self.margin, self.margin, self.margin, self.margin)
        for j in range(self.h):
            for i in range(self.w):
                id = self.idxremap(i + j * self.w)
                self.widgets[id] = type(id, self.app, self.scale)
                grid_layout.addWidget(self.widgets[id], j, i)
        
        scroll_area_widget = QWidget()
        scroll_area_widget.setLayout(grid_layout)
        
        self.setWidget(scroll_area_widget)
        self.setWidgetResizable(True)
        # we add 2 here because it inexplicably has a horizontal scroll if we don't
        self.setFixedWidth(scroll_area_widget.minimumSizeHint().width() + self.verticalScrollBar().sizeHint().width() + 2)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

class SpriteView(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.app = parent
        self.bgcols = [QColor(250, 100, 250), QColor(190, 80, 220)]
    
    def _applySpritePatch(self, patch):
        idx = self.app.sel_sprite
        if idx in range(patch.startidx, patch.startidx + len(patch.sprites)):
            sprite = patch.sprites[idx - patch.startidx]
            self.tiles = copy.copy(sprite.tiles)
            self.srcAddr = sprite.srcAddr
        
    def getSpriteTiles(self):
        self.tiles = []
        level, sublevel, screen = self.app.getLevel()
        self.sprite = None
        
        # TODO: cache
        
        self._applySpritePatch(self.app.j.globalSpritePatches.init)
        for sl in range(0, sublevel+1):
            jsl = self.app.j.levels[level].sublevels[sl]
            if "spritePatch" in jsl:
                self._applySpritePatch(jsl.spritePatch)
        
    def _getbbox(self):
        return \
            min([tile.xoff for tile in self.tiles] + [-8]),   \
            min([tile.yoff for tile in self.tiles] + [-8]),   \
            max([tile.xoff+8 for tile in self.tiles] + [8]), \
            max([tile.yoff+16 for tile in self.tiles] + [8]),
        
    def paintEvent(self, event):
        self.getSpriteTiles()
        bbx0, bby0, bbx1, bby1 = self._getbbox()
        bbx0 -= 4
        bby0 -= 4
        bbx1 += 4
        bby1 += 4
        scale = 4
        
        level, sublevel, screen = self.app.getLevel()
        self.app.vram.loadVramForStage(level, sublevel, load_sprites=True)
        
        painter = QPainter(self)
        painter.fillRect(QRect(0, 0, -bbx0*scale, -bby0*scale), self.bgcols[0])
        painter.fillRect(QRect(0, -bby0*scale, -bbx0*scale, bby1*scale), self.bgcols[1])
        painter.fillRect(QRect(-bbx0*scale, -bby0*scale, bbx1*scale, bby1*scale), self.bgcols[0])
        painter.fillRect(QRect(-bbx0*scale, 0, bbx1*scale, -bby0*scale), self.bgcols[1])
        
        for tile in self.tiles:
            flags = 0 if not "flags" in tile else tile.flags
            img = self.app.vram.getVramSpriteTile(tile.tidx, (flags >> 5) & 3)
            painter.drawImage(
                QRect(scale*(tile.xoff-bbx0), scale*(tile.yoff-bby0), 8*scale, 16*scale),
                img
            )

class ScreenWidget(QWidget):
    def __init__(self, parent, restoreTab, specialScreens=False, entityAlpha=0.9, gridSpacing=8*4):
        super().__init__(parent)
        self.specialScreens=specialScreens
        self.restoreTab = restoreTab
        self.app = parent
        self.hoverPos = None
        self.gridSpacing = gridSpacing
        self.entityAlpha = entityAlpha
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMouseTracking(True)
        
    def getRestoreContext(self):
        level, sublevel, screen = self.app.getLevel()
        def restore(app):
            assert app.sender() not in app.qcb_levels + app.qcb_sublevels + app.qcb_screens
            app.setLevel(level-1)
            app.setSublevel(sublevel)
            app.setScreen(screen)
            app.tabs.setCurrentWidget(self.restoreTab)
        
        return restore
    
    def resizeEvent(self, event):
        self.update()
        
    def leaveEvent(self, event):
        self.hoverPos = None
        self.update()
        
    def mouseMoveEvent(self, event):
        prevHoverPos = self.hoverPos
        self.hoverPos = (math.floor(event.position().x() / self.gridSpacing / self.getScale()), math.floor(event.position().y() / self.gridSpacing / self.getScale()))
        if self.hoverPos[0] < 0 or self.hoverPos[0] * self.gridSpacing >= 4*8*5:
            self.hoverPos = None
        elif self.hoverPos[1] < 0 or self.hoverPos[1] * self.gridSpacing >= 4*8*4:
            self.hoverPos = None
        if prevHoverPos != self.hoverPos:
            self.update()
        
    def getScale(self):
        return min(self.width() / (20*8), self.height() / (16*8))
        
    def paintEntities(self, painter):
        level, sublevel, screen = self.app.getLevel()
        jl, jsl, js = self.app.getLevelJ()
        font = QFont(['Helvetica', 'Arial'], 16)
        fm = QFontMetrics(font)
        a = int(256 * self.entityAlpha)
        padding = 2
        scale = self.getScale()
        for icat, cat in enumerate(CATS):
            for ent in js.get(cat, []):
                name = rom.getEntityName(ent.type)
                painter.setFont(font)
                
                # backbox
                rect = fm.boundingRect(name)
                rect.adjust(-padding, -padding, padding, padding)
                rect.translate(ent.x * scale - rect.x(), ent.y * scale - rect.y())
                painter.setPen(Qt.NoPen)
                painter.fillRect(rect, QColor(0, 0, 0, a*2//3))
                
                # text
                painter.setPen(QColor(*map(lambda x: (x + 255)//2, rom.ENTPALETTES[icat]), a))
                painter.drawText(rect, Qt.AlignCenter, name)
        painter.setPen(QColor(Qt.black))
        
    def paintEvent(self, event):
        squareSize = self.getScale()
        
        painter = QPainter(self)
        #painter.setRenderHint(QPainter.Antialiasing)
        
        level, sublevel, screen = self.app.getLevel()
        data = self.app.getSpecialScreenData(self.specialScreens)
        chunks = model.getLevelChunks(self.app.j, level)
        
        vram = self.app.vram
        vram.loadVramForStage(level, sublevel)
        
        for i in range(5):
            for j in range(4):
                chidx = data[j][i]
                chunk = chunks[chidx] if chidx < len(chunks) else [-1] * 0x10
                for ci in range(4):
                    for cj in range(4):
                        tileidx = chunk[ci + cj * 4]
                        x = (i * 4 + ci) * 8 * squareSize
                        y = (j * 4 + cj) * 8 * squareSize
                        paintTile(painter, vram, x, y, tileidx, squareSize)
        
        if self.entityAlpha > 0:
            self.paintEntities(painter)

class ScreenTileWidget(ScreenWidget):
    def __init__(self, parent, restoreTab, specialScreens=True):
        super().__init__(parent, restoreTab, specialScreens, 0)
    
    def mousePressEvent(self, event):
        self.mouseMoveEvent(event)
        chidx = self.app.chunkSelected.get(self.app.sel_level, None)
        level, sublevel, screen = self.app.getLevel()
        jl, jsl, js = self.app.getLevelJ()
        data = self.app.getSpecialScreenData(self.specialScreens)
        if self.hoverPos is not None:
            i, j = self.hoverPos
            prev = data[j][i]
            if event.button() == Qt.LeftButton and chidx is not None:
                if prev != chidx:
                    if data == js.data:
                        self.app.undoBuffer.push(
                            lambda app: lset(app.j.levels[level].sublevels[sublevel].screens[screen].data[j], i, chidx),
                            lambda app: lset(app.j.levels[level].sublevels[sublevel].screens[screen].data[j], i, prev),
                            self.getRestoreContext()
                        )
                    else:
                        # TODO: undo buffer for special screens
                        # (need to modify restore context)
                        print("WARNING: undo buffer support not available for special screens.")
                        data[j][i] = chidx
                        pass
            elif event.button() == Qt.RightButton:
                self.app.setChunk(None)
            elif event.button() == Qt.MiddleButton:
                self.app.setChunk(data[j][i])
        self.update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        squareSize = self.getScale()
        
        level, sublevel, screen = self.app.getLevel()
        chunks = model.getLevelChunks(self.app.j, level)
        
        chidx = self.app.chunkSelected.get(self.app.sel_level, None)
        if self.hoverPos is not None and chidx is not None:
            chunk = chunks[chidx] if chidx < len(chunks) else [-1] * 0x10
            i, j = self.hoverPos
            for ci in range(4):
                for cj in range(4):
                    tileidx = chunk[ci + cj * 4]
                    x = (i * 4 + ci) * 8 * squareSize
                    y = (j * 4 + cj) * 8 * squareSize
                    paintTile(painter, self.app.vram, x, y, tileidx, squareSize)
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)
            painter.fillRect(
                QRect(math.floor(i * 4 * 8 * squareSize), math.floor(j * 4 * 8 * squareSize+1), 4 * 8 * squareSize, 4 * 8 * squareSize+1),
                QColor(128, 128, 255)
            )
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

class RoomLayWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.gridSize = 16  # the number of squares in each row/column
        self.app = parent
        
    def resizeEvent(self, event):
        self.update()
        
    def mouseDoubleClickEvent(self, event):
        squareSize = self.getSquareSize()
        x = math.floor(event.position().x() / squareSize)
        y = math.floor(event.position().y() / squareSize)
        if x >= 0 and y >= 0 and x < 0x10 and y < 0x10:
            jl, jsl, js = self.app.getLevelJ()
            if jsl.layout[x][y] > 0:
                screen = jsl.layout[x][y] & 0x0f
                self.app.setScreen(screen)
                gotoTab = self.app.lastScreenTab or self.app.screenTabs[0]
                self.app.tabs.setCurrentWidget(gotoTab)
    
    def mousePressEvent(self, event):
        squareSize = self.getSquareSize()
        x = math.floor(event.position().x() / squareSize)
        y = math.floor(event.position().y() / squareSize)
        if x >= 0 and y >= 0 and x < 0x10 and y < 0x10:
            jl, jsl, js = self.app.getLevelJ()
            if jsl.layout[x][y] > 0:
                screen = jsl.layout[x][y] & 0x0f
                self.app.setScreen(screen)
            
            self.app.setScreenCoords(x, y)

    def getSquareSize(self):
        return min(self.width(), self.height()) // self.gridSize

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(Qt.black)
        pen.setWidth(2)
        
        bgpen = QPen(QColor(0, 0, 0, 40))
        bgpen.setWidth(1)

        font = QFont(['Helvetica', 'Arial'], 8)
        level, sublevel, screen = self.app.getLevel()
        screenCoords = self.app.sel_screencoords.get((level, sublevel), None)
        jsl = self.app.j.levels[level].sublevels[sublevel]
        startx = jsl.startx
        starty = jsl.starty
        vertical = jsl.vertical == 1
        jlayout = jsl.layout
        
        squareSize = self.getSquareSize()
        
        exits = []
        enterable = model.getEnterabilityLayout(self.app.j, level, sublevel)

        for i in range(self.gridSize):
            for j in range(self.gridSize):
                l = jlayout[i][j]
                for exit in model.getScreenExitDoor(self.app.j, level, sublevel, l & 0x0F):
                    exits.append((i, j, exit))
                text = f"{l:02X}"
                x = i * squareSize
                y = j * squareSize
                x2 = x + squareSize
                y2 = y + squareSize
                bg = False
                if l == 0:
                    if (i, j) == screenCoords:
                        painter.setBrush(QColor(100, 100, 180, 200))
                    else:
                        painter.setBrush(QColor(0, 0, 0, 50))
                    painter.setPen(Qt.NoPen)
                    painter.drawRect(x, y, squareSize, squareSize)
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(bgpen)
                    bg = True
                else:
                    painter.setPen(Qt.NoPen)
                    if (i, j) == screenCoords:
                        painter.setBrush(QColor(0x40, 0x40, 0xff, 50))
                    else:
                        painter.setBrush(Qt.white)
                    painter.drawRect(x, y, squareSize, squareSize)
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(pen)
                if bg:
                    painter.drawLine(x, y, x2, y)
                    painter.drawLine(x, y, x, y2)
                elif vertical:
                    painter.drawLine(x, y, x, y2)
                    painter.drawLine(x2, y, x2, y2)
                    if (l & 0x20):
                        painter.drawLine(x, y, x2, y)
                    if (l & 0x10):
                        painter.drawLine(x, y2, x2, y2)
                else:
                    painter.drawLine(x, y, x2, y)
                    painter.drawLine(x, y2, x2, y2)
                    if (l & 0x20):
                        painter.drawLine(x, y, x, y2)
                    if (l & 0x10):
                        painter.drawLine(x2, y, x2, y2)
                
                painter.setPen(Qt.NoPen)
                
                if enterable[i][j]:
                    h = 5
                    painter.fillRect(x, y, x2-x, h, QColor(100, 0xc0, 100, 0x80))
                
                if i == startx and j == starty:
                    painter.setBrush(QColor(100, 0xc0, 100))
                    if jlayout[i][j] & 0xF0 not in [0xB0, 0xA0, 0x90]:
                        painter.setBrush(QColor(0xC0, 90, 90))
                    margin=4
                    painter.drawEllipse(x + margin, y+ margin, squareSize-2*margin, squareSize-2*margin)
                    
                
                if not bg:
                    painter.setPen(Qt.black)
                    painter.drawText(x + squareSize/2 - 6, y + squareSize/2 + 4, text)
        
        for i, j, dir in exits:
            x = squareSize * ((i + 1) if dir == 1 else i)
            x -= 0.1 * dir * squareSize
            y = squareSize * j
            triangle = QPolygon([QPoint(x, y), QPoint(x, y+squareSize), QPoint(x+squareSize*0.9*dir, y+squareSize/2)])
            painter.setPen(Qt.NoPen)
            if i == 0 and dir == -1 or i == 15 and dir == 1 or jlayout[i+dir][j] > 0:
                painter.setBrush(QColor(0xB0, 0x40, 0x40, 0xC0))
            else:
                painter.setBrush(QColor(0x40, 0x40, 0xA0, 0xC0))
            painter.drawPolygon(triangle)


class MainWindow(QMainWindow):
    def __init__(self, rom):
        super(MainWindow, self).__init__()
        self.rom, self.j = model.loadRom(rom)
        model.addEmptyScreens(self.j)
        self.undoBuffer = UndoBuffer(self, self.onUndoBuffer)
        self.ioStore = dict()
        self.vram = VRam(self.j, self.rom)
        self.config = {
            "emuPath": DEFAULT_EMUPATH
        }
        self.sel_level = 1 # plant=1 index
        self.sel_sublevel = {}
        self.sel_screen = {}
        self.sel_special_screen = {}
        self.sel_screencoords = {}
        self.qcb_levels = []
        self.qcb_sublevels = []
        self.qcb_screens = []
        self.qcb_sprites = []
        self.screenGrids = []
        self.screenTabs = []
        self.lastScreenTab = None
        self.chunkSelected = {}
        self.tileSelected = {}
        self.entitySelected = {} # maps (level, sublevel, screen) -> (cat, index)
        self.chunkSelectors = []
        self.tileSelectors = []
        self.chunkEdit = None
        self.entityTab = None
        self.entitySelector = None
        self.entpropwidgets = []
        self.emptyIcon = QIcon()
        self.errorIcon = QIcon.fromTheme("dialog-error")
        
        # TODO: use pyside6-rcc to build the resources
        self.catIcons = {}
        try:
            self.setWindowIcon(QIcon(os.path.join(guipath, "etc/icon.png")))
            for cat in CATS:
                self.catIcons[cat] = QIcon(os.path.join(f"etc/ent{cat}.png"))
        except:
            for cat in CATS:
                self.catIcons[cat] = self.errorIcon
            
        
        self.setWindowTitle(APPNAME)
        self.defineActions()
        self.defineMenus()
        self.defineTabs()
        self.setGeometry(50, 50, 850, 550)
        self.sel_sprite = 7
        self.setLevel(3)
        self.setSprite(self.sel_sprite, True) # wall meat
    
    def getLevel(self):
        return self.sel_level, self.sel_sublevel.get(self.sel_level, 0), self.sel_screen.get((self.sel_level, self.sel_sublevel[self.sel_level]), 0)
    
    def getLevelJ(self):
        level, sublevel, screen = self.getLevel()
        jl = self.j.levels[level]
        jsl = jl.sublevels[sublevel]
        js = jsl.screens[screen]
        return jl, jsl, js
    
    def getSpecialScreenData(self, specScreensOk=True):
        level, sublevel, screen = self.getLevel()
        jl, jsl, js = self.getLevelJ()
        special_screen = self.sel_special_screen.get((level, sublevel), False)
        if specScreensOk:
            if special_screen is not False:
                specscreens = self.getSpecialScreens()
                if special_screen < len(specscreens):
                    return specscreens[special_screen].data
        return js.data

    def defineActions(self):
        self.actLoad = QAction("&Open Hack...", self)
        self.actLoad.triggered.connect(functools.partial(self.onFileIO, "hack", IO_OPEN))
        self.actLoad.setShortcut(QKeySequence("ctrl+o"))
        
        self.actSave = QAction("&Save Hack", self)
        self.actSave.triggered.connect(functools.partial(self.onFileIO, "hack", IO_SAVE))
        self.actSave.setShortcut(QKeySequence("ctrl+s"))
        
        self.actSaveAs = QAction("&Save Hack As...", self)
        self.actSaveAs.triggered.connect(functools.partial(self.onFileIO, "hack", IO_SAVEAS))
        self.actSaveAs.setShortcut(QKeySequence("ctrl+shift+s"))
        
        self.actExport = QAction("&Export ROM...", self)
        self.actExport.triggered.connect(functools.partial(self.onFileIO, "rom", IO_SAVEAS))
        self.actExport.setShortcut(QKeySequence("ctrl+e"))
        
        self.actPlaytest = QAction("&Playtest...", self)
        self.actPlaytest.triggered.connect(self.onPlaytest)
        self.actPlaytest.setShortcut(QKeySequence("ctrl+p"))
        
        self.actAbout = QAction(f"&About {APPNAME_SMALL}", self)
        self.actAbout.triggered.connect(self.onAbout)
        
        self.actUndo = QAction("&Undo", self)
        self.actUndo.triggered.connect(self.undo)
        self.actUndo.setShortcut(QKeySequence("Ctrl+z"))
        
        self.actRedo = QAction("&Redo", self)
        self.actRedo.triggered.connect(self.redo)
        self.actRedo.setShortcut(QKeySequence("ctrl+y"))
        self.actRedo2 = QAction("&Redo", self)
        self.actRedo2.triggered.connect(self.redo)
        self.actRedo2.setShortcut(QKeySequence("ctrl+shift+z"))
        self.addAction(self.actRedo2)
        
        self.actConfigure = QAction("&Configure Emulator", self)
        self.actConfigure.triggered.connect(self.onConfigure)
        
    def defineMenus(self):
        menu = self.menuBar()
        
        file_menu = menu.addMenu("&File")
        file_menu.addAction(self.actLoad)
        file_menu.addAction(self.actSave)
        file_menu.addAction(self.actSaveAs)
        file_menu.addSeparator()
        file_menu.addAction(self.actPlaytest)
        file_menu.addAction(self.actExport)
        
        edit_menu = menu.addMenu("&Edit")
        edit_menu.addAction(self.actUndo)
        edit_menu.addAction(self.actRedo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.actConfigure)
        
        help_menu = menu.addMenu("&Help")
        help_menu.addAction(self.actAbout)
        
    def defineTabs(self):
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.onChangeTab)
        self.setCentralWidget(self.tabs)
        TAB_LABELS = [
            "Layout", "Screen", "Entities", "Chunks", *(["Sprites"] if rom.ROMTYPE in ["jp", "us"] else []), "Usage"
        ]
        TAB_DEFS = [
            self.defineLevelLayTab,
            self.defineScreenTab,
            self.defineEntityTab,
            self.defineChunksTab,
            *([self.defineSpritesTab] if rom.ROMTYPE in ["jp", "us"] else []),
            self.defineUsageTab,
        ]
        for i, (label, define) in enumerate(zip(TAB_LABELS, TAB_DEFS)):
            tab = QWidget()
            define(tab)
            self.tabs.addTab(tab, label)
    
    def defineSpritesTab(self, tab):
        self.spritesTab = tab
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, [TAB_COMBO_LEVEL, TAB_COMBO_SUBLEVEL, TAB_COMBO_SPRITE])
        hlay = QHBoxLayout()
        self.spriteView = SpriteView(self)
        hlay.addWidget(self.spriteView)
        
        self.spriteLabel = QLabel()
        spriteLabelScroll = QScrollArea()
        spriteLabelScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        spriteLabelScroll.setWidgetResizable(True)
        spriteLabelScroll.setWidget(self.spriteLabel)
        spriteLabelScroll.setMaximumWidth(300)
        hlay.addWidget(spriteLabelScroll)
        
        vlay.addLayout(hlay)
    
    def defineLevelLayTab(self, tab):
        self.layTab = tab
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, [TAB_COMBO_LEVEL, TAB_COMBO_SUBLEVEL])
        hlay = QHBoxLayout()
        self.layGrid = RoomLayWidget(self)
        hlay.addWidget(self.layGrid)
        
        TOP_MARGIN = 20
        PROPW = 160
        
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        hlay.addWidget(separator)
        
        # Sublevel Properties
        cvlayw = QWidget()
        cvlay = QVBoxLayout()
        cvlayw.setLayout(cvlay)
        cvlayw.setMaximumWidth(PROPW)
        l = QLabel("Sublevel Properties:")
        l.setMaximumHeight(TOP_MARGIN)
        cvlay.addWidget(l)
        self.sublevelVerticalScrollingCheckbox = QCheckBox("Vertical")
        self.sublevelVerticalScrollingCheckbox.stateChanged.connect(self.setSublevelVertical)
        cvlay.addWidget(self.sublevelVerticalScrollingCheckbox)
        
        self.sublevelStartXBox, chlay = self.addSpinBoxWithLabel("Start X", 0, 15)
        self.sublevelStartXBox.valueChanged.connect(functools.partial(self.setSublevelProp, "startx"))
        cvlay.addLayout(chlay)
        self.sublevelStartYBox, chlay = self.addSpinBoxWithLabel("Start Y", 0, 15)
        self.sublevelStartYBox.valueChanged.connect(functools.partial(self.setSublevelProp, "starty"))
        cvlay.addLayout(chlay)
        
        self.sublevelTimerBox, chlay = self.addSpinBoxWithLabel("Time/10 s", 1, 99)
        self.sublevelTimerBox.valueChanged.connect(functools.partial(self.setSublevelProp, "timer"))
        cvlay.addLayout(chlay)
        
        cvlay.addWidget(QWidget()) # padding
        hlay.addWidget(cvlayw)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        hlay.addWidget(separator)
        
        # Screen Properties
        cvlayw = QWidget()
        cvlay = QVBoxLayout()
        cvlayw.setLayout(cvlay)
        cvlayw.setMaximumWidth(PROPW)
        l = QLabel("Screen Properties:")
        l.setMaximumHeight(TOP_MARGIN)
        cvlay.addWidget(l)
        
        self.screenIDSelector = QComboBox()
        self.screenIDSelector.currentIndexChanged.connect(self.setScreenID)
        cvlay.addWidget(self.screenIDSelector)
        
        def on_button_clicked(id):
            self.setLayoutScreen(0xF0, [0x80, 0xB0, 0xA0, 0x90][id])
        self.layoutScreenScrollButtonGroup, self.layoutScreenScrollButtons, cvlay = \
            self.addRadioButtons(*SCREENSCROLLNAMES_H, layout = lambda: cvlay, cb=on_button_clicked)
            
        self.screenLabel = QLabel()
        self.screenLabel.setMaximumHeight(TOP_MARGIN*3)
        cvlay.addWidget(self.screenLabel)
        
        cvlay.addWidget(QWidget()) # padding
        hlay.addWidget(cvlayw)
        
        self.layWidgets = [self.sublevelVerticalScrollingCheckbox, self.screenIDSelector, self.sublevelStartXBox, self.sublevelStartYBox, self.layoutScreenScrollButtonGroup, *self.layoutScreenScrollButtons]
        
        vlay.addLayout(hlay)
    
    def defineScreenTab(self, tab):
        self.screenGrids.append(ScreenTileWidget(self, tab))
        self.screenTabs.append(tab)
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, [TAB_COMBO_LEVEL, TAB_COMBO_SUBLEVEL, TAB_COMBO_SCREEN])
        self.qcb_screentab_screen = self.qcb_screens[-1]
        hlay = QHBoxLayout()
        hlay.addWidget(self.screenGrids[-1])
        self.chunkSelectors.append(SelectorPanel(self, ChunkSelectorWidget))
        hlay.addWidget(self.chunkSelectors[-1])
        vlay.addLayout(hlay)
        
    def addRadioButtons(self, *labels, **kwargs):
        hlay = kwargs.get("layout", QHBoxLayout)()
        if "label" in kwargs:
            l = QLabel()
            l.setText(kwargs["label"])
            l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            hlay.addWidget(l)
        bg = QButtonGroup()
        buttons = []
        for label in labels:
            buttons.append(QRadioButton(label))
            hlay.addWidget(buttons[-1])
        if "cb" in kwargs:
            for i, button in enumerate(buttons):
                button.clicked.connect(functools.partial(kwargs["cb"], i))
        return bg, buttons, hlay
        
    def addSpinBoxWithLabel(self, label, min, max):
        hlay = QHBoxLayout()
        l = QLabel()
        l.setText(label)
        l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hlay.addWidget(l)
        
        sb = HotkeySpinBox(self)
        sb.setMinimum(min)
        sb.setMaximum(max)
        hlay.addWidget(sb)
        return sb, hlay
    
    def defineEntityTab(self, tab):
        self.screenTabs.append(tab)
        self.entityTab = tab
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, [TAB_COMBO_LEVEL, TAB_COMBO_SUBLEVEL, TAB_COMBO_SCREEN])
        hlay = QHBoxLayout()
        
        self.screenGrids.append(ScreenWidget(self, tab))
        hlay.addWidget(self.screenGrids[-1])
        
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        hlay.addWidget(separator)
        
        cvlay = QVBoxLayout()
        
        self.entityIDDropdown = NonScrollableComboBox()
        for i in range(1,0x80):
            name = rom.getEntityName(i)
            self.entityIDDropdown.addItem(name)
        self.entityIDDropdown.currentIndexChanged.connect(self.setEntityID)
        cvlay.addWidget(self.entityIDDropdown)
        
        def on_button_clicked(id):
            self.setEntityCategory(CATS[id])
        self.entityCategoryButtonGroup, self.entityCategoryButtons, cvhlay = self.addRadioButtons(*CATS, cb=on_button_clicked)
        cvlay.addLayout(cvhlay)
        
        self.entitySlotBox, cvhlay = self.addSpinBoxWithLabel("slot: ", 0, 7)
        self.entitySlotBox.valueChanged.connect(functools.partial(self.setEntityProp, "slot"))
        self.entityRamAddrLabel = cvhlay.itemAt(0).widget()
        cvlay.addLayout(cvhlay)
        self.entityXBox, cvhlay = self.addSpinBoxWithLabel("x: ", 0, 0x9F)
        self.entityXBox.valueChanged.connect(functools.partial(self.setEntityProp, "x"))
        cvlay.addLayout(cvhlay)
        self.entityYBox, cvhlay = self.addSpinBoxWithLabel("y: ", 0, 0x7F)
        self.entityYBox.valueChanged.connect(functools.partial(self.setEntityProp, "y"))
        cvlay.addLayout(cvhlay)
        self.entityMarginBox, cvhlay = self.addSpinBoxWithLabel("spawn-distance: ", 0, 0xFF)
        self.entityMarginBox.valueChanged.connect(functools.partial(self.setEntityProp, "margin"))
        cvlay.addLayout(cvhlay)
        
        self.entpropwidgets = [self.entityIDDropdown, self.entitySlotBox, self.entityXBox, self.entityYBox, self.entityMarginBox, self.entityCategoryButtonGroup, *self.entityCategoryButtons]
        
        self.entitySelector = QListWidget(self)
        self.entitySelector.setMaximumWidth(240)
        self.entitySelectorWidgetIDMap = {}
        self.entitySelector.currentItemChanged.connect(self.onChangeSelectedEntity)
        self.entitySelector.setSelectionMode(QAbstractItemView.SingleSelection)
        cvlay.addWidget(self.entitySelector)
        
        bhlay = QHBoxLayout()
        entityCreateButton = QPushButton("Create")
        entityCreateButton.clicked.connect(self.addEntity)
        bhlay.addWidget(entityCreateButton)
        entityDeleteButton = QPushButton("Delete")
        entityDeleteButton.clicked.connect(self.removeEntity)
        bhlay.addWidget(entityDeleteButton)
        cvlay.addLayout(bhlay)
        hlay.addLayout(cvlay)
        vlay.addLayout(hlay)
        
    def timeInSeconds(self):
        return time.time()
    
    def defineUsageTab(self, tab):
        self.usageDirty = True
        self.usageCalc = None
        self.usageResult = None
        self.prevUsageResult = None
        self.usageTab = tab
        self.usageCalcTime = 0
        self.usageLock = threading.Lock()
        
        # ms
        self.usageCallTimerInterval = 10
        self.usageCalcSpinTime = 1
        
        vlay = QVBoxLayout()
        self.usageLabel = QLabel("usage")
        labelScroll = QScrollArea(self)
        labelScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        labelScroll.setWidget(self.usageLabel)
        labelScroll.setWidgetResizable(True)
        vlay.addWidget(labelScroll)
        
        bars = QScrollArea(self)
        bars.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bars.setWidgetResizable(True)
        self.usageBarLayout = QVBoxLayout(bars)
        self.usageBars = dict()
        bars.setLayout(self.usageBarLayout)
        vlay.addWidget(bars)
        
        tab.setLayout(vlay)
        
        # usage calculation timer
        
        timer = QTimer(self)
        timer.timeout.connect(self.updateUsage)
        timer.start(10)
    
    def updateUsage(self, iterations=1):
        self.updateUsageLabel()
        
        with self.usageLock:
            if self.usageDirty == False and self.usageResult is not None and self.timeInSeconds() - self.usageCalcTime < 15:
                return
            if self.usageCalc is None:
                self.usageDirty = False
                self.usageCalc = 1
                # note that no path is provided, so it won't save to disk.
                def threadRoutine():
                    regions, errors = model.saveRom(self.rom, copy.deepcopy(self.j))
                    regions.sort(key=lambda region: -region.max)
                    #print("locking...")
                    with self.usageLock:
                        #print("locked.")
                        self.usageCalcTime = self.timeInSeconds()
                        self.usageResult = {
                            "regions": regions,
                            "errors": errors
                        }
                        self.usageCalc = None
                threading.Thread(target=threadRoutine).start()
        
        self.updateUsageLabel()
            
    def defineChunksTab(self, tab):
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, [TAB_COMBO_LEVEL])
        hlay = QHBoxLayout()
        
        # chunk selector
        self.chunkSelectors.append(SelectorPanel(self, ChunkSelectorWidget))
        hlay.addWidget(self.chunkSelectors[-1])
        
        # chunk display
        cvlay = QVBoxLayout()
        self.chunkEdit = ChunkEdit(self, tab)
        cvlay.addWidget(self.chunkEdit)
        
        # chunk label
        self.chunkEditLabel = QLabel()
        font = self.chunkEditLabel.font()
        font.setPointSize(10)
        self.chunkEditLabel.setFont(font)
        cvlay.addWidget(self.chunkEditLabel)
        
        # padding
        cvlay.addWidget(QWidget())
        hlay.addLayout(cvlay)
        vlay.addLayout(hlay)
        
        # padding
        hlay.addWidget(QWidget())
        
        # tile selector
        self.tileSelectors.append(SelectorPanel(self, TileSelectorWidget, 4, 0x4, 0x24, idxremap=lambda x: x if x < 0x80 else x+0x70))
        hlay.addWidget(self.tileSelectors[-1])
    
    def defineWidgetLayoutWithLevelDropdown(self, w, combos=[TAB_COMBO_LEVEL]):
        vlay = QVBoxLayout()
        hlay = QHBoxLayout()
        
        vlay.addLayout(hlay)
        
        assert(len(combos) > 0)
        
        for combo in combos:
            dropdown = QComboBox()
            if combo == TAB_COMBO_LEVEL:
                dropdown.addItems(["Plant Castle", "Crystal Castle", "Cloud Castle", "Rock Castle", "Dracula I", "Dracula II", "Dracula III"])
                dropdown.currentIndexChanged.connect(self.setLevel)
                self.qcb_levels.append(dropdown)
            if combo == TAB_COMBO_SUBLEVEL:
                dropdown.currentIndexChanged.connect(self.setSublevel)
                self.qcb_sublevels.append(dropdown)
            if combo == TAB_COMBO_SCREEN:
                dropdown.currentIndexChanged.connect(self.setScreen)
                self.qcb_screens.append(dropdown)
            if combo == TAB_COMBO_SPRITE:
                dropdown.currentIndexChanged.connect(self.setSprite)
                self.qcb_sprites.append(dropdown)
            hlay.addWidget(dropdown)
        
        w.setLayout(vlay)
        return vlay
        
    def onChangeTab(self, idx):
        if idx < 0:
            return
        tab = self.tabs.widget(idx)
        if tab in self.screenTabs:
            self.lastScreenTab = tab
        if self.chunkEdit is not None and tab == self.chunkEdit.restoreTab:
            self.updateChunkLabel()
        if tab == self.entityTab:
            self.updateScreenEntityList()
            
    def onChangeSelectedEntity(self, item):
        level, sublevel, screen = self.getLevel()
        if item is not None:
            self.entitySelected[(level, sublevel, screen)] = self.entitySelectorWidgetIDMap[id(item)]
        else:
            self.entitySelected[(level, sublevel, screen)] = None
        self.updateScreenEntityList()
    
    def restoreEntityContext(app, level, sublevel, screen):
        app.setLevel(level-1)
        app.setSublevel(sublevel)
        app.setScreen(screen)
        app.tabs.setCurrentWidget(app.entityTab)
        
    def setLayoutScreen(self, mask, value):
        jl, jsl, js = self.getLevelJ()
        level, sublevel, screen = self.getLevel()
        selCoords = self.sel_screencoords.get((level, sublevel), None)
        if selCoords is not None:
            x, y = selCoords
            prev = jsl.layout[x][y]
            newvalue = (prev & ~mask) | (value & mask)
            if newvalue != prev:
                self.undoBuffer.push(
                    lambda app: lset(app.j.levels[level].sublevels[sublevel].layout[x], y, newvalue),
                    lambda app: lset(app.j.levels[level].sublevels[sublevel].layout[x], y, prev),
                    lambda app: app.restoreLayoutContext(level, sublevel),
                    lambda app: app.updateLay()
                )
        
    def setScreenID(self, id):
        if id == 0:
            self.setLayoutScreen(0xFF, 0)
        else:
            id -= 1
            self.setLayoutScreen(0x8F, id | 0x80)
    
    def setEntityProp(self, prop, value):
        level, sublevel, screen = self.getLevel()
        selectedEntity = self.entitySelected.get((level, sublevel, screen), None)
        if selectedEntity is not None:
            cat, i = selectedEntity
            prev = self.j.levels[level].sublevels[sublevel].screens[screen][cat][i][prop]
            if prev != value:
                self.undoBuffer.push(
                    lambda app: lset(app.j.levels[level].sublevels[sublevel].screens[screen][cat][i], prop, value),
                    lambda app: lset(app.j.levels[level].sublevels[sublevel].screens[screen][cat][i], prop, prev),
                    lambda app: app.restoreEntityContext(level, sublevel, screen),
                    lambda app: app.updateScreenEntityList()
                )
                self.updateScreenEntityList()
    
    def setEntityCategory(self, cat):
        level, sublevel, screen = self.getLevel()
        jl, jsl, js = self.getLevelJ()
        selectedEntity = self.entitySelected.get((level, sublevel, screen), None)
        if selectedEntity is not None:
            prevcat, i = selectedEntity
            if prevcat != cat:
                prevslot = js[prevcat][i].slot
                
                def moveCat(_src, _dst, _srcidx, _dstidx, slot, app):
                    jl, jsl, js = app.getLevelJ()
                    if _srcidx is None:
                        _srcidx = len(js[_src])-1
                    if _dstidx is None:
                        _dstidx = len(js[_dst])
                    ent = js[_src][_srcidx]
                    ent.slot = slot
                    js[_src][_srcidx:_srcidx+1] = []
                    js[_dst].insert(_dstidx, ent)
                    app.entitySelected[(level, sublevel, screen)] = (_dst, _dstidx)
                    
                self.undoBuffer.push(
                    functools.partial(moveCat, prevcat, cat, i, None, prevslot % rom.SLOTCOUNT[CATS.index(cat)]),
                    functools.partial(moveCat, cat, prevcat, None, i, prevslot),
                    lambda app: app.restoreEntityContext(level, sublevel, screen),
                    lambda app: app.updateScreenEntityList()
                )
                self.updateScreenEntityList()
    
    def _removeEntity(self, level, sublevel, screen, cat, i=None):
        jsl = self.j.levels[level].sublevels[sublevel] 
        js = jsl.screens[screen]
        if i is None:
            i = len(js[cat]) - 1
        js[cat][i:i+1] = []
    
    #adds a generic bat
    def _addEntity(self, level, sublevel, screen, cat="enemies", ent=None, i=None):
        jsl = self.j.levels[level].sublevels[sublevel] 
        js = jsl.screens[screen]
        if ent is None:
            e = model.JSONDict()
            e.x = 0x50
            e.y = 0x40
            e.type = 0x1F
            e.margin = model.getStandardMarginForEntity(e.type, jsl.vertical)
        else:
            e = copy.copy(ent)
        if i is None:
            i = len(js[cat])
        js[cat].insert(i, e)
        self.entitySelected[(level, sublevel, screen)] = (cat, i)
    
    def addEntity(self):
        level, sublevel, screen = self.getLevel()
        
        self.undoBuffer.push(
            lambda app: app._addEntity(level, sublevel, screen),
            lambda app: app._removeEntity(level, sublevel, screen, "enemies"),
            lambda app: app.restoreEntityContext(level, sublevel, screen),
            lambda app: app.updateScreenEntityList()
        )
    
    def removeEntity(self):
        jl, jsl, js = self.getLevelJ()
        level, sublevel, screen = self.getLevel()
        selectedEntity = self.entitySelected.get((level, sublevel, screen), None)
        if self.entitySelector is not None:
            cat, i = selectedEntity
            ent = js[cat][i]
            self.undoBuffer.push(
                lambda app: app._removeEntity(level, sublevel, screen, cat, i),
                lambda app: app._addEntity(level, sublevel, screen, cat, ent, i),
                lambda app: app.restoreEntityContext(level, sublevel, screen),
                lambda app: app.updateScreenEntityList()
            )
    
    def updateScreenEntityList(self):
        jl, jsl, js = self.getLevelJ()
        level, sublevel, screen = self.getLevel()
        self.entityRamAddrLabel.setText("slot:")
        selectedEntity = self.entitySelected.get((level, sublevel, screen), None)
        if self.entitySelector is not None:
            self.entitySelector.blockSignals(True)
            for w in self.entpropwidgets:
                if w is not self.entityCategoryButtonGroup:
                    w.setEnabled(selectedEntity is not None)
            self.entityMarginBox.setEnabled(selectedEntity is not None and model.getScreenEdgeType(self.j, level, sublevel, screen) != 0xB)
            selector = self.entitySelector
            self.entitySelectorWidgetIDMap = {}
            selector.clear()
            for icat, cat in enumerate(CATS):
                for i, ent in enumerate(js.get(cat, [])):
                    name = rom.getEntityName(ent.type)
                    item = QListWidgetItem(self.catIcons[cat], name)
                    selector.addItem(item)
                    self.entitySelectorWidgetIDMap[id(item)] = (cat, i)
                    if selectedEntity == (cat, i):
                        selector.setCurrentItem(item)
                        ramaddr = rom.SLOTRAMSTART[icat]+0x100*(ent.slot % rom.SLOTCOUNT[icat])
                        self.entityRamAddrLabel.setText(f"[${ramaddr:04X}] slot:")
                        if self.sender() not in self.entpropwidgets:
                            for w in self.entpropwidgets:
                                w.blockSignals(True)
                            self.entityIDDropdown.setCurrentIndex(ent.type-1)
                            self.entitySlotBox.setValue(ent.slot)
                            self.entitySlotBox.setMaximum(rom.SLOTCOUNT[icat]-1)
                            self.entityXBox.setValue(ent.x)
                            self.entityYBox.setValue(ent.y)
                            for button in self.entityCategoryButtons:
                                if button.text() == cat:
                                    button.setChecked(True)
                                    break

                            self.entityMarginBox.setValue(ent.margin)
                            for w in self.entpropwidgets:
                                w.blockSignals(False)
            self.entitySelector.blockSignals(False)
        for screenGrid in self.screenGrids:
            screenGrid.update()
    
    def setEntityID(self, index):
        index += 1
        self.setEntityProp("type", index)
        
    def setSublevelVertical(self, vertical):
        vertical = {Qt.Unchecked: 0, Qt.PartiallyChecked: 0, Qt.Checked: 1}[vertical]
        self.setSublevelProp("vertical", vertical)
    
    def setSublevelProp(self, prop, value):
        level, sublevel, screen = self.getLevel()
        prev = self.j.levels[level].sublevels[sublevel][prop]
        if prev != value:
            self.undoBuffer.push(
                lambda app: lset(app.j.levels[level].sublevels[sublevel], prop, value),
                lambda app: lset(app.j.levels[level].sublevels[sublevel], prop, prev),
                lambda app: app.restoreLayoutContext(level, sublevel),
                lambda app: app.updateLay()
            )
    
    def updateChunkLabel(self):
        level = self.sel_level
        chunks = model.getLevelChunks(self.j, level)
        chidx = self.chunkSelected.get(level, None)
        text = ""
        if chidx is None:
            text = "Select a chunk to edit."
        elif chidx == 0:
            text = "Chunk 0 is not editable."
        elif chidx >= len(chunks):
            text = "(Error: OoB)"
        else:
            if self.j.levels[level].get("chunks", None) is None:
                if self.j.levels[level].get("chunklink", None) is not None:
                    chunklink = self.j.levels[level].chunklink
                    text = f"Linked to f{rom.LEVELS[chunklink] or 'another stage'}"
                else:
                    text = f"(Error: chunklink)"
            else:
                text = f"Chunk {rom.LEVELS[level] or '?'}:{chidx:02X}"
                uses = model.getChunkUsage(self.j, level, chidx)
                levelsused = model.getChunkUsage(self.j, level, chidx, 1)
                if len(uses) == 0:
                    text += " (unused)"
                else:
                    text += f"\n{len(uses)} {plural(len(uses), 'appearance')}"
                    if not (set([(level,)]) >= set(levelsused)):
                        text += f"\n...including appearances in other levels as a glitch chunk!"
                    if len(uses) < 20:
                        for use in uses:
                            use_level, use_sublevel, use_screen, (use_x, use_y) = use
                            text += f"\n-> {rom.LEVELS[use_level]}-{use_sublevel+1} ${use_screen:X} at x={use_x}, y={use_y}"
                    else:
                        text += "\n(Too many appearances to list)"
        
        addTile = False
        if self.chunkEdit.hoverPos is not None:
            x, y = self.chunkEdit.hoverPos
            chunk = self.chunkEdit.getChunk()
            if chunk is not None:
                tidx = chunk[x + y * 4]
                text = f"Tile ${tidx:04X}\n" + text
                addTile = True
        if not addTile:
            text = f"Tile $- - - -\n" + text
        
        self.chunkEditLabel.setText(text)
        self.chunkEditLabel.update()
    
    def restoreLayoutContext(self, level, sublevel):
        self.setLevel(level-1)
        self.setSublevel(sublevel)
        self.tabs.setCurrentWidget(self.layTab)
    
    def updateUsageLabel(self):
        with self.usageLock:
            if self.usageResult is not self.prevUsageResult:
                self.prevUsageResult = self.usageResult
                regions = self.usageResult["regions"]
                names = set([region.name for region in regions])
                if names != set(self.usageBars.keys()):
                    for key in self.usageBars.keys():
                        self.usageBarLayout.removeWidget(self.usageBars[key])
                        self.usageBars[key].deleteLater()
                    self.usageBars.clear()
                    for region in regions:
                        usageBar = UsageBar(region.name, region.shortname)
                        self.usageBarLayout.addWidget(usageBar)
                        self.usageBars[region.name] = usageBar
                for region in regions:
                    assert region.name in self.usageBars
                    self.usageBars[region.name].region = region
                    self.usageBars[region.name].start = region.addr
                    self.usageBars[region.name].end = region.addr+region.max
                    self.usageBars[region.name].bank = region.bank
                    self.usageBars[region.name].used = region.used
                    self.usageBars[region.name].max = region.max
                    self.usageBars[region.name].subranges = region.subranges
                    self.usageBars[region.name].update()
            
            text = "Usage"
            icon = self.emptyIcon
            if self.usageDirty:
                text += "*"
            if self.usageCalc is not None:
                text += " (calculating)"
            if self.usageResult is not None:
                for error in self.usageResult["errors"]:
                    text += "\nERROR: " + error
                    icon = self.errorIcon
                self.usageLabel.setText(text)
                
            tabtext = "Usage"
            if self.usageDirty:
                tabtext += "*"
            self.tabs.setTabText(self.tabs.indexOf(self.usageTab), tabtext)
            self.tabs.setTabIcon(self.tabs.indexOf(self.usageTab), icon)
    
    def updateLay(self):
        jl, jsl, js = self.getLevelJ()
        level, sublevel, screen = self.getLevel()
        for w in self.layWidgets:
            w.blockSignals(True)
        self.sublevelVerticalScrollingCheckbox.setCheckState(Qt.Checked if jsl.vertical == 1 else Qt.Unchecked)
        self.sublevelStartXBox.setValue(jsl.startx)
        self.sublevelStartYBox.setValue(jsl.starty)
        self.sublevelTimerBox.setValue(jsl.timer)
        selCoords = self.sel_screencoords.get((level, sublevel), None)
        text = "(Select a screen.)"
        t = 0
        if selCoords is not None:
            x, y = selCoords
            s = jsl.layout[x][y] & 0xF
            text = f"Screen at ({x:X}, {y:X})"
            t = jsl.layout[x][y] >> 4
            self.screenIDSelector.setEnabled(True)
            self.screenIDSelector.clear()
            self.screenIDSelector.addItem(f"None")
            for i in range(min(len(jsl.screens), 0xF)):
                sn = ""
                if not model.screenUsed(self.j, level, sublevel, i):
                    sn = "* "
                self.screenIDSelector.addItem(f"{sn}Screen ${i:X}")
            if t == 0 and s == 0:
                self.screenIDSelector.setCurrentIndex(0)
            else:
                self.screenIDSelector.setCurrentIndex(s + 1)
                if (x, y) == (jsl.startx, jsl.starty):
                    text += "\nSublevel entrance."
                elif model.getScreenEnterable(self.j, level, sublevel, x, y):
                    text += "\nScreen is enterable."
                exits = model.getScreenExitDoor(self.j, level, sublevel, s)
                if -1 in exits and 1 in exits:
                    text += "\nDoors exit to left and right."
                elif -1 in exits:
                    text += "\nExits sublevel to left."
                elif 1 in exits:
                    text += "\nExits sublevel to right."
                for exit in exits:
                    if x + exit in range(0x10):
                        if jsl.layout[x+exit][y] != 0:
                            text += "\nExit blocked—glitches!"
                    else:
                        text += "\nExit out of bounds!"
        else:
            self.screenIDSelector.setEnabled(False)
        for button, name in zip(self.layoutScreenScrollButtons, SCREENSCROLLNAMES_V if jsl.vertical == 1 else SCREENSCROLLNAMES_H):
            button.setEnabled(selCoords is not None and t != 0)
            button.setText(name)
            if selCoords is None or SCREENSCROLLS[name] != t or t == 0:
                button.setChecked(False)
            elif SCREENSCROLLS[name] == t:
                button.setChecked(True)
                
        self.screenLabel.setText(text)
        self.layGrid.update()
        for w in self.layWidgets:
            w.blockSignals(False)
    
    def setLevel(self, level):
        sender = self.sender()
        self.sel_level = level+1
        for qcb in self.qcb_levels:
            if qcb != sender:
                qcb.blockSignals(True)
                qcb.setCurrentIndex(level)
                qcb.blockSignals(False)
        
        for selector in self.chunkSelectors + self.tileSelectors:
            for id, widget in selector.widgets.items():
                widget.update()
        
        self.chunkEdit.update()
        
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
        self.setSprite(self.sel_sprite, False)
        
        self.updateLay()
        
    def onUndoBuffer(self, kind):
        self.usageDirty = True
        
    def undo(self):
        self.undoBuffer.undo()
        
    def redo(self):
        self.undoBuffer.redo()
        
    def setSprite(self, sprite, resetItems=False):
        sender = self.sender()
        sprites = [f"Sprite ${i:02X}" for i in range(0x80)]
        self.sel_sprite = sprite
        for qcb in self.qcb_sprites:
            if qcb != sender:
                qcb.blockSignals(True)
                if resetItems:
                    qcb.clear()
                    qcb.addItems(sprites)
                qcb.setCurrentIndex(sprite)
                qcb.blockSignals(False)
        self.spriteView.update()
        self.spriteView.getSpriteTiles() # refresh sprite
        
        sltext = f"Sprite Address: {self.spriteView.srcAddr}"
        jl, jsl, js = self.getLevelJ()
        if "spritePatch" in jsl:
            sltext += f"\nSublevel sprite patch: ${jsl.spritePatch.startidx:02X}-${len(jsl.spritePatch.sprites)+jsl.spritePatch.startidx-1:02X}"
            for i, sprite in enumerate(jsl.spritePatch.sprites):
                sltext += f"\n - ${i+jsl.spritePatch.startidx:02X} <- {sprite.srcAddr}"
        self.spriteLabel.setText(sltext)
        
    def setScreen(self, screen, sublevelChanged=False):
        sender = self.sender()
        level, sublevel, _ = self.getLevel()
        
        # TODO: if there is only 1 copy of the screen, set screencoords to its coords
        self.sel_screencoords[(level, sublevel)] = None
        screens = [f"{'* ' if not model.screenUsed(self.j, level, sublevel, i) else ''}Screen ${i:X}" for i, sc in enumerate(self.j.levels[level].sublevels[sublevel].screens)]
        if screen >= len(screens):
            self.sel_special_screen[(level, sublevel)] = screen - len(screens)
        else:
            self.sel_special_screen[(level, sublevel)] = False
            self.sel_screen[(level, sublevel)] = screen
        screens_and_special_screens = screens + [f"Special ${i:X}" if "name" not in ss else ss.name for i,ss in enumerate(self.getSpecialScreens())]
        for qcb in self.qcb_screens:
            if qcb != sender:
                qcb.blockSignals(True)
                
                if qcb == self.qcb_screentab_screen: 
                    if sublevelChanged:
                        qcb.clear()
                        qcb.addItems(screens_and_special_screens)
                    qcb.setCurrentIndex(screen)
                else:
                    if sublevelChanged:
                        qcb.clear()
                        qcb.addItems(screens)
                    qcb.setCurrentIndex(self.sel_screen[(level, sublevel)])
                    
                qcb.blockSignals(False)
        
        for widget in self.screenGrids:
            widget.update()
            
        if self.tabs.currentWidget() == self.entityTab:
            self.updateScreenEntityList()
        
        self.updateLay()
        
    def setScreenCoords(self, x, y):
        self.sel_screencoords[(self.sel_level, self.sel_sublevel[self.sel_level])] = (x, y)
        self.updateLay()
    
    def setTile(self, tile):
        prevSelected = self.tileSelected.get(self.sel_level, None)
        self.tileSelected[self.sel_level] = tile
        if self.chunkEdit is not None:
            self.chunkEdit.update()
        for selector in self.tileSelectors:
            if prevSelected is not None:
                selector.widgets[prevSelected].update()
            if tile is not None:
                selector.widgets[tile].update()
                selector.ensureWidgetVisible(selector.widgets[tile])
    
    def setChunk(self, chunk):
        prevSelected = self.chunkSelected.get(self.sel_level, None)
        self.chunkSelected[self.sel_level] = chunk
        if self.chunkEdit is not None:
            self.chunkEdit.update()
            if self.tabs.currentWidget() == self.chunkEdit.restoreTab:
                self.updateChunkLabel()
        for screen in self.screenGrids:
            screen.update()
        for selector in self.chunkSelectors:
            if prevSelected is not None:
                selector.widgets[prevSelected].update()
            if chunk is not None:
                selector.widgets[chunk].update()
                selector.ensureWidgetVisible(selector.widgets[chunk])
    
    def onAbout(self):
        text = f"Developed by NaOH in March 2023 (cc-by-nc-sa v3.0), with contributions by Julien Neel.\n\nCreative Commons Licensed — use this program for any non-commercial means however you like, but please credit the author. Source available at https://github.com/nstbayless/cv2br-editor\n\nSpecial thanks to Spriven."
        text += "\n\nPlease support Konami."
        QMessageBox.information(
            self,
            f"{APPNAME}",
            text
        )
    
    def onConfigure(self):
        dialog = QDialog(self)
        vlay = QVBoxLayout()
        
        def onEmuPathChanged(value):
            self.config["emuPath"] = value
        
        emuPath = FilePathSelector(self.config["emuPath"], dialog, "Emulator Path:")
        emuPath.valueChanged.connect(onEmuPathChanged)
        
        vlay.addWidget(emuPath)
        
        dialog.setLayout(vlay)
        dialog.exec()
    
    def onPlaytest(self):
        if self.config["emuPath"] == "":
            QMessageBox.information(
                self, 'Cannot start Emulator', f"Please select an emulator via Edit -> {self.actConfigure.text().replace('&', '')}."
            )
            return
        
        if rom.ROMTYPE not in ["us"]:
            # to be honest, it's unclear why jp roms don't work
            # kgbc roms will require some more research to implement writePlaytestStart().
            # (it's probably easy, just haven't tried.)
            QMessageBox.information(
                self, 'ROM type not supported', f"Only US ROMs can be playtested.."
            )
            return
            
        level, sublevel, screen = self.getLevel()
        if "playtest-warning" not in self.ioStore and sublevel > 0:
            QMessageBox.warning(
                self, 'Warning', f"Some graphical glitches are to be expected when playtesting from anywhere other than the start of a level."
            )
            self.ioStore["playtest-warning"] = True
        
        level, sublevel, screen = self.getLevel()
        path = os.path.join(tempfile.gettempdir(), "revedit_test.gb")
        result = self.onFileIOSync("rom", IO_SAVE, path, playtestStart=(level, sublevel))
        if result is None:
            command = split_unquoted(f"{self.config['emuPath']}") if '"' in self.config['emuPath'] else [self.config['emuPath']]
            subprocess.Popen(command + [path])
            
    # load = 0
    # save = 1
    # saveas = 2
    def onFileIO(self, target, mode):
        
        verb = "Select" if target == IO_OPEN else "Save"
        
        DMESG = {
            "rom": f"{verb} a ROM file",
            "hack": f"{verb} a hack file"
        }
        
        DEXT = {
            "rom": ".gb",
            "hack": ".json",
        }
        
        DFILT = {
            "rom": "ROM files (*.gb *.gbc *.bin)",
            "hack": "Hack files (*.json)"
        }
        
        if target == "rom" and "rom-warning" not in self.ioStore:
            QMessageBox.information(
                self, 'Warning', f"Roms exported this way cannot be read back in by {APPNAME}.\n\nPlease ensure you save your hack (ctrl+s) -- and frequently, in case of unexpected crashes."
            )
            self.ioStore["rom-warning"] = True
        
        path = None
        if mode == IO_SAVE:
            if target in self.ioStore:
                path = self.ioStore[target]
            else:
                mode = IO_SAVEAS
        if path is None:
            options = QFileDialog.Options()
            options |= QFileDialog.DontUseNativeDialog
            file_dialog = QFileDialog(self, DMESG[target], "", DFILT[target], options=options)
            file_dialog.setAcceptMode(QFileDialog.AcceptOpen if mode == IO_OPEN else QFileDialog.AcceptSave)
            file_dialog.fileSelected.connect(lambda path: self.onFileIOSync(target, mode, path, defaultExtension=DEXT[target]) if path is not None else None)
            file_dialog.show()
        else:
            self.onFileIOSync(target, mode, path)
    
    def onFileIOSync(self, target, mode, path, **kwargs):
        assert path is not None
        
        if os.path.splitext(path)[1] == "":
            path += kwargs.get("defaultExtension", "")
        
        self.ioStore[target] = path
        
        if target == "rom":
            assert mode in [IO_SAVEAS, IO_SAVE]
            print(f"Exporting rom to {path}")
            _, errors = model.saveRom(self.rom, self.j, path, **kwargs)
            print("Done.")
            
            if len(errors) > 0:
                result = ""
                for error in errors:
                    result += error + "\n"
                    print("ERROR:", error)
                QMessageBox.information(
                    self,
                    'Error exporting rom',
                    result
                )
                return -1
                
        elif target == "hack":
            if mode == IO_OPEN:
                with open(path, "r") as f:
                    self.undoBuffer.clear()
                    j = json.load(f, object_hook=model.JSONDict)
                    self.j = j
            elif mode in [IO_SAVE, IO_SAVEAS]:
                with open(path, "w") as f:
                    json.dump(self.j, f, ensure_ascii=False, indent=4)
    
    def getSpecialScreens(self, level=None, sublevel=None):
        # gets special screens for this (level, sublevel)
        if level == None or sublevel == None:
            level, sublevel, screen = self.getLevel()
        jl, jsl, js = self.getLevelJ()
        
        specscreens = []
        
        if "initRoutines" in jsl:
            for i,initRoutine in enumerate(jsl.initRoutines):
                if initRoutine.type == "SCREEN":
                    specscreens.append(model.JSONDict(data=List2D(lambda: jsl.initRoutines[i].data, 5)))
            
        return specscreens

if "--help" in sys.argv or "-h" in sys.argv:
    print(f"{APPNAME}")
    print(f"{sys.argv[0]} [--base=/path/to/base.gb]")
    sys.exit(0)

app = QApplication(sys.argv)

base = None
multibase = False

for s in sys.argv:
    if s.startswith("--base="):
        base = s[7:]
        if not os.path.exists(base):
            print(f"not found: {base}")
            sys.exit(1)

if base is None:            
    for candidate in ["base.gb", "base-us.gb", "base-kgbc4eu.gb", "base-jp.gb"]:
        if os.path.exists(os.path.join(guipath, candidate)):
            base = os.path.join(guipath, candidate)
            break
    else:
        candidates = glob.glob(os.path.join(guipath, "*.gb"))
        if len(candidates) == 1:
            base = candidates[0]
        elif len(candidates) == 0:
            candidates = glob.glob("*.gb")
            if len(candidates) == 1:
                base = candidates[0]
        if len(candidates) > 1:
            multibase = True

if base is None:
    text = f"Place a gameboy rom in the {APPNAME} directory to automatically load a ROM on startup. Alternatively, select one now."
    if multibase:
        text = f"Place exactly one gameboy rom in the {APPNAME} directory to automatically load a ROM on startup"
        text += f"\n\nMultiple ROMs were found, so {APPNAME} can't disambiguate which one to load.\nYou can rename one of them to \"base.gb\", or else select one now."
    messageBox = QMessageBox()
    messageBox.setWindowTitle("Provide a ROM")
    messageBox.setText(text)
    messageBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    result = messageBox.exec()
    if result != QMessageBox.Ok:
        sys.exit(1)
    else:
        file_path, _ = QFileDialog.getOpenFileName(None, "Select ROM File", "", "ROM files (*.gb *.gbc *.bin)")
        if file_path:
            base = file_path

if base is not None:
    window = MainWindow(base)
    window.show()

    app.exec()