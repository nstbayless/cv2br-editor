import rom
from rom import readword, readtablebyte, readtableword, readbyte
import copy
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
    
# returns a pair: nes: bytes, data: JSONDict
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

def saveRom(base, path):
    pass

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
                    # print(f"Warning: screen {screen} appears twice in level {level}-{sublevel} with different entities")
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