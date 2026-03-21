"""
Bài 1. Cho dãy arr = [3, 6, 5, 2, 1 ,1, 3]
Viết một hàm get random để lấy một số tùy ý trong dãy trên sao cho xác suất lấy ra tỉ lệ thuận với giá trị được lấy ra. (ví dụ giá trị 6 là được dễ trả lại nhất).
"""

import random
import matplotlib.pyplot as plt


def get_random(arr, cumulative_weights):
    """
    Returns a random number from the array where the probability of selecting any number is directly proportional to its value.

    Args:
        arr (list): The list of numbers.
        cumulative_weights (list): The list of numbers summed consecutively from left to right.

    Returns:
        int: The selected random number.
    """
    number = random.randint(1, cumulative_weights[-1])

    for index in range(len(cumulative_weights)):
        if number <= cumulative_weights[index]:
            return arr[index]


if __name__ == "__main__":
    # Given
    arr = [3, 6, 5, 2, 1, 1, 3]

    # Build cumulative weights
    cumulative_weights = []
    total = 0
    for value in arr:
        total = total + value
        cumulative_weights.append(total)

    # Get random 10000 times
    results = []
    for _ in range(10000):
        random_number = get_random(arr, cumulative_weights)
        results.append(random_number)

    # Count frequency without library
    counts = {}
    for number in results:
        if number in counts:
            counts[number] += 1
        else:
            counts[number] = 1

    # Plot the frequency of each number
    keys = list(counts.keys())
    values = list(counts.values())
    plt.bar(keys, values)
    plt.xlabel("Value")
    plt.ylabel("Frequency")
    plt.show()
