# keeps a list of items
# The .add() method ensures the list remains unique (via __eq__)
# and sorted (via __lt__) by inserting new items in the correct position.
class UniqueSortedList:
    def __init__(self):
        self._items = []

    def add(self, item):
        #print(f"before add: {str(self)}")
        # Check if item already exists (using __eq__)
        if item not in self._items:
            # Insert item in sorted position for descending order (using __gt__)
            for i, existing_item in enumerate(self._items):
                if item > existing_item:
                    self._items.insert(i, item)
                    return
            # If item is smaller than all existing items, append it
            self._items.append(item)
        #print(f"after add: {str(self)}")

    def __iter__(self):
        # Return iterator for the internal list
        return iter(self._items)

    def get(self, index_nr):
        # Retrieve item at given index, raise IndexError if invalid
        try:
            return self._items[index_nr]
        except IndexError:
            raise IndexError("Index out of range")

    def __len__(self):
        # Return the number of items for len() calls
        return len(self._items)

    def __str__(self):
        #print("UniqueSortedList tostring called")
        return "\n".join(str(item) for item in self._items)

    def __eq__(self, other):
        if len(self._items) != len(other):
            return False
        return all(p1 == p2 for p1, p2 in zip(self._items, other))
