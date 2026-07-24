# for python-nostr

# enum.py: MicroPython compatibility layer for Python's enum module
# Implements Enum and IntEnum for integer-based enumerations, avoiding metaclass keyword

class Enum:
    """Base class for enumerations."""
    def __init__(self, value, name):
        self.value = value
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__}.{self.name}: {self.value}>"

    def __eq__(self, other):
        if isinstance(other, Enum):
            return self.value == other.value
        return self.value == other

    def __hash__(self):
        return hash(self.value)

def create_enum_class(base_class, name, attrs):
    """Factory function to create an enum class with metaclass-like behavior."""
    members = {}
    values = {}
    for key, value in attrs.items():
        if not key.startswith('__') and not callable(value):
            enum_item = base_class(value, key)
            members[key] = enum_item
            values[value] = enum_item
            attrs[key] = enum_item
    attrs['_members'] = members
    attrs['_values'] = values

    # Define iteration and lookup
    def __iter__(cls):
        return iter(cls._members.values())

    def __getitem__(cls, value):
        return cls._values.get(value)

    attrs['__iter__'] = __iter__
    attrs['__getitem__'] = __getitem__

    # Create class using type
    return type(name, (base_class,), attrs)

# Define IntEnum using factory function
IntEnum = create_enum_class(Enum, 'IntEnum', {
    '__int__': lambda self: self.value
})
