@server.tool()
def mcs_advice(rollouts_per_square: Budget = 10) -> dict:
    """Compare every empty square with full random game completions.

    Returns a recommended absolute cell index and estimated final scores.
    Future letters are sampled, never the actual hidden deal. Does not place a letter.
    """
    return context.mcs_advice(rollouts_per_square)
