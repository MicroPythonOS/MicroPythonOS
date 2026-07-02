# dataclasses.py: MicroPython compatibility layer for Python's dataclasses
# Implements @dataclass, field, and Field with support for default_factory

MISSING = object()  # Sentinel for missing values

class Field:
    """Represents a dataclass field, supporting default_factory."""
    def __init__(self, default=MISSING, default_factory=MISSING, init=True, repr=True):
        self.name = None  # Set by dataclass decorator
        self.type = None  # Set by dataclass decorator
        self.default = default
        self.default_factory = default_factory
        self.init = init
        self.repr = repr

def field(*, default=MISSING, default_factory=MISSING, init=True, repr=True):
    """Specify a dataclass field with optional default_factory."""
    if default is not MISSING and default_factory is not MISSING:
        raise ValueError("Cannot specify both default and default_factory")
    return Field(default=default, default_factory=default_factory, init=init, repr=repr)

def dataclass(cls):
    """Decorator to emulate @dataclass, generating __init__ and __repr__."""
    # Get class annotations and defaults
    annotations = getattr(cls, '__annotations__', {})
    defaults = {}
    fields = {}

    # Process class attributes for defaults and field() calls
    for name in dir(cls):
        if not name.startswith('__'):
            attr = getattr(cls, name, None)
            if not callable(attr):
                if isinstance(attr, Field):
                    fields[name] = attr
                    fields[name].name = name
                    fields[name].type = annotations.get(name)
                    if attr.default is not MISSING:
                        defaults[name] = attr.default
                elif name in annotations:
                    defaults[name] = attr

    # Ensure all annotated fields have a Field object
    for name in annotations:
        if name not in fields:
            fields[name] = Field(default=defaults.get(name, MISSING), init=True, repr=True)
            fields[name].name = name
            fields[name].type = annotations.get(name)

    # Generate __init__ method
    def __init__(self, *args, **kwargs):
        # Positional arguments
        init_fields = [name for name, f in fields.items() if f.init]
        for i, value in enumerate(args):
            print(f"dataclasses.py: {i} {value}")
            if i >= len(init_fields):
                raise TypeError(f"dataclasses.py: too many positional arguments")
            setattr(self, init_fields[i], value)

        # Keyword arguments, defaults, and default_factory
        for name, field in fields.items():
            if field.init and name in kwargs:
                setattr(self, name, kwargs[name])
            elif not hasattr(self, name):
                if field.default_factory is not MISSING:
                    setattr(self, name, field.default_factory())
                elif field.default is not MISSING:
                    setattr(self, name, field.default)
                elif field.init:
                    raise TypeError(f"Missing required argument: {name}")

        # Call __post_init__ if defined
        if hasattr(self, '__post_init__'):
            self.__post_init__()

    # Generate __repr__ method
    def __repr__(self):
        fields_repr = [
            f"{name}={getattr(self, name)!r}"
            for name, field in fields.items()
            if field.repr
        ]
        return f"{cls.__name__}({', '.join(fields_repr)})"

    # Attach generated methods to class
    setattr(cls, '__init__', __init__)
    setattr(cls, '__repr__', __repr__)

    return cls
