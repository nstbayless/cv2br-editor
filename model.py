import rom
from rom import readword, readtablebyte, readtableword, readbyte
import copy
import traceback

class JSONDict(dict):
    # This class implemented by ChatGPT
    # WARNING! some attributes are overshadowed by native dict attributes
    # for example, you can't access groove.values directly, must do groove["values"].
    # if you're experiencing an issue where your code works only if you change the
    # key's name, this is probably the reason.
    def __getattr__(self, attr):
        if hasattr(dict, attr):
            return getattr(dict, attr).__get__(self, type(self))
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)
    
    def __setattr__(self, attr, value):
        if hasattr(dict, attr):
            setattr(dict, attr, value)
        else:
            self[attr] = value

# returns a pair: gb: bytes, data: JSONDict
def loadRom(path):
    with open(path, "rb") as f:
        rom.readrom(f.read())
        j = JSONDict()
        j.tileset_common = getTilesetAtAddr(rom.LEVEL_TILESET_TABLE_BANK, rom.LEVEL_TILESET_COMMON)
        j.levels = []
        for i, levelname in enumerate(rom.LEVELS):
            jl = JSONDict()
            j.levels.append(jl)
            if i == 0:
                jl.index = i
                jl.name = "select"
            else:
                jl.index = i
                jl.name = levelname
                loadLevelTileset(j, i)
                loadLevelChunks(j, i)
                jl.sublevels = []
                for sublevel in range(rom.SUBSTAGECOUNT[i]):
                    jsl = JSONDict()
                    jl.sublevels.append(jsl)
                    loadSublevelScreens(j, i, sublevel)
                    loadSublevelScreenTable(j, i, sublevel)
                    loadSublevelScreenEntities(j, i, sublevel)
        return rom.data, j        

def loadSublevelScreens(j, level, sublevel):
    tiles_start_addr = readtableword(rom.BANK2, rom.LEVTAB_TILES_BANK2, level, sublevel)
    tiles_end_addr = rom.get_entry_end(rom.BANK2, rom.LEVTAB_TILES_BANK2, level, sublevel)
    assert (tiles_end_addr - tiles_start_addr) % 20 == 0
    screenc = (tiles_end_addr - tiles_start_addr) // 20
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    jsl.screens = []
    for i in range(screenc):
        js = JSONDict()
        js.data = []
        for y in range(4):
            js.data.append([])
            for x in range(5):
                js.data[y].append(readbyte(rom.BANK6, tiles_start_addr + i * 20 + y * 5 + x))
        jsl.screens.append(js)
        
CATS = ["misc", "enemies", "items"]
entmargins = dict()

def getStandardMarginForEntity(id, vertical=0):
    vertical = {0:0, 1:1, False:0, True:1}[vertical]
    if (id, vertical) in entmargins:
        lst = entmargins[(id, vertical)]
        return max(set(lst), key=lst.count)
    else:
        return 0x88 if vertical else 0xA8

def loadSublevelScreenEntities(j, level, sublevel):
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    startx, starty, vertical, layout = rom.produce_sublevel_screen_arrangement(level, sublevel)
    entstable = rom.get_entities_in_screens(level, sublevel)
    for x in range(16):
        for y in range(16):
            if layout[x][y] == 0:
                continue
            screen = layout[x][y] & 0xF
            if screen >= len(jsl.screens):
                continue
            js = jsl.screens[screen]
            for cat, ents in zip(CATS, entstable[x][y]):
                jents = []
                for ent in ents:
                    je = JSONDict()
                    je.x = ent["x"]
                    je.y = ent["y"]
                    je.type = ent["type"]
                    jents.append(je)
                    margin = ent.get("margin-x", ent.get("margin-y", ent.get("margin")))
                    if margin is not None:
                        entmargins[(vertical, je.type)] = entmargins.get((vertical, je.type), []) + [margin]
                    je.margin = margin or (0x80 if vertical == 1 else 0xA0)
                if cat in js and jents != js[cat]:
                    # Mystery: why does 3-4 split off..?
                    #print(f"screen {screen:X} appears twice in level {level}-{sublevel+1} with different entities (second appearance at {x:X},{y:X})")
                    # split out to new screen
                    js = copy.deepcopy(js)
                    screen = len(jsl.screens)
                    jsl.screens.append(js)
                    assert screen < 0xF, "too many screens after splitting screens due to differing entities"
                    jsl.layout[x][y] &= ~0x0F
                    jsl.layout[x][y] |= screen
                    js[cat] = jents
                else:
                    js[cat] = jents
    
    # set defaults
    for js in jsl.screens:
        for cat in CATS:
            if cat not in js:
                js[cat] = []
                
# screens can only appear with an edge type of 0xB/0xA/0x9 at most once
def getScreenEdgeType(j, level, sublevel, screen):
    jsl = j.levels[level].sublevels[sublevel]
    rv = 0x0
    for x in range(16):
        for y in range(16):
            c = jsl.layout[x][y]
            if c & 0x0F == screen:
                rv = c >> 4
                if rv > 8:
                    return rv
    return rv

def loadSublevelScreenTable(j, level, sublevel):
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    jsl.startx, jsl.starty, jsl.vertical, jsl.layout = rom.produce_sublevel_screen_arrangement(level, sublevel)
    
    # remove values outside of this level's screen array
    for x in range(16):
        for y in range(16):
            if jsl.layout[x][y] & 0xF >= len(jsl.screens):
                jsl.layout[x][y] = 0
                
def getLevelChunksAndGlitchChunks(j, level):
    if j.levels[level].get("chunks", None) is not None:
        chunks = j.levels[level].chunks
        if len(chunks) < 0x100 and rom.LEVELS[level+1] != "Drac3":
            return chunks + getLevelChunksAndGlitchChunks(j, level+1)
        return chunks + []
    else:
        return getLevelChunksAndGlitchChunks(j, j.levels[level].chunklink)
            
def getLevelChunks(j, level):
    if j.levels[level].get("chunks", None) is not None:
        return j.levels[level].chunks
    else:
        return getLevelChunks(j, j.levels[level].chunklink)
                
def loadLevelChunks(j, level):
    jl = j.levels[level]
    if rom.LEVELS[level] == "Drac3":
        jl.chunklink = level-1
    else:
        jl.chunks = [[0] * 16]
        chunk_start = readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
        chunk_end = rom.get_entry_end(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
        assert (chunk_end - chunk_start) % 0x10 == 0
        for i in range((chunk_end - chunk_start) // 0x10):
            chunk = [readbyte(rom.BANK2, chunk_start + i*0x10 + j) for j in range(0x10)]
            jl.chunks.append(chunk)

def getTilesetAtAddr(bank, addr):
    l = []
    while readbyte(bank, addr) != 0:
        jt = JSONDict()
        jt.destaddr = ((rom.readbyte(bank, addr) << 12) + (rom.readbyte(bank, addr + 1) << 4)) & 0xffff
        addr += 2
        jt.destlen = rom.readbyte(bank, addr) << 4
        addr += 1
        jt.srcbank = rom.readbyte(bank, addr)
        addr += 1
        jt.srcaddr = rom.readword(bank, addr)
        addr += 2
        l.append(jt)
    return l

def loadLevelTileset(j, level):
    jl = j.levels[level]
    bank = rom.LEVEL_TILESET_TABLE_BANK
    addr = readtableword(bank, rom.LEVEL_TILESET_TABLE, level)
    jl.tileset = getTilesetAtAddr(bank, addr)
    
# returns list of (level, sublevel, screen, (x, y))
# if infodepth < 4, crops the above tuples to infodepth entries.
def getChunkUsage(j, clevel, chidx, infodepth=4):
    uses = []
    for level, jl in enumerate(j.levels):
        if jl is not None and level > 0:
            if level <= clevel:
                compoffset = sum([len(getLevelChunks(j, lev))-1 for lev in range(level, clevel)])
                if compoffset + chidx >= 0x100:
                    continue
            else:
                break
            for sublevel, jsl in enumerate(jl.get("sublevels", [])):
                for screen, js in enumerate(jsl.screens):
                    for x in range(5):
                        for y in range(4):
                            if js.data[y][x] == chidx + compoffset:
                                uses += tuple([level, sublevel, screen, (y, x)][:infodepth])
    return uses

def addEmptyScreens(j):
    for jl in j.levels:
        if jl is not None and "sublevels" in jl:
            for jsl in jl.sublevels:
                for i in range(0x10 - len(jsl.screens)):
                    js = JSONDict()
                    js.data = [[0 for a in range(5)] for b in range(4)]
                    for cat in CATS:
                        js[cat] = []
                    jsl.screens.append(js)

# returns subset of {-1, 1}
def getScreenExitDoor(j, level, sublevel, screen):
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    js = jsl.screens[screen]
    chunks = getLevelChunksAndGlitchChunks(j, level)
    exits = set()
    DOORTILES = [0x17,0x18,0x19,0x1A]
    for dir, x in [(-1, 0), (1, 4)]:
        for y in range(4):
            chidx = js.data[y][x]
            if chidx < len(chunks):
                chunk = chunks[chidx]
                for i in range(4):
                    for j in range(4):
                        if chunk[i+j*4] in DOORTILES:
                            exits.add(dir)
                            break # ideally, break to outermost loop.
    return exits

# gets list of 'exits' from this screen (via ropes)
# returns subset of {(-1, 0), (1, 0), (0, -1), (0, 1)}
def getScreenPortals(j, level, sublevel, screen):
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    js = jsl.screens[screen]
    chunks = getLevelChunksAndGlitchChunks(j, level)
    ROPES = [0x1B, 0xF0, 0x28]
    portals = set()
    for x in range(5):
        for ydir, y in [(-1, 0), (1, 3)]:
            chidx = js.data[y][x]
            if chidx < len(chunks):
                chunk = chunks[chidx]
                for i in range(4):
                    j = y
                    if chunk[i+j*4] in ROPES:
                        portals.add((0, ydir))
                        break # ideally, break to outermost loop.
    return portals

def screenUsed(j, level, sublevel, screen):
    jsl = j.levels[level].sublevels[sublevel]
    for x in range(16):
        for y in range(16):
            if jsl.layout[x][y] & 0xF == screen:
                return True
    return False
    
# is there a way to enter this screen through a portal or door?
def getScreenEnterable(j, level, sublevel, x, y):
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    if (x, y) == (jsl.startx, jsl.starty):
        return True
    if jsl.layout[x][y] == 0:
        return False
    for xoff, yoff in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
        if x + xoff in range(16):
            neighbour = jsl.layout[x+xoff][(y+yoff + 16) % 16]
            if neighbour > 0:
                t = neighbour >> 4
                
                # don't count continuous scrolling
                if jsl.vertical == 1 and yoff > 0 and t in [0x8, 0x9]:
                    continue
                
                if jsl.vertical == 1 and yoff < 0 and t in [0x8, 0xA]:
                    continue
                
                if jsl.vertical == 0 and xoff > 0 and t in [0x8, 0x9]:
                    continue
                
                if jsl.vertical == 0 and xoff < 0 and t in [0x8, 0xA]:
                    continue
                
                if (-xoff, -yoff) in getScreenPortals(j, level, sublevel, neighbour & 0x0F):
                    return True
    return False

def getEnterabilityLayout(j, level, sublevel):
    return [[getScreenEnterable(j, level, sublevel, x, y) for y in range(16)] for x in range(16)]

# ------------------------------------------------------

class SaveContext:
    def __init__(self, gb, j):
        self.gb = copy.copy(gb)
        self.j = j
        self.errors = []
        self.regions = JSONDict({
            "ScreenTilesTable": {
                "shortname": "STT",
                "max": 0x4316 - 0x42C4,
                "addr": rom.LEVTAB_TILES_BANK2,
                "bank": rom.BANK2,
            }
        })
        self.regionc = JSONDict()
        for key in self.regions.keys():
            self.regions[key] = JSONDict(self.regions[key])
            self.regions[key].key = key
            self.regionc[key] = 0
    
    def romaddr(bank, addr):
        if addr < 0x4000 and bank != 0:
            raise Exception(f"Address out of bounds for bank {bank}")
        return bank * 0x4000 + addr % 0x4000
    
    def writeByte(self, bank, addr, v):
        if type(v) != int or v < 0 or v >= 0x100:
            raise Exception(f"Error with value {v}")
        self.gb[self.romaddr(bank, addr)] = v
    
    def writeWord(self, bank, addr, v, littleEndian=True):
        if littleEndian:
            self.writeByte(bank, addr, v & 0xff)
            self.writeByte(bank, addr+1, v >> 8)
        else:
            self.writeByte(bank, addr, v >> 8)
            self.writeByte(bank, addr+1, v & 0xff)
        
# returns:
#  - a list of (regionname, size, maxsize)
#  - a list of errors, or empty if successful
def saveRom(gb, j, path=None):
    assert(len(gb) > 0 and len(gb) % 0x4000 == 0)
    regions, errors = _saveRom(SaveContext(gb, j))
    if path is not None:
        try:
            with open(path, "wb") as f:
                f.write(gb)
        except IOError as e:
            errors += [f"I/O Error writing to file {path}: {e}"]
        except OSError as e:
            errors += [f"OS Error writing to file {path}: {e}"]
    return regions, errors
    
def _saveRom(cxt: SaveContext):
    try:
        writeRom(cxt)
        
        for key in cxt.regions.keys():
            c = cxt.regionc[key]
            m = cxt.regions[key]["max"]
            if c > m:
                cxt.errors.append(f"Region \"{key}\" exceeded ({c:04X} > {m:04X} bytes)")
                
        return [(key, cxt.regionc[key], cxt.regions[key]["max"]) for key in cxt.regions.keys()], cxt.errors
    except Exception as e:
        errors = [f"Fatal: {e}\n{traceback.format_exec()}"]
        regions = [(key, None, cxt.regions[key]["max"]) for key in cxt.regions.keys()]
        return regions, errors
    
def writeRom(cxt: SaveContext):
    # TODO: tileset_common (* no gui support)
    # TODO: level.tileset  (* no gui support)
    constructScreenRemapping(cxt)
    writeTilesetTable(cxt)
    
def constructScreenRemapping(cxt: SaveContext):
    cxt.screenRemapping = dict()
    cxt.screenEnterable = dict()
    cxt.screenUsed = dict()
    for i, jl in enumerate(cxt.j.levels):
        if i > 0:
            cxt.screenRemapping[i] = dict()
            cxt.screenEnterable[i] = dict()
            cxt.screenUsed[i] = dict()
            for sublevel, jsl in enumerate(jl.sublevels):
                cxt.screenRemapping[i][sublevel] = dict()
                cxt.screenEnterable[i][sublevel] = dict()
                cxt.screenUsed[i][sublevel] = dict()
                constructScreenRemappingForSublevel(cxt, i, sublevel)

def constructScreenRemappingForSublevel(cxt: SaveContext, level: int, sublevel: int):
    jsl = cxt.j.levels[level].sublevels[sublevel]
    screenMap = cxt.screenRemapping[level][sublevel]
    used = [screenUsed(level, sublevel, screen) for screen in range(0x10)]
    
    
    # screenMap: editor index -> out index
    # - skip unused screens
    # - ensure enterable screens come first
    # - deduplicate screens if possible

def writeTilesetTable(cxt: SaveContext):
    bank = cxt.ScreenTilesTable.bank
    addr = cxt.ScreenTilesTable.addr
    
    