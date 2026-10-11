"""Per-school adapters; a new school with a plain notice list only needs ``adapter: generic``."""

from __future__ import annotations

from kaoyan.collect.adapters.jnu import JnuAdapter
from kaoyan.collect.adapters.scnu import ScnuAdapter
from kaoyan.collect.adapters.scut import ScutAdapter
from kaoyan.collect.adapters.sysu import SysuAdapter
from kaoyan.collect.base import SiteConfig
from kaoyan.collect.generic_list import GenericListAdapter

ADAPTERS: dict[str, type[GenericListAdapter]] = {
    "generic": GenericListAdapter,
    "sysu": SysuAdapter,
    "scut": ScutAdapter,
    "jnu": JnuAdapter,
    "scnu": ScnuAdapter,
}


def build_adapter(site: SiteConfig) -> GenericListAdapter:
    try:
        return ADAPTERS[site.adapter](site)
    except KeyError:
        raise ValueError(f"Unknown adapter {site.adapter!r} for {site.school_id}") from None
