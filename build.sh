set -e

if [ -z "$1" ]
then
    echo "Usage: $0 rom.gb"
    exit 1
fi

BASE=${1%.*}

if [ ! -f "$BASE.gb" ]
then
    echo "No such file '$BASE.gb'"
    exit 1
fi

chmod a-w $BASE.gb

python3 ./leveldata.py $BASE.gb

BUILDNAME="$BASE.out.gb"
echo "incbin \"$BASE.gb\"" > incbase.asm
z80asm -o $BUILDNAME --label=$BASE.out.lbl -i incbase.asm ./game.asm
diff "$BASE.gb" "$BUILDNAME"