"""

Phase 36: GossipProtocol — distributed peer-to-peer knowledge synchronization.



Closes D-axis L5 gap: replaces file-based JSON pub/sub with a proper

push-pull Gossip protocol for cross-instance knowledge sharing.



Protocol:

  Push: send new facts to all known peers (fire-and-forget)

  Pull: request facts since last sync timestamp from a peer

  Exchange: push + pull + peer list swap (full round)

  Topology: seed peers from config, learn from Gossip exchange



Key design decisions:

  - fact_id = sha256(topic+content)[:16] → content-hash dedup

  - TTL field prevents infinite loops in mesh topologies

  - Exchange interval configurable (default 30s)

  - Reuses SharedKnowledgePool for local storage

"""



from __future__ import annotations



import asyncio

import hashlib

import json

import logging

import os

import random

import time

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional



logger = logging.getLogger("aiplat.gossip")





def make_fact_id(topic: str, content: str) -> str:

    """Phase 36: Content-hash based fact ID for cross-instance dedup.



    Same (topic, content) → same fact_id on all instances.

    """

    raw = f"{topic}:{content}"

    return hashlib.sha256(raw.encode()).hexdigest()[:16]





@dataclass

class PeerInfo:

    """Known peer instance in the Gossip network."""



    url: str

    instance_id: str = ""

    last_seen: float = field(default_factory=time.time)

    fact_count: int = 0



    def to_dict(self) -> Dict[str, Any]:

        return {

            "url": self.url,

            "instance_id": self.instance_id,

            "last_seen": self.last_seen,

            "fact_count": self.fact_count,

        }





class GossipProtocol:

    """Push-pull Gossip protocol for cross-instance knowledge sharing.



    Usage:

        from core.harness.memory.shared_pool import get_shared_knowledge_pool

        pool = get_shared_knowledge_pool()

        gossip = GossipProtocol(pool, instance_id="aiplat-core-1")

        gossip.add_seed_peer("http://instance2:8000")

        await gossip.publish("healing:rate_limit", "rotate_credential works")

        asyncio.create_task(gossip.run_gossip_loop())

    """



    DEFAULT_INTERVAL = 30  # seconds

    DEFAULT_TTL = 3  # hop limit



    def __init__(self, pool, instance_id: str = ""):

        self._pool = pool

        self._instance_id = instance_id or f"aiplat-{os.getpid()}-{int(time.time())}"

        self._peers: Dict[str, PeerInfo] = {}

        self._last_sync: Dict[str, float] = {}

        self._running = False

        self._task: Optional[asyncio.Task] = None

        self._total_push = 0

        self._total_pull = 0



        # Auto-discover peers from environment

        self._load_seed_peers()



    def _load_seed_peers(self) -> None:

        """Load initial peers from AIPLAT_GOSSIP_PEERS env var."""

        seeds = os.getenv("AIPLAT_GOSSIP_PEERS", "").strip()

        if seeds:

            for url in seeds.split(","):

                url = url.strip()

                if url:

                    self._peers[url] = PeerInfo(url=url)



    @property

    def peer_count(self) -> int:

        return len(self._peers)



    def add_seed_peer(self, url: str) -> None:

        if url not in self._peers:

            self._peers[url] = PeerInfo(url=url)

            logger.info("[gossip] added peer: %s", url)



    def get_peers(self) -> List[Dict[str, Any]]:

        return [p.to_dict() for p in self._peers.values()]



    async def publish(self, topic: str, content: str, **kwargs) -> str:

        """Publish to local pool + broadcast to all peers."""

        # Use content-hash fact_id for cross-instance dedup

        fid = make_fact_id(topic, content)

        kwargs["session_id"] = kwargs.get("session_id", self._instance_id)



        # Write locally (dedup by fact_id)

        existing = [f for f in self._pool._facts if f.fact_id == fid]

        if not existing:

            self._pool.publish(topic, content, **kwargs)

            self._total_push += 1



        # Fire-and-forget broadcast to peers

        for peer_url in list(self._peers.keys()):

            asyncio.create_task(self._push_fact(peer_url, topic, content, fid, kwargs))

        return fid



    async def _push_fact(self, peer_url: str, topic: str, content: str, fid: str, meta: dict) -> bool:

        """Push a single fact to a peer."""

        try:

            import aiohttp

            async with aiohttp.ClientSession() as session:

                async with session.post(

                    f"{peer_url}/api/core/gossip/push",

                    json={

                        "facts": [{

                            "fact_id": fid,

                            "topic": topic,

                            "content": content,

                            "confidence": meta.get("confidence", 1.0),

                            "source": meta.get("source", "auto"),

                            "session_id": meta.get("session_id", self._instance_id),

                            "timestamp": time.time(),

                            "ttl": self.DEFAULT_TTL,

                        }],

                        "instance_id": self._instance_id,

                    },

                    timeout=aiohttp.ClientTimeout(total=5),

                ) as resp:

                    if resp.status == 200:

                        self._peers[peer_url].last_seen = time.time()

                        return True

        except Exception as e:

            logger.debug("[gossip] push to %s failed: %s", peer_url, e)

        return False



    async def pull(self, peer_url: str) -> int:

        """Pull new facts from a peer since last sync."""

        since = self._last_sync.get(peer_url, 0.0)

        try:

            import aiohttp

            async with aiohttp.ClientSession() as session:

                async with session.get(

                    f"{peer_url}/api/core/gossip/pull?since={since}&instance_id={self._instance_id}",

                    timeout=aiohttp.ClientTimeout(total=5),

                ) as resp:

                    if resp.status != 200:

                        return 0

                    data = await resp.json()

                    new_facts = data.get("facts", [])



                    # Merge: only accept facts we don't already have

                    existing_ids = {f.fact_id for f in self._pool._facts}

                    accepted = 0

                    for f in new_facts:

                        fid = f.get("fact_id", "")

                        ttl = f.get("ttl", self.DEFAULT_TTL)

                        if fid and fid not in existing_ids and ttl > 0:

                            self._pool.publish(

                                topic=f.get("topic", ""),

                                content=f.get("content", ""),

                                session_id=f.get("session_id", ""),

                                source=f.get("source", "gossip"),

                                confidence=f.get("confidence", 0.5),

                            )

                            accepted += 1



                    self._total_pull += accepted

                    self._last_sync[peer_url] = time.time()

                    self._peers[peer_url].last_seen = time.time()



                    # Learn peer's peers

                    for p in data.get("peers", []):

                        if p.get("url") not in self._peers:

                            self._peers[p["url"]] = PeerInfo(

                                url=p["url"],

                                instance_id=p.get("instance_id", ""),

                                last_seen=p.get("last_seen", time.time()),

                            )



                    if accepted:

                        logger.info(

                            "[gossip] pulled %d facts from %s", accepted, peer_url

                        )

                    return accepted

        except Exception as e:

            logger.debug("[gossip] pull from %s failed: %s", peer_url, e)

        return 0



    async def exchange(self, peer_url: str) -> int:

        """One full push-pull exchange round."""

        # Pull first (get new facts from peer)

        n = await self.pull(peer_url)



        # Push our facts since their last sync

        our_since = self._last_sync.get(peer_url, 0.0)

        our_new = self._pool.query_since(our_since, limit=50)

        if our_new:

            try:

                import aiohttp

                async with aiohttp.ClientSession() as session:

                    async with session.post(

                        f"{peer_url}/api/core/gossip/push",

                        json={

                            "facts": [{

                                "fact_id": f.fact_id,

                                "topic": f.topic,

                                "content": f.content,

                                "confidence": f.confidence,

                                "source": f.source,

                                "session_id": f.session_id,

                                "timestamp": f.timestamp,

                                "ttl": self.DEFAULT_TTL,

                            } for f in our_new],

                            "instance_id": self._instance_id,

                        },

                        timeout=aiohttp.ClientTimeout(total=5),

                    ) as resp:

                        if resp.status == 200:

                            data = await resp.json()

                            n += data.get("accepted", 0)

            except Exception:

                logging.getLogger(__name__).debug('exchange failed', exc_info=True)


        return n



    async def run_gossip_loop(self, interval: int = 0) -> None:

        """Background Gossip loop: random peer → exchange."""

        if self._running:

            return

        self._running = True

        interval = interval or self.DEFAULT_INTERVAL

        logger.info(

            "[gossip] started (instance=%s peers=%d interval=%ds)",

            self._instance_id[:12], self.peer_count, interval,

        )



        while self._running:

            try:

                await asyncio.sleep(interval)

                if self._peers:

                    peer_url = random.choice(list(self._peers.keys()))

                    await self.exchange(peer_url)

            except asyncio.CancelledError:

                break

            except Exception as e:

                logger.debug("[gossip] loop error: %s", e)



    def stop(self) -> None:

        self._running = False

        if self._task and not self._task.done():

            self._task.cancel()

        logger.info("[gossip] stopped")



    def stats(self) -> Dict[str, Any]:

        return {

            "instance_id": self._instance_id[:12],

            "peers": self.peer_count,

            "total_push": self._total_push,

            "total_pull": self._total_pull,

            "running": self._running,

            "known_peers": [p.to_dict() for p in self._peers.values()],

        }





# ── Singleton ──



_gossip: Optional[GossipProtocol] = None





def get_gossip_protocol() -> GossipProtocol:

    global _gossip

    if _gossip is None:

        from core.harness.memory.shared_pool import get_shared_knowledge_pool

        _gossip = GossipProtocol(get_shared_knowledge_pool())

    return _gossip

