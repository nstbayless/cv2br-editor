import sys
import rom
import model
import math
from PySide6.QtWidgets import \
    QApplication, QMainWindow, QPushButton, QLabel, \
    QToolBar, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, \
    QComboBox, QGridLayout, QScrollArea, QListWidget, QListWidgetItem, \
    QAbstractItemView, QSpinBox
from PySide6.QtGui import QColor, QAction, QIcon, QPainter, QPen, QFont, QFontMetrics, QImage, QKeySequence
from PySide6.QtCore import Qt, QAbstractListModel, QSize, QRect, QEvent
import functools

def plural(i, singular, plural=None):
    if plural is None:
        plural = singular + 's'
    return singular if i == 1 else plural

# sets value in list
def lset(l, i, v):
    l[i] = v
    
CATS = ["misc", "enemies", "items"]

# Undoable Action
class UAction:
    def __init__(self, do, undo, restorecontext=None, refreshcontext=None):
        self.type = type
        self.do = do
        self.undo = undo
        self.restorecontext = restorecontext if restorecontext is not None else (lambda app: None)
        self.refreshcontext = refreshcontext if refreshcontext is not None else (lambda app: None)
        
class UndoBuffer:
    def __init__(self, app):
        self.idx = 0
        self.buff = []
        self.app = app
        self.max = 1023
    
    def undo(self):
        self.idx -= 1
        if self.idx < 0:
            self.idx = 0
        else:
            ua = self.buff[self.idx]
            ua.restorecontext(self.app)
            ua.undo(self.app)
            ua.refreshcontext(self.app)
        
    def redo(self):
        self.idx += 1
        if self.idx > len(self.buff):
            self.idx = len(self.buff)
        else:
            ua = self.buff[self.idx-1]
            ua.restorecontext(self.app)
            ua.do(self.app)
            ua.refreshcontext(self.app)
    
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

class VRam:
    def __init__(self, j, nes):
        self.j = j
        self.nes = nes
        self.tileset = [QImage(QSize(8, 8), QImage.Format_RGB32) for i in range(0x200)]
        self.defimg = QImage(QSize(8, 8), QImage.Format_RGB32)
        self.defimg.fill(QColor(0xff, 0x00, 0xff))
        self.cached_vram_descriptor = None
        
    def getVramBGTile(self, tileidx):
        return self.tileset[0x100 + tileidx]
        
    def loadVramTile(self, destaddr, srcaddr, srcbank):
        # create an 8x8 QImage with Format_RGB32
        image = QImage(QSize(8, 8), QImage.Format_RGB32)
        
        destaddr -= 0x8000
        destaddr //= 0x10
        
        def readbyte(srcbank, addr):
            return self.nes[0x4000 * srcbank + (addr)%0x4000]

        for y in range(8):
            b1 = readbyte(srcbank, srcaddr + y*2)
            b2 = readbyte(srcbank, srcaddr + y*2 + 1)
            for x in range(8):
                c1 = (b1 >> (7-x)) & 1
                c2 = (b2 >> (7-x)) & 1
                image.setPixelColor(x, y, QColor(*rom.PALETTE[c1 + c2*2]))
        
        self.tileset[destaddr] = image
        return image
        
    def getDefaultImage(self):
        return self.defimg
        
    def clearVram(self):
        for i in range(0x200):
            self.tileset[i] = self.getDefaultImage()
        
    def loadVramFromBuffer(self, buff):
        for entry in buff:
            destaddr = entry.destaddr
            srcaddr = entry.srcaddr
            for i in range(entry.destlen // 0x10):
                self.loadVramTile(destaddr + i * 0x10, srcaddr + i * 0x10, entry.srcbank)
        
    def loadVramForStage(self, level):
        desc = f"l{level}"
        if self.cached_vram_descriptor == desc:
            return
        self.cached_vram_descriptor = desc
        self.clearVram()
        
        # not sure what loads tile 0x100 to white (maybe nothing)
        # but it should be white.
        self.tileset[0x100] = QImage(QSize(8, 8), QImage.Format_RGB32)
        self.tileset[0x100].fill(Qt.white)
        
        self.loadVramFromBuffer(self.j.tileset_common)
        self.loadVramFromBuffer(self.j.levels[level].tileset)

def paintTile(painter, vram, x, y, tileidx, scale):
    x2 = x + scale * 8
    y2 = y + scale * 8
    if tileidx >= 0:
        img = vram.getVramBGTile(tileidx)
    else:
        img = vram.getDefaultImage()
    f = math.floor
    painter.drawImage(QRect(f(x), f(y), f(x2 - x + 1), f(y2 - y + 1)), img)

class HotkeySpinBox(QSpinBox):
    def __init__(self, app):
        super().__init__()
        self.app = app
        # Install an event filter on the spin box
        self.installEventFilter(self)
    
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
    
    def paintEvent(self, event):
        painter = QPainter(self)
        level, sublevel, screen = self.app.getLevel()
        vram = self.app.vram
        vram.loadVramForStage(level)
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
            for w in self.entpropwidgets:
                w.clearFocus()
        
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
    def __init__(self, parent, type=ChunkSelectorWidget, scale=2, w=4, h=0x40):
        super().__init__()
        self.app = parent
        self.scale = scale
        self.w = w
        self.h = h
        self.type = type
        self.margin = 4
        self.spacing = 3
        self.widgets = []
        grid_layout = QGridLayout()
        grid_layout.setSpacing(self.spacing)
        grid_layout.setContentsMargins(self.margin, self.margin, self.margin, self.margin)
        for j in range(self.h):
            for i in range(self.w):
                self.widgets.append(type(i + j * self.w, self.app, self.scale))
                grid_layout.addWidget(self.widgets[-1], j, i)
        
        scroll_area_widget = QWidget()
        scroll_area_widget.setLayout(grid_layout)
        
        self.setWidget(scroll_area_widget)
        self.setWidgetResizable(True)
        # we add 2 here because it inexplicably has a horizontal scroll if we don't
        self.setFixedWidth(scroll_area_widget.minimumSizeHint().width() + self.verticalScrollBar().sizeHint().width() + 2)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

class ScreenWidget(QWidget):
    def __init__(self, parent, restoreTab, entityAlpha=0.9, gridSpacing=8*4):
        super().__init__(parent)
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
        jl, jsl, js = self.app.getLevelJ()
        chunks = model.getLevelChunks(self.app.j, level)
        
        vram = self.app.vram
        vram.loadVramForStage(level)
        
        for i in range(5):
            for j in range(4):
                chidx = js.data[j][i]
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
    def __init__(self, parent, restoreTab):
        super().__init__(parent, restoreTab, 0)
    
    def mousePressEvent(self, event):
        self.mouseMoveEvent(event)
        chidx = self.app.chunkSelected.get(self.app.sel_level, None)
        level, sublevel, screen = self.app.getLevel()
        jl, jsl, js = self.app.getLevelJ()
        if self.hoverPos is not None:
            i, j = self.hoverPos
            prev = js.data[j][i]
            if event.button() == Qt.LeftButton and chidx is not None:
                if prev != chidx:
                    self.app.undoBuffer.push(
                        lambda app: lset(app.j.levels[level].sublevels[sublevel].screens[screen].data[j], i, chidx),
                        lambda app: lset(app.j.levels[level].sublevels[sublevel].screens[screen].data[j], i, prev),
                        self.getRestoreContext()
                    )
            elif event.button() == Qt.RightButton:
                self.app.setChunk(None)
            elif event.button() == Qt.MiddleButton:
                self.app.setChunk(js.data[j][i])
        self.update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        squareSize = self.getScale()
        
        level, sublevel, screen = self.app.getLevel()
        jl = self.app.j.levels[level]
        jsl = jl.sublevels[sublevel]
        screen = jsl.screens[screen]
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
        jsl = self.app.j.levels[level].sublevels[sublevel]
        startx = jsl.startx
        starty = jsl.starty
        vertical = jsl.vertical == 1
        jlayout = jsl.layout
        
        squareSize = self.getSquareSize()

        for i in range(self.gridSize):
            for j in range(self.gridSize):
                l = jlayout[i][j]
                text = f"{l:02X}"
                x = i * squareSize
                y = j * squareSize
                x2 = x + squareSize
                y2 = y + squareSize
                bg = False
                if i == startx and j == starty:
                    if l & 0x0f == screen:
                        painter.setBrush(QColor(0xff, 200, 0xff))
                    else:
                        painter.setBrush(QColor(0xff, 220, 220))
                    painter.setPen(Qt.NoPen)
                    painter.drawRect(x, y, squareSize, squareSize)
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(pen)
                elif l == 0:
                    painter.setBrush(QColor(0, 0, 0, 50))
                    painter.setPen(Qt.NoPen)
                    painter.drawRect(x, y, squareSize, squareSize)
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(bgpen)
                    bg = True
                else:
                    painter.setPen(Qt.NoPen)
                    if l & 0x0f == screen:
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
                
                if not bg:
                    painter.drawText(x + squareSize/2 - 6, y + squareSize/2 + 4, text)


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.nes, self.j = model.loadRom("base-us.gb")
        self.undoBuffer = UndoBuffer(self)
        self.vram = VRam(self.j, self.nes)
        self.sel_level = 1 # plant=1 index
        self.sel_sublevel = {}
        self.sel_screen = {}
        self.qcb_levels = []
        self.qcb_sublevels = []
        self.qcb_screens = []
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
        self.setWindowTitle("RevEdit")
        # TODO: use pyside6-rcc to build the resources
        self.setWindowIcon(QIcon("etc/icon.png"))
        self.defineActions()
        self.defineMenus()
        self.defineTabs()
        self.setGeometry(50, 50, 850, 550)
        self.setLevel(3)
    
    def getLevel(self):
        return self.sel_level, self.sel_sublevel[self.sel_level], self.sel_screen[(self.sel_level, self.sel_sublevel[self.sel_level])]
    
    def getLevelJ(self):
        level, sublevel, screen = self.getLevel()
        jl = self.j.levels[level]
        jsl = jl.sublevels[sublevel]
        js = jsl.screens[screen]
        return jl, jsl, js

    def defineActions(self):
        self.actLoad = QAction("&Open Hack...", self)
        self.actLoad.triggered.connect(functools.partial(self.onFileIO, "hack", 0))
        self.actLoad.setShortcut(QKeySequence("ctrl+o"))
        
        self.actSave = QAction("&Save Hack", self)
        self.actSave.triggered.connect(functools.partial(self.onFileIO, "hack", 1))
        self.actSave.setShortcut(QKeySequence("ctrl+s"))
        
        self.actSaveAs = QAction("&Save Hack As...", self)
        self.actSaveAs.triggered.connect(functools.partial(self.onFileIO, "hack", 2))
        self.actSaveAs.setShortcut(QKeySequence("ctrl+shift+s"))
        
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
        
    def defineMenus(self):
        menu = self.menuBar()
        
        file_menu = menu.addMenu("&File")
        file_menu.addAction(self.actLoad)
        file_menu.addAction(self.actSave)
        file_menu.addAction(self.actSaveAs)
        
        edit_menu = menu.addMenu("&Edit")
        edit_menu.addAction(self.actUndo)
        edit_menu.addAction(self.actRedo)
        
    def defineTabs(self):
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.onChangeTab)
        self.setCentralWidget(self.tabs)
        TAB_LABELS = [
            "Layout", "Screen", "Entities", "Chunks"
        ]
        TAB_DEFS = [
            self.defineLevelLayTab,
            self.defineScreenTab,
            self.defineEntityTab,
            self.defineChunksTab,
        ]
        for i, (label, define) in enumerate(zip(TAB_LABELS, TAB_DEFS)):
            tab = QWidget()
            define(tab)
            self.tabs.addTab(tab, label)
    
    def defineLevelLayTab(self, tab):
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, 1)
        self.layGrid = RoomLayWidget(self)
        vlay.addWidget(self.layGrid)
    
    def defineScreenTab(self, tab):
        self.screenGrids.append(ScreenTileWidget(self, tab))
        self.screenTabs.append(tab)
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, 2)
        hlay = QHBoxLayout()
        hlay.addWidget(self.screenGrids[-1])
        self.chunkSelectors.append(SelectorPanel(self, ChunkSelectorWidget))
        hlay.addWidget(self.chunkSelectors[-1])
        vlay.addLayout(hlay)
        
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
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, 2)
        hlay = QHBoxLayout()
        
        self.screenGrids.append(ScreenWidget(self, tab))
        hlay.addWidget(self.screenGrids[-1])
        
        cvlay = QVBoxLayout()
        
        self.entityIDDropdown = QComboBox()
        for i in range(1,0x80):
            name = rom.getEntityName(i)
            self.entityIDDropdown.addItem(name)
        self.entityIDDropdown.currentIndexChanged.connect(self.setEntityID)
        cvlay.addWidget(self.entityIDDropdown)
        
        self.entityXBox, cvhlay = self.addSpinBoxWithLabel("x: ", 0, 0x9F)
        self.entityXBox.valueChanged.connect(functools.partial(self.setEntityProp, "x"))
        cvlay.addLayout(cvhlay)
        self.entityYBox, cvhlay = self.addSpinBoxWithLabel("y: ", 0, 0x7F)
        self.entityYBox.valueChanged.connect(functools.partial(self.setEntityProp, "y"))
        cvlay.addLayout(cvhlay)
        self.entityMarginBox, cvhlay = self.addSpinBoxWithLabel("spawn-distance: ", 0, 0xFF)
        self.entityMarginBox.valueChanged.connect(functools.partial(self.setEntityProp, "margin"))
        cvlay.addLayout(cvhlay)
        
        self.entpropwidgets = [self.entityIDDropdown, self.entityXBox, self.entityYBox, self.entityMarginBox]
        
        # attributes: x, y, margin
        
        self.entitySelector = QListWidget(self)
        self.entitySelector.setMaximumWidth(240)
        self.entitySelectorWidgetIDMap = {}
        self.entitySelector.currentItemChanged.connect(self.onChangeSelectedEntity)
        self.entitySelector.setSelectionMode(QAbstractItemView.SingleSelection)
        cvlay.addWidget(self.entitySelector)
        
        hlay.addLayout(cvlay)
        vlay.addLayout(hlay)
        
    def defineChunksTab(self, tab):
        vlay = self.defineWidgetLayoutWithLevelDropdown(tab, 0)
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
        self.tileSelectors.append(SelectorPanel(self, TileSelectorWidget, 4, 0x4, 0x20))
        hlay.addWidget(self.tileSelectors[-1])
    
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
        
    def setEntityProp(self, prop, value):
        level, sublevel, screen = self.getLevel()
        selectedEntity = self.entitySelected.get((level, sublevel, screen), None)
        if self.entitySelector is not None:
            cat, i = selectedEntity
            prev = self.j.levels[level].sublevels[sublevel].screens[screen][cat][i][prop]
            if prev != value:
                def restore(app):
                    app.setLevel(level-1)
                    app.setSublevel(sublevel)
                    app.setScreen(screen)
                    app.tabs.setCurrentWidget(self.entityTab)
                self.undoBuffer.push(
                    lambda app: lset(app.j.levels[level].sublevels[sublevel].screens[screen][cat][i], prop, value),
                    lambda app: lset(app.j.levels[level].sublevels[sublevel].screens[screen][cat][i], prop, prev),
                    restore,
                    lambda app: app.updateScreenEntityList()
                )
                self.updateScreenEntityList()
    
    def updateScreenEntityList(self):
        jl, jsl, js = self.getLevelJ()
        level, sublevel, screen = self.getLevel()
        selectedEntity = self.entitySelected.get((level, sublevel, screen), None)
        if self.entitySelector is not None:
            self.entitySelector.blockSignals(True)
            self.entityIDDropdown.setEnabled(selectedEntity is not None)
            self.entityXBox.setEnabled(selectedEntity is not None)
            self.entityYBox.setEnabled(selectedEntity is not None)
            self.entityMarginBox.setEnabled(selectedEntity is not None and model.getScreenEdgeType(self.j, level, sublevel, screen) != 0xB)
            selector = self.entitySelector
            self.entitySelectorWidgetIDMap = {}
            selector.clear()
            for cat in CATS:
                for i, ent in enumerate(js.get(cat, [])):
                    name = rom.getEntityName(ent.type)
                    item = QListWidgetItem(name)
                    selector.addItem(item)
                    self.entitySelectorWidgetIDMap[id(item)] = (cat, i)
                    if selectedEntity == (cat, i):
                        selector.setCurrentItem(item)
                        if self.sender() not in self.entpropwidgets:
                            for w in self.entpropwidgets:
                                w.blockSignals(True)
                            self.entityIDDropdown.setCurrentIndex(ent.type-1)
                            self.entityXBox.setValue(ent.x)
                            self.entityYBox.setValue(ent.y)
                            self.entityMarginBox.setValue(ent.margin)
                            for w in self.entpropwidgets:
                                w.blockSignals(False)
            self.entitySelector.blockSignals(False)
        
        for screenGrid in self.screenGrids:
            screenGrid.update()
    
    def setEntityID(self, index):
        index += 1
        self.setEntityProp("type", index)
    
    def updateChunkLabel(self):
        level = self.sel_level
        chunks = model.getLevelChunks(self.j, level)
        chidx = self.chunkSelected.get(level, None)
        text = ""
        if chidx == 0 or chidx is None:
            text = "Chunk $00 is not editable."
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
                    if not (set([level]) >= set(levelsused)):
                        text += f"\n...including appearances in other levels as a glitch chunk"
        
        self.chunkEditLabel.setText(text)
        self.chunkEditLabel.update()
    
    def setLevel(self, level):
        sender = self.sender()
        self.sel_level = level+1
        for qcb in self.qcb_levels:
            if qcb != sender:
                qcb.blockSignals(True)
                qcb.setCurrentIndex(level)
                qcb.blockSignals(False)
        
        for selector in self.chunkSelectors + self.tileSelectors:
            for widget in selector.widgets:
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
        
        self.layGrid.update()
        
    def undo(self):
        self.undoBuffer.undo()
        
    def redo(self):
        self.undoBuffer.redo()
        
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
        
        for widget in self.screenGrids:
            widget.update()
            
        if self.tabs.currentWidget() == self.entityTab:
            self.updateScreenEntityList()
        
        self.layGrid.update()
    
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
            
    
    # load = 0
    # save = 1
    # saveas = 2
    def onFileIO(self, target, save):
        pass
        
app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()