# Exponents of length, mass, time, temperature and amount of substance.
# These are the five base quantities occurring in the 23 supported models.
UNITS = {
    "1": (0,0,0,0,0), "rad": (0,0,0,0,0), "m": (1,0,0,0,0), "s": (0,0,1,0,0),
    "kg": (0,1,0,0,0), "K": (0,0,0,1,0), "mol": (0,0,0,0,1), "Hz": (0,0,-1,0,0),
    "1/s": (0,0,-1,0,0), "rad/s": (0,0,-1,0,0), "rad/s²": (0,0,-2,0,0),
    "m/s": (1,0,-1,0,0), "m/s²": (1,0,-2,0,0), "N": (1,1,-2,0,0),
    "N/m": (0,1,-2,0,0), "N·s/m": (0,1,-1,0,0), "Pa": (-1,1,-2,0,0),
    "m²": (2,0,0,0,0), "m³": (3,0,0,0,0), "m³/s": (3,0,-1,0,0),
    "kg/m³": (-3,1,0,0,0), "kg·m/s": (1,1,-1,0,0), "J": (2,1,-2,0,0),
    "J/K": (2,1,-2,-1,0), "W/K": (2,1,-3,-1,0), "m²/s": (2,0,-1,0,0),
    "J/(mol·K)": (2,1,-2,-1,-1),
}


def dimension(unit):
    return " ".join(f"{base}^{value}" if value != 1 else base
                    for base, value in zip(("L","M","T","Θ","N"), UNITS[unit]) if value) or "1"


