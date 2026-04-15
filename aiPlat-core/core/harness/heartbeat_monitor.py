"""
HeartbeatMonitor - Agent Heartbeat Monitoring System
"""

import threading
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import time

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent 状态"""
    ACTIVE = "active"
    IDLE = "idle"
    WARNING = "warning"
    ERROR = "error"
    STALLED = "stalled"


@dataclass
class AgentHeartbeat:
    """Agent的心跳"""
    agent_id: str
    status: AgentStatus
    last_activity: float
    health_score: float
    metrics: Dict[str, Any]
    timestamp: float


class HeartbeatMonitor:
    """心跳监控器（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.agent_heartbeats: Dict[str, AgentHeartbeat] = {}
        self.active_alerts: Dict[str, Any] = {}
        self.heartbeat_history: Dict[str, list] = {}
        self.monitored_agents: Dict[str, Any] = {}
        self._running = False
        self._monitor_task = None
        
        self.heartbeat_interval = 10
        self.warning_threshold = 300
        self.error_threshold = 600
        self.stalled_threshold = 900
    
    def register_agent(self, agent_id: str, agent: Any):
        """注册Agent到心跳监控系统"""
        with self._lock:
            self.agent_heartbeats[agent_id] = AgentHeartbeat(
                agent_id=agent_id,
                status=AgentStatus.ACTIVE,
                last_activity=datetime.now().timestamp(),
                health_score=1.0,
                metrics={},
                timestamp=datetime.now().timestamp()
            )
            
            self.monitored_agents[agent_id] = agent
            
            if agent_id not in self.heartbeat_history:
                self.heartbeat_history[agent_id] = []
            
            if not self._running:
                self._start_monitor_loop()
            
            logger.info(f"Agent {agent_id} 已注册到心跳监控系统")
    
    def unregister_agent(self, agent_id: str):
        """注销Agent"""
        with self._lock:
            if agent_id in self.agent_heartbeats:
                del self.agent_heartbeats[agent_id]
            if agent_id in self.monitored_agents:
                del self.monitored_agents[agent_id]
            if agent_id in self.heartbeat_history:
                del self.heartbeat_history[agent_id]
            logger.info(f"Agent {agent_id} 已从心跳监控系统注销")

    def update_heartbeat(self, agent_id: str, status: AgentStatus = None, metrics: dict = None):
        """更新Agent心跳"""
        with self._lock:
            if agent_id not in self.agent_heartbeats:
                return
            
            heartbeat = self.agent_heartbeats[agent_id]
            heartbeat.last_activity = datetime.now().timestamp()
            heartbeat.timestamp = datetime.now().timestamp()
            
            if status:
                heartbeat.status = status
            
            if metrics:
                heartbeat.metrics.update(metrics)
            
            heartbeat.health_score = self._calculate_health_score(
                heartbeat.status,
                heartbeat.last_activity,
                datetime.now().timestamp()
            )
            
            self.heartbeat_history[agent_id].append({
                "timestamp": heartbeat.timestamp,
                "status": heartbeat.status.value,
                "health_score": heartbeat.health_score
            })
            
            if len(self.heartbeat_history[agent_id]) > 1000:
                self.heartbeat_history[agent_id] = self.heartbeat_history[agent_id][-1000:]

    def _calculate_health_score(self, status: AgentStatus, last_activity: float, current_time: float) -> float:
        base_score = {
            AgentStatus.ACTIVE: 1.0,
            AgentStatus.IDLE: 0.8,
            AgentStatus.WARNING: 0.5,
            AgentStatus.ERROR: 0.2,
            AgentStatus.STALLED: 0.0
        }[status]
        
        time_since_activity = current_time - last_activity
        decay_factor = max(0, 1 - time_since_activity / 3600)
        
        return base_score * decay_factor

    def _start_monitor_loop(self):
        self._running = True
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._monitor_loop())
            else:
                loop.create_task(self._monitor_loop())
        except RuntimeError:
            self._monitor_task = asyncio.ensure_future(self._monitor_loop())
    
    def stop_monitor_loop(self):
        self._running = False

    async def _monitor_loop(self):
        while self._running:
            try:
                await self._collect_heartbeats()
                await self._analyze_heartbeats()
                await self._generate_alerts()
                await self._record_metrics()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"心跳监控循环错误: {e}")
                await asyncio.sleep(self.heartbeat_interval)

    async def _collect_heartbeats(self):
        current_time = datetime.now().timestamp()
        
        for agent_id, heartbeat in self.agent_heartbeats.items():
            time_since_activity = current_time - heartbeat.last_activity
            
            if time_since_activity > self.stalled_threshold:
                heartbeat.status = AgentStatus.STALLED
            elif time_since_activity > self.error_threshold:
                heartbeat.status = AgentStatus.ERROR
            elif time_since_activity > self.warning_threshold:
                heartbeat.status = AgentStatus.WARNING
            elif time_since_activity < 60:
                heartbeat.status = AgentStatus.ACTIVE
            else:
                heartbeat.status = AgentStatus.IDLE
            
            heartbeat.health_score = self._calculate_health_score(
                heartbeat.status,
                heartbeat.last_activity,
                current_time
            )

    async def _analyze_heartbeats(self):
        for agent_id, heartbeat in self.agent_heartbeats.items():
            if heartbeat.status == AgentStatus.STALLED:
                await self._handle_stalled_agent(agent_id)
            elif heartbeat.status == AgentStatus.ERROR:
                await self._handle_error_agent(agent_id)
            elif heartbeat.status == AgentStatus.WARNING:
                await self._handle_warning_agent(agent_id)

    async def _handle_stalled_agent(self, agent_id: str):
        logger.warning(f"Agent {agent_id} 已停滞")

    async def _handle_error_agent(self, agent_id: str):
        logger.warning(f"Agent {agent_id} 状态错误")

    async def _handle_warning_agent(self, agent_id: str):
        logger.info(f"Agent {agent_id} 状态警告")

    async def _generate_alerts(self):
        for agent_id, heartbeat in self.agent_heartbeats.items():
            if heartbeat.health_score < 0.5:
                self.active_alerts[f"{agent_id}_health"] = {
                    "agent_id": agent_id,
                    "type": "low_health_score",
                    "severity": "critical",
                    "message": f"Agent {agent_id} 健康分数过低: {heartbeat.health_score:.2f}",
                    "timestamp": datetime.now().timestamp()
                }

    async def _record_metrics(self):
        pass

    def get_agent_status(self, agent_id: str) -> Optional[AgentHeartbeat]:
        return self.agent_heartbeats.get(agent_id)

    def get_all_status(self) -> Dict[str, AgentHeartbeat]:
        return self.agent_heartbeats.copy()

    def get_alerts(self) -> Dict[str, Any]:
        return self.active_alerts.copy()
    
    def clear_alert(self, alert_id: str):
        if alert_id in self.active_alerts:
            del self.active_alerts[alert_id]
    
    def clear_all_alerts(self):
        self.active_alerts.clear()


heartbeat_monitor = HeartbeatMonitor()