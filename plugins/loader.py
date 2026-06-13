import sys
import logging
import importlib
import importlib.util
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    name: str
    path: str
    description: str
    version: str
    module: object = None
    loaded: bool = False
    error: str = ""


class PluginLoader:
    def __init__(self, plugin_dir: str | Path = ""):
        self._plugin_dir = Path(plugin_dir) if plugin_dir else Path.home() / ".config" / "Osmograph" / "plugins"
        self._plugin_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, PluginInfo] = {}
        self._discovered: list[PluginInfo] = []

    def discover(self) -> list[PluginInfo]:
        self._discovered.clear()
        if not self._plugin_dir.exists():
            return []

        for pyfile in sorted(self._plugin_dir.glob("*.py")):
            if pyfile.name.startswith("_"):
                continue
            info = self._inspect_plugin(pyfile)
            self._discovered.append(info)
        return self._discovered

    def _inspect_plugin(self, path: Path) -> PluginInfo:
        try:
            source = path.read_text()
            name = path.stem
            description = ""
            version = "0.1.0"

            for line in source.split("\n"):
                line = line.strip()
                if line.startswith("# description:"):
                    description = line.split(":", 1)[1].strip()
                elif line.startswith("# version:"):
                    version = line.split(":", 1)[1].strip()
                elif line.startswith("# name:"):
                    name = line.split(":", 1)[1].strip()

            return PluginInfo(
                name=name,
                path=str(path),
                description=description,
                version=version,
            )
        except Exception as e:
            return PluginInfo(
                name=path.stem,
                path=str(path),
                description="",
                version="0.0.0",
                error=str(e),
            )

    def load(self, plugin_name: str) -> Optional[PluginInfo]:
        existing = self._plugins.get(plugin_name)
        if existing and existing.loaded:
            return existing

        for info in self._discovered:
            if info.name == plugin_name:
                return self._load_module(info)
        return None

    def _load_module(self, info: PluginInfo) -> Optional[PluginInfo]:
        try:
            path = Path(info.path)
            if not path.exists():
                info.error = "File not found"
                return info

            spec = importlib.util.spec_from_file_location(info.name, str(path))
            if spec is None or spec.loader is None:
                info.error = "Invalid Python module"
                return info

            module = importlib.util.module_from_spec(spec)
            sys.modules[info.name] = module
            spec.loader.exec_module(module)

            if not hasattr(module, "run"):
                info.error = "Plugin must define a run(latent_vector) function"
                return info

            plugin_fn = getattr(module, "run")
            if not callable(plugin_fn):
                info.error = "run attribute must be callable"
                return info

            import inspect
            sig = inspect.signature(plugin_fn)
            if len(sig.parameters) < 1:
                info.error = "run() must accept at least one argument (latent_vector)"
                return info

            info.module = module
            info.loaded = True
            info.error = ""
            self._plugins[info.name] = info
            logger.info(f"Plugin loaded: {info.name} v{info.version}")
            return info

        except Exception as e:
            info.error = str(e)
            logger.warning(f"Failed to load plugin {info.name}: {e}")
            return info

    def unload(self, plugin_name: str) -> bool:
        if plugin_name in sys.modules:
            del sys.modules[plugin_name]
        return self._plugins.pop(plugin_name, None) is not None

    def run_plugin(self, plugin_name: str, latent_vector: np.ndarray) -> Optional[dict]:
        info = self._plugins.get(plugin_name)
        if not info or not info.loaded or info.module is None:
            info = self.load(plugin_name)
            if info is None or not info.loaded:
                return None

        try:
            result = info.module.run(latent_vector)
            if result is None:
                return {}
            return result if isinstance(result, dict) else {"result": result}
        except Exception as e:
            logger.error(f"Plugin {plugin_name} run error: {e}")
            return {"error": str(e)}

    def get_loaded_plugins(self) -> list[PluginInfo]:
        return [p for p in self._plugins.values() if p.loaded]

    def get_discovered_plugins(self) -> list[PluginInfo]:
        return self._discovered

    def get_plugin_names(self) -> list[str]:
        return list(self._plugins.keys())

    def reload_all(self) -> list[PluginInfo]:
        self.discover()
        for info in self._discovered:
            self.load(info.name)
        return self.get_loaded_plugins()
