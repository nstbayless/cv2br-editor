import sys

def romaddr(bank, addr):
    return bank * 0x4000 + addr % 0x4000
    
def readbyte(bank, addr):
    return data[romaddr(bank, addr)]
    
def readword(bank, addr):
    return readbyte(bank, addr) + 0x100 * readbyte(bank, addr+1)

def readtableword(bank, addr, arg0, *args):
    for i in [arg0] + list(args):
        addr = readword(bank, addr + 2*i)
    return addr
    
def readtablebyte(bank, addr, arg0, *args):
    args = [arg0] + list(args)
    if len(args) > 1:
        addr = readtableword(bank, addr, *args[:-1])
    return readbyte(bank, addr + args[-1])
    
# returns startx, starty, scrolldir, then a 16x16 array of screen bytes
def produce_sublevel_screen_arrangement(level, sublevel):
    scrolldir = readtablebyte(BANK2, LEVEL_SCROLLDIR_TABLE, level, sublevel)
    screenbuffaddr = readtableword(BANK6, LEVEL_SCREEN_TABLE, level, sublevel)
    startx = readbyte(BANK6, screenbuffaddr)
    starty = readbyte(BANK6, screenbuffaddr+1)
    screenbuffaddr += 2
    buff = [[0 for j in range(16)] for i in range(16)]
    while True:
        dst = readword(BANK6, screenbuffaddr)
        x=dst%0x10
        y=(dst//0x10)%0x10
        screenbuffaddr += 2
        stride = readbyte(BANK6, screenbuffaddr)
        xstride = stride % 0x10
        if xstride >= 0x8:
            xstride -= 0x10
        ystride = stride // 0x10
        if ystride >= 0x8:
            ystride -= 0x8
        screenbuffaddr += 1
        while True:
            header = readbyte(BANK6, screenbuffaddr)
            screenbuffaddr += 1
            if header == 0xff:
                return startx, starty, scrolldir, buff
            elif header == 0xfe:
                break
            assert x >= 0 and x < 0x10, f"{x},{y},{LEVELS[level]}-{sublevel} :{startx},{starty} +{xstride}x"
            assert y >= 0 and y < 0x10, f"{x},{y},{LEVELS[level]}-{sublevel} :{startx},{starty} +{ystride}y"
            buff[x][y] = header
            x += xstride
            y += ystride

def get_entry_end(table, bank, level, substage=None, drac3_size=None):
    if drac3_size is None:
        if table == LEVTAB_TILES_BANK2 and bank == BANK2:
            drac3_size = 5*20 # this is a guess
        if table == LEVTAB_TILES4x4_BANK2 and bank == BANK2:
            drac3_size = 0x820 # this is a guess
    if substage is not None:
        substage += 1
        if substage >= SUBSTAGECOUNT[level]:
            substage = 0
            level += 1
        if level >= len(SUBSTAGECOUNT):
            level = len(SUBSTAGECOUNT) - 1
            substage = SUBSTAGECOUNT[level] - 1
        else:
            drac3_size = 0
    else:
        level += 1
        if level >= len(SUBSTAGECOUNT) or (table == LEVTAB_TILES4x4_BANK2 and bank == BANK2 and level >= len(SUBSTAGECOUNT)-1):
            level -= 1
        else:
            drac3_size = 0
        
    addr2 = readword(bank, table + 2*level)
    if substage is not None:
        addr2 = readword(bank, addr2 + 2*substage)
    return addr2 + drac3_size

def readrom(_data):
    global data
    data = _data
    
    if not data or len(data) <= 100:
        print(f"romfile invalid?")
        sys.exit(1)
    
    global ROMTYPE

    # determine which rom this is from header
    ROMTYPE = "unk"
    if data[0x14B] == 0xA4 and data[0x134] == 0x43:
        ROMTYPE = "us"
    elif data[0x14B] == 0xA4 and data[0x134] == 0x44:
        ROMTYPE = "jp"
    elif data[0x14B] == 0x33 and data[0x13C] == 0x34:
        ROMTYPE = "kgbc4eu"
    else:
        print("Unrecognized ROM. Please check the hash. Supported roms: us/ue, jp, kgbc4eu")
        sys.exit(1)

    # bank2
    global BANK2
    BANK2 = 2
    global LEVTAB_TILES4x4_BANK2
    LEVTAB_TILES4x4_BANK2 = 0x42a5
    global LEVTAB_TILES_BANK2
    LEVTAB_TILES_BANK2 = 0x42C4
    global TILES4x4_BEGIN
    TILES4x4_BEGIN = 0x44c0
    global LEVEL_TILESET_TABLE
    global LEVEL_TILESET_TABLE_BANK
    global LEVEL_TILESET_COMMON
    LEVEL_TILESET_TABLE_BANK = 0
    LEVEL_TILESET_TABLE = 0x2e06
    LEVEL_TILESET_COMMON = 0x2b50
    global LEVEL_SCROLLDIR_TABLE
    LEVEL_SCROLLDIR_TABLE = 0x4320
    
    # bank3
    global BANK
    BANK = 3
    global LEVTAB_ROUTINE
    LEVTAB_ROUTINE = 0x6cc7

    # bank6
    global BANK6
    BANK6 = 6
    global LEVEL_SCREEN_TABLE
    LEVEL_SCREEN_TABLE = 0x5020
    
    if ROMTYPE == "jp":
        LEVEL_SCREEN_TABLE = 0x4fb0

    if ROMTYPE == "kgbc4eu":
        BANK2 = 0x12
        BANK = 0x13
        BANK6 = 0x16
        LEVTAB_TILES4x4_BANK2 += 75
        LEVTAB_TILES_BANK2 += 75
        LEVEL_SCROLLDIR_TABLE += 75
        TILES4x4_BEGIN = 0x4560
        LEVTAB_ROUTINE = 0x70af
        LEVEL_TILESET_TABLE = 0x5A15
        LEVEL_TILESET_TABLE_BANK = 0x16
        LEVEL_TILESET_COMMON = 0x5a33
        LEVEL_SCREEN_TABLE = 0x50C8

    global LEVTAB_A, LEVTAB_B, LEVTAB_C, LEVELS, SUBSTAGECOUNT, Entities
    LEVTAB_A = readword(BANK, LEVTAB_ROUTINE + 4)
    LEVTAB_B = readword(BANK, LEVTAB_ROUTINE + 13)
    LEVTAB_C = readword(BANK, LEVTAB_ROUTINE + 22)

    LEVELS = [None, "Plant", "Crystal", "Cloud", "Rock", "Drac1", "Drac2", "Drac3"]
    SUBSTAGECOUNT = [0, 6, 5, 5, 6, 5, 5, 1]

    Entities = {
        0x00: "NONE",
        0x01: "ITM_CROSSAXE",
        0x02: "ITM_HOLYWATER",
        0x03: "ITM_COIN",
        0x04: "ITM_WHIP_FIRE",
        0x05: "ITM_HEARTSMALL",
        0x06: "ITM_HEARTBIG",
        0x0F: "ENM_PANAGUCHI_0F",
        
        0x08: "WALL_1UP",
        0x09: "ENM_RAT_09",
        
        0x0B: "WALL_MEAT",
        0x0C: "ENM_PANAGUCHI_0C",
        0x0D: "ENM_PANAGUCHI_0D",
        0x0E: "ENM_RAT_0E",
        
        0x1C: "ENM_SKELETON_1C",
        0x1E: "ENM_FORNEUS",
        0x1F: "ENM_BAT_1F",
        
        0x20: "ENM_SKELETON_20",
        0x21: "ENM_MUDMAN",
        0x22: "BOSS_TWIN_TRIDENT",
        0x24: "BG_ANIM",
        0x25: "SPAWNEYE_RIGHT",
        0x26: "SPAWNEYE_LEFT",
        
        0x33: "ENM_KNIGHT",
        0x34: "ENM_RAVEN",
        0x35: "ITM_WHIP_CHAIN",
        0x37: "ENM_WATER_CREEP",
        0x3C: "SPAWNEYE_ABOVE",
        
        0x41: "ENM_DAGGER",
        0x45: "BOSS_DARKSIDE",
        0x4E: "BGFLAME",
        
        0x53: "BOSS_ANGEL_MUMMY",
        0x5D: "ENM_BEATLE",
        
        0x60: "BOSS_IRON_DOLL",
        
        0x69: "BOSS_BONE_SERPENT",
        
        0x72: "BOSS_SOLEIL",
        0x73: "BOSS_DRACULA",
    }