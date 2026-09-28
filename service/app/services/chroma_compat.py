"""Chroma 原生组件在 Linux x86 虚拟机中的启动兼容。"""

import logging
import os
import platform
import sys
from functools import lru_cache
from importlib import import_module

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_chroma_bindings() -> None:
    """只在首次导入期间固定当前线程的 CPU，随后恢复原来的调度范围。"""
    if sys.platform != "linux" or platform.machine() not in {
        "x86_64",
        "AMD64",
        "i386",
        "i686",
    }:
        import_module("chromadb_rust_bindings")
        return

    # Chroma 1.5.9 的 fastant 0.1.11 在动态库加载时校准 TSC，跨核采样
    # 可能一直无法收敛。仅保护原生导入，不能把后续向量计算线程限制到单核。
    # https://docs.rs/crate/fastant/0.1.11/source/src/tsc_now.rs
    try:
        affinity = os.sched_getaffinity(0)
        if len(affinity) > 1:
            os.sched_setaffinity(0, {min(affinity)})
    except OSError as exc:
        # 受限容器可能不允许设置亲和性，保留依赖原有的加载行为。
        logger.warning("无法调整 Chroma 加载线程的 CPU 亲和性；errno=%s", exc.errno)
        import_module("chromadb_rust_bindings")
        return

    try:
        import_module("chromadb_rust_bindings")
    finally:
        if len(affinity) > 1:
            os.sched_setaffinity(0, affinity)
