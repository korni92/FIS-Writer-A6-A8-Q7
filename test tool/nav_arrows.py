# nav_arrows.py
# Dictionary structure: { "Group_Hex": { "Data_Hex": "Description" } }

KNOWN_ARROWS = {
    "0A": {
        "00": "Straight",
        "10": "Pointed ~20° left",
        "20": "Pointed ~40° left",
        "30": "Pointed ~60° left",
        "80": "Pointed ~180° left",
        "F0": "Pointed ~340° left"
    },
    "0B": {
        "FF": "Straight long from bottom (Autobahn?)",
        "40": "Straight 2. Arrow Left",
        "C0": "Straight 2. Arrow right"
    },
    "0C": {
        "C0": "Highway Exit right",
        "40": "Highway Exit left"
    },
    "0D": {
        "20": "Straight Top left",
        "40": "Turn left big",
        "60": "Hard turn back left",
        "A0": "Hard turn back right, prev street cont. slightly up right",
        "C0": "Turn right from bottom big view",
        "E0": "Straight Top right",
        "C0 E0": "Turn right, prev street cont. slightly up right"
    },
    "0E": {
        "00": "Straight",
        "20": "Straight Top left",
        "40": "Turn left big",
        "60": "Hard turn back left",
        "A0": "Hard turn back right",
        "C0": "Turn right from bottom big view",
        "E0": "Straight Top right"
    },
    "0F": {
        "00": "merge right",
        "C0": "Follow right",
        "C0 C0": "Unknown Multi-Byte",
        "E0": "Right right"
    }
}
