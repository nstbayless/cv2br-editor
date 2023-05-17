import rom
from rom import readword, readtablebyte, readtableword, readbyte
import copy
import traceback
import hashlib

VERSION_INT=2023041819
VERSION_NAME="v1.3"

def flatten(l):
    a = []
    for b in l:
        a += b
    return a

def gcd(*args):
    # implemented by ChatGPT
    result = args[0]
    for arg in args[1:]:
        result = gcd_two(result, arg)
    return result

def gcd_two(a, b):
    # implemented by ChatGPT
    while b != 0:
        a, b = b, a % b
    return a

def lcm(*args):
    # implemented by ChatGPT
    result = args[0]
    for arg in args[1:]:
        result = lcm_two(result, arg)
    return result

def lcm_two(a, b):
    # implemented by ChatGPT
    return a * b // gcd_two(a, b)

class JSONDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        for key, value in kwargs.items():
            self[key] = value
            
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
        j.VERSION=VERSION_INT
        j.tileset_common = getTilesetAtAddr(rom.LEVEL_TILESET_TABLE_BANK, rom.LEVEL_TILESET_COMMON)
        j.screenTilesAddr = rom.readtableword(rom.BANK2, rom.LEVTAB_TILES_BANK2, 1, 0)
        loadGlobalSpritePatches(j)
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
                    loadSublevelTimer(j, i, sublevel);
                    loadSublevelScreenTable(j, i, sublevel)
                    loadSublevelScreenEntities(j, i, sublevel)
                    loadSublevelInitRoutine(j, i, sublevel)
                    loadSublevelSpritesPatch(j, i, sublevel)
                    if sublevel >= 1:
                        loadSublevelTilesPatch(j, i, sublevel)
        j.entC4Routine = loadInitRoutine(j, rom.ENT4C_FLICKER_ROUTINE_BANK, rom.ENT4C_FLICKER_ROUTINE, maxAddr = rom.ENT4C_FLICKER_ROUTINE_END)
        j.ent78Routine = loadInitRoutine(j, rom.ENT78_FLICKER_ROUTINE_BANK, rom.ENT78_FLICKER_ROUTINE, maxaddr=rom.ENT78_FLICKER_ROUTINE_END)
        j.crusherRoutine = loadInitRoutine(j, rom.CRUSHER_ROUTINE_BANK, rom.CRUSHER_ROUTINE, maxaddr=rom.CRUSHER_ROUTINE_END)
        return rom.data, j

# returns a json object for the sprite located at the given address
# also returns the address of the end of the sprite
def readSprite(bank, addr):
    jsprite = JSONDict({
        "tileCount": rom.readbyte(bank, addr),
        "tiles": []
    })
    addr += 1
    for t in range(jsprite.tileCount):
        jtile = JSONDict()
        jsprite.tiles.append(jtile)
        jtile.yoff = rom.readSignedByte(bank, addr)
        addr += 1
        jtile.xoff = rom.readSignedByte(bank, addr)
        addr += 1
        jtile.tidx = rom.readbyte(bank, addr)
        addr += 1
        if jtile.tidx & 1 == 1:
            jtile.tidx &= ~1
            jtile.flags = rom.readbyte(bank, addr)
            addr += 1
    return jsprite, addr

# each sublevel (other than 0) edits/patches a portion of the vram tile palette
# we presume this is only to change the sprites available
def loadSublevelTilesPatch(j, level, sublevel):
    assert sublevel >= 1, "sublevel 0 does not patch tiles"
    if rom.ROMTYPE not in ["us", "jp"]:
        return
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    bank = 0
    addr = readtableword(bank, rom.SUBLEVEL_TILES_PATCH_TABLE, level, sublevel-1)
    jsl.tilePatches = []
    count = rom.readbyte(bank, addr)
    addr += 1
    for i in range(count):
        jpatch = JSONDict()
        idx = rom.readbyte(bank, addr + i)
        patchaddr = idx + rom.TILES_PATCH_LIST
        jpatch.count = rom.readbyte(bank, patchaddr)
        jpatch.bank = rom.readbyte(bank, patchaddr+1)
        jpatch.source = rom.readword(bank, patchaddr+2)
        jpatch.dst = rom.readword(bank, patchaddr+4)
        jsl.tilePatches.append(jpatch)

# each sublevel edits/patches a portion of the sprite lookup table, which is at $DF00-$DFFF in WRAM.
def loadSublevelSpritesPatch(j, level, sublevel):
    if rom.ROMTYPE not in ["us", "jp"]:
        return
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    bank = rom.BANK3
    patchstructaddr = readtableword(bank, rom.SPRITE_PATCH_TABLE, level) + 4*sublevel
    count = rom.readbyte(bank, patchstructaddr)
    start = rom.readbyte(bank, patchstructaddr+1)
    source = rom.readword(bank, patchstructaddr+2)
    if count != 0:
        jsl.spritePatch = JSONDict({
            "startidx": start,
            "sprites": []
        })
        for i in range(count):
            ptr = rom.readword(bank, source + 2*i)
            sprite, end = readSprite(bank, ptr)
            jsl.spritePatch.sprites.append(sprite)

def readSpritePatchRoutine(bank, addr):
    # ld hl, xxxx
    source = rom.readword(bank, addr+1)
    addr += 3
    
    # ld a, xx
    start = rom.readbyte(bank, addr+1)
    addr += 2
    
    # ld b, xx
    count = rom.readbyte(bank, addr+1)
    
    assert(count > 0)
    
    jpatch = JSONDict({
        "startidx": start,
        "sprites": []
    })
    
    for i in range(count):
        ptr = rom.readword(bank, source + 2*i)
        sprite, end = readSprite(bank, ptr)
        jpatch.sprites.append(sprite)
    
    # (jr $7048)
    return jpatch
    
def loadGlobalSpritePatches(j):
    bank = rom.BANK3
    addr = rom.LOAD_SPRITES_ROUTINES
    if rom.ROMTYPE not in ["us", "jp"]:
        return
    j.globalSpritePatches = JSONDict({
        "init": readSpritePatchRoutine(bank, addr),
        "title": readSpritePatchRoutine(bank, addr+9),
        "unk2": readSpritePatchRoutine(bank, addr+18),
        "unk3": readSpritePatchRoutine(bank, addr+27),
    })

def loadSublevelInitRoutine(j, level, sublevel):
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    bank = rom.BANK3
    addr = readtableword(bank, rom.VRAM_SPECIAL_ROUTINES, level, sublevel)
    jsl.initRoutines = loadInitRoutine(j, bank, addr, level)

def loadInitRoutine(j, bank, addr, level=None, **kwargs):
    r = []
    
    maxaddr = kwargs.get("maxaddr", None)
    
    while True:
        if maxaddr is not None and addr >= maxaddr:
            return r
        assert len(r) < 10 # seems reasonable
        if rom.readbyte(bank, addr) == 0xC9: # ret
            return r
        elif rom.readword(bank, addr + 1) == rom.UNK_254:
            r.append(JSONDict({"type": "UNK254"}))
            addr += 8
        elif rom.readword(bank, addr + 1) == rom.UNK_7001:
            # length of this one depends on rom type
            # too complicated, but it's only ever alone like so,
            # so we just call it here.
            r.append(JSONDict({"type": "UNK7001"}))
            return r
        elif rom.readbyte(bank, addr+1) == 0x20:
            r.append(JSONDict({"type": "CNTEFFECT", "effect": 0x0f, "scanline": 0x10}))
            addr += 11
            if rom.readbyte(bank, addr-3) == 0xC3: # jp
                break
        elif rom.readbyte(bank, addr+1) == 0x1B:
            r.append(JSONDict({"type": "UNKD802"}))
            addr += 8
        elif rom.readbyte(bank, addr+6) == 0xFA:
            de = [0, 0]
            hl = [0, 0]
            de[0] = rom.readword(bank, addr+1)
            hl[0] = rom.readword(bank, addr+1+3)
            de[1] = rom.readword(bank, addr+13+1)
            hl[1] = rom.readword(bank, addr+13+1+3)
            cplvl = rom.readbyte(bank, addr+10)
            bc = rom.readword(bank, addr+19+1)
            addr += 25
            
            if level is not None:
                assert hl == rom.readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
            else:
                for i in range(len(rom.LEVELS)):
                    if rom.readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, i) == hl[0] and i > 0:
                        level = i
                        break
            assert level is not None
            assert hl[1] == rom.readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, cplvl)
            
            levels = [level, cplvl]
            
            screendata = [None, None]
            linkscreen = [None, None]
            
            levelRoutineSpec = []
            for i in range(2):
                screendata[i] = [rom.readbyte(rom.BANK6, de[i]+j) for j in range(20)]
                for _level, jl in enumerate(j.levels):
                    if _level != 0:
                        for sublevel, jsl in enumerate(jl.sublevels):
                            for screen, js in enumerate(jsl.screens):
                                if js.data == screendata:
                                    linkscreen[i] = (_level, sublevel, screen)
                                    screendata[i] = None
                levelRoutineSpec.append(JSONDict({
                    "srcAddr": de[i],
                    "level": levels[i]
                }))
                if screendata[i] is not None:
                    levelRoutineSpec[-1].data = screendata[i]
                if linkscreen[i] is not None:
                    levelRoutineSpec[-1].data = linkscreen[i]
            
            r.append(JSONDict({"type": "LVLSCREEN", "dstAddr": bc, "levels": levelRoutineSpec}))
            if rom.readbyte(bank, addr-3) == 0xC3: # jp
                break
                
        elif rom.readbyte(bank, addr) == 0x11:
            de = rom.readword(bank, addr+1)
            hl = rom.readword(bank, addr+1+3)
            bc = rom.readword(bank, addr+1+6)
            assert type(bc) == int
            
            if level is not None:
                assert hl == rom.readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
            else:
                for i in range(len(rom.LEVELS)):
                    if rom.readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, i) == hl and i > 0:
                        level = i
                        break
            assert level is not None
            
            screendata = [rom.readbyte(rom.BANK6, de+i) for i in range(20)]
            
            r.append(JSONDict({"type": "SCREEN", "dstAddr": bc, "data": screendata, "srcAddr": de, "level": level}))
                
            # instead of data, link to an existing screen if possible
            linkscreen = None
            for _level, jl in enumerate(j.levels):
                if _level != 0:
                    for sublevel, jsl in enumerate(jl.sublevels):
                        for screen, js in enumerate(jsl.screens):
                            if js.data == screendata:
                                linkscreen = (_level, sublevel, screen)
            
            if linkscreen is not None:
                r[-1].linkscreen = linkscreen
                del r[-1]["data"]
            
            addr += 3*4
            
            # exception -- these seem to be spurious! Pop these.
            if (level, sublevel) in [(1, 0)]:
                r = r[:-1]
            
            if rom.readbyte(bank, addr-3) == 0xC3: # jp
                break
        else:
            assert False, f"unrecognized routine at {bank:X}:{addr:04X}"
    return r

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
                    je.slot = ent["slot"]
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
                                uses.append(tuple([level, sublevel, screen, (y, x)][:infodepth]))
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
    ROPES = [0x1B]
    # FIXME: find the way that secret ropes occur... probably by entities?
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
    if jsl.layout[x][y] >> 4 == 0xB:
        # we just assume that all 1x1 enclosed screens are enterable
        # surely the user would remove it if it weren't..?
        # This saves us from having to check for hidden ropes, as in the base game they all connect to 1x1 rooms.
        return True
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

def loadSublevelTimer(j, level, sublevel):
    jl = j.levels[level]
    jsl = jl.sublevels[sublevel]
    levelTimerPointer = rom.readword(rom.BANK3, rom.LEVEL_TIMER_TABLE + level*2) # fetch timer table of the level
    levelTimerPointerData = rom.readbyte(rom.BANK3, levelTimerPointer + sublevel) # fetch sublevel timer value
    jsl.timer = levelTimerPointerData

# ------------------------------------------------------

class SaveContext:
    def __init__(self, gb, j, **kwargs):
        self.gb = list(copy.copy(gb))
        self.j = j
        self.playtestStart = kwargs.get("playtestStart", None)
        self.errors = []
        self.regions = JSONDict({
            "ScreenTilesTable": {
                "shortname": "ST",
                "max": 0x4316 - 0x42C4,
                "addr": rom.LEVTAB_TILES_BANK2,
                "bank": rom.BANK2,
            },
            # could combine this with the above, which ends at the same spot
            # we just need to adjust calls to the routine at $4316
            "SublevelVertical": {
                "shortname": "SV",
                "max":  0x4339 - 0x4316,
                "addr": rom.LEVEL_SCROLLDIR_TABLE-10, # routine before this table is 10 bytes, and we rewrite it.
                "bank": rom.BANK2,
            },
            "ChunkTable": {
                "shortname": "CT",
                "max": 0x10,
                "addr": rom.LEVTAB_TILES4x4_BANK2,
                "bank": rom.BANK2,
            },
            "ChunkValues": {
                "shortname": "CV",
                "max": 0x6500 - 0x44C0 + 0x820,
                "addr": rom.TILES4x4_BEGIN,
                "bank": rom.BANK2,
                "units": ("chunk",),
                "unitdiv": 0x10,
            },
            # could combine the next four into one if we edit the accesses to their base addresses.
            "Entmisc": {
                "shortname": "EM",
                "max": rom.LEVTAB_B - rom.LEVTAB_A,
                "addr": rom.LEVTAB_A,
                "bank": rom.BANK3,
            },
            "Entenemies": {
                "shortname": "EE",
                "max": rom.LEVTAB_C - rom.LEVTAB_B,
                "addr": rom.LEVTAB_B,
                "bank": rom.BANK3,
            },
            "Entitems": {
                "shortname": "EI",
                "max": rom.SCREEN_ENT_TABLE - rom.LEVTAB_C,
                "addr": rom.LEVTAB_C,
                "bank": rom.BANK3,
            },
            "EntLookup": {
                "shortname": "EL",
                "max": 0x6991 - 0x62C1,
                "addr": rom.SCREEN_ENT_TABLE,
                "bank": rom.BANK3,
            },
            "SublevelInitRoutines": {
                "shortname": "SI",
                "max": rom.VRAM_SPECIAL_ROUTINES_END - rom.VRAM_SPECIAL_ROUTINES + 7,
                "addr": rom.VRAM_SPECIAL_ROUTINES - 7,
                "bank": rom.BANK3,
            },
            "ScreenTiles": {
                "shortname": "ZT",
                "max": 0x73F8 - 0x62B4 + 20 * 5,
                "addr": j.screenTilesAddr,
                "bank": rom.BANK6,
                "units": ("screen",),
                "unitdiv": 20,
            },
            "Layouts": {
                "shortname": "L",
                "max": 0x52C1 - 0x5020 + 12,
                "addr": rom.LEVEL_SCREEN_TABLE,
                "bank": rom.BANK6,
            },
            # this routine loads a screen (on cloud castle), so we need to modify it
            "EntC4Routine": {
                "shortname": "CF",
                "max": rom.ENT4C_FLICKER_ROUTINE_END - rom.ENT4C_FLICKER_ROUTINE,
                "addr": rom.ENT4C_FLICKER_ROUTINE,
                "bank": rom.ENT4C_FLICKER_ROUTINE_BANK,
            },
            # as above, but rock castle
            "Ent78Routine": {
                "shortname": "RF",
                "max": rom.ENT78_FLICKER_ROUTINE_END - rom.ENT78_FLICKER_ROUTINE,
                "addr": rom.ENT78_FLICKER_ROUTINE,
                "bank": rom.ENT78_FLICKER_ROUTINE_BANK,
            },
            "CrusherRoutine": {
                "shortname": "CR",
                "max": rom.CRUSHER_ROUTINE_END - rom.CRUSHER_ROUTINE,
                "addr": rom.CRUSHER_ROUTINE,
                "bank": rom.CRUSHER_ROUTINE_BANK,
            },
            "SublevelTime": {
                "shortname": "ST",
                "max": 0x31,
                "addr": rom.LEVEL_TIMER_TABLE,
                "bank": rom.BANK3
            }
        })
        for key in self.regions.keys():
            self.regions[key] = JSONDict(self.regions[key])
            self.regions[key].key = key
            self.regions[key].name = key
            self.regions[key].used = 0
            self.regions[key].subranges = JSONDict()
        
        # maps (level, sublevel) -> list[(x, y, l)]
        self.uniqueScreens = dict()
        
        # maps (level, sublevel, x, y) -> index in ctx.uniqueScreens[sublevel, level]
        self.screenRemap = dict()
        
        # maps (level, sublevel) -> int (index into self.uniqueScreens[(level, sublevel)])
        self.numPriorityUniqueScreens = dict()
        
        # maps (level, sublevel, cat, uscreen) -> 
        self.enterableScreenData = dict()
        
        self.sublevelInitSubroutines = dict()
    
    # returns screen, js
    def getUniqueScreenOriginalScreen(self, level, sublevel, uscreen):
        key = (level, sublevel)
        assert key in self.uniqueScreens
        s = self.uniqueScreens[key][uscreen][2] & 0xF
        return s, self.j.levels[level].sublevels[sublevel].screens[s]
    
    def romaddr(self, bank, addr):
        if (addr < 0x4000 and bank != 0) or (addr >= 0x4000 and bank == 0) or addr >= 0x8000:
            raise Exception(f"Address {addr:04X} out of bounds for bank {bank:X}")
        return bank * 0x4000 + addr % 0x4000
    
    def writeBytes(self, bank, addr, bl):
        for b in bl:
            self.writeByte(bank, addr, b)
            addr += 1
    
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
    
    def readByte(self, bank, addr):
        return self.gb[self.romaddr(bank, addr)]
    
    def readWord(self, bank, addr, littleEndian=True):
        if littleEndian:
            return self.readByte(bank, addr) | (self.readByte(bank, addr+1) << 8)
        else:
            return self.readByte(bank, addr+1) | (self.readByte(bank, addr) << 8)
        
# returns:
#  - a list of (regionname, size, maxsize)
#  - a list of errors, or empty if successful
def saveRom(gb, j, path=None, **kwargs):
    assert(len(gb) > 0 and len(gb) % 0x4000 == 0)
    ctx = SaveContext(gb, j, **kwargs)
    
    _saveRom(ctx)
    regions, errors, gb = ctx.result
    if path is not None and gb is not None:
        try:
            with open(path, "wb") as f:
                f.write(gb)
        except IOError as e:
            errors += [f"I/O Error writing to file {path}: {e}"]
        except OSError as e:
            errors += [f"OS Error writing to file {path}: {e}"]
    return regions, errors
    
def _saveRom(ctx: SaveContext):
    try:
        writeRom(ctx)
        
        for key in ctx.regions.keys():
            c = ctx.regions[key].used
            m = ctx.regions[key].max
            if c > m:
                ctx.errors.append(f"Region \"{key}\" exceeded ({c:04X} > {m:04X} bytes)")
        ctx.result = [ctx.regions[key] for key in ctx.regions.keys()], ctx.errors, bytes(ctx.gb)
    except Exception as e:
        errors = [f"Fatal: {e}\n{traceback.format_exc()}"]
        for key, region in ctx.regions.items():
            region.used = None
            region.subranges = {}
        regions = [ctx.regions[key] for key in ctx.regions.keys()]
        ctx.result = regions, errors, None
    
def writeRom(ctx: SaveContext):
    # TODO: tileset_common (* no gui support)
    # TODO: level.tileset  (* no gui support)
    constructScreenRemapping(ctx)
    writeScreenTiles(ctx)
    writeScreenLayout(ctx)
    writeSublevelTimer(ctx)
    writeSublevelVertical(ctx)
    writeEntities(ctx)
    writeChunks(ctx)
    
    if ctx.playtestStart is not None:
        writePlaytestStart(ctx, *ctx.playtestStart)
    
    # this one reads some of the screenTiles from before
    writeSublevelInitRoutines(ctx)
    
    writeEntLoadRoutine(ctx, ctx.regions.EntC4Routine, ctx.j.entC4Routine, label="EntC4")
    writeEntLoadRoutine(ctx, ctx.regions.Ent78Routine, ctx.j.ent78Routine, False, label="Ent78")
    writeEntLoadRoutine(ctx, ctx.regions.CrusherRoutine, ctx.j.crusherRoutine, False, label="Crusher")
    
    # do this one last, it's an opportunist
    writeLoadEnclosedScreenEntityBugfixPatch(ctx)
    
    writeLoadLayoutPatch(ctx)

# basically just for cloud castle flicker preview at door to final sublevel
def requiresVerticalPreview(jsl):
        for routine in jsl.initRoutines:
            if routine.type == "SCREEN" and routine.dstAddr == 0x9A00:
                return True
        return False

def constructScreenRemapping(ctx: SaveContext):
    for i, jl in enumerate(ctx.j.levels):
        if i > 0:
            for sublevel, jsl in enumerate(jl.sublevels):
                constructScreenRemappingForSublevel(ctx, i, sublevel)

def constructScreenRemappingForSublevel(ctx: SaveContext, level: int, sublevel: int):
    jl = ctx.j.levels[level]
    jsl = jl.sublevels[sublevel]
    enterable = getEnterabilityLayout(ctx.j, level, sublevel)
    
    # screenMap: coords -> out index
    # - skip unused screens
    # - ensure enterable screens come first
    # - deduplicate screens if possible
    screenCoords = []
    for x in range(16):
        for y in range(16):
            l = jsl.layout[x][y]
            if l > 0:
                screenCoords.append((x, y))
    
    # screens are combinable if:
    # - they have the same tiles, and
    # - either of them is not enterable, or
    # - both are enterable, but both also appear in identical continuous rooms at the same x value (y if vertical)
    # - the last condition is a lot of work to check, so instead we simplify it to
    #   "both are enclosed (0xB*)"
    
    def combinable(x1, y1, x2, y2):
        l1 = jsl.layout[x1][y1]
        l2 = jsl.layout[x2][y2]
        e1 = enterable[x1][y1]
        e2 = enterable[x2][y2]
        t1 = l1 >> 4
        t2 = l2 >> 4
        s1 = l1 & 0x0F
        s2 = l2 & 0x0F
        js1 = jsl.screens[s1]
        js2 = jsl.screens[s2]
        
        if js1.data == js2.data: # tiles the same
            if not e1 or not e2:
                return True
            else:
                assert e1 and e2
                return t1 == 0xB and t2 == 0xB
                
        return False
    
    uniqueScreens = []
    uniqueScreensPriority = []
    
    def getPriority(x, y):
        priority = 0 if enterable[x][y] else 2
        if (x, y) == (jsl.startx, jsl.starty):
            priority = -2
        if sublevel > 0:
            # TODO: we can do slightly better by figuring out which of (x-1,y) and (x+1,y) is relevant,
            # given direction previous sublevel exits.
            if (jsl.startx, jsl.starty) in [(x-1, y), (x+1, y)]:
                priority -= 1
            elif (jsl.startx, jsl.starty) in [(x, y-1), (x+1, y)] and requiresVerticalPreview(jsl):
                priority -= 1
        return priority
    
    for i, (x, y) in enumerate(screenCoords):
        l = jsl.layout[x][y]
        if not screenUsed(ctx.j, level ,sublevel, l & 0x0F):
            continue
        else:
            for j, (x2, y2) in enumerate(screenCoords[:i]):
                if combinable(x, y, x2, y2):
                    uscreen = ctx.screenRemap[(level, sublevel, x2, y2)]
                    ctx.screenRemap[(level, sublevel, x, y)] = uscreen
                    uniqueScreensPriority[uscreen] = min(getPriority(x, y), uniqueScreensPriority[uscreen])
                    break
            else:
                ctx.screenRemap[(level, sublevel, x, y)] = len(uniqueScreens)
                uniqueScreensPriority.append(getPriority(x, y))
                uniqueScreens.append((x, y, l))
    
    if len(uniqueScreens) >= 0x10:
        levelname = rom.LEVELS[level]
        raise Exception(f"Level {levelname} Sublevel {sublevel} requires {len(uniqueScreens)} screens to fully represent uniqueness of screens in layout, but 16 is the max.")
    
    numPrioritizedScreens = sum([p <= 0 for p in uniqueScreensPriority])
    numNonPrioritizedPreviewScreens = sum([p == 1 for p in uniqueScreensPriority])
    if numNonPrioritizedPreviewScreens > 0 and sublevel > 0:
        #print(level, sublevel+1, uniqueScreensPriority)
        if len(jl.sublevels[sublevel-1]) + numPrioritizedScreens + numNonPrioritizedPreviewScreens > 0x10:
            # move preview screens so that they are at the start
            # unusual behaviour, so let's print it out in case it causes problems.
            print(f"{rom.LEVELS[level]}-{sublevel+1} - Remapping some screen IDs to allow previous sublevel access to the start-adjacent room(s)...")
            print("<- ", level, sublevel+1, uniqueScreensPriority)
            uniqueScreensPriority = [(u if u != 1 else -1) for u in uniqueScreensPriority]
            print(" -> ", level, sublevel+1, uniqueScreensPriority)
    
    ctx.numPriorityUniqueScreens[(level, sublevel)] = sum([p <= 0 for p in uniqueScreensPriority])
    
    # remap unique screens to ensure the enterable ones come first, and starting room is the very first.
    remapEnterable = sorted(list(range(len(uniqueScreens))), key=lambda i: uniqueScreensPriority[i])
    remapEnterableIndices = [remapEnterable.index(i) for i in range(len(uniqueScreens))]
    #if level == 4 and sublevel == 1:
    #    print(uniqueScreens, "|", remapEnterable)
    #    for (_level, _sublevel, x, y), v in ctx.screenRemap.items():
    #        if _level == level and _sublevel == sublevel:
    #            print(x, y, v)
    
    # apply remapping
    for x, y in screenCoords:
        ctx.screenRemap[(level, sublevel, x, y)] = remapEnterableIndices[ctx.screenRemap[(level, sublevel, x, y)]]
    
    ctx.uniqueScreens[(level, sublevel)] = [uniqueScreens[remapEnterable[i]] for i in range(len(uniqueScreens))]
    
    #if level == 7:
    #    printRemappedScreenLayout(ctx, level, sublevel)

def printRemappedScreenLayout(ctx, level, sublevel):
    jsl = ctx.j.levels[level].sublevels[sublevel]
    uniqueScreens = ctx.uniqueScreens[(level, sublevel)]
    
    x1, x2, y1, y2 = rom.get_screensbuff_boundingbox(jsl.layout)
    print(f"{rom.LEVELS[level]}-{sublevel+1}:")
    for y in range(y1, y2):
        s = ";"
        for x in range(x1, x2):
            if jsl.layout[x][y] > 0:
                i = ctx.screenRemap[(level, sublevel, x, y)]
                assert i < len(uniqueScreens)
                l = (jsl.layout[x][y] & 0xF0) | i
                s += f" {l:02X}"
            else:
                s += "   "
        print(s)

def writeScreenTiles(ctx: SaveContext):
    tbank = ctx.regions.ScreenTilesTable.bank
    taddr = ctx.regions.ScreenTilesTable.addr
    bank = ctx.regions.ScreenTiles.bank
    addr = ctx.regions.ScreenTiles.addr
    subranges = ctx.regions.ScreenTiles.subranges
    
    tsaddr = taddr + len(ctx.j.levels)*2
    for level, jl in enumerate(ctx.j.levels):
        if level == 0:
            taddr += 2
        else:
            ctx.writeWord(tbank, taddr, tsaddr)
            taddr += 2
            for sublevel, jsl in enumerate(jl.sublevels):
                subrangekey = f"{jl.name}-{sublevel+1}"
                subranges[subrangekey] = JSONDict(start=addr)
                ctx.writeWord(tbank, tsaddr, addr)
                tsaddr += 2
                for uscreen, uscm in enumerate(ctx.uniqueScreens[(level, sublevel)]):
                    oscreen, js = ctx.getUniqueScreenOriginalScreen(level, sublevel, uscreen)
                    for y in range(4):
                        for x in range(5):
                            # TODO: remap chunks also :)
                            ctx.writeByte(bank, addr, js.data[y][x])
                            addr += 1
                subranges[subrangekey].end = addr
    ctx.regions.ScreenTilesTable.used = tsaddr - ctx.regions.ScreenTilesTable.addr
    ctx.regions.ScreenTiles.used = addr - ctx.regions.ScreenTiles.addr

# gives a (massive) over-approximation in cover sets for this sublevel
def constructScreenCoverSets(ctx: SaveContext, level, sublevel):
    # constructs a set of segments of screens
    # each segment has a startx, starty, stride, and list of screens.
    # smallest screen layout requires solving the set-cover problem.
    # we wish to use the fewest number of segments to describe the layout.
    
    # (we could consider this a weighted set-cover problem, but assuming that
    # we can cover everything with no overlap, we can subtract the non-constant
    # portion of the weights -- the number of screens -- from each set)
    
    # This is NP complete, so we use an approximation.
    
    csets = []
    cvalues = set()
    MAXMARGIN = 5 # because every packet requires 4 bytes of padding
    layout = constructRemappedLayout(ctx, level, sublevel, True)
    for x in range(16):
        for y in range(16):
            if layout[x][y] > 0:
                cvalues.add((x, y))
                cset = []
                for xoff in range(0x10):
                    if not any(layout[(x + xoff + i) % 0x10][y] for i in range(MAXMARGIN)):
                        break
                    else:
                        if layout[(x + xoff) % 0x10][y] > 0:
                            cset.append(((x + xoff) % 0x10, y))
                        else:
                            cset.append(((x + xoff) % 0x10, y, 0))
                        csets.append(copy.copy(cset))
                cset = []
                for yoff in range(0x10):
                    if not any(layout[x][(y + yoff + i) % 0x10] for i in range(MAXMARGIN)):
                        break
                    else:
                        if layout[x][(y + yoff) % 0x10] > 0:
                            cset.append((x, (y + yoff) % 0x10))
                        else:
                            cset.append((x, (y + yoff) % 0x10, 0))
                        csets.append(copy.copy(cset))
    return cvalues, csets

def constructRemappedLayout(ctx: SaveContext, level, sublevel, preview=False):
    jl = ctx.j.levels[level]
    jsl = jl.sublevels[sublevel]
    layout = copy.deepcopy(jsl.layout)
    
    for x in range(16):
        for y in range(16):
            if jsl.layout[x][y] == 0 and x == jsl.startx and y == jsl.starty:
                ctx.errors += [f"{jl.name}-{sublevel+1}: Start screen ({jsl.startx}, {jsl.starty}) is empty"]
            if jsl.layout[x][y] > 0:
                layout[x][y] &= 0xF0
                assert ctx.screenRemap[(level, sublevel, x, y)] < 0x10
                layout[x][y] |= ctx.screenRemap[(level, sublevel, x, y)] & 0x0F
                if preview:
                    for xoff in getScreenExitDoor(ctx.j, level, sublevel, jsl.layout[x][y] & 0xF):
                        if jsl is jl.sublevels[-1]:
                            ctx.errors += "Sublevel door on final sublevel of {jl.name}"
                        else:
                            jsl2 = jl.sublevels[sublevel+1]
                            previewDown = 1 if requiresVerticalPreview(jsl2) else 0
                            for i in range(2):
                                for j in range(1 + previewDown):
                                    key = (level, sublevel+1, jsl2.startx + xoff*i, jsl2.starty + j)
                                    nextsublevelscreen = ctx.screenRemap[key] if key in ctx.screenRemap else None
                                    if nextsublevelscreen is not None:
                                        #print(level, sublevel, f"{nextsublevelscreen:02X}", len(ctx.uniqueScreens[(level, sublevel)]))
                                        nextsublevelscreent = (nextsublevelscreen & 0x0F) + len(ctx.uniqueScreens[(level, sublevel)])
                                        if nextsublevelscreent >= 0x10:
                                            ctx.errors += [f"{rom.LEVELS[level]}-{sublevel+1} uses more than 15 unique screens when including preview screens for {rom.LEVELS[level]}-{sublevel+2}"]
                                        _x = (x + xoff*(i+1) + 0x10) % 0x10
                                        _y = (y + j + 0x10) % 0x10
                                        if layout[_x][_y] > 0:
                                            ctx.errors += [f"Unable to place next-sublevel-preview screen for {rom.LEVELS[level]}-{sublevel+1}, as it is coincident with an existing screen."]
                                        else:
                                            layout[_x][_y] = nextsublevelscreent | 0x80
    return layout
                
def produceScreenLayoutPackets(ctx: SaveContext, level, sublevel, addr):
    if level == 0:
        return None
    jsl = ctx.j.levels[level].sublevels[sublevel]
    layout = constructRemappedLayout(ctx, level, sublevel, True)
    cvalues, csets = constructScreenCoverSets(ctx, level, sublevel)
    outsets = []
    def sortkey(cset):
        # TODO: actually sensible sortkey
        value = 0
        for op in cset:
            if len(op) == 2:
                value += 1
        return value
    while len(cvalues) > 0:
        assert len(csets) > 0
        csets.sort(key=sortkey)
        cset = csets[-1]
        csets = csets[:-1]
        outsets.append(copy.copy(cset))
        removed = 0
        for c in cset:
            if len(c) == 2:
                removed += 1
                if c in cvalues:
                    cvalues.remove(c)
            for _cset in csets:
                if c in _cset:
                    _cset.remove(c)
        assert removed > 0
        csets = list(filter(lambda cset: any([len(c) == 2 for c in cset]), csets))
    
    packets = []
    for outset in outsets:
        coords = list(filter(lambda coord: len(coord) == 2, outset))
        assert len(coords) > 0
        startx, starty = coords[0]
        stride = 0
        if len(coords) > 0:
            vs = [y * 0x10 + x for (x, y) in coords]
            pvs = copy.copy(vs)
            for i, v in enumerate(vs):
                if i > 0:
                    while vs[i] < vs[i-1]:
                        vs[i] += 0x100
            for i, v in reversed(list(enumerate(vs))):
                vs[i] -= vs[0]
            stride = gcd(*vs)
            #if stride not in [0, 1, 0x10]:
            #    print(level, sublevel, stride, ":", *coords, "|", *pvs, "|", *vs)
        assert type(stride) == int
        i = 0
        
        entries = []
        x, y = startx, starty
        for i in range(0x100):
            entries.append(layout[x][y])
            if (x, y) == coords[-1]:
                break
            x += stride % 0x10
            y += stride // 0x10
            x %= 0x10
            y %= 0x10
        
        packets.append([
            # write address
            startx | (starty << 4),
            # the usual routine requires this always-the-same byte. But we patch the ROM so it isn't required anymore.
            #0xDD,
            
            stride,
            *entries,
            0xFE # terminator
        ])
        
    # final terminator is 0xFF
    if len(packets) > 0:
        packets[-1][-1] = 0xFF
        
    return [jsl.startx, jsl.starty] + flatten(packets)

def writeScreenLayout(ctx: SaveContext):
    addr = ctx.regions.Layouts.addr
    bank = ctx.regions.Layouts.bank
    addr = writeSublevelTableData(ctx, addr, bank, produceScreenLayoutPackets)
    ctx.regions.Layouts.used = addr - ctx.regions.Layouts.addr

def rrange(a, b):
    return range(b-1,a-1,-1)

def writeLevelTableData(ctx: SaveContext, addr, bank, cb, **kwargs):
    taddr = addr
    addr += len(ctx.j.levels)*2
    
    for level, jl in enumerate(ctx.j.levels):
        if level == 0:
            taddr += 2
        else:
            ctx.writeWord(bank, taddr, addr)
            taddr += 2
            v = cb(ctx, level, addr)
            for byte in v:
                ctx.writeByte(bank, addr, byte)
                addr += 1
    return addr

def writeSublevelTableData(ctx: SaveContext, addr, bank, cb, **kwargs):
    allowMerging = kwargs.get("allowMerging", False)
    tableAtStart = kwargs.get("tableAtStart", False)
    sbbase = kwargs.get("singleByteAddressBase", None)
    taddr = addr
    addr += len(ctx.j.levels)*2
    
    if tableAtStart:
        tsaddr = addr
        total_sublevels = sum(len(jl.sublevels) for jl in ctx.j.levels[1:])
        addr += total_sublevels * (1 if sbbase is not None else 2)
    
    orgaddr = addr
    
    for level, jl in enumerate(ctx.j.levels):
        if level == 0:
            taddr += 2
        else:
            if not tableAtStart:
                tsaddr = addr
                addr += len(jl.sublevels) * (1 if sbbase is not None else 2)
            ctx.writeWord(bank, taddr, tsaddr)
            taddr += 2
            for sublevel, jsl in enumerate(jl.sublevels):
                def writeSubtableByte(addr):
                    if sbbase is None:
                        ctx.writeWord(bank, tsaddr, addr)
                    else:
                        ctx.writeByte(bank, tsaddr, addr - sbbase)
                writeSubtableByte(addr)
                rv = cb(ctx, level, sublevel, addr)
                replaceAddr = None
                if type(rv) is tuple:
                    hunk, replaceaddr = rv
                    if replaceaddr is not None:
                        writeSubtableByte(replaceaddr)
                else:
                    hunk = rv
                if replaceAddr is None and allowMerging and len(hunk) > 0:
                    hunk0 = hunk[0]
                    mergeAddr = None
                    lhunk = len(hunk)
                    for iaddr in rrange(orgaddr, addr - lhunk+1):
                        if hunk0 == ctx.readByte(bank, iaddr):
                            if hunk == [ctx.readByte(bank, iaddr + i) for i in range(lhunk)]:
                                mergeAddr = iaddr
                                break
                    if mergeAddr is not None:
                        writeSubtableByte(mergeAddr)
                        tsaddr += 1 if sbbase is not None else 2
                        continue
                tsaddr += 1 if sbbase is not None else 2
                #if cb == produceSublevelInitRoutine and len(hunk) > 0:
                #    print(level, sublevel, len(hunk), [f"{h:02X}" for h in hunk])
                for b in hunk:
                    ctx.writeByte(bank, addr, b)
                    addr += 1
    return addr

def writeSublevelTimer(ctx: SaveContext):
    if rom.ROMTYPE != "us":
        return
    
    bank = ctx.regions.SublevelTime.bank
    addr = ctx.regions.SublevelTime.addr
    
    addr = writeLevelTableData(
        ctx, addr, bank,
        lambda ctx, level, addr: [sublevel.timer for sublevel in ctx.j.levels[level].sublevels]
    )
    
    ctx.regions.SublevelTime.used = addr - ctx.regions.SublevelTime.addr

def writeSublevelVertical(ctx: SaveContext):
    # the old routine at 2:4316 was too restrictive and compressed.
    # solving the shortest-superstring problem is too hard and unlikely to be small.
    # we introduce an entirely new routine for loading this bit.
    """
    set_sublevel_vertical:
        ld a, ($c8c1)  ; 3 ; (or c8c0 if sublevel-major)
        ld b, a        ; 1
        ; inc b if sublevel-major
        ld hl, table   ; 3
        ld a, ($c8c0)  ; 3  ; (or c8c1 if sublevel-major)
        rst $28        ; 1
        ld a, (hl)     ; 1
        
    routine:
        add a, a       ; 1
        dec b          ; 1
        jr nz, routine ; 1

    done:
        sbc a, a       ; 1
        inc a          ; 1
        ld ($ca95), a  ; 3
        ret            ; 1

    table:
    """
    
    addr = ctx.regions.SublevelVertical.addr
    bank = ctx.regions.SublevelVertical.bank
    
    level_count = len(ctx.j.levels)-1
    sublevel_count = max([len(jl.sublevels) for jl in ctx.j.levels[1:]])
    
    # we prefer sublevel-major because we can save an 'inc b' operation
    level_major = level_count > 8
    if level_major and sublevel_count > 8:
        # In this case, we can fall back on another routine...?
        raise Exception("sublevel vertical routine requires either a maximum of 8 sublevels *or* 8 levels")
    
    ROUTINE_LEN = 23 if level_major else 22
    table_addr = addr + ROUTINE_LEN - (1 if level_major else 0)
    data = [
        0xFA, 0xC1 if level_major else 0xC0, 0xC8, #ld a, (...)
        0x47, # ld b, a
        *([0x04] if level_major else []),      # inc b
        0x21, table_addr & 0xFF, table_addr >> 8,  #ld hl, ...
        0xFA, 0xC0 if level_major else 0xC1, 0xC8,
        0xEF, # rst $28 (hl += a)
        0x7E, # ld a, (hl)
        0x87, # add a, a
        0x05, # dec bc
        0x20, 0xFC, # jr nz, ...
        0x9F, # sbc a, a
        0x3C, # inc a
        0xEA, 0x95, 0xCA, # ld ($CA95), a
        0xC9 # ret
    ]
    assert len(data) == ROUTINE_LEN
    table = [0] * (level_count if level_major else sublevel_count)
    for level, jl in enumerate(ctx.j.levels):
        if level > 0:
            for sublevel, jsl in enumerate(jl.sublevels):
                def lsh(i):
                    return 1 << (7 - i)
                if jsl.vertical == 0:
                    if level_major:
                        table[level-1] |= lsh(sublevel)
                    else:
                        table[sublevel] |= lsh(level-1)
    
    for b in data + table:
        ctx.writeByte(bank, addr, b)
        addr += 1
    ctx.regions.SublevelVertical.used = addr - ctx.regions.SublevelVertical.addr

def getSublevelRemappedLayout(ctx: SaveContext, level, sublevel):
    layout = copy.deepcopy(ctx.j.levels[level].sublevels[sublevel])
    for x in range(16):
        for y in range(16):
            if layout[x][y] > 0:
                key = (level, sublevel, x, y)
                assert key in ctx.screenRemap
                layout[x][y] &= 0xF0
                layout[x][y] &= 0xF0

def floodfillFindContinuousRoomHelper(layout, x, y, dir, stop):
    xstart = x 
    ystart = y
    coords = []
    while layout[x][y] > 0:
        coords.append((x, y))
        if (layout[x][y] >> 4) in stop:
            break
        x += dir[0]
        y += dir[1]
        if (x, y) == (xstart, ystart):
            break
    return coords
                
def floodfillFindContinuousRoom(layout, x, y, vertical):
    dirinc = (0, 1) if vertical else (1, 0)    
    dirdec = (0, -1) if vertical else (-1, 0)
    return (list(reversed(floodfillFindContinuousRoomHelper(layout, x, y, dirdec, [0xB, 0xA]))) +
     floodfillFindContinuousRoomHelper(layout, x, y, dirinc, [0xB, 0x9])[1:])[:16]

def cameraArithmetic(screen, offset, axismax):
    s = screen * axismax + offset
    return [((s // axismax) + 16) % 16, (((s + axismax) % axismax) + axismax) % axismax]

def getDataForEnt(sx, sy, vertical, condensed, ent):
    if condensed:
        return [ent.slot, ent.type, ent.x, ent.y]
    elif vertical:
        ca = cameraArithmetic(sy, ent.y-ent.margin, 0x80)
        ca[0] |= 0x80
        return [*ca, ent.slot, ent.type, ent.x, ent.margin]
    else:
        return [*cameraArithmetic(sx, ent.x-ent.margin, 0xA0), ent.slot, ent.type, ent.margin, ent.y]

def produceEntityPackets(ctx: SaveContext, level, sublevel, cat, addr):
    jsl = ctx.j.levels[level].sublevels[sublevel]
    vertical = jsl.vertical == 1
    layout = constructRemappedLayout(ctx, level, sublevel)
    enterable = getEnterabilityLayout(ctx.j, level, sublevel)
    processed = [[None for y in range(16)] for x in range(16)] # (x, y) -> seckey | None
    
    SLOTMAX = {"misc": 8, "enemies": 8, "items": 4}[cat]
    
    enterableCoords = [(x, y) for x, col in enumerate(enterable) for y, val in enumerate(col) if val]
    
    # populate ents table
    entsc = [[None for y in range(16)] for x in range(16)]
    for x in range(16):
        for y in range(16):
            if layout[x][y] > 0:
                idx, js = ctx.getUniqueScreenOriginalScreen(level, sublevel, layout[x][y] & 0x0F)
                entsc[x][y] = js[cat]
    
    packets = []
    screenPacketOffset = dict() # (x, y) -> packetoffset
    enterablekeys = dict() # (x, y) -> packet index
            
    # floodfill from enterable coords~
    for xe, ye in enterableCoords:
        seckey = (xe, ye)
        if processed[xe][ye] is not None:
            enterablekeys[seckey] = enterablekeys[processed[xe][ye]]
        else:
            condensed = (layout[xe][ye] >> 4) == 0xB
            entsize = 4 if condensed else 6
            # FIXME: should we sort these, or take them in order?
            # only matters if the room wraps around the 16x16 sublevel layout square
            roomcoords = floodfillFindContinuousRoom(layout, xe, ye, vertical)
            packet = JSONDict({
                "condensed": condensed,
                "data": []
            })
            for x, y in roomcoords:
                processed[x][y] = seckey
                # screenPacketOffset[(x, y)] = len(packet.data) # tempting, but wrong apparently.
                # This is weird, but it works?
                screenPacketOffset[(x, y)] = max(len(packet.data) - entsize, 0) if len(entsc[x][y]) == 0 else len(packet.data)
                # add to data
                for ent in entsc[x][y]:
                    data = getDataForEnt(x, y, vertical, condensed, ent)
                    assert len(data) == entsize
                    packet.data.extend(data)
            
            # reuse previous packet if identical to this one
            for i, prevpacket in enumerate(packets):
                if prevpacket.data == packet.data and prevpacket.condensed == packet.condensed:
                    enterablekeys[seckey] = i
                    break
            else:
                # new packet!
                enterablekeys[seckey] = len(packets)
                packets.append(packet)
    
    # sort packets so that the non-empty non-condensed packets come first
    def getPacketPriority(i):
        packet = packets[i]
        if len(packet.data) == 0:
            return 2
        elif packet.condensed:
            return 1
        else:
            return 0
            
    remapPacketsIndices = sorted(list(range(len(packets))), key=getPacketPriority) # (new packet index) -> (old packet index)
    remapPackets = [remapPacketsIndices.index(i) for i in range(len(packets))] # (old packet index) -> (new packet index)
    packets = [packets[remapPacketsIndices[i]] for i in range(len(packets))]
    
    for seckey, packetidx in enterablekeys.items():
        enterablekeys[seckey] = remapPackets[packetidx]
    
    # okay, now let's write these packets to data
    data = []
    packetStartByIdx = dict()
    packetEndByIdx = dict()
    
    if len(packets) == 0:
        return data
        
    #startWithTerm = any([len(packet.data) == 0 for packet in packets])
    
    for i, packet in enumerate(packets):
        if len(packet.data) == 0:
            # we'll come back to this
            # reuse previous idx
            packetStartByIdx[i] = None
            packetEndByIdx[i] = None
        else:
            if len(data) > 0 or packet.condensed:
                data.append(0xFE if packet.condensed else 0xFF)
            packetStartByIdx[i] = len(data)
            data.extend(packet.data)
            packetEndByIdx[i] = len(data)
    
    data.append(0xFD)
    
    # now let's record the start and end addresses for each enterable room
    for x, y in enterableCoords:
        uscreen = layout[x][y] & 0x0F
        key = (level, sublevel, cat, uscreen)
        if key in ctx.enterableScreenData:
            # we previously guaranteed that any time this happens, it's okay
            if layout[x][y] & 0xF0 == 0xB0: # but we only *expect* it to happen at 0xB0 rooms still, because that's all we checked for before...
                continue
            s, js = ctx.getUniqueScreenOriginalScreen(level, sublevel, uscreen)
            raise Exception(f"{rom.LEVELS[level]}-{sublevel+1}: Same enterable room (screen {s:X}/u={uscreen:X}) appears twice in two enterable-screen contexts; second time at ({x},{y})")
        seckey = (x, y)
        assert seckey in enterablekeys
        i = enterablekeys[seckey]
        if packetStartByIdx[i] == None or packetEndByIdx[i] == None:
            ctx.enterableScreenData[key] = JSONDict({
                "seclength": 0,
            })
            continue
        
        offset = screenPacketOffset[(x, y)]
        condensed = layout[x][y] >> 4 == 0xB
        entsize = 4 if condensed else 6
        assert packets[i].condensed == condensed
        assert (packetEndByIdx[i] - packetStartByIdx[i]) % entsize == 0
        assert len(packets[i].data) % entsize == 0
        assert len(packets[i].data) == (packetEndByIdx[i] - packetStartByIdx[i])
        
        ctx.enterableScreenData[key] = JSONDict({
            "secaddr": packetStartByIdx[i] + addr,
            "eaddr": packetStartByIdx[i] + offset + addr,
            "endaddr": packetEndByIdx[i] + addr,
            "entsToLoad": len(entsc[x][y]), # entities on this scren
            "seclength": packetEndByIdx[i] - packetStartByIdx[i],
            "secstart": packetStartByIdx[i],
            "eoffset": packetStartByIdx[i] + offset,
            "condensed": condensed,
            "entsize": entsize,
            "ex": x,
            "ey": y,
            "entcat": cat
        })
    
    return data

def produceEntityLookupPackets(ctx: SaveContext, level, sublevel, addr):
    # get number of priority rooms
    numPriorityUniqueScreens = ctx.numPriorityUniqueScreens[(level, sublevel)]
    
    # write pointer table for priority rooms
    # it's okay to leave the unenterable ones as garbage/0
    data = [0] * (numPriorityUniqueScreens * 2)
    # write packets
    for uscreen in range(numPriorityUniqueScreens):
        keys = []
        for i, cat in enumerate(CATS):
            keys.append((level, sublevel, cat, uscreen))
        if any([key in ctx.enterableScreenData for key in keys]):
            word = len(data) + addr
            data[uscreen*2] = word & 0xFF
            data[uscreen*2 + 1] = word >> 8
            for i, key in enumerate(keys):
                cat = CATS[i]
                edata = ctx.enterableScreenData[key]
                if edata.seclength == 0:
                    data.append(0x80)
                else:
                    data.append(edata.entsToLoad)
                    
                    # this field is troublesome, and doesn't seem entirely consistent
                    # not sure exactly what it should be, but if it's left as just `edata.eoffset`
                    # it causes some wall meats to not spawn, like the one in cloud-2
                    if edata.condensed:
                        data.append(edata.eoffset + edata.entsize * edata.entsToLoad)
                    else:
                        data.append(edata.eoffset)
                    data.append(edata.eaddr & 0xFF)
                    data.append(edata.eaddr >> 8)

    return data

def writePlaytestStart(ctx: SaveContext, level, sublevel=0):
    data = [
        0xCD, *word(rom.LEVEL_START_2855), #call 2855
        0x21, *word(0xC8C0), # ld hl, $c8c0
        0x36, level, #ld (hl), level
        0x23, #hl++
        0x36, sublevel, #ld (hl), sublevel
        0xCD, *word(rom.LEVEL_START_28DB), #call 28db
        0x3E, 4, #lda 4
        0xC3, *word(rom.LEVEL_START_0578), #call 578
    ]
    
    ctx.writeBytes(0, rom.TITLE_DONEFADE, data)
    addr = rom.TITLE_DONEFADE + len(data)

def writeChunks(ctx: SaveContext):
    tbank = ctx.regions.ChunkTable.bank
    taddr = ctx.regions.ChunkTable.addr
    addr = ctx.regions.ChunkValues.addr
    bank = ctx.regions.ChunkValues.bank
    
    addr = rom.TILES4x4_BEGIN + 0x10
    addrs = []
    for level, jl in enumerate(ctx.j.levels):
        if level == 0:
            taddr += 2
            addrs.append(0)
        else:
            if "chunks" in jl:
                ctx.writeWord(tbank, taddr, addr)
                addrs.append(addr)
                taddr += 2
                for chunk in jl.chunks[1:]:
                    for t in chunk:
                        ctx.writeByte(bank, addr, t)
                        addr += 1
            else:
                addrs.append(0)
                assert "chunklink" in jl
                ctx.writeWord(bank, taddr, addrs[jl.chunklink])
                taddr += 2
    
    ctx.regions.ChunkTable.used = taddr - ctx.regions.ChunkTable.addr
    ctx.regions.ChunkValues.used = addr - ctx.regions.ChunkValues.addr

def writeEntities(ctx: SaveContext):
    for cat in CATS:
        region = ctx.regions[f"Ent{cat}"]
        addr = region.addr
        bank = region.bank
        addr = writeSublevelTableData(ctx, addr, bank, lambda ctx, level, sublevel, addr: produceEntityPackets(ctx, level, sublevel, cat, addr))
        region.used = addr - region.addr
    
    addr = ctx.regions.EntLookup.addr
    bank = ctx.regions.EntLookup.bank
    addr = writeSublevelTableData(ctx, addr, bank, produceEntityLookupPackets)
    ctx.regions.EntLookup.used = addr -  ctx.regions.EntLookup.addr

def debugWriteBytes(path, b):
    with open(path, "wb") as f:
        f.write(bytes(b))

def writeSublevelInitRoutines(ctx: SaveContext):
    region = ctx.regions.SublevelInitRoutines
    addr = region.addr
    bank = region.bank
    
    # new routine
    DATALEN = 10
    data = [
        0x21, *word(addr + DATALEN), # ld hl, table
        0xE5, #pushhl, 
        0xCD, *word(rom.LOAD_SUBSTAGE_BYTE_FROM_TABLE), # a <- substage byte
        0xE1, #pophl,
        0xEF,
        0xE9 #jp hl
    ]
    assert len(data) == DATALEN, f"{len(data)}"
    for b in data:
        ctx.writeByte(bank, addr, b)
        addr += 1
    
    addr = writeSublevelTableData(ctx, addr, bank, produceSublevelInitRoutine, allowMerging=True, tableAtStart=True, singleByteAddressBase=addr)
    region.used = addr - ctx.regions.SublevelInitRoutines.addr
    
    debugWriteBytes("debugout.bin", [ctx.readByte(bank, i) for i in range(region.addr, region.addr + region.used)])

def word(w, littleEndian=True):
    if littleEndian:
        return [w & 0xff, w >> 8]
    else:
        return [w >> 8, w & 0xff]

def makeSubroutineUNK254(ctx, hunk, addr):
    if "UNK254" in ctx.sublevelInitSubroutines:
        return hunk, addr
    
    data = [
        # OPTIMIZE: can probably save a byte here by reordering this to a tail-call
        0xCD, *word(rom.UNK_254), # call UNK254
        0x3E, 0x09, # ld a, $9
        0xEA, *word(0xCACF), # ld ($CACF), a
        0xC9, # ret
    ]
    ctx.sublevelInitSubroutines["RET"] = addr + len(data) - 1
    
    ctx.sublevelInitSubroutines["UNK254"] = addr
    return hunk + data, addr + len(data)

def makeSubroutineLoadScreen(ctx, hunk, addr):
    if "SRLS" in ctx.sublevelInitSubroutines:
        return hunk, addr
    
    # old-style
    data = [
        0xE1, #pop hl
        0x01, *word(6), #ld bc, $0006
        0x09, #add hl, bc
        0xe5, #push hl
        
        # OPTIMIZE: check if some of these loads already exist in the ROM.
        0x32, # ld a, (hl-)
        0x4F, # ld c, a
        0x32, # ld a, (hl-)
        0x47, # ld b, a
        0x32, # ld a, (hl-)
        0x5F, # ld e, a
        0x32, # ld a, (hl-)
        0x57, # ld d, a
        0x32, # ld a, (hl-)
        0x6F, # ld l, a
        0x66, # ld h, (hl)
        0xC3, *word(rom.FARCALL_LOAD_SCREEN_TILES) # jp FARCALL_LOAD_SCREEN_TILES
    ]
    
    tableaddr = addr
    # we need a copy of the LEVTAB_TILES4x4_BANK2 from bank 2 here (this is bank3)
    # OPTIMIZE: we can do better by cropping this table to just the levels that need it (MAXLEVEL)
    MINLEVEL = 1
    MAXLEVEL = len(ctx.j.levels)
    table = [ctx.readByte(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2+i) for i in range(MINLEVEL*2, MAXLEVEL*2)]
    
    
    routine1addr = tableaddr + len(table)
    data = [
        0xE1, # pop hl
        0x3E, 0x01, # ld a, $1
        0x01, # ld bc, ~~; (skip 2 bytes)
    ]
    routineaddr = routine1addr + len(data)
    data += [
        0xE1, # pop hl
        0x2A, # ld a, (hl+)
    ]
    
    # better:
    loopd = [
        # top:
        0xF5, # push af
        
        # OPTIMIZE: check if some of these loads already exist in the ROM.
        0x2A, # ld a, (hl+)
        0x4F, # ld c, a
        0x2A, # ld a, (hl+)
        0x47, # ld b, a
        0x2A, # ld a, (hl+)
        0x5F, # ld e, a
        0x2A, # ld a, (hl+)
        0x57, # ld d, a
        0xE5, # push hl
        0x21, *word(tableaddr-MINLEVEL*2), # ld hl, table
        0xCD, *word(rom.LD_HL_LEVEL_A_SUBLEVEL), # call LD_HL_LEVEL_A_SUBLEVEL
        0xCD, *word(rom.FARCALL_LOAD_SCREEN_TILES), # jp FARCALL_LOAD_SCREEN_TILES
        0xE1, # pop hl
        0xF1, # pop af
        0x3D, # dec a
        0x20, # jr nz, top
    ]
    data += loopd + [0x100 - len(loopd)-1]
    data += [
        0xC8, # ret
    ]
    
    ctx.sublevelInitSubroutines["SRLS"] = routineaddr
    ctx.sublevelInitSubroutines["SRLS1"] = routine1addr
    ctx.sublevelInitSubroutines["RET"] = routineaddr + len(data) - 1
    
    return hunk + table + data, addr + len(table) + len(data)

def getKeySubroutineScanlineEffect(effect, scanline):
    return f"SCEFFECT_{effect:02X}_{scanline:02X}" 

def makeSubroutineScanlineEffect(ctx, hunk, addr, effect, scanline):
    key = getKeySubroutineScanlineEffect(effect, scanline)
    if key in ctx.sublevelInitSubroutines:
        return hunk, addr
    
    data = [
        0x3E, 0x20, # ld a, $20
        0xEA, *word(0xCA96), # ld ($ca96), a
        0x01, scanline, effect, # ld bc, <effect><scanline>
        0xC3, *word(rom.SET_SCANLINE_EFFECT), # jp SET_SCANLINE_EFFECT
    ]
    
    ctx.sublevelInitSubroutines[key] = addr
    return hunk + data, addr + len(data)

def writeEntLoadRoutine(ctx, region, routines, ret=True, **kwargs):
    addr = region.addr
    bank = region.bank
    label = kwargs.get("label", region.shortname)
    
    returned = [False]
    data = []
    for routine in routines:
        def getRetOrCallOpcode():
            if routine is routines[-1] and ret:
                returned[0] = True
                return 0xC3
            else:
                return 0xCD
        if routine.type == "UNK254":
            data += [
                # OPTIMIZE: can probably save a byte here by reordering this to a tail-call
                0xCD, *word(rom.UNK_254), # call UNK254
                0x3E, 0x09, # ld a, $9
                0xEA, *word(0xCACF), # ld ($CACF), a
            ]
        elif routine.type == "CNTEFFECT":
            data += [
                0x3E, 0x20, # ld a, $20
                0xEA, *word(0xCA96), # ld ($ca96), a
                0x01, routine.scanline, routine.effect, # ld bc, <effect><scanline>
                getRetOrCallOpcode(), *word(rom.SET_SCANLINE_EFFECT), # jp SET_SCANLINE_EFFECT
            ]
        elif routine.type == "LVLSCREEN":
            assert len(routine.levels) == 2
            hl = [ctx.readWord(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2 + 2*rlev.level) for rlev in routine.levels]
            bc = routine.dstAddr
            de = [getAddressForScreenOrAddScreen(ctx, rlev, label=f"{label}-{rom.LEVELS[rlev.level]}") for rlev in routine.levels]
            data += [
                0x11, *word(de[0]), # ld de, ...
                0x21, *word(hl[0]), # ld hl, ...
                0xfa, *word(0xC8C0), #ld a, ($c8c0)
                0xfe, routine.levels[1].level, # cp a, <level[1]>
                0x20, 0x06, # br nz, +6
                0x11, *word(de[1]), # ld de, ...
                0x21, *word(hl[1]), # ld hl, ...
                0x01, *word(bc), # ld bc, ...
                getRetOrCallOpcode(), *word(rom.FARCALL_LOAD_SCREEN_TILES)
            ]
        elif routine.type == "SCREEN":
            hl = ctx.readWord(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2 + 2*routine.level)
            bc = routine.dstAddr
            de = getAddressForScreenOrAddScreen(ctx, routine, label=label)
            data += [
                0x01, *word(bc), # ld bc, ...
                0x11, *word(de), # ld de, ...
                0x21, *word(hl), # ld hl, ...
                getRetOrCallOpcode(), *word(rom.FARCALL_LOAD_SCREEN_TILES)
            ]
        elif routine.type == "UNKD802":
            # this adds in a secret rope.
            data += [
                0x3E, 0x1B, #ld a, $1b
                0xEA, *word(0xD802), #ld (D802), a
                0xEA, *word(0xD822), #ld (D822), a
            ]
        else:
            # we could do this, I'm just too lazy to write the bankswap code right now.
            raise Exception(f"routine {routine.type} unsupported for Entity C4")
    
    # return
    if not returned[0] and len(data) != region.max and ret:
        data += [0xC9]
    
    for b in data:
        ctx.writeByte(bank, addr, b)
        addr += 1
        
    if not ret:
        while addr < region.max + region.addr:
            ctx.writeByte(bank, addr, 0) # nop
            addr += 1
    
    region.used = addr - region.addr

def produceSublevelInitRoutine(ctx, level, sublevel, addr):
    # this is quite spaghetti.
    jl = ctx.j.levels[level]
    jsl = jl.sublevels[sublevel]
    hunk = []
    orgaddr = addr
    
    # make any necessary subroutines
    for routine in jsl.initRoutines:
        if routine.type == "UNK254":
            hunk, addr = makeSubroutineUNK254(ctx, hunk, addr)
        elif routine.type == "CNTEFFECT":
            hunk, addr = makeSubroutineScanlineEffect(ctx, hunk, addr, routine.effect, routine.scanline)
        elif routine.type == "SCREEN":
            hunk, addr = makeSubroutineLoadScreen(ctx, hunk, addr)
    
    if len(jsl.initRoutines) == 0:
        # special case -- return
        if "RET" in ctx.sublevelInitSubroutines:
            return hunk,  ctx.sublevelInitSubroutines["RET"]
        else:
            return [0xC9] # yeesh.
    
    if len(jsl.initRoutines) == 1:
        routine = jsl.initRoutines[0]
        if routine.type == "UNK254":
            return hunk, ctx.sublevelInitSubroutines["UNK254"]
        elif routine.type == "CNTEFFECT":
            return hunk, ctx.sublevelInitSubroutines[getKeySubroutineScanlineEffect(routine.effect, routine.scanline)]
    
    returned = [False]
    modaddr = addr != orgaddr
    
    for i, routine in enumerate(jsl.initRoutines):
        def getRetOrCallOpcode():
            if routine is jsl.initRoutines[-1]:
                returned[0] = True
                return 0xC3
            else:
                return 0xCD
        if routine.type == "UNK254":
            # call subroutine
            hunk += [
                getRetOrCallOpcode(), *word(ctx.sublevelInitSubroutines["UNK254"])
            ]
        elif routine.type == "CNTEFFECT":
            hunk += [
                getRetOrCallOpcode(), *word(ctx.sublevelInitSubroutines[getKeySubroutineScanlineEffect(routine.effect, routine.scanline)])
            ]
        elif routine.type == "UNK7001":
            hunk += [
                0xCD, *word(rom.UNK_7001)
            ]
            if rom.UNK_7E5A_BANK == rom.BANK3:
                hunk += [
                    getRetOrCallOpcode(), *word(rom.UNK_7E5A)
                ]
            else:
                assert rom.BANKSWAP_ARBITRARY is not None
                hunk += [
                    0x0E, rom.UNK_7E5A_BANK, # ldc, bank
                    0x21, *word(rom.UNK_7E5A), # ld hl, addr
                    getRetOrCallOpcode(), *word(rom.BANKSWAP_ARBITRARY)
                ]
        elif routine.type == "SCREEN":
            assert routine.level == level
            hl = ctx.readWord(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2 + 2*level)
            count = len(jsl.initRoutines[i:])
            if "SRLS" in ctx.sublevelInitSubroutines and all([routine.type == "SCREEN" for routine in jsl.initRoutines[i:]]) and count < 0x100:
                hunk += [0xCD, *word(ctx.sublevelInitSubroutines["SRLS1" if count == 1 else "SRLS"])]
                if count != 1:
                    hunk += [count]
                for scroutine in jsl.initRoutines[i:]:
                    bc = scroutine.dstAddr
                    de = getAddressForScreenOrAddScreen(ctx, scroutine, label=f"Init{jl.name}-{sublevel+1}r{i}")
                    hunk += word(bc)
                    hunk += word(de)
                    
                if modaddr:
                    return hunk, addr
                else:
                    return hunk
            else:
                bc = routine.dstAddr
                de = getAddressForScreenOrAddScreen(ctx, routine, label=f"Init{jl.name}-{sublevel+1}r{i}")
                hunk += [
                    0x01, *word(bc), # ld bc, ...
                    0x11, *word(de), # ld de, ...
                    0x21, *word(hl), # ld hl, ...
                    getRetOrCallOpcode(), *word(rom.FARCALL_LOAD_SCREEN_TILES)
                ]
        else:
            # we could implement it easily though!
            assert False, f"unsupported routine '{routine.type}' for sublevel init routine"
    
    # return
    if not returned[0]:
        hunk += [0xC9]
        
    assert len(hunk) > 0
    if modaddr:
        return hunk, addr
    else:
        return hunk
            
def getAddressForScreenOrAddScreen(ctx: SaveContext, data, **kwargs):
    region = ctx.regions.ScreenTiles
    bank = region.bank
    addr = region.addr
    
    if type(data) != list:
        assert "data" in data or "linkscreen" in data
        if "data" in data:
            if "srcAddr" in data:
                if data.srcAddr not in range(region.addr, region.addr+region.max):
                    if data.data == [ctx.readByte(bank, data.srcAddr + i) for i in range(20)]:
                        return data.srcAddr
            data = data.data
        else:
            level, sublevel, screen = data.linksceen
            data = ctx.levels[level].sublevel[sublevel].screens[screen]
    
    label = kwargs.get("label", "Unk" + hashlib.md5(bytes(data)).hexdigest()[:8])
    
    dc = len(data)
    zdata = data[0]
    z2data = data[1]
    for startaddr in range(addr, addr + region.used-len(data)+1):
        if ctx.readByte(bank, startaddr) == zdata:
            if ctx.readByte(bank, startaddr+1) == z2data:
                if [ctx.readByte(bank, startaddr+i) for i in range(dc)] == data:
                    return startaddr
    else:
        if region.max - region.used < dc:
            ctx.errors += ["Need to insert extra screen, but not enough room in screen bank."]
            region.used += dc
            return 0
        else:
            addr = region.addr + region.used
            for i, d in enumerate(data):
                ctx.writeByte(bank, i + addr, d)
            while label in region.subranges:
                label += "*"
            region.subranges[label] = JSONDict(start=addr, end=addr+dc)
            region.used += dc
            return addr

def writeLoadLayoutPatch(ctx: SaveContext):
    bank = rom.BANK6
    addr = rom.LOAD_LAYOUT_500B
    ctx.writeBytes(bank, addr+2, [
        0x16, 0xDD # ld d, $DD
    ])
    ctx.writeBytes(bank, addr+16, [
        0x83, # add a, e
        0x5F, # ld e, a
        0x00, # nop
    ])

def writeLoadEnclosedScreenEntityBugfixPatch(ctx: SaveContext):
    # somehow, this routine seems bugged
    # it's supposed add 6 to hl, not 4
    # we correct for it by subtracting 2
    # just need to find some free space to jump to.
    
    for name, region in ctx.regions.items():
        if region.bank == rom.BANK3 and region.max - region.used > 5:
            addr = region.addr + region.used
            detour_from = rom.BSCREEN_BUGFIX_DETOUR+1
            detour_to = ctx.readWord(rom.BANK3, rom.BSCREEN_BUGFIX_DETOUR+1)
            ctx.writeWord(rom.BANK3, detour_from, addr)
            
            #print(f"Bugfix patch; detour from ${detour_from:04X} to ${detour_to:04X} tramp ${addr:04X}")
            
            data = [
                0x2b, # dec hl
                0x2b, # dec hl
                0xc3, (detour_to & 0xFF), (detour_to >> 8) # jp detour_to
            ]
            for b in data:
                ctx.writeByte(rom.BANK3, addr, b)
                addr += 1
            
            region.used += 5
            return
    else:
        ctx.errors += [f"Unable to find enough room in bank ${rom.BANK3:X} to fix enclosed-screen entity loading routine bug."]
    