; call bank after org, seeks to $ in given bank.

banksk:  macro n
    seek n ? (n - 1) * $4000 + $ : $
endm

banksk0: macro
    seek $
endm

banksk1: macro
    seek $4000 * (1-1) + $
endm

banksk2: macro
    seek $4000 * (2-1) + $
endm

banksk3: macro
    seek $4000 * (3-1) + $
endm

banksk4: macro
    seek $4000 * (4-1) + $
endm

banksk6: macro
    seek $4000 * (6-1) + $
endm

banksk7: macro
    seek $4000 * (7-1) + $
endm

banksk12: macro
    seek $4000 * (0x12-1) + $
endm

banksk13: macro
    seek $4000 * (0x13-1) + $
endm

banksk16: macro
    seek $4000 * (0x16-1) + $
endm

banksk19: macro
    seek $4000 * (0x19-1) + $
endm

; z80asm seems to have trouble emitting ld a, ($imm) for some reason.
ldai16: macro addr
    db $FA
    defw addr
endm

ldi16a: macro addr
    db $EA
    defw addr
endm

pushhl: macro value
    ld hl, value
    push hl
endm

pushbc: macro value
    ld bc, value
    push bc
endm

pushde: macro value
    ld de, value
    push de
endm

ldiahl: macro
    db $2A
endm

ldihla: macro
    db $22
endm

ldhlhl: macro
    ldiahl
    ld h, (hl)
    ld l, a
endm

advance_to: macro value
    if $ > value
        panic
    endif
    org value
endm