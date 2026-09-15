# SPDX-License-Identifier: Apache-2.0
"""Fresh-process policy checks; injected dependencies are structural tests."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def _run(source: str) -> None:
    prefix = """
import importlib
import importlib.abc
import logging
import sys
from pathlib import Path
from unittest.mock import patch
import torch

assert 'sglang_omni.relay' not in sys.modules
records = []
class Capture(logging.Handler):
    def emit(self, record):
        records.append(record)
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger().addHandler(Capture())
"""
    result = subprocess.run(
        [sys.executable, "-c", prefix + textwrap.dedent(source)],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("backend", ["mooncake", "nixl"])
@pytest.mark.parametrize(
    "failure",
    [
        "top-level",
        "api-submodule",
        "transitive",
        "prefix",
        "symbol",
        "import-name",
        "unnamed",
    ],
)
def test_import_failure_classification_and_selected_backend_errors(backend, failure):
    _run(
        f"""
        backend, failure = {backend!r}, {failure!r}
        api = backend + ('.engine' if backend == 'mooncake' else '._api')
        names = {{'top-level': backend, 'api-submodule': api, 'transitive': 'vendor_runtime',
                  'prefix': backend + '_support', 'symbol': api,
                  'import-name': backend, 'unnamed': None}}
        error_type = ImportError if failure in {{'symbol', 'import-name'}} else ModuleNotFoundError
        original = error_type('injected import failure: ' + failure, name=names[failure])
        attempts = []
        modules = []
        class FailedDependencies(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname in {{'sglang_omni.relay.mooncake', 'sglang_omni.relay.nixl'}}:
                    modules.append(fullname.rsplit('.', 1)[1])
                if fullname.split('.')[0] in {{'mooncake', 'nixl'}}:
                    attempts.append(fullname)
                    if fullname.split('.')[0] == backend:
                        raise original
                    raise ModuleNotFoundError(fullname, name=fullname.split('.')[0])
        sys.meta_path.insert(0, FailedDependencies())
        import sglang_omni.relay as package
        from sglang_omni.relay.base import RELAY_REGISTRY, create_relay
        assert Path(package.__file__).resolve() == Path.cwd() / 'sglang_omni/relay/__init__.py'
        assert modules == ['mooncake', 'nixl']
        assert list(RELAY_REGISTRY) == ['mooncake', 'nixl']
        assert package.MOONCAKE_AVAILABLE is False
        assert package.NIXL_AVAILABLE is False
        assert '__getattr__' not in vars(package)
        namespace = {{}}
        exec('from sglang_omni.relay import *', namespace)
        for name in package.__all__:
            assert namespace[name] is getattr(package, name)
        relevant = [r for r in records if r.name == 'sglang_omni.relay.' + backend]
        assert len(relevant) == 1, [r.getMessage() for r in relevant]
        assert relevant[0].levelno == (logging.DEBUG if failure == 'top-level' else logging.ERROR)
        before = list(attempts)
        module = importlib.import_module('sglang_omni.relay.' + backend)
        relay_class = package.MooncakeRelay if backend == 'mooncake' else package.NixlRelay
        def forbidden(*args, **kwargs):
            raise AssertionError('unavailable backend initialized native code or a pool')
        if backend == 'mooncake':
            module.TransferEngine = forbidden
            connection = lambda: module.MooncakeConnection('direct', '127.0.0.1')
        else:
            module.nixl_agent_config = forbidden
            connection = lambda: package.Connection('direct')
        callers = [
            connection,
            lambda: relay_class(engine_id='class', device='cpu', slot_size_mb=1, credits=1),
            lambda: create_relay(backend, engine_id='factory', device='cpu', slot_size_mb=1, credits=1),
        ]
        with patch.object(torch, 'zeros', side_effect=forbidden):
            for call in callers:
                try:
                    call()
                except RuntimeError as exc:
                    assert exc.__cause__ is original
                    assert backend in str(exc).lower()
                    assert 'installation requirements for your platform' in str(exc)
                else:
                    raise AssertionError('unavailable backend constructed')
        assert attempts == before, 'construction retried dependency imports'
        assert len([r for r in records if r.name == 'sglang_omni.relay.' + backend]) == 1
        """
    )


@pytest.mark.parametrize("backend", ["mooncake", "nixl"])
@pytest.mark.parametrize("error_type", ["OSError", "RuntimeError"])
def test_non_import_errors_propagate_eagerly(backend, error_type):
    _run(
        f"""
        original = {error_type}('injected native initialization failure')
        class BrokenDependency(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] == {backend!r}:
                    raise original
                if fullname.split('.')[0] in {{'mooncake', 'nixl'}}:
                    raise ModuleNotFoundError(fullname, name=fullname.split('.')[0])
        sys.meta_path.insert(0, BrokenDependency())
        try:
            import sglang_omni.relay
        except {error_type} as exc:
            assert exc is original
        else:
            raise AssertionError('non-ImportError was suppressed or deferred')
        """
    )


def test_synthetic_success_preserves_eager_exports_and_native_construction():
    _run(
        """
        from types import ModuleType
        events = []
        class Engine:
            def initialize(self, *args):
                events.append(('mooncake-init', args))
                return 0
            def get_rpc_port(self):
                return 12345
            def register_memory(self, *args):
                events.append(('mooncake-register', args))
                return 0
            def unregister_memory(self, *args):
                return 0
        class Agent:
            def __init__(self, name, config):
                events.append(('nixl-init', config))
            def register_memory(self, *args):
                events.append(('nixl-register', args))
                return object()
            def deregister_memory(self, *args):
                pass
        def config(**kwargs):
            return kwargs
        for name in ['mooncake', 'nixl']:
            module = ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module
        mooncake = ModuleType('mooncake.engine')
        mooncake.TransferEngine = Engine
        mooncake.TransferNotify = type('TransferNotify', (), {})
        mooncake.TransferOpcode = type('TransferOpcode', (), {'Read': 0, 'Write': 1})
        nixl = ModuleType('nixl._api')
        nixl.nixl_agent = Agent
        nixl.nixl_agent_config = config
        sys.modules['mooncake.engine'] = mooncake
        sys.modules['nixl._api'] = nixl
        import sglang_omni.relay as package
        from sglang_omni.relay.base import RELAY_REGISTRY, create_relay
        assert package.MOONCAKE_AVAILABLE is True
        assert package.NIXL_AVAILABLE is True
        assert list(RELAY_REGISTRY) == ['mooncake', 'nixl']
        assert 'sglang_omni.relay._optional_dependency' not in sys.modules
        namespace = {}
        exec('from sglang_omni.relay import *', namespace)
        expected = ['Relay', 'NixlRelay', 'NixlOperation', 'Connection',
                    'NIXL_AVAILABLE', 'MooncakeRelay', 'MOONCAKE_AVAILABLE']
        assert package.__all__ == expected
        assert set(expected) <= set(dir(package))
        for name in expected:
            assert namespace[name] is vars(package)[name]
        package.Connection('direct', num_threads=3)
        assert events[-1] == ('nixl-init', {'num_threads': 3})
        from sglang_omni.relay.mooncake import MooncakeConnection
        connection = MooncakeConnection('direct', '127.0.0.1', 'tcp', '')
        assert events[-1][0] == 'mooncake-init'
        connection.close()
        for backend, cls in [('mooncake', package.MooncakeRelay), ('nixl', package.NixlRelay)]:
            for construct in [cls, lambda **kwargs: create_relay(backend, **kwargs)]:
                relay = construct(engine_id='success', device='cpu', slot_size_mb=1, credits=1)
                assert relay.pool_tensor.numel() == 1024 * 1024
                assert relay.pool_tensor.device.type == 'cpu'
                assert events[-2][0] == backend + '-init'
                assert events[-1][0] == backend + '-register'
                relay.close()
        assert 'sglang_omni.relay._optional_dependency' not in sys.modules
        assert not [r for r in records if r.name.startswith('sglang_omni.relay') and r.levelno >= logging.WARNING]
        """
    )


def test_top_level_absence_allows_real_shm():
    _run(
        """
        import asyncio
        class MissingDependency(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in {'mooncake', 'nixl'}:
                    raise ModuleNotFoundError(fullname, name=fullname.split('.')[0])
        sys.meta_path.insert(0, MissingDependency())
        from sglang_omni.relay.base import create_relay
        async def transfer():
            sender = create_relay('shm', engine_id='sender', device='cpu', credits=1)
            receiver = create_relay('shm', engine_id='receiver', device='cpu', credits=1)
            source = torch.arange(4096, dtype=torch.float32)
            destination = torch.empty_like(source)
            put = await sender.put_async(source)
            get = await receiver.get_async(put.metadata, destination)
            await get.wait_for_completion()
            assert torch.equal(source, destination)
            put.mark_receiver_done()
            await put.wait_for_completion()
            sender.close()
            receiver.close()
        asyncio.run(transfer())
        assert not [r for r in records if r.name.startswith('sglang_omni.relay') and r.levelno >= logging.WARNING]
        """
    )
