import sys
import os
import rom
from rom import readword, readbyte, readtableword
from PIL import Image

MARGIN = 2
MARGINCOL = (0x80, 0x00, 0x20)
PALETTE = [
    (0xff, 0xff, 0xff),
    (0xb0, 0xb0, 0xb0),
    (0x30, 0x30, 0x30),
    (0, 0, 0),
]

if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} base.gb out/")
    sys.exit(1)

with open(sys.argv[1], "rb") as f:
    rom.readrom(f.read())
dir = sys.argv[2]

VOFF = 0x8000
vrambuffer = [0 for i in range(0x2000)]
def load_vram_buffer(dst, len, bank, addr):
    for i in range(0, len):
        vrambuffer[i + dst - VOFF] = rom.readbyte(bank, addr + i)

def load_vram_metabuffer(bank, addr):
    # this does what routine 0:2E24 does
    while rom.readbyte(bank, addr) != 0:
        destaddr = ((rom.readbyte(bank, addr) << 12) + (rom.readbyte(bank, addr + 1) << 4)) & 0xffff
        addr += 2
        destlen = rom.readbyte(bank, addr) << 4
        addr += 1
        srcbank = rom.readbyte(bank, addr)
        addr += 1
        srcaddr = rom.readword(bank, addr)
        addr += 2
        load_vram_buffer(destaddr, destlen, srcbank, srcaddr)

def get_tile_chunk(id, level):
    if id == 0:
        return [0] * 16
    id -= 1
    base = readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
    return [rom.readbyte(rom.BANK2, base + id * 0x10 + i) for i in range(0x10)]

def get_tile_img_memoized(id, level):
    img = Image.new(mode="RGB", size=(8, 8))
    pixels = img.load()
    for i in range(8):
        for j in range(8):
            pixels[i,j] = (0xff, 0xff, 0xff)
    tileaddr = id * 0x10 + 0x1000
    tilevram = vrambuffer[tileaddr:tileaddr+0x10]
    pixelsc = [[0 for i in range(8)] for j in range(8)]
    for i in range(0,16,2):
        for b in range(2):
            for j in range(8):
                pixelsc[j][i//2] += (1 << b) * (1 & (tilevram[i+b] >> (7-j)))
    for i in range(8):
        for j in range(8):
            pixels[i,j] = PALETTE[pixelsc[i][j]]
    return img

TILE_IMG_MAP = {}
# produces an 8x8 tile image
def get_tile_img(id, level):
    if (id, level) not in TILE_IMG_MAP:
        TILE_IMG_MAP[(id, level)] = get_tile_img_memoized(id, level)
    return TILE_IMG_MAP[(id, level)]
    
for i, level in enumerate(rom.LEVELS):
    if level is None:
        continue
    
    # first, load vram for level
    vrambuffer[:] = [0 for i in range(0x2000)]
    buffaddr = readtableword(rom.LEVEL_TILESET_TABLE_BANK, rom.LEVEL_TILESET_TABLE, i)
    load_vram_metabuffer(rom.LEVEL_TILESET_TABLE_BANK, buffaddr)
    
    outvram = Image.new(mode="RGB", size=(8*16,8*32))
    for t in range(0x80):
        tx = t % 0x10
        ty = t // 0x10
        
    
    for sublevel in range(rom.SUBSTAGECOUNT[i]):
        tiles_begin = readtableword(rom.BANK2, rom.LEVTAB_TILES_BANK2, i, sublevel)
        tiles_end = rom.get_entry_end(rom.LEVTAB_TILES_BANK2, rom.BANK2, i, sublevel)
        assert tiles_end > tiles_begin
        assert (tiles_begin - tiles_end) % 20 == 0
        screenc = (tiles_end - tiles_begin) // 20
        out = Image.new(mode="RGB", color=MARGINCOL, size=(8 * 5 * 4 * screenc + MARGIN*(screenc-1), 4 * 4 * 8))
        
        # iterate over 4x4 tile chunks
        for t in range(0, screenc * 20):
            screen = t // 20
            st = t % 20
            sx = st % 5
            sy = st // 5
            chidx = rom.readbyte(rom.BANK6, tiles_begin + t)
            chunk = get_tile_chunk(chidx, i)
            
            #iterate over tiles
            for k, c in enumerate(chunk):
                cx = k % 4
                cy = k // 4
                xdraw = ((((screen * 5) + sx) * 4) + cx) * 8 + screen*MARGIN
                ydraw = (sy * 4 + cy) * 8
                out.paste(get_tile_img(c, i), (xdraw, ydraw))
        
        out.save(os.path.join(dir, f"{level}_{sublevel}.png"))