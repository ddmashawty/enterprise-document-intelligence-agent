"""Per-school adapters; a new school with a plain notice list only needs ``adapter: generic``."""

from __future__ import annotations

from doc_agent.collect.adapters.jnu import JnuAdapter
from doc_agent.collect.adapters.scnu import ScnuAdapter
from doc_agent.collect.adapters.scut import ScutAdapter
from doc_agent.collect.adapters.sysu import SysuAdapter
from doc_agent.collect.base import SiteConfig
from doc_agent.collect.generic_list import GenericListAdapter

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
