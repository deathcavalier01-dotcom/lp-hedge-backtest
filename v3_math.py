"""
Uniswap V3 LP position calculator.
Computes token amounts and position value for a concentrated liquidity position.
No fees, no external dependencies.
"""

import math
from typing import Tuple


def amounts_from_L(P: float, Pl: float, Pu: float, L: float) -> Tuple[float, float]:
    """
    Calculate token amounts (x, y) at price P for given liquidity L.
    
    Args:
        P: Current price (quote per base)
        Pl: Lower bound price
        Pu: Upper bound price
        L: Virtual liquidity
        
    Returns:
        (x, y): Base token amount, quote token amount
    """
    if P <= 0 or Pl <= 0 or Pu <= 0:
        raise ValueError("All prices must be positive")
    if L <= 0:
        raise ValueError("Liquidity must be positive")
    if Pl >= Pu:
        raise ValueError("Pl must be < Pu")
    
    sqrtP = math.sqrt(P)
    sqrtPa = math.sqrt(Pl)
    sqrtPb = math.sqrt(Pu)
    
    # Case 1: Below range - all base token
    if P <= Pl:
        x = L * (1/sqrtPa - 1/sqrtPb)
        y = 0.0
    
    # Case 2: In range - both tokens
    elif P < Pu:
        x = L * (1/sqrtP - 1/sqrtPb)
        y = L * (sqrtP - sqrtPa)
    
    # Case 3: Above range - all quote token
    else:
        x = 0.0
        y = L * (sqrtPb - sqrtPa)
    
    return (x, y)


def lp_value(P: float, Pl: float, Pu: float, L: float) -> float:
    """
    Calculate total position value at price P.
    
    Args:
        P: Current price (quote per base)
        Pl: Lower bound price
        Pu: Upper bound price
        L: Virtual liquidity
        
    Returns:
        Total value in quote token units
    """
    x, y = amounts_from_L(P, Pl, Pu, L)
    return x * P + y


def L_from_initial_usd(P0: float, Pl: float, Pu: float, initial_usd: float) -> float:
    """
    Derive liquidity L such that position value = initial_usd at P0.
    
    Args:
        P0: Initial price (must be in (Pl, Pu))
        Pl: Lower bound price
        Pu: Upper bound price
        initial_usd: Desired position value at P0
        
    Returns:
        Liquidity L
        
    Raises:
        ValueError: If P0 not in valid range or initial_usd <= 0
    """
    if not (Pl < P0 < Pu):
        raise ValueError(f"P0={P0} must be strictly within ({Pl}, {Pu})")
    if initial_usd <= 0:
        raise ValueError(f"initial_usd must be positive, got {initial_usd}")
    
    sqrtP0 = math.sqrt(P0)
    sqrtPa = math.sqrt(Pl)
    sqrtPb = math.sqrt(Pu)
    
    value_per_L = 2*sqrtP0 - P0/sqrtPb - sqrtPa
    
    if value_per_L <= 0:
        raise ValueError(f"Invalid price range configuration: value_per_L={value_per_L}")
    
    L = initial_usd / value_per_L
    
    return L


class LPPosition:
    """
    Represents a Uniswap V3 concentrated liquidity position.
    
    Attributes:
        L: Virtual liquidity (invariant)
        Plower: Lower tick price
        Pupper: Upper tick price
    """
    
    def __init__(self, L: float, Plower: float, Pupper: float):
        """
        Initialize LP position with liquidity and price range.
        
        Args:
            L: Virtual liquidity (must be positive)
            Plower: Lower bound price (must be positive)
            Pupper: Upper bound price (must be > Plower)
            
        Raises:
            ValueError: If inputs violate constraints
        """
        if L <= 0:
            raise ValueError(f"Liquidity must be positive, got {L}")
        if Plower <= 0 or Pupper <= 0:
            raise ValueError(f"Prices must be positive, got Plower={Plower}, Pupper={Pupper}")
        if Plower >= Pupper:
            raise ValueError(f"Plower must be < Pupper, got {Plower} >= {Pupper}")
        
        self.L = L
        self.Plower = Plower
        self.Pupper = Pupper
        self.sqrtPa = math.sqrt(Plower)
        self.sqrtPb = math.sqrt(Pupper)
    
    def get_amounts(self, P: float) -> Tuple[float, float]:
        """Calculate token amounts (x, y) at price P."""
        return amounts_from_L(P, self.Plower, self.Pupper, self.L)
    
    def get_value(self, P: float) -> float:
        """Calculate total position value at price P."""
        return lp_value(P, self.Plower, self.Pupper, self.L)
    
    @classmethod
    def from_initial_value(cls, P0: float, Plower: float, Pupper: float, 
                          initial_value: float) -> 'LPPosition':
        """
        Create LP position from initial USD value at P0.
        Derives liquidity L such that position value = initial_value at P0.
        """
        L = L_from_initial_usd(P0, Plower, Pupper, initial_value)
        return cls(L, Plower, Pupper)


if __name__ == "__main__":
    # Self-test with asserts
    Pl, Pu = 1800.0, 2200.0
    P0 = 2000.0
    initial_usd = 100000.0
    
    # Test 1: L derivation is accurate
    L = L_from_initial_usd(P0, Pl, Pu, initial_usd)
    value_at_P0 = lp_value(P0, Pl, Pu, L)
    assert abs(value_at_P0 - initial_usd) < 1e-6, f"Value mismatch: {value_at_P0} vs {initial_usd}"
    
    # Test 2: Below range has only base token
    x_below, y_below = amounts_from_L(1700.0, Pl, Pu, L)
    assert x_below > 0 and y_below == 0, "Below range should have x>0, y=0"
    
    # Test 3: Above range has only quote token
    x_above, y_above = amounts_from_L(2300.0, Pl, Pu, L)
    assert x_above == 0 and y_above > 0, "Above range should have x=0, y>0"
    
    # Test 4: In range has both tokens
    x_in, y_in = amounts_from_L(P0, Pl, Pu, L)
    assert x_in > 0 and y_in > 0, "In range should have x>0, y>0"
    
    # Test 5: P0 validation rejects boundary
    try:
        L_from_initial_usd(Pl, Pl, Pu, initial_usd)
        assert False, "Should reject P0 at boundary"
    except ValueError:
        pass
    
    print("All tests passed")
