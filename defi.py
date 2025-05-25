JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"
PRIVATE_KEY = "39dnVrRCL36dj71Mx7FkyRoyTAoGhmhrthvfiGh3dttS8NPWJmxD75ZQf6tGbshoCYugQRecXqW25jmUM2Lm2RKs"
INPUT_MINT = "So1111111111111111111111111111111111111111234"

def lamp_to_sol(lamp):
    return lamp / 1000000000
def sol_to_lamp(sol):
    return sol * 1000000000
def slip_to_bps(slip):
    return slip*100
def bps_to_slip(bps):
    return bps/100