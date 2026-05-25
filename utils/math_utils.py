import math

def factorial(n):
    """
    Calculate the factorial of a number
    
    Args:
        n (int): The input number
    Returns:
        int: The factorial of the input number
    """
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers")
    elif n == 0 or n == 1:
        return 1
    else:
        result = 1
        for i in range(2, n + 1):
            result *= i
        return result

def is_prime(n):
    """
    Check if a number is prime
    
    Args:
        n (int): The input number
    Returns:
        bool: True if the number is prime, False otherwise
    """
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True
