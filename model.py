import rom
from rom import readword, readtablebyte, readtableword, readbyte

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
                loadLevelChunks(j, i)
                jl.sublevels = []
                for sublevel in range(rom.SUBSTAGECOUNT[i]):
                    jsl = JSONDict()
                    jl.sublevels.append(jsl)
                    loadSublevelScreens(j, i, sublevel)
                    loadSublevelScreenTable(j, i, sublevel)
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
            
def loadSublevelScreenTable(j, level, sublevel):
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    jsl.startx, jsl.starty, jsl.vertical, jsl.layout = rom.produce_sublevel_screen_arrangement(level, sublevel)
    
    # remove values outside of this level's screen array
    for x in range(16):
        for y in range(16):
            if jsl.layout[x][y] >= len(jsl.screens):
                jsl.layout[x][y] = 0
                
def getLevelChunks(j, level):
    if j.levels[level].chunks is not None:
        return j.levels[level].chunks
    else:
        return getLevelChunks(j, j.levels[level].chunklink)
                
def loadLevelChunks(j, level):
    jl = j.levels[level]
    jl.chunks = [[0] * 16]
    if rom.LEVELS[level] == "Drac3":
        jl.chunklink = level-1
    else:
        chunk_start = readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
        chunk_end = rom.get_entry_end(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
        assert (chunk_end - chunk_start) % 0x10 == 0
        for i in range((chunk_end - chunk_start) // 0x10):
            chunk = [readbyte(rom.BANK2, chunk_start + i*0x10 + j) for j in range(0x10)]
            jl.chunks.append(chunk)

def loadLevelTileset(j, level):
    jl = j.levels[level]
    jl.tileset = []
    bank = rom.LEVEL_TILESET_TABLE_BANK
    addr = readtableword(bank, rom.LEVEL_TILESET_TABLE)
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
        jl.tileset.append(jt)