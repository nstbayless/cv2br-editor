import rom
from rom import readword, readtablebyte, readtableword, readbyte
import copy
import traceback

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
        j.screenTilesAddr = rom.readtableword(rom.BANK2, rom.LEVTAB_TILES_BANK2, 1, 0)
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

# ------------------------------------------------------

class SaveContext:
    def __init__(self, gb, j):
        self.gb = list(copy.copy(gb))
        self.j = j
        self.errors = []
        self.regions = JSONDict({
            "ScreenTilesTable": {
                "shortname": "STT",
                "max": 0x4316 - 0x42C4,
                "addr": rom.LEVTAB_TILES_BANK2,
                "bank": rom.BANK2,
            },
            # could combine this with the above, which ends at the same spot
            # we just need to adjust calls to the routine at $4316
            "SublevelVertical": {
                "shortname": "SLV",
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
            "ScreenTiles": {
                "shortname": "ST",
                "max": 0x73F8 - 0x62B4 + 20 * 5,
                "addr": j.screenTilesAddr,
                "bank": rom.BANK6,
            },
            "Layouts": {
                "shortname": "L",
                "max": 0x52C1 - 0x5020 + 12,
                "addr": rom.LEVEL_SCREEN_TABLE,
                "bank": rom.BANK6,
            }
        })
        for key in self.regions.keys():
            self.regions[key] = JSONDict(self.regions[key])
            self.regions[key].key = key
            self.regions[key].used = 0
        
        # maps (level, sublevel) -> list[(x, y, l)]
        self.uniqueScreens = dict()
        
        # maps (level, sublevel, x, y) -> index in ctx.uniqueScreens[sublevel, level]
        self.screenRemap = dict()
        
        # maps (level, sublevel) -> int (index into self.uniqueScreens[(level, sublevel)])
        self.numPriorityUniqueScreens = dict()
        
        # maps (level, sublevel, cat, uscreen) -> 
        self.enterableScreenData = dict()
    
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
    regions, errors, gb = _saveRom(SaveContext(gb, j))
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
                
        return [(key, ctx.regions[key].used, ctx.regions[key].max) for key in ctx.regions.keys()], ctx.errors, bytes(ctx.gb)
    except Exception as e:
        errors = [f"Fatal: {e}\n{traceback.format_exc()}"]
        regions = [(key, None, ctx.regions[key]["max"]) for key in ctx.regions.keys()]
        return regions, errors, None
    
def writeRom(ctx: SaveContext):
    # TODO: tileset_common (* no gui support)
    # TODO: level.tileset  (* no gui support)
    constructScreenRemapping(ctx)
    writeScreenTiles(ctx)
    writeScreenLayout(ctx)
    writeSublevelVertical(ctx)
    writeEntities(ctx)
    writeChunks(ctx)
    
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
    
    tsaddr = taddr + len(ctx.j.levels)*2
    
    for level, jl in enumerate(ctx.j.levels):
        if level == 0:
            taddr += 2
        else:
            ctx.writeWord(tbank, taddr, tsaddr)
            taddr += 2
            for sublevel, jsl in enumerate(jl.sublevels):
                ctx.writeWord(tbank, tsaddr, addr)
                tsaddr += 2
                for uscreen, uscm in enumerate(ctx.uniqueScreens[(level, sublevel)]):
                    oscreen, js = ctx.getUniqueScreenOriginalScreen(level, sublevel, uscreen)
                    for y in range(4):
                        for x in range(5):
                            # TODO: remap chunks also :)
                            ctx.writeByte(bank, addr, js.data[y][x])
                            addr += 1
    ctx.regions.ScreenTilesTable.used = tsaddr - ctx.regions.ScreenTilesTable.addr
    ctx.regions.ScreenTiles.addr = addr - ctx.regions.ScreenTiles.addr

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
                            for i in range(2):
                                key = (level, sublevel+1, jsl2.startx + xoff*i, jsl2.starty)
                                nextsublevelscreen = ctx.screenRemap[key] if key in ctx.screenRemap else None
                                if nextsublevelscreen is not None:
                                    #print(level, sublevel, f"{nextsublevelscreen:02X}", len(ctx.uniqueScreens[(level, sublevel)]))
                                    nextsublevelscreent = (nextsublevelscreen & 0x0F) + len(ctx.uniqueScreens[(level, sublevel)])
                                    if nextsublevelscreent >= 0x10:
                                        ctx.errors += [f"{rom.LEVELS[level]}-{sublevel+1} uses more than 15 unique screens when including preview screens for {rom.LEVELS[level]}-{sublevel+2}"]
                                    _x = (x + xoff*(i+1) + 0x10) % 0x10
                                    if layout[_x][y] > 0:
                                        ctx.errors += [f"Unable to place next-sublevel-preview screen for {rom.LEVELS[level]}-{sublevel+1}, as it is coincident with an existing screen."]
                                    else:
                                        layout[_x][y] = nextsublevelscreent | 0x80
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
            0xDD,
            
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

def writeLevelTableData(ctx: SaveContext, addr, bank, cb):
    taddr = addr
    addr += 8*2
    for level, jl in enumerate(ctx.j.levels):
        taddr += 2
        if level == 0:
            taddr += 2
        else:
            ctx.writeWord(bank, taddr, addr)
            hunk = cb(ctx, level, addr)
            for b in hunk:
                ctx.writeByte(bank, addr, b)
                addr += 1
    
    return addr

def writeSublevelTableData(ctx: SaveContext, addr, bank, cb):
    taddr = addr
    addr += 8*2
    
    for level, jl in enumerate(ctx.j.levels):
        if level == 0:
            taddr += 2
        else:
            tsaddr = addr
            ctx.writeWord(bank, taddr, tsaddr)
            taddr += 2
            addr += len(jl.sublevels) * 2
            for sublevel, jsl in enumerate(jl.sublevels):
                ctx.writeWord(bank, tsaddr, addr)
                tsaddr += 2
                hunk = cb(ctx, level, sublevel, addr)
                for b in hunk:
                    ctx.writeByte(bank, addr, b)
                    addr += 1
    return addr

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
        
    startWithTerm = any([len(packet.data) == 0 for packet in packets])
    
    for i, packet in enumerate(packets):
        if len(packet.data) == 0:
            # we'll come back to this
            # reuse previous idx
            assert startWithTerm
            packetStartByIdx[i] = 0
            packetEndByIdx[i] = 0
        else:
            if len(data) > 0 or packet.condensed or startWithTerm:
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
                    data.append(edata.eoffset)
                    data.append(edata.eaddr & 0xFF)
                    data.append(edata.eaddr >> 8)

    return data

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