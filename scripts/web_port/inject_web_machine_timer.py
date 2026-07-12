import sys
path = sys.argv[1]
with open(path) as f:
    src = f.read()
anchor = 'sys.path.insert(0, "lib")\n'
inject = (
    '\n# Web build: native machine.Timer is unavailable (machine_timer.c is\n'
    '# removed). The native `machine` module dict is read-only, so install an\n'
    '# asyncio-backed Timer by replacing sys.modules["machine"] with a thin\n'
    '# wrapper that delegates every other attribute to the native module.\n'
    'try:\n'
    '    import machine as _native_machine\n'
    '    if not hasattr(_native_machine, "Timer"):\n'
    '        import sys as _sys\n'
    '        import _web_machine_timer\n'
    '        import _web_machine_pin\n'
    '        import _web_machine_hw\n'
    '        class _MachineWrapper:\n'
    '            Timer = _web_machine_timer.Timer\n'
    '            if not hasattr(_native_machine, "Pin"):\n'
    '                Pin = _web_machine_pin.Pin\n'
    '            def __getattr__(self, name):\n'
    '                try:\n'
    '                    return getattr(_native_machine, name)\n'
    '                except AttributeError:\n'
    '                    return getattr(_web_machine_hw, name)\n'
    '        _sys.modules["machine"] = _MachineWrapper()\n'
    'except Exception as _e:\n'
    '    print("could not install web machine.Timer:", _e)\n'
)
if anchor in src and 'import _web_machine_timer' not in src:
    src = src.replace(anchor, anchor + inject, 1)
    with open(path, 'w') as f:
        f.write(src)
    print("Injected web machine.Timer into staged main.py")
else:
    print("WARNING: could not inject machine.Timer (anchor missing or already present)")
