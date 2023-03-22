set -e

function build() {
    BASE=$1
    if [ ! -f "$BASE.gb" ]
    then
        echo "No such file '$BASE.gb'"
        exit 1
    fi

    chmod a-w $BASE.gb

    python3 ./leveldata.py $BASE.gb

    mkdir -p outimg

    if [ -d "outimg/$BASE" ]
    then
        rm -r "outimg/$BASE"
    fi

    #mkdir -p "outimg/$BASE"
    #python3 ./levelimages.py "$BASE.gb" "outimg/$BASE"

    BUILDNAME="$BASE.out.gb"
    echo "incbin \"$BASE.gb\"" > incbase.asm

    if command -v z80asm > /dev/null
    then
        z80asm -o $BUILDNAME --label=$BASE.out.lbl -i incbase.asm ./game.asm
        diff "$BASE.gb" "$BUILDNAME"
    else
        echo "Install z80asm (ubuntu: apt install z80asm) to build the extracted data as a patch"
    fi
    
}

if [ "$#" -eq 0 ]
then
    for file in *.gb
    do
        if [[ "$file" != *.out.gb ]]
        then
            echo "extracting from $file"
            build "${file%.*}"
        fi
    done
    exit 0
fi

if [ -z "$1" ]
then
    echo "Usage: $0 rom.gb"
    exit 1
fi


build ${1%.*}